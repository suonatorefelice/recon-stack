# Connessione a OpenStack, in sola lettura. Il servizio legge le risorse (VM,
# porte, floating IP) da Nova e Neutron con openstacksdk, che prende le
# credenziali da clouds.yaml scegliendo il profilo CONF.scanner.cloud (in
# DevStack "devstack-admin", ruolo admin, ADR 0003). Non modifica mai niente.
# Tenerla qui permette ai test di sostituirla con una finta.

import logging

import openstack

from recon_stack import conf

LOG = logging.getLogger(__name__)


def connect():
    """Apre e restituisce la connessione al cloud configurato (profilo in clouds.yaml).

    Se il file o il profilo mancano, solleva un'eccezione: giusto che la
    scansione fallisca subito invece di proseguire senza poter leggere OpenStack.
    """
    cloud = conf.CONF.scanner.cloud
    LOG.info("connessione al cloud '%s'", cloud)
    return openstack.connect(cloud=cloud)
