# Installa, configura e avvia Recon-Stack dentro DevStack (ADR 0009).
#
# DevStack esegue questo file più volte durante stack.sh, unstack.sh e
# clean.sh, passando due parole: $1 dice cosa sta facendo (stack, unstack,
# clean), $2 a che punto è (install, post-config, extra). In fondo al file
# c'è lo smistamento: per ogni momento si chiamano le funzioni giuste.
#
# Le funzioni usate qui senza definirle (setup_develop, install_package,
# iniset, run_process, ...) sono fornite da DevStack. Le variabili RECON_*
# sono definite in devstack/settings.

# Riduce il rumore nel log di stack.sh: DevStack di solito stampa ogni
# comando eseguito (xtrace); lo spegniamo dentro il plugin e lo ripristiniamo
# com'era alla fine del file.
_XTRACE_RECON=$(set +o | grep xtrace)
set +o xtrace

# --- stack install: installazione dei programmi ------------------------------

function install_recon_stack {
    # Installa il pacchetto Python in modalità "sviluppo": il codice resta in
    # $RECON_DIR e una modifica ai file si vede al riavvio del servizio,
    # senza reinstallare. setup_develop installa anche requirements.txt.
    setup_develop $RECON_DIR

    # Programmi di sistema (come "apt install"): nmap per le scansioni.
    install_package nmap
}

# --- stack post-config: configurazione e registrazione in Keystone ----------

function configure_recon_stack {
    # Cartella della configurazione, di proprietà dell'utente di DevStack
    # ($STACK_USER), che è anche l'utente con cui girano i processi.
    sudo install -d -o $STACK_USER $RECON_CONF_DIR
    rm -f $RECON_CONF

    # iniset scrive "opzione = valore" nella sezione indicata di un file .ini.
    # $ENABLE_DEBUG_LOG_LEVEL è l'impostazione di DevStack per i log di debug.
    iniset $RECON_CONF DEFAULT debug $ENABLE_DEBUG_LOG_LEVEL

    # Database MySQL (ADR 0001). recreate_database è un aiuto di DevStack che
    # crea (ricreandolo da zero se c'era già) un database vuoto sul server
    # MySQL condiviso. database_connection_url costruisce l'indirizzo completo
    # in formato SQLAlchemy, driver e credenziali comprese
    # (mysql+pymysql://.../recon_stack): così non scriviamo utente e password a
    # mano e seguiamo le impostazioni di DevStack.
    recreate_database $RECON_DB_NAME
    iniset $RECON_CONF database connection "$(database_connection_url $RECON_DB_NAME)"

    # Configurazione di uwsgi. Il quarto argomento è l'indirizzo su cui
    # ascoltare: passandolo, uwsgi risponde direttamente sulla porta 5238
    # invece di stare dietro Apache (ADR 0008). Il terzo, il percorso sotto
    # Apache, in questo caso non serve.
    write_uwsgi_config "$RECON_UWSGI_CONF" "$RECON_UWSGI" "" "0.0.0.0:$RECON_API_PORT" "recon-api"

    # Un solo processo uwsgi con i thread attivi (ADR 0013, ADR 0008): un solo
    # processo significa un solo scheduler APScheduler, quindi niente scansioni
    # duplicate; i thread servono per le scansioni lanciate in background da
    # POST /v1/scans e per lo scheduler stesso.
    iniset "$RECON_UWSGI_CONF" uwsgi processes 1
    iniset "$RECON_UWSGI_CONF" uwsgi enable-threads true
    # Con lazy-apps uwsgi importa l'app DENTRO il worker, non nel master (senza,
    # il worker nasce da fork e i thread del master non vengono ereditati).
    # Così lo scheduler APScheduler e fail_orphan_scans girano nel processo che
    # serve le richieste; con processes=1 resta un solo scheduler.
    iniset "$RECON_UWSGI_CONF" uwsgi lazy-apps true

    configure_recon_stack_privsep
}

function configure_recon_stack_privsep {
    # Il demone privilegiato di oslo.privsep (ADR 0007) esegue le sole operazioni
    # che richiedono root: entrare nelle network namespace di Neutron per l'host
    # discovery (le capability da sole non bastano per `ip netns exec` su OVN,
    # ADR 0013). oslo.privsep lo avvia con "sudo privsep-helper": qui
    # diciamo a privsep quale comando usare e diamo allo $STACK_USER (l'utente non
    # privilegiato con cui gira il server) il permesso di lanciarlo senza
    # password. È l'unico comando che gli concediamo via sudo. Il server resta uno
    # solo: privsep è un suo figlio privilegiato, non un servizio a sé.
    local helper
    helper="$(get_python_exec_prefix)/privsep-helper"
    iniset $RECON_CONF privsep helper_command "sudo $helper --config-file $RECON_CONF"

    local sudoers=/etc/sudoers.d/recon-stack-privsep
    echo "$STACK_USER ALL=(root) NOPASSWD: $helper *" | sudo tee $sudoers >/dev/null
    sudo chmod 440 $sudoers
}

function init_recon_stack {
    # Crea lo schema (le tabelle, dai modelli) in un colpo solo; ripetibile, le
    # tabelle già presenti restano (recon_stack/cmd/dbsync.py).
    $(get_python_exec_prefix)/recon-stack-dbsync --config-file $RECON_CONF
}

function create_recon_stack_accounts {
    # Registra il servizio nel catalogo di Keystone, così compare in
    # "openstack catalog list" e i client trovano il suo indirizzo da soli.
    # Le due funzioni sono ripetibili: se servizio ed endpoint esistono già,
    # non li duplicano.
    local service
    service=$(get_or_create_service recon-stack $RECON_SERVICE_TYPE \
        "Recon-Stack: service discovery senza agenti")
    get_or_create_endpoint $service "$REGION_NAME" \
        "$SERVICE_PROTOCOL://$SERVICE_HOST:$RECON_API_PORT"

    # Utente di servizio per keystonemiddleware (ADR 0002): con questo utente il
    # middleware parla con Keystone per validare i token in arrivo. Lo crea
    # DevStack nel progetto di servizio, con la password standard SERVICE_PASSWORD.
    create_service_user "recon-stack"

    # Scrive la sezione [keystone_authtoken] in recon-stack.conf (indirizzo di
    # Keystone, utente di servizio, password): la riempie DevStack. Il nostro
    # codice la legge tramite keystonemiddleware.
    configure_keystone_authtoken_middleware $RECON_CONF recon-stack
}

# --- stack post-config: dashboard Horizon (ADR 0010) -------------------------

function install_recon_dashboard {
    # Aggiunge i nostri pannelli a Horizon, solo se Horizon è attivo qui.
    is_service_enabled horizon || return 0
    echo_summary "Installazione del plugin Horizon di Recon-Stack"

    # Horizon carica i file "enabled" dalla sua cartella local/enabled: ci
    # copiamo i nostri (settings registra la cartella sorgente). Solo i file
    # numerati come _5000_recon.py: il pacchetto ha anche un __init__.py.
    local dst="$HORIZON_DIR/openstack_dashboard/local/enabled"
    cp $RECON_DASHBOARD_ENABLED_SRC/_[0-9]*.py "$dst/"

    # Raccoglie i file statici e riavvia Horizon, così i pannelli compaiono.
    python "$HORIZON_DIR/manage.py" collectstatic --noinput >/dev/null 2>&1 || true
    python "$HORIZON_DIR/manage.py" compress --force >/dev/null 2>&1 || true
    restart_apache_server
}

function cleanup_recon_dashboard {
    is_service_enabled horizon || return 0
    sudo rm -f "$HORIZON_DIR/openstack_dashboard/local/enabled"/_5000_recon.py
}

# --- stack extra: avvio dei processi -----------------------------------------

function start_recon_stack {
    # run_process crea il servizio systemd devstack@<nome> e lo avvia.
    # Per recon-api il comando è uwsgi con il file scritto in configure. È l'unico
    # processo del servizio; il demone privsep lo avvia da sé alla prima scansione.
    run_process recon-api "$(which uwsgi) --procname-prefix recon-stack --ini $RECON_UWSGI_CONF"
}

# --- unstack e clean ---------------------------------------------------------

function stop_recon_stack {
    stop_process recon-api
}

function cleanup_recon_stack {
    # Toglie configurazione e database. Non serve togliere un sito Apache,
    # perché recon-api non ne ha uno: ascolta direttamente sulla sua porta.
    sudo rm -rf $RECON_CONF_DIR
    # Elimina il database MySQL del servizio. Le variabili DATABASE_* sono
    # quelle con cui DevStack ha configurato il server MySQL condiviso.
    mysql -u"$DATABASE_USER" -p"$DATABASE_PASSWORD" -h"$DATABASE_HOST" \
        -e "DROP DATABASE IF EXISTS $RECON_DB_NAME;" || true
    # E la regola sudo del demone di privsep.
    sudo rm -f /etc/sudoers.d/recon-stack-privsep
    # E i file "enabled" aggiunti a Horizon (ADR 0010).
    cleanup_recon_dashboard
}

# --- smistamento: cosa fare in ogni momento ----------------------------------

if is_service_enabled recon-api; then
    if [[ "$1" == "stack" && "$2" == "install" ]]; then
        echo_summary "Installazione di Recon-Stack"
        install_recon_stack

    elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
        # A questo punto Keystone è già avviato: si può registrare il servizio.
        echo_summary "Configurazione di Recon-Stack"
        configure_recon_stack
        init_recon_stack
        create_recon_stack_accounts
        install_recon_dashboard

    elif [[ "$1" == "stack" && "$2" == "extra" ]]; then
        echo_summary "Avvio di Recon-Stack"
        start_recon_stack
    fi

    if [[ "$1" == "unstack" ]]; then
        stop_recon_stack
    fi

    if [[ "$1" == "clean" ]]; then
        cleanup_recon_stack
    fi
fi

$_XTRACE_RECON
