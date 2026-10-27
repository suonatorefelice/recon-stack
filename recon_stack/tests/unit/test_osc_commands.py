# Test dei comandi openstack recon (osc/commands.py).
#
# I comandi cliff restituiscono (colonne, righe) per le liste e (colonne, valori)
# per i "mostra". Qui li costruiamo con un'app finta il cui client_manager.recon
# è un client finto: così proviamo la trasformazione dei dati senza API né rete.

import argparse

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
        return [{"host_id": "h-1", "port_number": 22, "protocol": "tcp",
                 "name": "ssh", "product": "OpenSSH", "version": "8.9p1"}]

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


class _ClientManager:
    def __init__(self, recon):
        self.recon = recon


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
    assert rows == [("h-1", 22, "tcp", "ssh", "OpenSSH", "8.9p1")]


def test_scan_list():
    (headers, rows), _ = _run(commands.ListScan, project=None, status="DONE")
    assert rows == [("s-1", "p-1", "DONE", "manual", "2026-10-27T10:00:00")]


def test_scan_start_mostra_la_scansione_creata():
    (columns, values), client = _run(commands.StartScan, project="p-1")
    assert client.calls[0] == ("create_scan", "p-1")
    assert values[columns.index("Stato")] == "PENDING"
