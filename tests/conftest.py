import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.auth import verify_firebase_token
from app.db import orm_models  # noqa: F401
from app.db.base import Base
from app.dependencies import (
    get_group_service,
    get_task_group_service,
    get_task_service,
    get_user_group_service,
    get_user_service,
)
from app.main import app
from app.repositories.group_repository import GroupRepository
from app.repositories.task_group_repository import TaskGroupRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.user_group_repository import UserGroupRepository
from app.repositories.user_repository import UserRepository
from app.services.group_service import GroupService
from app.services.task_group_service import TaskGroupService
from app.services.task_service import TaskService
from app.services.user_group_service import UserGroupService
from app.services.user_service import UserService

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://ranjith@localhost:5432/tasks_net_db_test"
)
engine = create_engine(TEST_DATABASE_URL)


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session():
    connection = engine.connect()
    outer_txn = connection.begin()
    session_factory = sessionmaker(bind=connection)
    session = session_factory()
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    yield session

    session.close()
    outer_txn.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    user_repo = UserRepository(db_session)
    group_repo = GroupRepository(db_session)
    user_group_repo = UserGroupRepository(db_session)
    task_repo = TaskRepository(db_session)
    task_group_repo = TaskGroupRepository(db_session)

    user_service = UserService(user_repo)
    group_service = GroupService(group_repo, user_service, user_group_repo)
    user_group_service = UserGroupService(user_group_repo, user_service, group_service)
    task_service = TaskService(task_repo, user_service, task_group_repo, group_service)
    task_group_service = TaskGroupService(
        task_group_repo, task_service, group_service, user_service, user_group_service
    )

    app.dependency_overrides[get_user_service] = lambda: user_service
    app.dependency_overrides[get_group_service] = lambda: group_service
    app.dependency_overrides[get_user_group_service] = lambda: user_group_service
    app.dependency_overrides[get_task_service] = lambda: task_service
    app.dependency_overrides[get_task_group_service] = lambda: task_group_service
    app.dependency_overrides[verify_firebase_token] = lambda: "test-firebase-uid"

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def authenticate_as():
    def _authenticate_as(user_id: str) -> None:
        app.dependency_overrides[verify_firebase_token] = lambda: user_id
    return _authenticate_as


@pytest.fixture
def unauthenticated_client(db_session):
    user_repo = UserRepository(db_session)
    group_repo = GroupRepository(db_session)
    user_group_repo = UserGroupRepository(db_session)
    task_repo = TaskRepository(db_session)
    task_group_repo = TaskGroupRepository(db_session)

    user_service = UserService(user_repo)
    group_service = GroupService(group_repo, user_service, user_group_repo)
    user_group_service = UserGroupService(user_group_repo, user_service, group_service)
    task_service = TaskService(task_repo, user_service, task_group_repo, group_service)
    task_group_service = TaskGroupService(
        task_group_repo, task_service, group_service, user_service, user_group_service
    )

    app.dependency_overrides[get_user_service] = lambda: user_service
    app.dependency_overrides[get_group_service] = lambda: group_service
    app.dependency_overrides[get_user_group_service] = lambda: user_group_service
    app.dependency_overrides[get_task_service] = lambda: task_service
    app.dependency_overrides[get_task_group_service] = lambda: task_group_service
    # deliberately NOT overriding verify_firebase_token

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
