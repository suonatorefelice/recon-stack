# Test del servizio.
#   unit/     test unitari, senza OpenStack (tox -e py3); quelli sul database
#             vogliono un MySQL raggiungibile (vedi unit/conftest.py)
#   tempest/  test del percorso completo, su un DevStack vero
