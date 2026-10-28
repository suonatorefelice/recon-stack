# Preparazione comune a tutti i test unitari.
#
# pytest legge da solo questo file. Le "fixture" definite qui sono funzioni
# che preparano qualcosa prima di un test e, se serve, lo smontano dopo.

import os

import pytest

from recon_stack import conf
from recon_stack.db import api

# Indirizzo del database usato dai test (ADR 0001): un server MySQL vero, lo
# stesso tipo di database del servizio (su DevStack c'è già). Si cambia con la
# variabile d'ambiente qui sotto. Per una prova rapida senza MySQL si può usare
# SQLite (sqlite:///percorso/file): passa tutto tranne il test sul vincolo di
# chiave esterna, che SQLite non applica. I test che non usano il database
# (dashboard, parsing di nmap, perimetro, ...) non dipendono da questa variabile.
TEST_DATABASE_CONNECTION = os.environ.get(
    "RECON_TEST_DATABASE_CONNECTION",
    "mysql+pymysql://root@127.0.0.1/recon_stack_test",
)


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
    # Anche il collegamento al database è globale: lo chiudiamo, così il test
    # successivo ne apre uno nuovo verso il suo database.
    api.reset()


@pytest.fixture
def clean_database():
    """Database MySQL di test vuoto, con lo schema creato dai modelli.

    I test unitari usano MySQL come il servizio vero (ADR 0001). Il database è
    un server condiviso, non un file usa-e-getta: prima di ogni test eliminiamo
    le tabelle rimaste dal test precedente e ricreiamo lo schema (db/api.py),
    così ognuno parte pulito.

    I singoli file di test non ripetono questa preparazione: dichiarano soltanto
    questa fixture fra i loro argomenti.
    """
    conf.load([])
    conf.CONF.set_override(
        "connection", TEST_DATABASE_CONNECTION, group="database")
    api.reset()
    api.drop_all()
    api.create_all()
    yield
    api.reset()
