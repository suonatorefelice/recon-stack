# Gli indirizzi del pannello "Servizi" (sotto /dashboard/recon/services/).

from django.urls import re_path

from recon_stack.dashboard.recon.services import views

urlpatterns = [
    re_path(r"^$", views.IndexView.as_view(), name="index"),
]
