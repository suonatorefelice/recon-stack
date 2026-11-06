# Operazioni privilegiate: host e service discovery dentro una namespace. Girano
# nel demone di oslo.privsep (ADR 0007) perché entrare nelle namespace di Neutron
# (ADR 0006) richiede root. Restituiscono l'XML di nmap, che il chiamante non
# privilegiato analizza, così nel demone resta il meno codice possibile.
#
# Gli argomenti sono controllati, non è una shell: namespace è un nome, targets
# indirizzi IP: ogni target è validato come IP qui, nel confine privilegiato
# (_valida_target), e la namespace deve essere 'ovnmeta-<uuid>'
# (_valida_namespace), prima di costruire il comando; scope una parola di un
# elenco chiuso. Dal confine privilegiato non passano mai opzioni nmap libere.
# namespace=None = namespace radice dell'host (serve alla vista esterna).
#
# La costruzione del comando sta in funzioni pure (_*_command), così si prova
# senza demone né nmap; l'esecuzione vera è negli @entrypoint, dentro il demone.

import ipaddress
import re

from oslo_concurrency import processutils

from recon_stack.privsep import recon_privsep

NMAP = "nmap"  # installato dal plugin DevStack

# Tetti di tempo: una nmap bloccata non deve lasciare la scansione RUNNING (con
# le periodiche, max_instances=1, bloccherebbe anche le successive).
# HOST_TIMEOUT: nmap abbandona da sé un host dopo tanto (--host-timeout).
# PROCESS_TIMEOUT (secondi): tetto sul processo nmap intero, oltre HOST_TIMEOUT.
HOST_TIMEOUT = "600s"
PROCESS_TIMEOUT = 1800

# Profondità della scansione servizi -> opzioni nmap. La mappa sta qui: dal
# confine passa solo una di queste parole, mai opzioni nmap libere.
#   -F = ~100 porte più comuni; "" = default nmap (1000 porte); -p- = tutte.
_SCOPE_FLAGS = {
    "comuni": ["-F"],
    "top1000": [],
    "tutte": ["-p-"],
}


def _namespace_prefix(namespace):
    """["ip", "netns", "exec", <nome>] per entrare in una namespace; [] se None."""
    return ["ip", "netns", "exec", namespace] if namespace else []


def _valida_target(targets):
    """Solleva ValueError se un target non è un indirizzo IP valido."""
    for target in targets:
        try:
            ipaddress.ip_address(target)
        except ValueError:
            raise ValueError(
                f"target non valido (non è un IP): {target!r}") from None


# Namespace di metadati OVN: 'ovnmeta-' + UUID di Neutron (8-4-4-4-12 esadecimali
# minuscoli o maiuscoli, con trattini). fullmatch: nessun carattere in più, nemmeno
# un a-capo finale.
_NAMESPACE_RE = re.compile(
    r"ovnmeta-[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}")


def _valida_namespace(namespace):
    """Solleva ValueError se la namespace non è 'ovnmeta-<uuid>'.

    None è ammesso (namespace radice, vista esterna): non entra in nessuna
    namespace. Qualunque altro valore, stringa vuota compresa, va rifiutato.
    """
    if namespace is None:
        return
    if not isinstance(namespace, str) or not _NAMESPACE_RE.fullmatch(namespace):
        raise ValueError(
            f"namespace non valida (atteso ovnmeta-<uuid>): {namespace!r}")


def live_hosts_command(namespace, targets):
    """Comando nmap per l'host discovery (lista di argomenti, senza shell).

    -sn host discovery senza esame delle porte; -n niente DNS; -oX - output XML.
    --disable-arp-ping: con OVN all'ARP risponde OVN stesso, anche per le VM
    spente, che sembrerebbero accese; senza ARP nmap usa sonde IP, a cui
    risponde solo una VM davvero attiva.
    """
    _valida_namespace(namespace)
    _valida_target(targets)
    return [*_namespace_prefix(namespace), NMAP, "-sn", "-n",
            "--disable-arp-ping", "--host-timeout", HOST_TIMEOUT,
            "-oX", "-", *targets]


def service_scan_command(namespace, targets, scope="top1000"):
    """Comando nmap per il service discovery (lista di argomenti).

    -sV riconosce servizio e versione sulle porte aperte; -n niente DNS; -oX -
    output XML; le porte da esaminare le decide scope (_SCOPE_FLAGS).
    namespace=None scansiona nella namespace radice (vista esterna).
    """
    _valida_namespace(namespace)
    _valida_target(targets)
    flags = _SCOPE_FLAGS.get(scope)
    if flags is None:
        # Non dovrebbe capitare (choices in conf.py filtra già); protegge il
        # demone da una chiamata con un valore a mano.
        raise ValueError(f"profondità di scansione sconosciuta: {scope}")
    return [*_namespace_prefix(namespace), NMAP, "-sV", "-n",
            "--host-timeout", HOST_TIMEOUT, "-oX", "-", *flags, *targets]


@recon_privsep.entrypoint
def live_hosts_xml(namespace, targets):
    """Host discovery nel namespace (eseguito dal demone root): ritorna l'XML."""
    stdout, _stderr = processutils.execute(
        *live_hosts_command(namespace, targets), timeout=PROCESS_TIMEOUT)
    return stdout


@recon_privsep.entrypoint
def service_scan_xml(namespace, targets, scope="top1000"):
    """Service discovery nel namespace (eseguito dal demone root): ritorna l'XML."""
    stdout, _stderr = processutils.execute(
        *service_scan_command(namespace, targets, scope),
        timeout=PROCESS_TIMEOUT)
    return stdout
