from typing import Optional

from sqlalchemy.orm import Session

from app.db.orm_models import GroupRow
from app.models.group import Group
from app.repositories.base import BaseRepository


class InMemoryGroupRepository(BaseRepository[Group]):
    def __init__(self) -> None:
        self._store: dict[str, Group] = {}

    def add(self, entity: Group) -> Group:
        self._store[entity.groupId] = entity
        return entity

    def get(self, entity_id: str) -> Optional[Group]:
        return self._store.get(entity_id)

    def update(self, entity: Group) -> Group:
        self._store[entity.groupId] = entity
        return entity

    def list_all(self) -> list[Group]:
        return list(self._store.values())

    def list_by_creator(self, creater_id: str) -> list[Group]:
        return [group for group in self._store.values() if group.groupCreaterId == creater_id]


class GroupRepository(BaseRepository[Group]):
    def __init__(self, session: Session):
        self._session = session

    def add(self, entity: Group) -> Group:
        row = GroupRow(
            id=entity.groupId,
            group_name=entity.groupName,
            group_desc=entity.groupDesc,
            group_category=entity.groupCategory,
            group_status=entity.groupStatus,
            group_icon_url=entity.groupIconUrl,
            group_creater_id=entity.groupCreaterId,
            created_at=entity.createdAt,
            updated_at=entity.updatedAt,
        )
        self._session.add(row)
        self._session.flush()
        return entity

    def get(self, entity_id: str) -> Optional[Group]:
        row = self._session.get(GroupRow, entity_id)
        return self._to_domain(row) if row is not None else None

    def update(self, entity: Group) -> Group:
        row = self._session.get(GroupRow, entity.groupId)
        row.group_name = entity.groupName
        row.group_desc = entity.groupDesc
        row.group_status = entity.groupStatus
        row.group_icon_url = entity.groupIconUrl
        row.updated_at = entity.updatedAt
        self._session.flush()
        return entity

    def list_all(self) -> list[Group]:
        return [self._to_domain(row) for row in self._session.query(GroupRow).all()]

    def list_by_creator(self, creater_id: str) -> list[Group]:
        rows = self._session.query(GroupRow).filter(GroupRow.group_creater_id == creater_id).all()
        return [self._to_domain(row) for row in rows]

    @staticmethod
    def _to_domain(row: GroupRow) -> Group:
        return Group(
            groupId=row.id,
            groupName=row.group_name,
            groupDesc=row.group_desc,
            groupCategory=row.group_category,
            groupStatus=row.group_status,
            groupIconUrl=row.group_icon_url,
            groupCreaterId=row.group_creater_id,
            createdAt=row.created_at,
            updatedAt=row.updated_at,
        )
