# Chi ha fatto la richiesta, e se può chiedere una scansione (ADR 0002). A dire
# "chi sei" è Keystone: keystonemiddleware valida il token e aggiunge alla
# richiesta le intestazioni con l'identità (X-User-Id, X-Roles, ...); qui le
# leggiamo e controlliamo il ruolo. Il modulo non dipende da Flask (riceve le
# intestazioni come dizionario), così si prova nei test senza richieste HTTP.
# Le intestazioni sono affidabili solo perché keystonemiddleware, nella pipeline
# di uwsgi, le riscrive a ogni richiesta. Con "flask run" (sviluppo locale) il
# middleware non c'è e chiunque potrebbe inviarle: quella modalità è solo locale.

import dataclasses

IDENTITY_CONFIRMED = "Confirmed"  # X-Identity-Status quando il token è valido
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
    project_id: str | None = None
    roles: tuple[str, ...] = ()

    @property
    def is_admin(self):
        return ADMIN_ROLE in self.roles

    @classmethod
    def from_headers(cls, headers):
        """Costruisce il contesto dalle intestazioni di keystonemiddleware
        (un dizionario o request.headers di Flask)."""
        # X-Roles è una lista separata da virgole, es. "admin,member,reader".
        raw_roles = headers.get("X-Roles") or ""
        roles = tuple(r.strip() for r in raw_roles.split(",") if r.strip())

        return cls(
            authenticated=headers.get("X-Identity-Status") == IDENTITY_CONFIRMED,
            user_id=headers.get("X-User-Id"),
            project_id=headers.get("X-Project-Id"),
            roles=roles,
        )

    def require_admin(self):
        """Lascia passare solo un chiamante autenticato e admin.

        Solleva NotAuthenticated o NotAuthorized; chi chiama le traduce in
        401/403.
        """
        if not self.authenticated:
            raise NotAuthenticated("token Keystone assente o non valido")
        if not self.is_admin:
            raise NotAuthorized(f"ruolo '{ADMIN_ROLE}' richiesto")
