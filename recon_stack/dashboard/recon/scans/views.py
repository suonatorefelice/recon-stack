# Le viste del pannello "Scansioni": elenco, dettaglio e avvio.

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _
from django.views import generic
from horizon import exceptions
from horizon import forms as horizon_forms
from horizon import tables as horizon_tables

from recon_stack.dashboard import api
from recon_stack.dashboard.recon import labels
from recon_stack.dashboard.recon.scans import forms as scans_forms
from recon_stack.dashboard.recon.scans import tables as scans_tables
from recon_stack import vocab


class IndexView(horizon_tables.DataTableView):
    table_class = scans_tables.ScansTable
    template_name = "recon/scans/index.html"
    page_title = _("Scansioni")

    def get_data(self):
        try:
            scans = api.reconclient(self.request).list_scans()
        except Exception:
            exceptions.handle(self.request,
                              _("Impossibile leggere le scansioni dalla API."))
            return []
        return [api.wrap(s) for s in scans]


class DetailView(generic.TemplateView):
    template_name = "recon/scans/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Ultima briciola del breadcrumb (Horizon usa page_title): l'id
        # accorciato, preso dall'URL così c'è anche se l'API non risponde.
        context["page_title"] = labels.short_uuid(self.kwargs["scan_id"])
        client = api.reconclient(self.request)
        try:
            scan = client.get_scan(self.kwargs["scan_id"])
        except Exception:
            exceptions.handle(self.request,
                              _("Impossibile leggere la scansione dalla API."))
            scan = {}
        # I template Django non chiamano le funzioni di labels: prepariamo qui i
        # campi pronti (etichette italiane, UUID accorciati, date brevi).
        if scan:
            scan = labels.enrich_scan(scan)
            # Fase leggibile e flag "in corso": il template mostra la rotella e
            # si auto-ricarica finché la scansione non è finita.
            scan["phase_text"] = labels.phase_text(scan.get("phase"))
            scan["in_corso"] = scan.get("status") in (
                vocab.SCAN_PENDING, vocab.SCAN_RUNNING)
        context["scan"] = api.wrap(scan) if scan else None
        # Confronto con la scansione precedente; se fallisce non blocca la pagina.
        try:
            context["diff"] = client.get_scan_diff(self.kwargs["scan_id"])
        except Exception:
            context["diff"] = None
        # Segnalazioni, tradotte per il template; se falliscono mostriamo
        # comunque il resto.
        try:
            raw = client.get_scan_exposure(self.kwargs["scan_id"])
            context["findings"] = [api.wrap(labels.enrich_finding(f))
                                   for f in raw]
        except Exception:
            context["findings"] = None
        return context


class ReportView(generic.TemplateView):
    """Report stampabile di una scansione, da stampare (o salvare in PDF) dal
    browser. Il template non estende base.html: niente menu e barre di Horizon,
    solo il contenuto e il suo stile di stampa. I dati vengono dalle rotte /v1
    (scansione, segnalazioni, host e servizi della scansione)."""

    template_name = "recon/scans/report.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        scan_id = self.kwargs["scan_id"]
        client = api.reconclient(self.request)
        try:
            scan = client.get_scan(scan_id)
            findings = client.get_scan_exposure(scan_id)
            hosts = client.list_hosts(scan_id=scan_id)
            services = client.list_services(scan_id=scan_id)
        except Exception:
            exceptions.handle(self.request,
                              _("Impossibile leggere il report dalla API."))
            context["error"] = True
            return context

        # Servizi per host, divisi in vista interna ed esterna.
        internal, external = {}, {}
        for s in services:
            dest = external if s.get("view") == "external" else internal
            dest.setdefault(s["host_id"], []).append(s)

        host_rows = []
        by_class = {"known": 0, "unknown": 0, "absent": 0}
        for h in hosts:
            by_class[h["classification"]] = by_class.get(
                h["classification"], 0) + 1
            host_rows.append({
                "ip_address": h["ip_address"],
                "classification_it": labels.classification_label(
                    h["classification"]),
                "server_name": h.get("server_name"),
                "services_internal": sorted(
                    internal.get(h["id"], []), key=lambda s: s["port_number"]),
                "services_external": sorted(
                    external.get(h["id"], []), key=lambda s: s["port_number"]),
            })

        context["scan"] = labels.enrich_scan(scan)
        context["findings"] = [labels.enrich_finding(f) for f in findings]
        context["hosts"] = host_rows
        context["summary"] = {
            "hosts_total": len(hosts),
            "known": by_class["known"],
            "unknown": by_class["unknown"],
            "absent": by_class["absent"],
            "findings_total": len(findings),
        }
        return context


class StartScanView(horizon_forms.ModalFormView):
    form_class = scans_forms.StartScanForm
    template_name = "recon/scans/start.html"
    submit_url = reverse_lazy("horizon:recon:scans:start")
    success_url = reverse_lazy("horizon:recon:scans:index")
    modal_header = _("Avvia scansione")
    page_title = _("Avvia scansione")
