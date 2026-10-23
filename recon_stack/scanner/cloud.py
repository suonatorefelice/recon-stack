# Connessione a OpenStack, in sola lettura.
#
# Tutto ciò che il servizio sa delle risorse (VM, porte, floating IP) lo legge
# da Nova e Neutron tramite openstacksdk, la libreria ufficiale per parlare con
# OpenStack da Python. openstacksdk legge le credenziali da un file
# clouds.yaml (di solito /etc/openstack/clouds.yaml) scegliendo il profilo il
# cui nome sta in CONF.scanner.cloud: in DevStack è "devstack-admin", che ha il
# ruolo admin e quindi può vedere le risorse di tutti i progetti (ADR 0003).
#
# Il servizio non modifica mai niente in OpenStack (ADR 0003, architettura.md):
# questo modulo offre solo letture. Tenere la connessione in un posto solo
# permette, nei test, di sostituirla con una finta senza toccare il resto del
# codice.

import logging

import openstack

from recon_stack import conf

LOG = logging.getLogger(__name__)


def connect():
    """Apre e restituisce la connessione al cloud configurato.

    openstack.connect cerca il profilo CONF.scanner.cloud in clouds.yaml. Se il
    file non c'è o il profilo è sbagliato, solleva un'eccezione: è giusto che la
    scansione fallisca subito invece di proseguire senza poter leggere Nova e
    Neutron.
    """
    cloud = conf.CONF.scanner.cloud
    LOG.info("connessione al cloud '%s'", cloud)
    return openstack.connect(cloud=cloud)
