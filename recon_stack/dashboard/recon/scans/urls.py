# Gli indirizzi del pannello "Scansioni" (sotto /dashboard/recon/scans/).

from django.urls import re_path

# Gli identificativi del servizio sono UUID (db/models.py, new_id). Il dettaglio
# accetta solo quel formato, non "qualunque cosa senza barre": "hosts" è il
# pannello predefinito della dashboard, e Horizon monta i suoi indirizzi anche
# alla radice; con [^/]+ l'indirizzo /recon/hosts/ veniva letto come il
# dettaglio dell'host "hosts" (pagina vuota) e /recon/hosts/<id>/ dava 404
# (trovato nel test su DevStack).
ID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

from recon_stack.dashboard.recon.scans import views

urlpatterns = [
    re_path(r"^$", views.IndexView.as_view(), name="index"),
    re_path(r"^start/$", views.StartScanView.as_view(), name="start"),
    re_path(rf"^(?P<scan_id>{ID})/$", views.DetailView.as_view(), name="detail"),
]
