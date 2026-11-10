# Esposizione: confronta i servizi trovati con i security group e
# produce delle "segnalazioni" (frasi in italiano) su incongruenze o rischi —
# porte aperte per sbaglio, servizi accesi ma non previsti, floating IP inutili.
# Tipi in models.FINDING_*.
#
# Regola dello scanner (ADR 0012): il security group filtra anche il traffico
# che parte dalla namespace da cui scansioniamo, quindi un servizio su una porta
# bloccata risulterebbe invisibile. L'admin può aprire le porte al solo indirizzo
# dello scanner (porta metadati OVN): quella regola la riconosciamo e
# la escludiamo dal confronto, così non falsa i servizi latenti né conta come
# regola inutile.
#
# build_findings non tocca il database (riceve liste di oggetti, si prova da
# sola); findings_for_scan la collega al database (host e servizi) e all'inventario
# in memoria.

import ipaddress
import logging

from recon_stack import vocab
from recon_stack.db import api as db
from recon_stack.db import models

LOG = logging.getLogger(__name__)

# Prefissi che indicano "qualunque indirizzo" in una regola.
ANY_ADDRESS = ("0.0.0.0/0", "::/0")

# Ruoli delle porte Neutron da cui parte la scansione interna (ADR 0006): il
# loro indirizzo è la sorgente dello scanner.
SCANNER_PORT_OWNERS = ("network:distributed",)  # metadati di OVN (ovnmeta-)


def _is_scanner_rule(rule, scanner_ips):
    """La regola apre il traffico al solo indirizzo dello scanner? (ADR 0012)

    È la regola che l'admin aggiunge perché lo scanner veda le porte chiuse ai
    client: non dice nulla su chi può raggiungere il servizio, quindi non conta
    né come esposizione né come regola inutile. La riconosciamo solo se la
    sorgente è esattamente l'indirizzo dello scanner (/32 in IPv4, /128 in
    IPv6): una rete più ampia lo comprende, ma apre anche ad altri.
    """
    if rule.remote_group_id or not rule.remote_ip_prefix:
        return False
    return rule.remote_ip_prefix in {f"{ip}/32" for ip in scanner_ips} | {
        f"{ip}/128" for ip in scanner_ips}


def _rule_source_is_anywhere(rule):
    """La regola permette il traffico da qualunque indirizzo?

    Senza remote_ip_prefix né remote_group_id, o con 0.0.0.0/0 (::/0), vale per
    qualunque sorgente; con un remote_group_id la sorgente è ristretta.
    """
    if rule.remote_group_id:
        return False
    return rule.remote_ip_prefix in (None, *ANY_ADDRESS)


def _source_includes_scanner(rule, scanner_ips):
    """La sorgente della regola comprende almeno un indirizzo dello scanner?"""
    if _rule_source_is_anywhere(rule):
        return True
    if rule.remote_group_id or not rule.remote_ip_prefix:
        return False
    try:
        rete = ipaddress.ip_network(rule.remote_ip_prefix, strict=False)
    except ValueError:
        return False
    for ip in scanner_ips:
        try:
            if ipaddress.ip_address(ip) in rete:
                return True
        except ValueError:
            continue
    return False


def _rule_covers_port(rule, port_number, protocol):
    """La regola in ingresso lascia passare questa porta/protocollo?"""
    if rule.direction != models.DIRECTION_INGRESS:
        return False
    if rule.protocol is not None and rule.protocol != protocol:
        return False
    # port_range_min None = tutte le porte; altrimenti deve cadere nell'intervallo.
    if rule.port_range_min is None:
        return True
    return rule.port_range_min <= port_number <= rule.port_range_max


def _ports_label(rule):
    """Porte di una regola in forma leggibile, es. '22' o '8000-8100'."""
    if rule.port_range_min is None:
        return "qualunque porta"
    if rule.port_range_min == rule.port_range_max:
        return str(rule.port_range_min)
    return f"{rule.port_range_min}-{rule.port_range_max}"


def _finding(finding_type, severity, message, ip_address=None,
             port_number=None, protocol=None):
    """Costruisce il dizionario di una segnalazione (senza scan_id)."""
    return {
        "finding_type": finding_type,
        "severity": severity,
        "ip_address": ip_address,
        "port_number": port_number,
        "protocol": protocol,
        "message": message,
    }


def build_findings(hosts, services, inventory):
    """Calcola le segnalazioni di una scansione da host, servizi e inventario.

    inventory è un dizionario con le liste "ports", "floating_ips" e
    "security_group_rules" (namedtuple di scanner/inventory.py).

    Restituisce una lista di dizionari pronti per db.save_findings (manca solo
    lo scan_id, aggiunto da chi chiama).
    """
    rules_by_sg = {}
    for rule in inventory["security_group_rules"]:
        rules_by_sg.setdefault(rule.security_group_id, []).append(rule)

    # Le reti possono riusare gli stessi IP: l'identità è (network_id, ip).
    sg_ids_by_key = {}         # security group applicati a ogni (rete, indirizzo)
    port_security_by_key = {}  # port security di ogni (rete, indirizzo), None se ignota
    scanner_ips = set()        # indirizzi da cui parte lo scanner
    for port in inventory["ports"]:
        key = (port.network_id, port.ip_address)
        if port.security_group_ids:
            sg_ids_by_key[key] = port.security_group_ids
        # Solo le porte delle VM (device_owner "compute:..."): quelle di
        # infrastruttura non hanno mai port security e segnalarle sarebbe un
        # falso positivo.
        if (port.device_owner or "").startswith(vocab.COMPUTE_OWNER_PREFIX):
            port_security_by_key[key] = port.port_security_enabled
        if port.device_owner in SCANNER_PORT_OWNERS:
            scanner_ips.add(port.ip_address)

    # Servizi raggruppati per host e per vista (interna / esterna).
    internal_by_host = {}
    external_by_host = {}
    for svc in services:
        bucket = (external_by_host if svc.view == models.VIEW_EXTERNAL
                  else internal_by_host)
        bucket.setdefault(svc.host_id, []).append(svc)

    findings = []
    for host in hosts:
        key = (host.network_id, host.ip_address)
        findings.extend(_host_findings(
            host, internal_by_host.get(host.id, []),
            sg_ids_by_key.get(key, []), rules_by_sg,
            port_security_by_key.get(key), scanner_ips))

    findings.extend(_external_findings(
        hosts, internal_by_host, external_by_host, inventory["floating_ips"],
        inventory["ports"]))
    return findings


def _host_findings(host, internal_services, sg_ids, rules_by_sg,
                   port_security=None, scanner_ips=frozenset()):
    """Segnalazioni dal confronto servizi/regole su un singolo host."""
    findings = []

    # Host non censito che risponde e ha porte aperte: il segnale più forte.
    if host.classification == models.HOST_UNKNOWN:
        if internal_services:
            porte = ", ".join(sorted(
                f"{s.port_number}/{s.protocol}" for s in internal_services))
            findings.append(_finding(
                models.FINDING_UNKNOWN_EXPOSED, models.SEVERITY_HIGH,
                f"L'host {host.ip_address} risponde e ha porte aperte ({porte}) "
                f"ma non corrisponde a nessuna risorsa Neutron del progetto: "
                f"host non censito.",
                ip_address=host.ip_address))
        return findings

    # Il confronto con le regole ha senso solo per gli host censiti.
    if host.classification != models.HOST_KNOWN:
        return findings

    # Port security disattivata: nessun security group protegge la porta, quindi
    # i servizi non sono "latenti" ma raggiungibili da tutta la rete.
    if port_security is False:
        if internal_services:
            porte = ", ".join(sorted(
                f"{s.port_number}/{s.protocol}" for s in internal_services))
            dettaglio = f"i servizi in ascolto ({porte}) sono raggiungibili"
        else:
            dettaglio = "qualunque servizio verrà avviato sarà raggiungibile"
        findings.append(_finding(
            models.FINDING_NO_PORT_SECURITY, models.SEVERITY_HIGH,
            f"La porta di {host.ip_address} ha la port security disattivata: "
            f"nessun security group la protegge e {dettaglio} da qualunque "
            f"indirizzo della rete.",
            ip_address=host.ip_address))
        return findings

    ingress_rules = []
    scanner_rules = []
    for sg in sg_ids:
        for rule in rules_by_sg.get(sg, []):
            if rule.direction != models.DIRECTION_INGRESS:
                continue
            # Le regole dello scanner (ADR 0012) restano fuori dal confronto,
            # ma ci dicono quali porte lo scanner poteva raggiungere.
            if _is_scanner_rule(rule, scanner_ips):
                scanner_rules.append(rule)
            else:
                ingress_rules.append(rule)

    # Per ogni servizio in ascolto: è aperto a tutti? è previsto da una regola?
    for svc in internal_services:
        covering = [r for r in ingress_rules
                    if _rule_covers_port(r, svc.port_number, svc.protocol)]
        descr = _service_label(svc)
        if not covering:
            findings.append(_finding(
                models.FINDING_LATENT_SERVICE, models.SEVERITY_MEDIUM,
                f"Il servizio {descr} su {host.ip_address} è in ascolto ma "
                f"nessuna regola in ingresso lo prevede: è attivo ma non "
                f"dichiarato.",
                ip_address=host.ip_address, port_number=svc.port_number,
                protocol=svc.protocol))
        elif any(_rule_source_is_anywhere(r) for r in covering):
            findings.append(_finding(
                models.FINDING_OVEREXPOSED, models.SEVERITY_HIGH,
                f"Il servizio {descr} su {host.ip_address} è raggiungibile da "
                f"qualunque indirizzo (0.0.0.0/0): valuta di restringere la "
                f"regola agli indirizzi che ne hanno davvero bisogno.",
                ip_address=host.ip_address, port_number=svc.port_number,
                protocol=svc.protocol))

    # Regole che aprono una porta precisa dove non è in ascolto nessun servizio.
    listening = {(s.port_number, s.protocol) for s in internal_services}
    for rule in ingress_rules:
        # Le regole "qualunque porta" o senza protocollo (es. ICMP) non si
        # prestano a questo confronto: le saltiamo per non fare rumore.
        if rule.port_range_min is None or rule.protocol not in ("tcp", "udp"):
            continue
        coperta = any(rule.port_range_min <= port <= rule.port_range_max
                      and proto == rule.protocol
                      for port, proto in listening)
        if coperta:
            continue
        # Se la regola è ristretta ad altri indirizzi e nessuna regola dello
        # scanner copre la porta, lo scanner la vede "filtered": l'assenza del
        # servizio non prova nulla, quindi non si segnala.
        visibile = _source_includes_scanner(rule, scanner_ips) or any(
            _rule_covers_port(r, rule.port_range_min, rule.protocol)
            for r in scanner_rules)
        if visibile:
            findings.append(_finding(
                models.FINDING_USELESS_RULE, models.SEVERITY_LOW,
                f"Una regola apre {_ports_label(rule)}/{rule.protocol} su "
                f"{host.ip_address} ma lì non è in ascolto nessun servizio: "
                f"regola inutile, superficie di attacco evitabile.",
                ip_address=host.ip_address, port_number=rule.port_range_min,
                protocol=rule.protocol))

    return findings


def _external_findings(hosts, internal_by_host, external_by_host, floating_ips,
                       ports=()):
    """Segnalazioni dalla vista esterna (floating IP).

    Un floating IP indica l'IP fisso ma non la rete: la ricaviamo dalla porta
    Neutron a cui è associato, così l'host giusto è identificato per (rete, IP).
    """
    findings = []
    host_by_key = {(h.network_id, h.ip_address): h for h in hosts}
    network_by_port_id = {p.port_id: p.network_id for p in ports
                          if p.port_id}

    def fip_key(fip):
        return (network_by_port_id.get(fip.port_id), fip.fixed_ip_address)

    # Floating IP per (rete, IP fisso); quelli con rete ignota solo per IP.
    fip_by_key = {}
    fip_by_ip_only = {}
    for f in floating_ips:
        if not f.fixed_ip_address:
            continue
        network_id, fixed_ip = fip_key(f)
        if network_id is None:
            fip_by_ip_only[fixed_ip] = f.floating_ip_address
        else:
            fip_by_key[(network_id, fixed_ip)] = f.floating_ip_address

    def host_of(fip):
        network_id, fixed_ip = fip_key(fip)
        if network_id is not None:
            return host_by_key.get((network_id, fixed_ip))
        # Rete ignota: vale solo se l'IP identifica un host univoco.
        candidates = [h for h in hosts if h.ip_address == fixed_ip]
        return candidates[0] if len(candidates) == 1 else None

    for host in hosts:
        external = external_by_host.get(host.id, [])
        if not external:
            continue
        key = (host.network_id, host.ip_address)
        fip = fip_by_key.get(key) or fip_by_ip_only.get(
            host.ip_address, "il floating IP")
        internal_keys = {(s.port_number, s.protocol)
                         for s in internal_by_host.get(host.id, [])}
        for svc in external:
            descr = _service_label(svc)
            if (svc.port_number, svc.protocol) not in internal_keys:
                # Visto da fuori ma non censito internamente.
                findings.append(_finding(
                    models.FINDING_EXTERNAL_ONLY, models.SEVERITY_MEDIUM,
                    f"Il servizio {descr} si vede dal floating IP {fip} ma non "
                    f"era stato censito internamente su {host.ip_address}.",
                    ip_address=host.ip_address, port_number=svc.port_number,
                    protocol=svc.protocol))
            else:
                # Conferma: raggiungibile da Internet.
                findings.append(_finding(
                    models.FINDING_EXTERNALLY_REACHABLE, models.SEVERITY_INFO,
                    f"Il servizio {descr} di {host.ip_address} è raggiungibile "
                    f"da Internet sul floating IP {fip}.",
                    ip_address=host.ip_address, port_number=svc.port_number,
                    protocol=svc.protocol))

    # Floating IP allocati ma senza nessun servizio raggiungibile da fuori.
    for fip in floating_ips:
        host = host_of(fip)
        risponde = host is not None and external_by_host.get(host.id)
        if risponde:
            continue
        if not fip.port_id:
            motivo = "non è associato a nessuna porta"
        else:
            motivo = "non risponde nessun servizio da fuori"
        findings.append(_finding(
            models.FINDING_WASTED_FLOATING_IP, models.SEVERITY_LOW,
            f"Il floating IP {fip.floating_ip_address} è allocato ma {motivo}: "
            f"indirizzo pubblico inutilizzato, valuta di rilasciarlo.",
            ip_address=fip.floating_ip_address))

    return findings


def _service_label(svc):
    """Descrizione breve di un servizio, es. 'ssh (22/tcp)' o '(3306/tcp)'."""
    porta = f"{svc.port_number}/{svc.protocol}"
    return f"{svc.name} ({porta})" if svc.name else f"({porta})"


def findings_for_scan(scan_id, inventory):
    """Calcola le segnalazioni di una scansione: host e servizi dal database,
    inventario passato dal chiamante (raccolto all'inizio della scansione)."""
    hosts = db.get_hosts(scan_id)
    services = db.get_services(scan_id=scan_id)
    findings = build_findings(hosts, services, inventory)
    for finding in findings:
        finding["scan_id"] = scan_id
    return findings


def compute_and_save(scan_id, inventory):
    """Calcola e salva le segnalazioni di una scansione; le restituisce."""
    findings = findings_for_scan(scan_id, inventory)
    db.save_findings(findings)
    LOG.info("scansione %s: %d segnalazioni di esposizione", scan_id, len(findings))
    return findings
