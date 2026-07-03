import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_group_service, get_user_service
from app.main import app
from app.repositories.group_repository import InMemoryGroupRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.group_service import GroupService
from app.services.user_service import UserService


@pytest.fixture
def client():
    user_repo = InMemoryUserRepository()
    group_repo = InMemoryGroupRepository()

    user_service = UserService(user_repo)
    group_service = GroupService(group_repo, user_service)

    app.dependency_overrides[get_user_service] = lambda: user_service
    app.dependency_overrides[get_group_service] = lambda: group_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
