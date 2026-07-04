from typing import Optional

from sqlalchemy.orm import Session

from app.db.orm_models import UserGroupRow
from app.models.user_group import UserGroupRelationship
from app.repositories.base import BaseRepository


class UserGroupRepository(BaseRepository[UserGroupRelationship]):
    def __init__(self, session: Session):
        self._session = session

    def add(self, entity: UserGroupRelationship) -> UserGroupRelationship:
        row = UserGroupRow(
            id=entity.uuid,
            group_id=entity.groupId,
            user_id=entity.userId,
            relationship_label=entity.relationship,
        )
        self._session.add(row)
        self._session.flush()
        return entity

    def get(self, entity_id: str) -> Optional[UserGroupRelationship]:
        row = self._session.get(UserGroupRow, entity_id)
        return self._to_domain(row) if row is not None else None

    def update(self, entity: UserGroupRelationship) -> UserGroupRelationship:
        row = self._session.get(UserGroupRow, entity.uuid)
        row.relationship_label = entity.relationship
        self._session.flush()
        return entity

    def list_all(self) -> list[UserGroupRelationship]:
        return [self._to_domain(row) for row in self._session.query(UserGroupRow).all()]

    def find_by_user_and_group(
        self, user_id: str, group_id: str
    ) -> Optional[UserGroupRelationship]:
        row = (
            self._session.query(UserGroupRow)
            .filter(UserGroupRow.user_id == user_id, UserGroupRow.group_id == group_id)
            .first()
        )
        return self._to_domain(row) if row is not None else None

    def list_by_group(self, group_id: str) -> list[UserGroupRelationship]:
        rows = self._session.query(UserGroupRow).filter(UserGroupRow.group_id == group_id).all()
        return [self._to_domain(row) for row in rows]

    def delete(self, entity_id: str) -> None:
        row = self._session.get(UserGroupRow, entity_id)
        if row is not None:
            self._session.delete(row)
            self._session.flush()

    @staticmethod
    def _to_domain(row: UserGroupRow) -> UserGroupRelationship:
        return UserGroupRelationship(
            uuid=row.id,
            groupId=row.group_id,
            userId=row.user_id,
            relationship=row.relationship_label,
        )
