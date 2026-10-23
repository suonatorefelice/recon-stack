# Test del processo recon-scanner (recon_stack/cmd/scanner.py).
#
# Non avviamo lo scheduler, che resterebbe acceso per sempre: controlliamo
# che venga costruito con i compiti giusti.

from recon_stack import conf
from recon_stack.cmd import scanner


def test_lo_scheduler_ha_il_battito_con_l_intervallo_configurato():
    conf.load([])
    conf.CONF.set_override("heartbeat_interval", 15, group="scanner")
    job = scanner.build_scheduler().get_job("heartbeat")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 15
    assert job.max_instances == 1
