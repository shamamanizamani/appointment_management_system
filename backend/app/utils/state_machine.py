from app.core.errors import AppError


class InvalidTransition(AppError):
    def __init__(self, entity: str, frm: str, to: str):
        # Shown to end users, e.g. "This appointment is already cancelled, so that isn't possible."
        status = str(frm).replace("_", " ")
        super().__init__(
            409, "INVALID_TRANSITION", f"This {entity} is already {status}, so that isn't possible."
        )


def check_transition(allowed: dict, entity: str, frm: str, to: str) -> None:
    """CLAUDE.md §6: only moves listed in the transition table are allowed."""
    if to not in allowed.get(frm, ()):
        raise InvalidTransition(entity, frm, to)
