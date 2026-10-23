# Preparazione comune a tutti i test unitari.
#
# pytest legge da solo questo file. Le "fixture" definite qui sono funzioni
# che preparano qualcosa prima di un test e, se serve, lo smontano dopo.

import pytest

from recon_stack import conf


@pytest.fixture(autouse=True)
def clean_conf():
    """Riporta la configurazione ai valori predefiniti dopo ogni test.

    oslo.config usa un oggetto globale (conf.CONF): senza questa pulizia, un
    test che legge un file di configurazione lascerebbe i suoi valori al test
    successivo, e i risultati dipenderebbero dall'ordine dei test.
    autouse=True vuol dire che vale per tutti i test, senza doverla chiedere.
    """
    yield
    conf.CONF.reset()
    conf.CONF.clear()
