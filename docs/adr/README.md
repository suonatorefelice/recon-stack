# Decisioni di architettura (ADR)

Un ADR (*Architecture Decision Record*) registra una scelta di forma del progetto: il problema, la decisione, le alternative scartate con il motivo, le conseguenze accettate e le fonti. Un ADR non si riscrive quando la decisione cambia: se ne scrive uno nuovo che lo sostituisce.

| N. | Decisione |
| --- | --- |
| [0001](0001-database-sqlite.md) | Database SQLite (WAL) con SQLAlchemy e migrazioni Alembic |
| [0002](0002-autenticazione-keystone.md) | Autenticazione con token Keystone; scansioni solo con ruolo admin |
| [0003](0003-scoperta-senza-agenti.md) | Scoperta senza agenti, scansione dall'esterno delle VM |
| [0004](0004-scheduler-separato.md) | Scheduler in un processo separato dal server web |
| [0005](0005-perimetro-da-neutron.md) | Perimetro dalle subnet Neutron, ricalcolato a ogni scansione |
| [0006](0006-vista-interna-namespace.md) | Vista interna dalle network namespace di Neutron |
| [0007](0007-privilegi-oslo-privsep.md) | Separazione dei privilegi con oslo.privsep |
| [0008](0008-servizio-stile-openstack.md) | Flask + uwsgi sulla porta 5238, registrato nel catalogo Keystone |
| [0009](0009-plugin-devstack.md) | Plugin DevStack `recon-stack` |
