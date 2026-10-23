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

    # Programmi di sistema (come "apt install"): nmap per le scansioni,
    # graphviz per la mappa della topologia (step 12).
    install_package nmap graphviz
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
    iniset $RECON_CONF api port $RECON_API_PORT

    # Database SQLite (ADR 0001). L'indirizzo ha quattro barre perché è
    # "sqlite:///" seguito da un percorso assoluto che inizia con "/".
    sudo install -d -o $STACK_USER $RECON_DATA_DIR
    iniset $RECON_CONF database connection "sqlite:///$RECON_DB_FILE"

    # Configurazione di uwsgi. Il quarto argomento è l'indirizzo su cui
    # ascoltare: passandolo, uwsgi risponde direttamente sulla porta 5238
    # invece di stare dietro Apache (ADR 0008). Il terzo, il percorso sotto
    # Apache, in questo caso non serve.
    write_uwsgi_config "$RECON_UWSGI_CONF" "$RECON_UWSGI" "" "0.0.0.0:$RECON_API_PORT" "recon-api"

    configure_recon_stack_privsep
}

function configure_recon_stack_privsep {
    # Il demone privilegiato di oslo.privsep (ADR 0007) esegue le operazioni
    # che richiedono root (entrare nelle network namespace per l'host
    # discovery). oslo.privsep lo avvia con "sudo privsep-helper": qui diciamo
    # a privsep quale comando usare e diamo allo $STACK_USER (l'utente non
    # privilegiato con cui girano i processi) il permesso di lanciarlo senza
    # password. È l'unico comando che gli concediamo via sudo.
    local helper
    helper="$(get_python_exec_prefix)/privsep-helper"
    iniset $RECON_CONF privsep helper_command "sudo $helper --config-file $RECON_CONF"

    local sudoers=/etc/sudoers.d/recon-stack-privsep
    echo "$STACK_USER ALL=(root) NOPASSWD: $helper *" | sudo tee $sudoers >/dev/null
    sudo chmod 440 $sudoers
}

function init_recon_stack {
    # Crea le tabelle, o le aggiorna se il database c'è già: il comando
    # applica solo le migrazioni che mancano (recon_stack/cmd/dbsync.py).
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
    # codice la legge tramite keystonemiddleware (recon_stack/api/middleware.py).
    configure_keystone_authtoken_middleware $RECON_CONF recon-stack
}

# --- stack extra: avvio dei processi -----------------------------------------

function start_recon_stack {
    # run_process crea il servizio systemd devstack@<nome> e lo avvia.
    # Per recon-api il comando è uwsgi con il file scritto in configure.
    run_process recon-api "$(which uwsgi) --procname-prefix recon-stack --ini $RECON_UWSGI_CONF"

    # recon-scanner è il comando installato da setup.cfg (console_scripts).
    # get_python_exec_prefix dice in quale cartella DevStack mette i comandi
    # dei pacchetti Python.
    run_process recon-scanner "$(get_python_exec_prefix)/recon-stack-scanner --config-file $RECON_CONF"
}

# --- unstack e clean ---------------------------------------------------------

function stop_recon_stack {
    stop_process recon-api
    stop_process recon-scanner
}

function cleanup_recon_stack {
    # Toglie configurazione e dati, compreso il database. Non serve togliere
    # un sito Apache, perché recon-api non ne ha uno: ascolta direttamente
    # sulla sua porta.
    sudo rm -rf $RECON_CONF_DIR $RECON_DATA_DIR
    # E la regola sudo del demone di privsep.
    sudo rm -f /etc/sudoers.d/recon-stack-privsep
}

# --- smistamento: cosa fare in ogni momento ----------------------------------

if is_service_enabled recon-api recon-scanner; then
    if [[ "$1" == "stack" && "$2" == "install" ]]; then
        echo_summary "Installazione di Recon-Stack"
        install_recon_stack

    elif [[ "$1" == "stack" && "$2" == "post-config" ]]; then
        # A questo punto Keystone è già avviato: si può registrare il servizio.
        echo_summary "Configurazione di Recon-Stack"
        configure_recon_stack
        init_recon_stack
        create_recon_stack_accounts

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
