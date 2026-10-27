# Report HTML e orchestrazione della generazione (step 12).
#
# render_html(data) produce il report come pagina HTML a sé stante (uno stile
# minimo incluso, così il file si apre e si stampa da solo). generate() mette
# insieme i pezzi: raccoglie i dati (builder), eventualmente li rende anonimi
# (redaction), costruisce la mappa (topology) e scrive i file su disco.
#
# Il PDF è facoltativo: se è installato weasyprint lo produciamo dall'HTML,
# altrimenti lo si ottiene aprendo l'HTML e stampando su PDF dal browser. Non
# aggiungiamo weasyprint fra le dipendenze obbligatorie: è pesante e il report
# HTML, con la mappa dentro, è già completo.

import logging
import os

import jinja2

from recon_stack.report import builder
from recon_stack.report import topology

LOG = logging.getLogger(__name__)

_TEMPLATE = """<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<title>Report Recon-Stack{% if data.redacted %} (condivisibile){% endif %}</title>
<style>
  body { font-family: Helvetica, Arial, sans-serif; margin: 2em; color: #222; }
  h1, h2 { color: #1a3a5a; }
  table { border-collapse: collapse; margin: 1em 0; width: 100%; }
  th, td { border: 1px solid #ccc; padding: 4px 8px; text-align: left;
           font-size: 0.9em; vertical-align: top; }
  th { background: #f0f4f8; }
  .sev-high { color: #a00; font-weight: bold; }
  .sev-medium { color: #c66a00; }
  .sev-low { color: #666; }
  .sev-info { color: #06c; }
  .map { margin: 1em 0; }
  .note { color: #666; font-size: 0.85em; }
</style>
</head>
<body>
<h1>Report Recon-Stack{% if data.redacted %} — versione condivisibile{% endif %}</h1>
{% if data.redacted %}
<p class="note">Indirizzi, nomi e identificativi reali sono stati sostituiti da
pseudonimi coerenti: questa versione si può condividere fuori dal laboratorio.</p>
{% endif %}

<h2>Scansione</h2>
<table>
  <tr><th>Progetto</th><td>{{ data.scan.project_id }}</td></tr>
  <tr><th>Stato</th><td>{{ data.scan.status }}</td></tr>
  <tr><th>Creata</th><td>{{ data.scan.created_at or "—" }}</td></tr>
  <tr><th>Conclusa</th><td>{{ data.scan.finished_at or "—" }}</td></tr>
</table>
<p>
  Host: {{ data.summary.hosts_total }}
  (censiti {{ data.summary.hosts_by_classification.known }},
   sconosciuti {{ data.summary.hosts_by_classification.unknown }},
   assenti {{ data.summary.hosts_by_classification.absent }}).
  Segnalazioni: {{ data.summary.findings_total }}.
</p>

{% if svg %}
<h2>Mappa della topologia</h2>
<div class="map">{{ svg|safe }}</div>
{% endif %}

<h2>Esposizione</h2>
{% if data.findings %}
<table>
  <tr><th>Gravità</th><th>Tipo</th><th>Indirizzo</th><th>Porta</th><th>Descrizione</th></tr>
  {% for f in data.findings %}
  <tr>
    <td class="sev-{{ f.severity }}">{{ f.severity }}</td>
    <td>{{ f.type }}</td>
    <td>{{ f.ip_address or "—" }}</td>
    <td>{% if f.port_number %}{{ f.port_number }}/{{ f.protocol }}{% else %}—{% endif %}</td>
    <td>{{ f.message }}</td>
  </tr>
  {% endfor %}
</table>
{% else %}
<p>Nessuna segnalazione.</p>
{% endif %}

<h2>Host e servizi</h2>
<table>
  <tr><th>Indirizzo</th><th>Classificazione</th><th>VM</th>
      <th>Servizi (interni)</th><th>Servizi (esterni)</th></tr>
  {% for h in data.hosts %}
  <tr>
    <td>{{ h.ip_address }}</td>
    <td>{{ h.classification }}</td>
    <td>{{ h.server_name or "—" }}</td>
    <td>{% for s in h.services_internal %}{{ s.port_number }}/{{ s.protocol }}
        {{ s.name or "" }} {{ s.product or "" }} {{ s.version or "" }}<br>
        {% else %}—{% endfor %}</td>
    <td>{% for s in h.services_external %}{{ s.port_number }}/{{ s.protocol }}
        {{ s.name or "" }}<br>{% else %}—{% endfor %}</td>
  </tr>
  {% endfor %}
</table>
</body>
</html>
"""


def render_html(data, svg=None):
    """Costruisce il report HTML dai dati (e, se c'è, dalla mappa SVG)."""
    template = jinja2.Template(_TEMPLATE, autoescape=True)
    return template.render(data=data, svg=svg)


def _write_pdf(html, pdf_path):
    """Prova a scrivere un PDF dall'HTML con weasyprint; dice se c'è riuscito."""
    try:
        import weasyprint
    except ImportError:
        LOG.warning("weasyprint non è installato: salto il PDF (apri l'HTML e "
                    "stampa su PDF dal browser)")
        return False
    weasyprint.HTML(string=html).write_pdf(pdf_path)
    LOG.info("report PDF scritto in %s", pdf_path)
    return True


def generate(scan_id, output_dir=".", redacted=False, pdf=False):
    """Genera il report di una scansione e restituisce i percorsi dei file scritti.

    Scrive report.html (o report-condivisibile.html con la redaction) nella
    cartella indicata, incorporando la mappa della topologia se `dot` è
    disponibile. Con pdf=True prova anche a scrivere il PDF. Restituisce None se
    la scansione non esiste.
    """
    data = builder.gather(scan_id)
    if data is None:
        return None
    if redacted:
        data = builder.redact(data)

    dot = topology.build_dot(data)
    svg = topology.render_svg_text(dot)
    if svg is None:
        LOG.warning("Graphviz ('dot') non disponibile: report senza mappa")

    html = render_html(data, svg=svg)

    os.makedirs(output_dir, exist_ok=True)
    base = "report-condivisibile" if redacted else "report"
    written = {}

    html_path = os.path.join(output_dir, f"{base}.html")
    with open(html_path, "w", encoding="utf-8") as out:
        out.write(html)
    written["html"] = html_path

    # Salviamo anche il DOT: è utile per rigenerare la mappa a mano se serve.
    dot_path = os.path.join(output_dir, f"{base}.dot")
    with open(dot_path, "w", encoding="utf-8") as out:
        out.write(dot)
    written["dot"] = dot_path

    if pdf:
        pdf_path = os.path.join(output_dir, f"{base}.pdf")
        if _write_pdf(html, pdf_path):
            written["pdf"] = pdf_path

    return written
