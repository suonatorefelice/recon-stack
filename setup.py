# Punto d'ingresso per l'installazione del pacchetto.
#
# Non contiene informazioni: con pbr (Python Build Reasonableness, lo strumento
# usato da tutti i componenti OpenStack) nome, versione, dipendenze e comandi
# stanno in setup.cfg. pbr ricava la versione dai tag git e le dipendenze da
# requirements.txt, così non vanno ripetute in due posti.
import setuptools

setuptools.setup(
    setup_requires=["pbr>=6.0.0"],
    pbr=True,
)
