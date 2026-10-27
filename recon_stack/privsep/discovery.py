# Le operazioni privilegiate: la scoperta di host e servizi dentro una namespace.
#
# Queste funzioni girano nel demone di oslo.privsep (ADR 0007), perché per
# entrare nella network namespace di Neutron (ADR 0006) servono privilegi di
# root. Fanno due cose, una per step:
#   - live_hosts_xml (Step 6): host discovery (nmap -sn), scopre quali indirizzi
#     rispondono senza esaminarne le porte;
#   - service_scan_xml (Step 7): service discovery (nmap -sV), per gli host che
#     rispondono scopre quali programmi sono in ascolto e la loro versione.
# Entrambe restituiscono l'output di nmap in formato XML, che il chiamante non
# privilegiato analizza (scanner/discovery.py, scanner/services.py): così nel
# demone resta il meno codice possibile.
#
# Gli argomenti sono controllati, non è una shell: namespace è un nome, targets
# è una lista di indirizzi già verificati contro il perimetro (ADR 0005) prima
# di arrivare qui, e scope è una parola presa da un elenco chiuso. Non
# costruiamo comandi a partire da testo libero: dal confine privilegiato non
# passano mai opzioni nmap libere.

from oslo_concurrency import processutils

from recon_stack.privsep import recon_privsep

# Nome del programma; nmap lo installa il plugin DevStack (devstack/plugin.sh).
NMAP = "nmap"

# Profondità della scansione dei servizi -> opzioni nmap. La mappa sta qui, nel
# demone, apposta: così attraverso il confine privilegiato passa solo una delle
# parole di questo elenco (opzione [scanner] service_scan_scope), mai opzioni
# nmap libere.
#   -F  = "fast scan", solo le ~100 porte più comuni;
#   ""  = nessuna opzione, cioè il default di nmap (le 1000 porte più comuni);
#   -p- = tutte le 65535 porte TCP.
_SCOPE_FLAGS = {
    "comuni": ["-F"],
    "top1000": [],
    "tutte": ["-p-"],
}


@recon_privsep.entrypoint
def live_hosts_xml(namespace, targets):
    """Esegue la scoperta degli host nel namespace e restituisce l'XML di nmap.

    Opzioni usate:
      -sn   solo scoperta degli host (nessun esame delle porte);
      -n    non risolvere i nomi DNS (più veloce e senza traffico extra);
      -oX - scrive il risultato in XML sullo standard output.
    """
    command = ["ip", "netns", "exec", namespace, NMAP, "-sn", "-n", "-oX", "-",
               *targets]
    stdout, _stderr = processutils.execute(*command)
    return stdout


@recon_privsep.entrypoint
def service_scan_xml(namespace, targets, scope="top1000"):
    """Esegue il service discovery nel namespace e restituisce l'XML di nmap.

    Opzioni usate:
      -sV   per ogni porta aperta tenta di riconoscere servizio e versione;
      -n    non risolvere i nomi DNS;
      -oX - scrive il risultato in XML sullo standard output.
    A queste si aggiungono le opzioni che decidono quante porte esaminare,
    scelte da scope (vedi _SCOPE_FLAGS).
    """
    flags = _SCOPE_FLAGS.get(scope)
    if flags is None:
        # Non dovrebbe succedere: le choices in conf.py filtrano già il valore.
        # Questo protegge il demone se qualcuno lo chiama con un valore a mano.
        raise ValueError(f"profondità di scansione sconosciuta: {scope}")
    command = ["ip", "netns", "exec", namespace, NMAP, "-sV", "-n", "-oX", "-",
               *flags, *targets]
    stdout, _stderr = processutils.execute(*command)
    return stdout
