# Inventario da Nova e Neutron: all'inizio di ogni scansione legge le risorse
# del progetto (VM, porte Neutron con i loro IP, floating IP e regole dei
# security group). Serve a calcolare il perimetro, a capire se un IP che
# risponde ha una porta nota (host "censito") o no ("sconosciuto") e a
# confrontare i servizi con le regole. Solo lettura (ADR 0003); conn è passata
# dal chiamante, così i test la simulano.

import collections
import logging

LOG = logging.getLogger(__name__)

# L'inventario resta in memoria per la durata della scansione: namedtuple con
# i soli campi che leggono perimetro, discovery, scansione ed esposizione.

# VM letta da Nova: serve per i nomi nella discovery.
ServerInfo = collections.namedtuple("ServerInfo", "server_id name status")

# Un IP fisso di una porta Neutron (una porta con più IP dà più elementi).
# security_group_ids è una tupla di id; port_security_enabled è None se ignoto.
PortInfo = collections.namedtuple(
    "PortInfo",
    "port_id network_id subnet_id ip_address device_owner device_id "
    "security_group_ids port_security_enabled")

FloatingIpInfo = collections.namedtuple(
    "FloatingIpInfo", "floating_ip_address fixed_ip_address port_id")

RuleInfo = collections.namedtuple(
    "RuleInfo",
    "security_group_id direction protocol port_range_min port_range_max "
    "remote_ip_prefix remote_group_id")


def collect(conn, project_id, scan_id):
    """Legge l'inventario del progetto e lo ritorna in memoria.

    Ritorna quattro liste di namedtuple: (server, porte, floating IP, regole),
    che run_scan passa al perimetro, alla discovery e all'esposizione.
    """
    servers = [
        ServerInfo(server_id=server.id, name=server.name, status=server.status)
        # all_projects=True: il servizio gira come admin; project_id filtra.
        for server in conn.compute.servers(all_projects=True, project_id=project_id)
    ]

    ports = []
    for port in conn.network.ports(project_id=project_id):
        # Security group della porta (uguali per tutti i suoi IP).
        sg_ids = tuple(getattr(port, "security_group_ids", None) or ())
        # Una porta può avere più IP fissi: un elemento per ciascuno.
        for fixed in port.fixed_ips or []:
            ports.append(PortInfo(
                port_id=port.id,
                network_id=port.network_id,
                subnet_id=fixed.get("subnet_id"),
                ip_address=fixed.get("ip_address"),
                device_owner=port.device_owner,
                device_id=port.device_id,
                security_group_ids=sg_ids,
                # None se il dato manca (estensione non attiva, o porte finte nei test).
                port_security_enabled=getattr(port, "is_port_security_enabled", None),
            ))

    floating_ips = [
        FloatingIpInfo(
            floating_ip_address=fip.floating_ip_address,
            fixed_ip_address=fip.fixed_ip_address,
            port_id=fip.port_id,
        )
        for fip in conn.network.ips(project_id=project_id)
    ]

    rules = [
        RuleInfo(
            security_group_id=rule.security_group_id,
            direction=rule.direction,
            protocol=rule.protocol,
            port_range_min=rule.port_range_min,
            port_range_max=rule.port_range_max,
            remote_ip_prefix=rule.remote_ip_prefix,
            remote_group_id=rule.remote_group_id,
        )
        for rule in conn.network.security_group_rules(project_id=project_id)
    ]

    LOG.info("scansione %s, inventario del progetto %s: %d VM, %d IP di porta, "
             "%d floating IP, %d regole", scan_id, project_id, len(servers),
             len(ports), len(floating_ips), len(rules))
    return servers, ports, floating_ips, rules
