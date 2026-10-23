# L'unica operazione privilegiata: la scoperta degli host dentro una namespace.
#
# Questa funzione gira nel demone di oslo.privsep (ADR 0007), perché per entrare
# nella network namespace di Neutron (ADR 0006) servono privilegi di root. Fa
# una cosa sola: eseguire nel namespace indicato una scoperta degli host "vivi"
# (host discovery di nmap, opzione -sn, che controlla quali indirizzi rispondono
# senza esaminarne le porte: i servizi arrivano allo step 7). Restituisce
# l'output di nmap in formato XML, che il chiamante non privilegiato analizza
# (scanner/discovery.py): così nel demone resta il meno codice possibile.
#
# Gli argomenti sono controllati, non è una shell: namespace è un nome, targets
# è una lista di indirizzi già verificati contro il perimetro (ADR 0005) prima
# di arrivare qui. Non costruiamo comandi a partire da testo libero.

from oslo_concurrency import processutils

from recon_stack.privsep import recon_privsep

# Nome del programma; nmap lo installa il plugin DevStack (devstack/plugin.sh).
NMAP = "nmap"


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
