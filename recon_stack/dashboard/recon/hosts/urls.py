# Gli indirizzi (URL) del pannello "Host".
#
# Horizon aggancia questi percorsi sotto /dashboard/recon/hosts/. Il nome di
# ogni percorso (name=...) è quello usato nei collegamenti, ad esempio
# "horizon:recon:hosts:detail" nella tabella.

from django.urls import re_path

# Gli identificativi del servizio sono UUID (db/models.py, new_id). Il dettaglio
# accetta solo quel formato, non "qualunque cosa senza barre": "hosts" è il
# pannello predefinito della dashboard, e Horizon monta i suoi indirizzi anche
# alla radice; con [^/]+ l'indirizzo /recon/hosts/ veniva letto come il
# dettaglio dell'host "hosts" (pagina vuota) e /recon/hosts/<id>/ dava 404
# (trovato nel test su DevStack).
ID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

from recon_stack.dashboard.recon.hosts import views

urlpatterns = [
    re_path(r"^$", views.IndexView.as_view(), name="index"),
    re_path(rf"^(?P<host_id>{ID})/$", views.DetailView.as_view(), name="detail"),
]
