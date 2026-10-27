# Mappa della topologia in formato Graphviz (step 12).
#
# build_dot(data) costruisce il testo nel linguaggio DOT di Graphviz a partire
# dai dati del report (builder.gather): un nodo per ogni rete e un nodo per ogni
# host, collegati, con i servizi elencati dentro il nodo dell'host e un colore
# che ne indica la classificazione. Produrre il testo DOT non richiede Graphviz
# ed è facile da provare.
#
# render(dot, output_path, fmt) trasforma il DOT in un'immagine (SVG o PNG)
# chiamando il programma `dot` (lo installa il plugin DevStack). È separato dal
# build apposta: sul Mac, dove `dot` può mancare, si prova comunque build_dot.

import logging
import shutil
import subprocess

from recon_stack.db import models

LOG = logging.getLogger(__name__)

# Colore di ogni classificazione: verde censito, arancione sconosciuto (sospetto),
# grigio assente. Le tinte sono chiare per restare leggibili in un report stampato.
_CLASS_COLOR = {
    models.HOST_KNOWN: "#d5e8d4",
    models.HOST_UNKNOWN: "#ffe6cc",
    models.HOST_ABSENT: "#f0f0f0",
}


def _escape(text):
    """Mette al sicuro un testo dentro una stringa DOT fra virgolette."""
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


def _host_label(host):
    """Etichetta di un host: indirizzo, nome VM e servizi, una riga ciascuno."""
    righe = [host["ip_address"]]
    if host["server_name"]:
        righe.append(host["server_name"])
    for svc in host["services_internal"]:
        nome = svc["name"] or "?"
        righe.append(f"{svc['port_number']}/{svc['protocol']} {nome}")
    for svc in host["services_external"]:
        nome = svc["name"] or "?"
        righe.append(f"[est] {svc['port_number']}/{svc['protocol']} {nome}")
    # \l allinea a sinistra ogni riga in Graphviz.
    return "\\l".join(_escape(r) for r in righe) + "\\l"


def build_dot(data):
    """Costruisce il testo DOT della topologia a partire dai dati del report."""
    lines = ["digraph recon {", "  rankdir=LR;",
             '  node [shape=box, style="rounded,filled", fontname="Helvetica"];',
             '  edge [color="#999999"];']

    # Le reti: dalle subnet del perimetro, altrimenti dalle reti degli host.
    networks = {}
    for subnet in data["subnets"]:
        networks[subnet.get("network_id")] = subnet.get("cidr") or subnet.get(
            "network_id")
    for host in data["hosts"]:
        networks.setdefault(host["network_id"], host["network_id"])

    for net_id, label in networks.items():
        if net_id is None:
            continue
        lines.append(f'  "net_{_escape(net_id)}" '
                     f'[label="rete\\n{_escape(label)}", fillcolor="#dae8fc"];')

    # Gli host, collegati alla propria rete (se la conoscono).
    for i, host in enumerate(data["hosts"]):
        node = f"host_{i}"
        color = _CLASS_COLOR.get(host["classification"], "#ffffff")
        lines.append(f'  "{node}" [label="{_host_label(host)}", '
                     f'fillcolor="{color}"];')
        if host["network_id"] is not None:
            lines.append(f'  "net_{_escape(host["network_id"])}" -> "{node}";')

    lines.append("}")
    return "\n".join(lines)


def dot_available():
    """Dice se il programma `dot` di Graphviz è installato."""
    return shutil.which("dot") is not None


def render(dot, output_path, fmt="svg"):
    """Trasforma il DOT in un file immagine con `dot`; restituisce output_path.

    Solleva FileNotFoundError se `dot` non è installato: chi chiama decide se
    rinunciare alla mappa (il report HTML resta valido anche senza).
    """
    if not dot_available():
        raise FileNotFoundError(
            "il programma 'dot' di Graphviz non è installato: "
            "il plugin DevStack lo installa, sul Mac va aggiunto a parte")
    with open(output_path, "wb") as out:
        subprocess.run(["dot", f"-T{fmt}"], input=dot.encode("utf-8"),
                       stdout=out, check=True)
    LOG.info("mappa della topologia scritta in %s", output_path)
    return output_path


def render_svg_text(dot):
    """Restituisce l'SVG come testo, per incorporarlo nell'HTML (None se manca dot)."""
    if not dot_available():
        return None
    result = subprocess.run(["dot", "-Tsvg"], input=dot.encode("utf-8"),
                            stdout=subprocess.PIPE, check=True)
    return result.stdout.decode("utf-8")
