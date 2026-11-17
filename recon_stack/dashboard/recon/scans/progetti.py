# Scelta dei progetti da mostrare nel menu "Avvia scansione": le scansioni
# girano solo sul progetto demo, quindi filtriamo l'elenco di Keystone tenendo i
# soli progetti "scansionabili". Logica pura (niente Horizon/Django): il form
# la richiama con l'elenco e i nomi consentiti.

# Progetti scansionabili di default, sovrascrivibili da RECON_SCANNABLE_PROJECTS.
PROGETTI_SCANSIONABILI_DEFAULT = ("recon-demo",)


def scelte_menu(progetti, consentiti=PROGETTI_SCANSIONABILI_DEFAULT):
    """Dai progetti di Keystone ricava le voci (id, nome) del menu.

    Tiene solo quelli col nome fra i `consentiti`; se nessuno combacia ripiega su
    tutti (meglio un menu completo che vuoto). `progetti` hanno `.id` e `.name`.
    """
    consentiti = set(consentiti)
    tutte = [(p.id, getattr(p, "name", p.id)) for p in progetti]
    filtrate = [voce for voce in tutte if voce[1] in consentiti]
    return filtrate or tutte
