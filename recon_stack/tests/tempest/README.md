# Test tempest di Recon-Stack

Questi test provano il servizio su un DevStack vero, dall'esterno, via API REST
(step 13 di `docs/piano.md`). **Non girano sul Mac**: hanno bisogno di tempest e
di OpenStack. I test unitari, che girano senza OpenStack, stanno invece in
`recon_stack/tests/unit` e si eseguono con `tox -e py3`.

## Come si eseguono (sul nodo DevStack)

1. Installa il plugin Recon-Stack con DevStack (`enable_plugin recon-stack ...`)
   e crea il progetto demo:

   ```
   source /opt/stack/devstack/openrc admin admin
   bash demo/setup_demo.sh
   ```

2. Fai in modo che tempest veda il plugin. In un DevStack con tempest installato
   il pacchetto `recon_stack` è già nell'ambiente, quindi tempest scopre il
   plugin da solo (entry point `tempest.test_plugins` in `setup.cfg`). Verifica:

   ```
   cd /opt/stack/tempest
   tempest list-plugins        # deve comparire "recon_tests"
   ```

3. Esegui i test di Recon-Stack:

   ```
   tempest run --regex recon_stack.tests.tempest
   ```

## Opzioni

Nella sezione `[recon]` di `tempest.conf`:

- `enabled` (default `true`): se eseguire i test.
- `demo_project` (default `recon-demo`): il progetto da scansionare.
- `scan_timeout` (default `300`): secondi massimi di attesa perché una scansione
  finisca.

## Cosa prova

`test_scansione_completa_del_progetto_demo` ripercorre tutto il flusso: chiede
una scansione del progetto demo via `POST /v1/scans`, aspetta che lo scanner la
porti a `DONE`, poi controlla che ci siano host e almeno una segnalazione di
esposizione (il progetto demo contiene regole volutamente sbagliate, che devono
essere segnalate).
