# Test dei comandi openstack recon (osc/commands.py).
#
# I comandi cliff restituiscono (colonne, righe) per le liste e (colonne, valori)
# per i "mostra". Qui li costruiamo con un'app finta il cui client_manager.recon
# è un client finto: così proviamo la trasformazione dei dati senza API né rete.

import argparse
import types

import pytest
from osc_lib import exceptions

from recon_stack.osc import commands


class _FakeClient:
    def __init__(self):
        self.calls = []

    def list_hosts(self, project_id=None, scan_id=None, classification=None):
        self.calls.append(("list_hosts", project_id, scan_id, classification))
        return [{"id": "h-1", "ip_address": "10.0.0.5", "classification": "known",
                 "server_name": "web", "network_id": "net-1"}]

    def get_host(self, host_id):
        self.calls.append(("get_host", host_id))
        return {"id": host_id, "ip_address": "10.0.0.5", "classification": "known",
                "server_name": "web", "network_id": "net-1",
                "neutron_port_id": "port-1",
                "services": [{"port_number": 22, "protocol": "tcp", "name": "ssh",
                              "product": "OpenSSH", "version": "8.9p1"}]}

    def list_services(self, project_id=None, scan_id=None, name=None):
        self.calls.append(("list_services", project_id, scan_id, name))
        return [{"host_id": "h-1", "ip_address": "10.0.0.5", "port_number": 22,
                 "protocol": "tcp", "name": "ssh", "product": "OpenSSH",
                 "version": "8.9p1", "view": "internal"}]

    def list_scans(self, project_id=None, status=None):
        self.calls.append(("list_scans", project_id, status))
        return [{"id": "s-1", "project_id": "p-1", "status": "DONE",
                 "trigger": "manual", "created_at": "2026-10-27T10:00:00"}]

    def create_scan(self, project_id):
        self.calls.append(("create_scan", project_id))
        return {"id": "s-9", "project_id": project_id, "status": "PENDING",
                "trigger": "manual", "requested_by_user": "user-1",
                "created_at": "x", "started_at": None, "finished_at": None,
                "fault": None}

    def get_scan(self, scan_id):
        self.calls.append(("get_scan", scan_id))
        return {"id": scan_id, "project_id": "p-1", "status": "RUNNING",
                "trigger": "manual", "requested_by_user": "user-1",
                "created_at": "x", "started_at": "y", "finished_at": None,
                "fault": None, "phase": "discovery"}

    def get_scan_diff(self, scan_id):
        self.calls.append(("get_scan_diff", scan_id))
        return {"previous_scan_id": "s-0",
                "hosts_appeared": ["10.0.0.9"], "hosts_disappeared": [],
                "hosts_reclassified": [],
                "services_appeared": [{"ip": "10.0.0.5", "port": 80,
                                       "protocol": "tcp", "name": "http"}],
                "services_disappeared": []}

    def get_scan_exposure(self, scan_id, severity=None):
        self.calls.append(("get_scan_exposure", scan_id, severity))
        return [{"type": "overexposed", "severity": "high",
                 "ip_address": "10.0.0.5", "port_number": 22, "protocol": "tcp",
                 "message": "ssh aperto a tutti"}]


class _FakeIdentity:
    """Keystone finto: conosce solo il progetto recon-demo, con id p-1."""

    def find_project(self, name_or_id, ignore_missing=True):
        if name_or_id in ("recon-demo", "p-1"):
            return types.SimpleNamespace(id="p-1", name="recon-demo")
        return None


class _ClientManager:
    def __init__(self, recon):
        self.recon = recon
        # La connessione openstacksdk che la CLI dà ai plugin: la usiamo per
        # risolvere --project da nome a id.
        self.sdk_connection = types.SimpleNamespace(identity=_FakeIdentity())


class _App:
    def __init__(self, recon):
        self.client_manager = _ClientManager(recon)


def _run(command_cls, **args):
    """Costruisce il comando con un client finto e ne esegue take_action."""
    client = _FakeClient()
    command = command_cls(_App(client), [])
    return command.take_action(argparse.Namespace(**args)), client


def test_host_list():
    (headers, rows), client = _run(
        commands.ListHost, project="p-1", scan=None, classification="known")
    assert client.calls[0] == ("list_hosts", "p-1", None, "known")
    assert rows == [("h-1", "10.0.0.5", "known", "web", "net-1")]


def test_host_show_riassume_i_servizi():
    (columns, values), _ = _run(commands.ShowHost, host="h-1")
    assert "Servizi" in columns
    servizi = values[columns.index("Servizi")]
    assert servizi == "22/tcp ssh OpenSSH 8.9p1"


def test_service_list():
    (headers, rows), client = _run(
        commands.ListService, project=None, scan=None, name="ssh")
    assert client.calls[0] == ("list_services", None, None, "ssh")
    assert rows == [("10.0.0.5", 22, "tcp", "ssh", "OpenSSH", "8.9p1", "internal")]


def test_scan_list():
    (headers, rows), _ = _run(commands.ListScan, project=None, status="DONE")
    assert rows == [("s-1", "p-1", "DONE", "manual", "2026-10-27T10:00:00")]


def test_scan_start_mostra_la_scansione_creata():
    (columns, values), client = _run(commands.StartScan, project="p-1")
    assert client.calls[0] == ("create_scan", "p-1")
    assert values[columns.index("Stato")] == "PENDING"


def test_scan_show_mostra_la_fase():
    (columns, values), client = _run(commands.ShowScan, scan="s-1")
    assert client.calls[0] == ("get_scan", "s-1")
    assert values[columns.index("Fase")] == "discovery"


def test_scan_diff_riassume_le_differenze():
    (columns, values), client = _run(commands.DiffScan, scan="s-9")
    assert client.calls[0] == ("get_scan_diff", "s-9")
    assert values[columns.index("Host comparsi")] == "10.0.0.9"
    assert values[columns.index("Servizi comparsi")] == "10.0.0.5 80/tcp http"


def test_scan_exposure_elenca_le_segnalazioni():
    (headers, rows), client = _run(commands.ExposureScan, scan="s-9",
                                   severity=None)
    assert client.calls[0] == ("get_scan_exposure", "s-9", None)
    assert rows == [("high", "overexposed", "10.0.0.5", 22,
                     "ssh aperto a tutti")]


def test_project_per_nome_diventa_id():
    # Chi usa la CLI scrive il nome del progetto; alla API deve arrivare l'id.
    (_, _), client = _run(
        commands.ListHost, project="recon-demo", scan=None, classification=None)
    assert client.calls[0] == ("list_hosts", "p-1", None, None)


def test_project_inesistente_da_errore_chiaro():
    with pytest.raises(exceptions.CommandError, match="non trovato"):
        _run(commands.ListHost, project="non-esiste", scan=None,
             classification=None)


def test_scan_start_accetta_il_nome_del_progetto():
    (_, _), client = _run(commands.StartScan, project="recon-demo")
    assert client.calls[0] == ("create_scan", "p-1")


def test_servizio_della_vista_esterna_e_indicato():
    servizio = {"port_number": 22, "protocol": "tcp", "name": "ssh",
                "product": None, "version": None, "view": "external"}
    assert commands._format_service(servizio) == "22/tcp ssh (vista esterna)"


# --- Client finto con stati controllati (per --wait, riepilogo, host per IP) --

class _ScanFake:
    """Client finto che restituisce stati scansione a comando.

    `statuses` è la sequenza di stati che get_scan ritorna a ogni chiamata
    (esaurita, ritorna DONE). Serve a simulare una scansione che avanza.
    """

    def __init__(self, statuses, findings=None):
        self._statuses = list(statuses)
        self._findings = findings or []
        self.calls = []

    def create_scan(self, project_id):
        self.calls.append(("create_scan", project_id))
        return {"id": "s-9", "project_id": project_id, "status": "PENDING"}

    def get_scan(self, scan_id):
        self.calls.append(("get_scan", scan_id))
        status = self._statuses.pop(0) if self._statuses else "DONE"
        return {"id": scan_id, "project_id": "p-1", "status": status,
                "phase": "discovery", "trigger": "manual",
                "requested_by_user": "user-1", "created_at": "x",
                "started_at": "y", "finished_at": None, "fault": None}

    def get_scan_exposure(self, scan_id, severity=None):
        self.calls.append(("get_scan_exposure", scan_id, severity))
        return self._findings

    def list_hosts(self, project_id=None, scan_id=None, classification=None):
        self.calls.append(("list_hosts", project_id, scan_id, classification))
        return [{"id": "h-1", "ip_address": "10.10.10.142"}]

    def get_host(self, host_id):
        self.calls.append(("get_host", host_id))
        return {"id": host_id, "ip_address": "10.10.10.142",
                "classification": "known", "server_name": "web",
                "network_id": "net-1", "neutron_port_id": "port-1",
                "services": []}


def _run_with(client, command_cls, **args):
    """Come _run, ma con un client finto fornito da fuori."""
    command = command_cls(_App(client), [])
    return command.take_action(argparse.Namespace(**args)), client


# --- Riepilogo delle segnalazioni --------------------------------------------

def test_riepilogo_segnalazioni_conta_per_gravita():
    assert commands._exposure_summary(None) == "—"
    assert commands._exposure_summary([]) == "nessuna"
    findings = [{"severity": "high"}, {"severity": "high"}, {"severity": "high"},
                {"severity": "medium"},
                {"severity": "low"}, {"severity": "low"},
                {"severity": "info"}]
    assert commands._exposure_summary(findings) == \
        "Grave: 3 · Media: 1 · Bassa: 2 · Info: 1"


def test_scan_show_include_il_riepilogo_se_conclusa():
    client = _ScanFake(statuses=["DONE"],
                       findings=[{"severity": "high"}, {"severity": "high"},
                                 {"severity": "medium"}, {"severity": "info"}])
    (columns, values), _ = _run_with(client, commands.ShowScan, scan="s-1")
    assert values[columns.index("Stato")] == "DONE"
    assert values[columns.index("Segnalazioni")] == "Grave: 2 · Media: 1 · Info: 1"


def test_scan_show_non_conclusa_non_chiede_le_segnalazioni():
    # Scansione in corso: niente riepilogo e nessuna chiamata a exposure.
    client = _ScanFake(statuses=["RUNNING"])
    (columns, values), _ = _run_with(client, commands.ShowScan, scan="s-1")
    assert values[columns.index("Segnalazioni")] == "—"
    assert all(c[0] != "get_scan_exposure" for c in client.calls)


# --- scan start --wait -------------------------------------------------------

def test_scan_start_wait_segue_fino_a_conclusa():
    client = _ScanFake(statuses=["RUNNING", "DONE"],
                       findings=[{"severity": "low"}])
    (columns, values), _ = _run_with(
        client, commands.StartScan, project="p-1", wait=True,
        timeout=10, interval=0)
    assert values[columns.index("Stato")] == "DONE"
    assert values[columns.index("Segnalazioni")] == "Bassa: 1"
    assert ("create_scan", "p-1") in client.calls
    assert ("get_scan", "s-9") in client.calls


def test_scan_start_senza_wait_non_aspetta():
    client = _ScanFake(statuses=["RUNNING"])
    (columns, values), _ = _run_with(
        client, commands.StartScan, project="p-1", wait=False,
        timeout=180, interval=3)
    assert values[columns.index("Stato")] == "PENDING"
    # non deve aver ricontrollato lo stato
    assert all(c[0] != "get_scan" for c in client.calls)


def test_wait_timeout_da_errore_chiaro():
    client = _ScanFake(statuses=["RUNNING"])
    tempi = iter([0, 100])   # deadline a 5, poi "sono passati 100s"
    with pytest.raises(exceptions.CommandError, match="non è finita"):
        commands._wait_for_scan(client, "s-9", timeout=5, interval=0,
                                sleep=lambda _n: None,
                                monotonic=lambda: next(tempi))


# --- host show per indirizzo IP ----------------------------------------------

def test_looks_like_ip():
    assert commands._looks_like_ip("10.10.10.142")
    assert not commands._looks_like_ip("h-1")
    assert not commands._looks_like_ip(
        "e0a96c8e-8f80-4407-aed0-3eb1cee11c77")


def test_host_show_per_ip_risolve_id():
    client = _ScanFake(statuses=[])
    (columns, values), _ = _run_with(
        client, commands.ShowHost, host="10.10.10.142", project=None, scan=None)
    assert ("list_hosts", None, None, None) in client.calls
    assert ("get_host", "h-1") in client.calls
    assert values[columns.index("Indirizzo IP")] == "10.10.10.142"


def test_host_show_ip_inesistente_da_errore():
    client = _ScanFake(statuses=[])
    with pytest.raises(exceptions.CommandError, match="nessun host con indirizzo"):
        _run_with(client, commands.ShowHost, host="10.0.0.99",
                  project=None, scan=None)
