# URL del pannello "Riepilogo": solo la pagina principale (nessun dettaglio proprio).

from django.urls import re_path

from recon_stack.dashboard.recon.overview import views

urlpatterns = [
    re_path(r"^$", views.IndexView.as_view(), name="index"),
]
