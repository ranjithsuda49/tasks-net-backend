from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.auth import verify_firebase_token


def test_missing_header_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        verify_firebase_token(authorization=None)
    assert exc_info.value.status_code == 401


def test_wrong_scheme_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        verify_firebase_token(authorization="Basic abc123")
    assert exc_info.value.status_code == 401


def test_bearer_with_empty_token_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        verify_firebase_token(authorization="Bearer ")
    assert exc_info.value.status_code == 401


def test_invalid_token_raises_401():
    with patch("app.auth.auth.verify_id_token", side_effect=ValueError("bad token")):
        with pytest.raises(HTTPException) as exc_info:
            verify_firebase_token(authorization="Bearer some-token")
    assert exc_info.value.status_code == 401


def test_valid_token_returns_uid():
    with patch("app.auth.auth.verify_id_token", return_value={"uid": "firebase-uid-123"}):
        result = verify_firebase_token(authorization="Bearer some-token")
    assert result == "firebase-uid-123"
