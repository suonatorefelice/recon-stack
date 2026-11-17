# URL del pannello "Scansioni" (sotto /dashboard/recon/scans/).

from django.urls import re_path

from recon_stack.dashboard.recon.scans import views

# Il dettaglio accetta solo un UUID (vedi la stessa nota in hosts/urls.py).
ID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"

urlpatterns = [
    re_path(r"^$", views.IndexView.as_view(), name="index"),
    re_path(r"^start/$", views.StartScanView.as_view(), name="start"),
    re_path(rf"^(?P<scan_id>{ID})/$", views.DetailView.as_view(), name="detail"),
    re_path(rf"^(?P<scan_id>{ID})/report/$", views.ReportView.as_view(),
            name="report"),
]
