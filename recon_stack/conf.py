# Opzioni di configurazione del servizio, con oslo.config (ADR 0008). Ogni
# opzione è dichiarata qui una volta, con tipo, default e aiuto; il resto del
# codice la legge da CONF (es. CONF.scanner.cloud). Il file
# recon-stack.conf, se non indicato, oslo.config lo cerca in ~/.recon-stack/,
# ~/, /etc/recon-stack/, /etc/: su DevStack lo scrive il plugin, sul Mac di
# solito non c'è e valgono i default.

import logging

from oslo_config import cfg

CONF = cfg.CONF

# Sezione [DEFAULT].
default_opts = [
    cfg.BoolOpt(
        "debug",
        default=False,
        help="Scrive nei log anche i messaggi di dettaglio (livello DEBUG).",
    ),
]

# Sezione [scanner]: scansioni e scheduler periodico, dentro il processo unico.
scanner_group = cfg.OptGroup("scanner", title="Opzioni dello scanner")
scanner_opts = [
    # Lo scanner legge Nova e Neutron con le credenziali di questo profilo (ADR 0003).
    cfg.StrOpt(
        "cloud",
        default="devstack-admin",
        help="Profilo di /etc/openstack/clouds.yaml usato per leggere Nova e "
             "Neutron. In DevStack 'devstack-admin' ha il ruolo admin.",
    ),
    # Il tetto protegge da subnet enormi, che richiederebbero scansioni
    # interminabili (ADR 0005).
    cfg.IntOpt(
        "max_perimeter_addresses",
        default=4096,
        min=1,
        help="Massimo numero di indirizzi interni di un perimetro: oltre, "
             "la scansione non parte. Con il valore predefinito una /20 "
             "(4094 indirizzi utilizzabili) passa, una /19 o una /16 no.",
    ),
    cfg.IntOpt(
        "min_scan_interval",
        default=60,
        min=0,
        help="Secondi minimi fra due scansioni avviate dello stesso progetto "
             "(limite di frequenza). 0 disattiva il limite.",
    ),
    cfg.IntOpt(
        "periodic_scan_interval",
        default=0,
        min=0,
        help="Ogni quanti secondi avviare una scansione periodica dei progetti "
             "in periodic_projects. 0 (default) le disattiva.",
    ),
    cfg.ListOpt(
        "periodic_projects",
        default=[],
        help="Progetti da scansionare periodicamente (nomi o id, separati da "
             "virgola), usati solo se periodic_scan_interval > 0.",
    ),
    # La parola scelta è tradotta in opzioni nmap da privsep/discovery.py: dal
    # confine privilegiato non passano opzioni libere.
    cfg.StrOpt(
        "service_scan_scope",
        default="top1000",
        choices=[
            ("comuni", "circa 100 porte (nmap -F), rapida"),
            ("top1000", "le 1000 porte più comuni (default di nmap)"),
            ("tutte", "tutte le 65535 porte (nmap -p-), lenta"),
        ],
        help="Quante porte TCP esamina il service discovery (nmap -sV).",
    ),
]

# Sezione [database] (ADR 0001).
database_group = cfg.OptGroup("database", title="Opzioni del database")
database_opts = [
    # Il database è MySQL, raggiunto con il driver PyMySQL (ADR 0001).
    cfg.StrOpt(
        "connection",
        default="mysql+pymysql://root@127.0.0.1/recon_stack",
        secret=True,
        help="Indirizzo del database (SQLAlchemy). Su DevStack il plugin ci "
             "mette utente, password e host. Forma: "
             "mysql+pymysql://utente:password@host/recon_stack.",
    ),
]

CONF.register_opts(default_opts)
CONF.register_group(database_group)
CONF.register_opts(database_opts, group=database_group)
CONF.register_group(scanner_group)
CONF.register_opts(scanner_opts, group=scanner_group)


def list_opts():
    """Elenco di tutte le opzioni, per oslo-config-generator (registrato in setup.cfg)."""
    return [
        (None, default_opts),
        (database_group, database_opts),
        (scanner_group, scanner_opts),
    ]


def load(argv=None):
    """Legge la configurazione e prepara i log.

    argv: argomenti da riga di comando (es. ["--config-file", "x.conf"]); None
    come dentro uwsgi.
    """
    CONF(argv if argv is not None else [], project="recon-stack")
    logging.basicConfig(
        level=logging.DEBUG if CONF.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Le librerie di terze parti sono rumorose a INFO/DEBUG (ogni richiesta HTTP,
    # token, plugin): le teniamo a WARNING, così nel terminale si legge il nostro.
    for noisy in ("keystoneauth", "stevedore", "urllib3", "requests",
                  "openstack", "keystonemiddleware", "oslo_policy",
                  "oslo_concurrency"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # Il demone privsep rigira come WARNING l'avviso di deprecazione di eventlet
    # a ogni scansione: lo alziamo a ERROR (un problema vero emerge comunque).
    for privsep_log in ("oslo.privsep", "oslo_privsep"):
        logging.getLogger(privsep_log).setLevel(logging.ERROR)
