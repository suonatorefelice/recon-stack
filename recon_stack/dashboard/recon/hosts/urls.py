# Gli indirizzi (URL) del pannello "Host".
#
# Horizon aggancia questi percorsi sotto /dashboard/recon/hosts/. Il nome di
# ogni percorso (name=...) è quello usato nei collegamenti, ad esempio
# "horizon:recon:hosts:detail" nella tabella.

from django.urls import re_path

from recon_stack.dashboard.recon.hosts import views

urlpatterns = [
    re_path(r"^$", views.IndexView.as_view(), name="index"),
    re_path(r"^(?P<host_id>[^/]+)/$", views.DetailView.as_view(), name="detail"),
]
