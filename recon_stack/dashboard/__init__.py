# Plugin di Horizon: la dashboard web di Recon-Stack (ADR 0010).
#
# Non è una dashboard a sé: aggiunge dei pannelli alla dashboard ufficiale di
# OpenStack (Horizon), dove l'amministratore accede già con le sue credenziali.
# I pannelli non leggono il database: chiamano la nostra API REST /v1 (api/v1.py)
# usando il token Keystone dell'utente collegato a Horizon, quindi valgono le
# stesse regole di accesso della API (solo admin, ADR 0002).
#
#   api.py     costruisce il client verso /v1 a partire dalla richiesta Horizon
#   enabled/   i file che dicono a Horizon di caricare la dashboard e i pannelli
#   recon/     la dashboard Django vera e propria (dashboard, pannelli, viste)
