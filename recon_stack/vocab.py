# Vocabolario condiviso: stringhe e costanti SENZA SQLAlchemy. Lo importano sia
# db/models.py sia la dashboard Horizon (dove SQLAlchemy non è installato), così
# la dashboard non tira dentro recon_stack.db.

# Stati di una scansione.
SCAN_PENDING = "PENDING"    # registrata, in attesa che il thread la esegua
SCAN_RUNNING = "RUNNING"    # in corso
SCAN_DONE = "DONE"          # completata
SCAN_FAILED = "FAILED"      # interrotta da un errore (motivo in "fault")
SCAN_STATUSES = (SCAN_PENDING, SCAN_RUNNING, SCAN_DONE, SCAN_FAILED)

# Chi ha originato la scansione.
TRIGGER_MANUAL = "manual"      # da un admin con POST /v1/scans
TRIGGER_PERIODIC = "periodic"  # dallo scheduler

# Fase di una scansione in corso, per l'avanzamento in dashboard ("... 3 di 6").
# L'ordine di SCAN_PHASES è l'ordine dei passi, la sua lunghezza è il "di 6".
# L'inventario viene prima del perimetro, che usa i floating IP già raccolti.
PHASE_INVENTORY = "inventory"
PHASE_PERIMETER = "perimeter"
PHASE_DISCOVERY = "discovery"
PHASE_SAVING = "saving"
PHASE_EXTERNAL = "external"
PHASE_EXPOSURE = "exposure"
SCAN_PHASES = (PHASE_INVENTORY, PHASE_PERIMETER, PHASE_DISCOVERY,
               PHASE_SAVING, PHASE_EXTERNAL, PHASE_EXPOSURE)

# Tipi di segnalazione di esposizione: incongruenze fra i servizi in
# ascolto e ciò che i security group permettono, o situazioni di rischio.
FINDING_USELESS_RULE = "useless_rule"            # regola che apre una porta senza servizio
FINDING_LATENT_SERVICE = "latent_service"        # servizio attivo non previsto da regole
FINDING_OVEREXPOSED = "overexposed"              # servizio aperto a qualunque indirizzo
FINDING_EXTERNALLY_REACHABLE = "externally_reachable"  # raggiungibile dal floating IP
FINDING_UNKNOWN_EXPOSED = "unknown_exposed"      # host non censito con porte aperte
FINDING_WASTED_FLOATING_IP = "wasted_floating_ip"  # floating IP senza servizi dietro
FINDING_EXTERNAL_ONLY = "external_only"          # visto da fuori ma non censito internamente
FINDING_NO_PORT_SECURITY = "no_port_security"    # porta senza port security

# device_owner delle porte Neutron che appartengono a una VM ("compute:nova",
# "compute:<zona>"); le altre sono porte di infrastruttura (router, metadati).
COMPUTE_OWNER_PREFIX = "compute:"

# Gravità di una segnalazione, dalla più alla meno urgente.
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"
SEVERITY_ORDER = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1,
                  SEVERITY_LOW: 2, SEVERITY_INFO: 3}
