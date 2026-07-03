import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_user_service
from app.main import app
from app.repositories.user_repository import InMemoryUserRepository
from app.services.user_service import UserService


@pytest.fixture
def client():
    user_repo = InMemoryUserRepository()
    user_service = UserService(user_repo)

    app.dependency_overrides[get_user_service] = lambda: user_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
