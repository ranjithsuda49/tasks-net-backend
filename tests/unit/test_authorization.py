import pytest

from app.exceptions import ForbiddenError
from app.services.authorization import ensure_owner, ensure_owner_or_related


def test_ensure_owner_allows_when_current_user_id_is_none():
    ensure_owner(None, "owner-1", "should not raise")


def test_ensure_owner_allows_when_current_user_matches_owner():
    ensure_owner("owner-1", "owner-1", "should not raise")


def test_ensure_owner_raises_when_current_user_does_not_match_owner():
    with pytest.raises(ForbiddenError, match="not authorized"):
        ensure_owner("someone-else", "owner-1", "not authorized")


def test_ensure_owner_or_related_allows_when_current_user_id_is_none():
    ensure_owner_or_related(None, "owner-1", lambda: False, "should not raise")


def test_ensure_owner_or_related_allows_when_current_user_matches_owner_without_calling_is_related():
    calls = []

    def is_related():
        calls.append(1)
        return False

    ensure_owner_or_related("owner-1", "owner-1", is_related, "should not raise")
    assert calls == []


def test_ensure_owner_or_related_allows_when_is_related_returns_true():
    ensure_owner_or_related("someone-else", "owner-1", lambda: True, "should not raise")


def test_ensure_owner_or_related_raises_when_neither_owner_nor_related():
    with pytest.raises(ForbiddenError, match="not authorized"):
        ensure_owner_or_related("someone-else", "owner-1", lambda: False, "not authorized")
