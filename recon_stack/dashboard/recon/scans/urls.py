# Gli indirizzi del pannello "Scansioni" (sotto /dashboard/recon/scans/).

from django.urls import re_path

from recon_stack.dashboard.recon.scans import views

urlpatterns = [
    re_path(r"^$", views.IndexView.as_view(), name="index"),
    re_path(r"^start/$", views.StartScanView.as_view(), name="start"),
    re_path(r"^(?P<scan_id>[^/]+)/$", views.DetailView.as_view(), name="detail"),
]
