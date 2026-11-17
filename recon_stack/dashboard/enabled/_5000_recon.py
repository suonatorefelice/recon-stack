# Registra in Horizon la dashboard "recon" (ADR 0010): Horizon legge questo file,
# aggiunge la dashboard al menu e carica i suoi pannelli (dashboard.py).

DASHBOARD = "recon"  # slug nell'URL (/dashboard/recon/)

# L'app Django con la dashboard e i pannelli, aggiunta alle INSTALLED_APPS.
ADD_INSTALLED_APPS = [
    "recon_stack.dashboard.recon",
]

AUTO_DISCOVER_STATIC_FILES = True
