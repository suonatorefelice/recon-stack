# Opzioni di configurazione del servizio.
#
# Usiamo oslo.config, la libreria con cui tutti i componenti OpenStack leggono
# i propri file .conf (ADR 0008). Ogni opzione è dichiarata qui una sola volta,
# con tipo, valore predefinito e spiegazione; il resto del codice la legge da
# CONF, ad esempio CONF.scanner.heartbeat_interval.
#
# Il file si chiama recon-stack.conf. Se non gli si indica un percorso,
# oslo.config lo cerca da solo in ~/.recon-stack/, ~/, /etc/recon-stack/ e /etc/:
# in DevStack lo scrive il plugin in /etc/recon-stack/; sul Mac, durante lo
# sviluppo, di solito non c'è e valgono i valori predefiniti.
#
# Le opzioni si aggiungono man mano che uno step le usa (docs/piano.md).

import logging

from oslo_config import cfg

CONF = cfg.CONF

# Opzioni generali, sezione [DEFAULT] del file.
default_opts = [
    cfg.BoolOpt(
        "debug",
        default=False,
        help="Scrive nei log anche i messaggi di dettaglio (livello DEBUG).",
    ),
]

# Sezione [api]: il processo recon-api.
api_group = cfg.OptGroup("api", title="Opzioni della API REST e della dashboard")
api_opts = [
    cfg.PortOpt(
        "port",
        default=5238,
        help="Porta TCP su cui ascolta recon-api. In DevStack la usa uwsgi; "
             "sul Mac la usa il server di sviluppo di Flask.",
    ),
]

# Sezione [scanner]: il processo recon-scanner (ADR 0004).
scanner_group = cfg.OptGroup("scanner", title="Opzioni del processo recon-scanner")
scanner_opts = [
    cfg.IntOpt(
        "heartbeat_interval",
        default=60,
        min=5,
        help="Ogni quanti secondi recon-scanner scrive nel log che è attivo. "
             "Serve a verificare che il processo giri anche prima che esegua "
             "scansioni vere.",
    ),
    cfg.StrOpt(
        "cloud",
        default="devstack-admin",
        help="Nome del cloud da usare in /etc/openstack/clouds.yaml per "
             "leggere l'inventario da Nova e Neutron (ADR 0003). In DevStack "
             "il profilo 'devstack-admin' ha il ruolo admin, necessario per "
             "vedere le risorse di tutti i progetti.",
    ),
    cfg.IntOpt(
        "max_perimeter_addresses",
        default=65536,
        min=1,
        help="Numero massimo di indirizzi interni che un perimetro può avere "
             "(ADR 0005). Oltre questa soglia la scansione non parte: serve a "
             "evitare scansioni interminabili su subnet molto grandi (es. /16).",
    ),
    cfg.IntOpt(
        "min_scan_interval",
        default=60,
        min=0,
        help="Secondi minimi fra due scansioni avviate dello stesso progetto "
             "(limite di frequenza, Step 5). Una richiesta che arriva prima "
             "viene rifiutata e registrata nel log. 0 disattiva il limite.",
    ),
    cfg.StrOpt(
        "network_driver",
        default="ovn",
        choices=["ovn", "ovs"],
        help="Driver di rete di Neutron in uso sul nodo (ADR 0006): decide il "
             "nome delle network namespace in cui la scansione entra. 'ovn' "
             "(predefinito in DevStack recenti) usa ovnmeta-<id rete>; 'ovs' "
             "usa qdhcp-<id rete>. Si verifica sul nodo con 'sudo ip netns list'.",
    ),
    cfg.StrOpt(
        "service_scan_scope",
        default="top1000",
        choices=["comuni", "top1000", "tutte"],
        help="Quante porte TCP esaminare col service discovery (nmap -sV, "
             "Step 7): decide quanto a fondo va la scansione. 'comuni' = le "
             "circa 100 porte più comuni (nmap -F), rapidissima; 'top1000' = "
             "le 1000 porte più comuni (default di nmap), buon compromesso; "
             "'tutte' = tutte le 65535 porte (nmap -p-), copertura totale ma "
             "molto più lenta. La parola scelta viene tradotta in opzioni nmap "
             "dentro il demone privilegiato (privsep/discovery.py): dal confine "
             "privilegiato non passano mai opzioni nmap libere.",
    ),
]

# Sezione [database] (ADR 0001).
database_group = cfg.OptGroup("database", title="Opzioni del database")
database_opts = [
    cfg.StrOpt(
        "connection",
        default="sqlite:///recon-stack.sqlite",
        secret=True,
        help="Indirizzo del database nel formato di SQLAlchemy. Il valore "
             "predefinito è un file SQLite nella cartella corrente, comodo "
             "durante lo sviluppo; in DevStack il plugin indica un file in "
             "$DATA_DIR/recon-stack/. Per MySQL: "
             "mysql+pymysql://utente:password@host/recon_stack",
    ),
    cfg.IntOpt(
        "busy_timeout",
        default=5000,
        min=0,
        help="Solo SQLite: per quanti millisecondi chi deve scrivere aspetta "
             "che finisca la scrittura di un altro processo, prima di "
             "rinunciare con un errore.",
    ),
]

CONF.register_opts(default_opts)
CONF.register_group(database_group)
CONF.register_opts(database_opts, group=database_group)
CONF.register_group(api_group)
CONF.register_opts(api_opts, group=api_group)
CONF.register_group(scanner_group)
CONF.register_opts(scanner_opts, group=scanner_group)


def list_opts():
    """Elenco di tutte le opzioni, per oslo-config-generator.

    Lo strumento oslo-config-generator chiama questa funzione (è registrata in
    setup.cfg) e produce un file di esempio con tutte le opzioni commentate.
    """
    return [
        (None, default_opts),
        (database_group, database_opts),
        (api_group, api_opts),
        (scanner_group, scanner_opts),
    ]


def load(argv=None):
    """Legge la configurazione e prepara i log.

    argv sono gli argomenti da riga di comando (es. ["--config-file", "x.conf"]);
    None vuol dire "nessuno", come quando il codice gira dentro uwsgi.
    """
    CONF(argv if argv is not None else [], project="recon-stack")
    logging.basicConfig(
        level=logging.DEBUG if CONF.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
