# Gli indirizzi del pannello "Riepilogo": solo la pagina principale.
#
# Il Riepilogo non ha pagine di dettaglio proprie (i link portano al dettaglio
# scansione, in un altro pannello), quindi c'è un solo percorso: la radice.

from django.urls import re_path

from recon_stack.dashboard.recon.overview import views

urlpatterns = [
    re_path(r"^$", views.IndexView.as_view(), name="index"),
]
