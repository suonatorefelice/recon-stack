# Esposizione: confronto fra i servizi trovati e i security group (step 11).
#
# Gli step precedenti dicono COSA gira nelle reti del progetto (host e servizi) e
# COSA permettono le regole dei security group (inventario, step 11 parte 1).
# Qui mettiamo le due cose a confronto e produciamo delle "segnalazioni": frasi
# in italiano che indicano un'incongruenza o un rischio. È uno strumento
# difensivo, pensato per chi amministra il cloud: serve a trovare porte aperte
# per sbaglio, servizi accesi ma non previsti, indirizzi pubblici inutili.
#
# I tipi di segnalazione (models.FINDING_*):
#   - esposizione eccessiva: un servizio in ascolto è raggiungibile da qualunque
#     indirizzo (una regola lo apre a 0.0.0.0/0);
#   - servizio latente: un servizio è in ascolto ma nessuna regola in ingresso lo
#     prevede (acceso ma non "dichiarato");
#   - regola inutile: una regola apre una porta dove non è in ascolto nessun
#     servizio (superficie di attacco inutile);
#   - raggiungibile dall'esterno: la vista esterna conferma un servizio visibile
#     da Internet sul floating IP (conferma, non un problema in sé);
#   - visto solo da fuori: un servizio appare dal floating IP ma non era stato
#     censito internamente;
#   - host non censito esposto: un host che risponde senza corrispondere a nessuna
#     risorsa Neutron, con porte aperte;
#   - floating IP inutile: un indirizzo pubblico senza nessun servizio dietro.
#
# Le funzioni di calcolo (build_findings) non toccano il database: ricevono liste
# di oggetti e si provano da sole. findings_for_scan le collega al database.

import json
import logging

from recon_stack.db import api as db
from recon_stack.db import models

LOG = logging.getLogger(__name__)

# Prefissi che indicano "qualunque indirizzo" in una regola di security group.
ANY_ADDRESS = ("0.0.0.0/0", "::/0")


def _rule_source_is_anywhere(rule):
    """La regola permette il traffico da qualunque indirizzo?

    In Neutron una regola senza remote_ip_prefix e senza remote_group_id vale per
    qualunque sorgente; lo stesso un prefisso 0.0.0.0/0 (o ::/0). Se invece punta
    a un altro security group (remote_group_id) la sorgente è ristretta.
    """
    if rule.remote_group_id:
        return False
    return rule.remote_ip_prefix in (None, *ANY_ADDRESS)


def _rule_covers_port(rule, port_number, protocol):
    """La regola in ingresso lascia passare questa porta/protocollo?

    - la direzione deve essere "ingress" (il traffico in entrata verso la VM);
    - il protocollo deve combaciare, oppure essere None (= qualunque protocollo);
    - la porta deve cadere nell'intervallo [port_range_min, port_range_max];
      se entrambi sono None la regola vale per tutte le porte.
    """
    if rule.direction != models.DIRECTION_INGRESS:
        return False
    if rule.protocol is not None and rule.protocol != protocol:
        return False
    if rule.port_range_min is None:
        return True
    return rule.port_range_min <= port_number <= rule.port_range_max


def _ports_label(rule):
    """Descrizione leggibile delle porte di una regola, es. '22' o '8000-8100'."""
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
    """Calcola le segnalazioni di esposizione di una scansione.

    - hosts: gli host trovati (models.Host);
    - services: i servizi trovati (models.Service), vista interna ed esterna;
    - inventory: il dizionario di db.get_inventory (porte, security group,
      regole, floating IP).
    Restituisce una lista di dizionari pronti per db.save_findings (manca solo
    lo scan_id, che aggiunge chi chiama).
    """
    rules_by_sg = {}
    for rule in inventory["security_group_rules"]:
        rules_by_sg.setdefault(rule.security_group_id, []).append(rule)

    # Security group applicati a ogni indirizzo, dalle porte dell'inventario.
    sg_ids_by_ip = {}
    for port in inventory["ports"]:
        if port.security_group_ids:
            sg_ids_by_ip[port.ip_address] = json.loads(port.security_group_ids)

    # Servizi raggruppati per host e per vista (interna / esterna).
    internal_by_host = {}
    external_by_host = {}
    for svc in services:
        bucket = (external_by_host if svc.view == models.VIEW_EXTERNAL
                  else internal_by_host)
        bucket.setdefault(svc.host_id, []).append(svc)

    findings = []
    for host in hosts:
        findings.extend(_host_findings(
            host, internal_by_host.get(host.id, []),
            sg_ids_by_ip.get(host.ip_address, []), rules_by_sg))

    findings.extend(_external_findings(hosts, internal_by_host,
                                       external_by_host, inventory["floating_ips"]))
    return findings


def _host_findings(host, internal_services, sg_ids, rules_by_sg):
    """Segnalazioni che nascono dal confronto servizi/regole su un singolo host."""
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

    # Il confronto con le regole ha senso solo per gli host censiti (una porta
    # Neutron con i suoi security group). Gli host assenti non rispondono.
    if host.classification != models.HOST_KNOWN:
        return findings

    ingress_rules = [r for sg in sg_ids for r in rules_by_sg.get(sg, [])
                     if r.direction == models.DIRECTION_INGRESS]

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
        if rule.port_range_min is None or rule.protocol not in ("tcp", "udp"):
            # Le regole "qualunque porta" o senza protocollo (es. ICMP) non si
            # prestano a questo confronto: le lasciamo stare per non fare rumore.
            continue
        coperta = any(rule.port_range_min <= port <= rule.port_range_max
                      and proto == rule.protocol
                      for port, proto in listening)
        if not coperta:
            findings.append(_finding(
                models.FINDING_USELESS_RULE, models.SEVERITY_LOW,
                f"Una regola apre {_ports_label(rule)}/{rule.protocol} su "
                f"{host.ip_address} ma lì non è in ascolto nessun servizio: "
                f"regola inutile, superficie di attacco evitabile.",
                ip_address=host.ip_address, port_number=rule.port_range_min,
                protocol=rule.protocol))

    return findings


def _external_findings(hosts, internal_by_host, external_by_host, floating_ips):
    """Segnalazioni che nascono dalla vista esterna (floating IP)."""
    findings = []
    host_by_ip = {h.ip_address: h for h in hosts}
    # Floating IP che hanno risposto, per indirizzo privato dietro di essi.
    fip_by_fixed_ip = {f.fixed_ip_address: f.floating_ip_address
                       for f in floating_ips if f.fixed_ip_address}

    for host in hosts:
        external = external_by_host.get(host.id, [])
        if not external:
            continue
        fip = fip_by_fixed_ip.get(host.ip_address, "il floating IP")
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

    # Floating IP sprecati: allocati ma senza nessun servizio raggiungibile.
    for fip in floating_ips:
        host = host_by_ip.get(fip.fixed_ip_address)
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


def findings_for_scan(scan_id):
    """Calcola le segnalazioni di una scansione leggendo host, servizi e inventario.

    Restituisce la lista di dizionari (con scan_id) pronta per db.save_findings.
    """
    hosts = db.get_hosts(scan_id)
    services = db.get_services(scan_id=scan_id)
    inventory = db.get_inventory(scan_id)
    findings = build_findings(hosts, services, inventory)
    for finding in findings:
        finding["scan_id"] = scan_id
    return findings


def compute_and_save(scan_id):
    """Calcola e salva le segnalazioni di una scansione; le restituisce."""
    findings = findings_for_scan(scan_id)
    db.save_findings(findings)
    LOG.info("scansione %s: %d segnalazioni di esposizione", scan_id, len(findings))
    return findings
