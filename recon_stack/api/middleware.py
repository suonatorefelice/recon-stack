# Aggancio di keystonemiddleware alla pipeline WSGI (ADR 0002).
#
# keystonemiddleware è il "filtro" che tutti i servizi OpenStack mettono davanti
# alla propria API: intercetta la richiesta, prende il token dall'intestazione
# X-Auth-Token, lo fa validare da Keystone e, se è valido, aggiunge alla
# richiesta le intestazioni con l'identità (X-User-Id, X-Project-Id, X-Roles,
# ...). Il nostro codice legge quelle intestazioni in api/context.py.
#
# Lo mettiamo in "delay_auth_decision": così il middleware NON blocca da solo le
# richieste senza token (metterebbe solo X-Identity-Status: Invalid) e lascia
# decidere a noi, endpoint per endpoint. Serve perché /health deve restare
# pubblico, mentre le scansioni richiedono il ruolo admin (api/context.py).
#
# Le opzioni di connessione a Keystone (indirizzo, utente di servizio, password)
# non le dichiariamo noi: keystonemiddleware le legge dalla sezione
# [keystone_authtoken] del file di configurazione, che su DevStack scrive il
# plugin (devstack/plugin.sh). Per questo l'import è "pigro", dentro la
# funzione: lo sviluppo locale con "flask run" non passa di qui e non ha bisogno
# né della libreria né di un Keystone raggiungibile.

from recon_stack import conf


def install_auth_token(app):
    """Avvolge l'app WSGI con keystonemiddleware e la restituisce.

    app è l'applicazione Flask (è anche un'app WSGI). Il valore restituito è la
    stessa applicazione "incartata" dal middleware: è questo che uwsgi deve
    servire.
    """
    from keystonemiddleware import auth_token

    return auth_token.AuthProtocol(app, {
        # Config group: la sezione del file da cui leggere le opzioni.
        "oslo_config_config": conf.CONF,
        "oslo_config_project": "recon-stack",
        # Non rifiutare da solo le richieste senza token: decide il nostro codice.
        "delay_auth_decision": True,
    })
