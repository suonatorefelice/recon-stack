# Plugin per l'OpenStackClient: i comandi "openstack recon ..." (Step 8).
#
# L'OpenStackClient (il comando `openstack`) è estendibile con plugin: un
# pacchetto dichiara, tramite entry point in setup.cfg, un proprio client e i
# propri comandi, e il comando `openstack` li scopre da solo. Qui aggiungiamo il
# gruppo di comandi `openstack recon ...` (host list, service list, scan start,
# ...) che parlano con la nostra API REST /v1 (api/v1.py).
#
#   plugin.py    aggancio dell'OpenStackClient (come costruire il client)
#   client.py    client HTTP minimale verso l'API /v1, usa la sessione Keystone
#   commands.py  i comandi veri e propri (classi cliff)
