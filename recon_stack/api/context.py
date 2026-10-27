# Chi ha fatto la richiesta, e se può chiedere una scansione (ADR 0002).
#
# Le scansioni sono operazioni delicate: si avviano solo con il ruolo admin.
# A dire "chi sei" è Keystone, non il nostro codice: keystonemiddleware valida
# il token del chiamante e, se è valido, aggiunge alla richiesta alcune
# intestazioni HTTP con l'identità (X-User-Id, X-Project-Id, X-Roles, ...).
# Noi ci limitiamo a leggerle e a controllare il ruolo.
#
# Questo modulo non dipende da Flask: riceve le intestazioni come un semplice
# dizionario. Così la logica si prova nei test senza costruire richieste HTTP,
# e l'app Flask (step 8) la userà passando request.headers.

import dataclasses

# Valore dell'intestazione X-Identity-Status quando il token è valido.
IDENTITY_CONFIRMED = "Confirmed"

# Ruolo necessario per avviare una scansione.
ADMIN_ROLE = "admin"


class NotAuthenticated(Exception):
    """La richiesta non porta un token Keystone valido."""


class NotAuthorized(Exception):
    """La richiesta è autenticata ma manca del ruolo richiesto."""


@dataclasses.dataclass
class RequestContext:
    """L'identità del chiamante, ricavata dalle intestazioni di Keystone."""

    authenticated: bool = False
    user_id: str | None = None
    user_name: str | None = None
    project_id: str | None = None
    project_name: str | None = None
    roles: tuple[str, ...] = ()

    @property
    def is_admin(self):
        return ADMIN_ROLE in self.roles

    @classmethod
    def from_headers(cls, headers):
        """Costruisce il contesto dalle intestazioni aggiunte da keystonemiddleware.

        headers è un dizionario (o request.headers di Flask). I nomi non fanno
        differenza fra maiuscole e minuscole in HTTP, ma qui li leggiamo con la
        forma standard; Flask li espone già così.
        """
        def get(name):
            return headers.get(name)

        # X-Roles è una lista separata da virgole, es. "admin,member,reader".
        raw_roles = get("X-Roles") or ""
        roles = tuple(r.strip() for r in raw_roles.split(",") if r.strip())

        return cls(
            authenticated=get("X-Identity-Status") == IDENTITY_CONFIRMED,
            user_id=get("X-User-Id"),
            user_name=get("X-User-Name"),
            project_id=get("X-Project-Id"),
            project_name=get("X-Project-Name"),
            roles=roles,
        )

    def require_admin(self):
        """Lascia passare solo un chiamante autenticato e con ruolo admin.

        Vale sia per avviare una scansione sia per leggere il catalogo via API
        (Step 8): Recon-Stack è uno strumento per chi amministra il cloud e i
        suoi dati sono inventari a livello di cloud (CLAUDE.md).

        Solleva NotAuthenticated o NotAuthorized: chi chiama le traduce nella
        risposta HTTP giusta (401 o 403) e, per le scansioni, registra comunque
        il tentativo nel log (Step 5).
        """
        if not self.authenticated:
            raise NotAuthenticated("token Keystone assente o non valido")
        if not self.is_admin:
            raise NotAuthorized(f"ruolo '{ADMIN_ROLE}' richiesto")
