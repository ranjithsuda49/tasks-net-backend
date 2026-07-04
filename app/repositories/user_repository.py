from typing import Optional

from sqlalchemy.orm import Session

from app.db.orm_models import UserRow
from app.models.user import Name, User
from app.repositories.base import BaseRepository


class InMemoryUserRepository(BaseRepository[User]):
    def __init__(self) -> None:
        self._store: dict[str, User] = {}

    def add(self, entity: User) -> User:
        self._store[entity.userId] = entity
        return entity

    def get(self, entity_id: str) -> Optional[User]:
        return self._store.get(entity_id)

    def update(self, entity: User) -> User:
        self._store[entity.userId] = entity
        return entity

    def list_all(self) -> list[User]:
        return list(self._store.values())


class UserRepository(BaseRepository[User]):
    def __init__(self, session: Session):
        self._session = session

    def add(self, entity: User) -> User:
        row = UserRow(
            id=entity.userId,
            name={"firstName": entity.name.firstName, "lastName": entity.name.lastName},
            phone_num=entity.phoneNum,
            email_id=entity.emailId,
            user_status=entity.userStatus,
            created_at=entity.createdAt,
            updated_at=entity.updatedAt,
        )
        self._session.add(row)
        self._session.flush()
        return entity

    def get(self, entity_id: str) -> Optional[User]:
        row = self._session.get(UserRow, entity_id)
        return self._to_domain(row) if row is not None else None

    def update(self, entity: User) -> User:
        row = self._session.get(UserRow, entity.userId)
        row.name = {"firstName": entity.name.firstName, "lastName": entity.name.lastName}
        row.phone_num = entity.phoneNum
        row.email_id = entity.emailId
        row.user_status = entity.userStatus
        row.updated_at = entity.updatedAt
        self._session.flush()
        return entity

    def list_all(self) -> list[User]:
        return [self._to_domain(row) for row in self._session.query(UserRow).all()]

    @staticmethod
    def _to_domain(row: UserRow) -> User:
        return User(
            userId=row.id,
            name=Name(firstName=row.name["firstName"], lastName=row.name["lastName"]),
            phoneNum=row.phone_num,
            emailId=row.email_id,
            userStatus=row.user_status,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )
