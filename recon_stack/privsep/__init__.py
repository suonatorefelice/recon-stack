# Confinamento dei privilegi con oslo.privsep (ADR 0007).
#
# Quasi tutto il server gira come utente normale, senza privilegi. Un'unica
# operazione ne ha bisogno: entrare in una network namespace di Neutron per
# scansionare una rete privata (ADR 0006), cosa che richiede root vero (su
# DevStack le sole capability sull'utente non bastano per `ip netns exec`).
# Invece di dare i privilegi all'intero server, oslo.privsep avvia un piccolo
# demone separato che esegue SOLO le funzioni che dichiariamo qui, con gli
# argomenti che gli passiamo: non accetta comandi arbitrari.
#
# recon_privsep è il "contesto": le funzioni decorate con @recon_privsep.entrypoint
# (vedi privsep/discovery.py) vengono eseguite dentro quel demone privilegiato,
# a cui il server parla via un socket Unix privato (non la REST). Il demone si
# avvia da solo alla prima chiamata.

from oslo_privsep import capabilities
from oslo_privsep import priv_context

# Il nome del contesto e la sezione di configurazione da cui oslo.privsep legge
# le proprie opzioni (quale comando usare per avviare il demone, ecc.): in
# DevStack le imposta il plugin. pypath deve indicare questo stesso oggetto.
recon_privsep = priv_context.PrivContext(
    "recon_stack",
    cfg_section="privsep",
    pypath=__name__ + ".recon_privsep",
    # Il demone parte come root (via sudo e privsep-helper) e subito dopo
    # rinuncia a tutte le capability tranne queste, le sole che servono:
    #   CAP_SYS_ADMIN -> entrare in una namespace esistente (setns);
    #   CAP_NET_RAW   -> i socket raw usati da alcune modalità di nmap.
    capabilities=[capabilities.CAP_SYS_ADMIN,
                  capabilities.CAP_NET_RAW],
)
