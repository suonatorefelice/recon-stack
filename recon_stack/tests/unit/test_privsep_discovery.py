# Test dei comandi costruiti dalle funzioni privilegiate (privsep/discovery.py).
#
# Non eseguiamo nmap e non avviamo il demone privsep: sostituiamo
# processutils.execute con una funzione finta che registra il comando, e
# chiamiamo direttamente la funzione originale. oslo.privsep, decorando una
# funzione con @entrypoint, la avvolge in un functools.partial il cui primo
# argomento è la funzione originale: .args[0].

from recon_stack.privsep import discovery


def _run(entrypoint, monkeypatch, *args):
    commands = []

    def fake_execute(*command):
        commands.append(list(command))
        return "<nmaprun/>", ""

    monkeypatch.setattr(discovery.processutils, "execute", fake_execute)
    original = entrypoint.args[0]
    assert original(*args) == "<nmaprun/>"
    return commands[0]


def test_host_discovery_nel_namespace_senza_arp(monkeypatch):
    command = _run(discovery.live_hosts_xml, monkeypatch,
                   "ovnmeta-net-1", ["10.10.10.0/24"])
    # Eseguito dentro la network namespace della rete.
    assert command[:4] == ["ip", "netns", "exec", "ovnmeta-net-1"]
    # Solo scoperta degli host, senza DNS, con risultato in XML.
    assert "-sn" in command and "-n" in command
    assert command[-3:] == ["-oX", "-", "10.10.10.0/24"]
    # Senza ARP: con OVN le risposte ARP arrivano anche per le VM spente
    # (trovato nel test su DevStack), quindi non vanno usate.
    assert "--disable-arp-ping" in command
