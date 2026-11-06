# Test della parte privilegiata (privsep/discovery.py).
#
# Controlliamo i costruttori di comando puri (live_hosts_command,
# service_scan_command): sono la logica che conta (prefisso del namespace,
# opzioni nmap, traduzione dello scope). Non avviamo il demone privsep né nmap,
# così il test gira identico sul Mac e sulla VM.

import pytest

from recon_stack.privsep import discovery

# Namespace valida: 'ovnmeta-' + UUID Neutron (8-4-4-4-12 esadecimali).
NS = "ovnmeta-0c3b9a52-6f1e-4d7a-9b8c-1a2b3c4d5e6f"


def test_host_discovery_nel_namespace_senza_arp():
    command = discovery.live_hosts_command(NS, ["10.10.10.5"])
    # Eseguito dentro la network namespace della rete.
    assert command[:4] == ["ip", "netns", "exec", NS]
    # Solo scoperta degli host, senza DNS, risultato in XML, senza ARP.
    assert "-sn" in command and "-n" in command
    assert "--disable-arp-ping" in command
    assert command[-3:] == ["-oX", "-", "10.10.10.5"]


def test_service_scan_traduce_lo_scope_in_opzioni():
    # namespace=None: nessun prefisso 'ip netns exec' (vista esterna).
    command = discovery.service_scan_command(None, ["172.24.4.10"], scope="comuni")
    assert command[:3] == ["nmap", "-sV", "-n"]
    assert "-F" in command  # 'comuni' -> -F
    assert command[-1] == "172.24.4.10"


def test_service_scan_scope_sconosciuto_errore():
    with pytest.raises(ValueError):
        discovery.service_scan_command(NS, ["10.0.0.5"], scope="boh")


def test_target_non_ip_rifiutato():
    # Un target che non è un IP non arriva mai alla riga di comando di nmap.
    with pytest.raises(ValueError):
        discovery.live_hosts_command(NS, ["10.0.0.1; rm -rf /"])
    with pytest.raises(ValueError):
        discovery.service_scan_command(None, ["non-un-ip"])
    # Un IP valido produce il comando atteso.
    assert discovery.live_hosts_command(NS, ["10.0.0.1"])[-1] == "10.0.0.1"


def test_comando_nmap_ha_host_timeout():
    # Una nmap bloccata su un host non deve tenere appesa la scansione: entrambi
    # i comandi portano --host-timeout con un valore.
    for command in (
        discovery.live_hosts_command(NS, ["10.0.0.1"]),
        discovery.service_scan_command(NS, ["10.0.0.1"]),
    ):
        assert "--host-timeout" in command
        valore = command[command.index("--host-timeout") + 1]
        assert valore == discovery.HOST_TIMEOUT


def test_timeout_di_processo_oltre_quello_per_host():
    # Il tetto del processo (usato dagli entrypoint) scatta solo dopo che nmap ha
    # avuto il tempo di abbandonare da sé l'host con --host-timeout.
    host = int(discovery.HOST_TIMEOUT.rstrip("s"))
    assert discovery.PROCESS_TIMEOUT > host


@pytest.mark.parametrize("ns", [
    "ovnmeta-../../x",
    "root",
    "",
    "ovnmeta-",
    "ovnmeta-net-1",  # non è un UUID
    "ovnmeta-0c3b9a52-6f1e-4d7a-9b8c-1a2b3c4d5e6f; reboot",
    "ovnmeta-0c3b9a526f1e4d7a9b8c1a2b3c4d5e6f",  # UUID senza trattini
    "../ovnmeta-0c3b9a52-6f1e-4d7a-9b8c-1a2b3c4d5e6f",
    "ovnmeta-0c3b9a52-6f1e-4d7a-9b8c-1a2b3c4d5e6f\n",
])
def test_namespace_non_valido_rifiutato(ns):
    # Solo 'ovnmeta-<uuid>' arriva a 'ip netns exec', nel confine privilegiato.
    with pytest.raises(ValueError):
        discovery.live_hosts_command(ns, ["10.0.0.1"])
    with pytest.raises(ValueError):
        discovery.service_scan_command(ns, ["10.0.0.1"])


def test_namespace_valido_accettato():
    for command in (
        discovery.live_hosts_command(NS, ["10.0.0.1"]),
        discovery.service_scan_command(NS, ["10.0.0.1"]),
    ):
        assert command[:4] == ["ip", "netns", "exec", NS]
    # None = namespace radice (vista esterna): resta ammesso.
    assert discovery.live_hosts_command(None, ["10.0.0.1"])[0] == "nmap"
