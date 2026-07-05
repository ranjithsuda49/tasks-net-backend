from typing import Callable, Optional

from app.exceptions import ForbiddenError


def ensure_owner(current_user_id: Optional[str], owner_id: str, message: str) -> None:
    if current_user_id is not None and current_user_id != owner_id:
        raise ForbiddenError(message)


def ensure_owner_or_related(
    current_user_id: Optional[str],
    owner_id: str,
    is_related: Callable[[], bool],
    message: str,
) -> None:
    if current_user_id is None or current_user_id == owner_id:
        return
    if not is_related():
        raise ForbiddenError(message)
