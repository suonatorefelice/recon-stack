# Report e mappa della topologia (step 12).
#
# Questo pacchetto trasforma i risultati di una scansione (host, servizi,
# segnalazioni di esposizione) in due cose leggibili da una persona:
#   - una mappa della topologia in formato Graphviz (report/topology.py);
#   - un report HTML, con dentro la mappa (report/render.py).
#
# C'è anche una versione "con redaction" (report/builder.py), in cui indirizzi,
# nomi e identificativi reali sono sostituiti da pseudonimi coerenti: serve a
# condividere il report senza rivelare i dati veri del cloud.
#
# La raccolta dei dati (builder.gather) e la redaction non toccano la rete né
# richiedono Graphviz: leggono solo dal database e si provano da sole.
