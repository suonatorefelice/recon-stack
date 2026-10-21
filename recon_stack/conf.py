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
]

CONF.register_opts(default_opts)
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
