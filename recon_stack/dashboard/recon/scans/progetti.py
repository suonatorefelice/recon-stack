# Scelta dei progetti da mostrare nel menu "Avvia scansione".
#
# Le scansioni vere girano SOLO sul progetto demo (recon-demo): è la regola di
# sicurezza del progetto (ADR 0002). Far scegliere all'utente uno
# qualunque dei progetti di sistema di OpenStack (admin, service, demo, ...) non
# ha senso e confonde: quei progetti non si scansionano. Qui filtriamo l'elenco
# letto da Keystone e teniamo solo i progetti "scansionabili".
#
# Questa è logica PURA: nessun import di Horizon o di Django, così si prova con i
# test unitari sul Mac. Il form (forms.py) la richiama passando l'elenco dei
# progetti di Keystone e la lista dei nomi consentiti.

# I progetti che ha senso scansionare, quando la configurazione non dice altro.
# È sovrascrivibile da Django con l'impostazione RECON_SCANNABLE_PROJECTS.
PROGETTI_SCANSIONABILI_DEFAULT = ("recon-demo",)


def scelte_menu(progetti, consentiti=PROGETTI_SCANSIONABILI_DEFAULT):
    """Dalle risorse progetto di Keystone ricava le voci (id, nome) del menu.

    Tiene solo i progetti il cui nome è fra quelli `consentiti`. Se nessuno
    combacia — per esempio in un ambiente diverso, con nomi diversi — ripiega su
    TUTTI i progetti: meglio un menu completo che un menu vuoto che
    impedirebbe di avviare qualunque scansione.

    `progetti` sono oggetti con attributo `.id` e (di solito) `.name`.
    Ritorna una lista di coppie (id, nome) adatta a un ChoiceField di Horizon.
    """
    consentiti = set(consentiti)
    tutte = [(p.id, getattr(p, "name", p.id)) for p in progetti]
    filtrate = [voce for voce in tutte if voce[1] in consentiti]
    return filtrate or tutte
