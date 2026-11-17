# URL del pannello "Host" (sotto /dashboard/recon/hosts/). Il name= di ogni
# percorso è quello usato nei link, es. "horizon:recon:hosts:detail".

from django.urls import re_path

from recon_stack.dashboard.recon.hosts import views

# Il dettaglio accetta solo un UUID: "hosts" è anche lo slug del pannello
# predefinito, montato alla radice, e un [^/]+ generico lo prenderebbe per un id.
ID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

urlpatterns = [
    re_path(r"^$", views.IndexView.as_view(), name="index"),
    re_path(rf"^(?P<host_id>{ID})/$", views.DetailView.as_view(), name="detail"),
]
