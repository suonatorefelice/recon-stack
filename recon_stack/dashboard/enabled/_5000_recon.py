# Registra in Horizon la dashboard "recon" (ADR 0010).
#
# Questo file dice a Horizon: esiste una dashboard con slug "recon", il suo
# codice è nell'app Django recon_stack.dashboard.recon. Horizon la aggiunge al
# menu e carica i pannelli elencati nella classe della dashboard (dashboard.py).

# Slug della dashboard (compare nell'URL: /dashboard/recon/).
DASHBOARD = "recon"

# L'app Django che contiene la dashboard e i suoi pannelli. Horizon la aggiunge
# alle INSTALLED_APPS di Django, così ne trova viste, template e file statici.
ADD_INSTALLED_APPS = [
    "recon_stack.dashboard.recon",
]

# Fa cercare a Horizon i file statici (CSS/JS) dentro l'app, se ce ne sono.
AUTO_DISCOVER_STATIC_FILES = True
