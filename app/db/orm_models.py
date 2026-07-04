import uuid

from sqlalchemy import Column, DateTime, Enum, ForeignKey, JSON, String, UniqueConstraint

from app.db.base import Base
from app.models.enums import GroupStatus, TaskState, UserStatus


def _enum_column(enum_cls, constraint_name, default):
    return Column(
        Enum(
            enum_cls,
            values_callable=lambda e: [m.value for m in e],
            native_enum=False,
            name=constraint_name,
            length=20,
        ),
        nullable=False,
        server_default=default.value,
    )


class UserRow(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(JSON, nullable=False)
    phone_num = Column(String(20), nullable=True)
    email_id = Column(String(255), nullable=True)
    user_status = _enum_column(UserStatus, "ck_users_user_status", UserStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class GroupRow(Base):
    __tablename__ = "groups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_name = Column(String(200), nullable=False)
    group_desc = Column(String(1000), nullable=True)
    group_category = Column(String(100), nullable=False)
    group_status = _enum_column(GroupStatus, "ck_groups_group_status", GroupStatus.ACTIVE)
    group_icon_url = Column(String(500), nullable=True)
    group_creater_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)


class UserGroupRow(Base):
    __tablename__ = "user_groups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    group_id = Column(String(36), ForeignKey("groups.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    # Python attribute renamed to avoid clashing with sqlalchemy.orm.relationship;
    # the actual database column name is still exactly "relationship".
    relationship_label = Column("relationship", String(100), nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "group_id", name="uq_user_groups_user_id_group_id"),
    )


class TaskRow(Base):
    __tablename__ = "tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_title = Column(String(200), nullable=False)
    task_desc = Column(String(2000), nullable=True)
    task_due_date = Column(DateTime(timezone=True), nullable=True)
    task_state = _enum_column(TaskState, "ck_tasks_task_state", TaskState.TODO)
    created_at = Column(DateTime(timezone=True), nullable=False)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)


class GroupTaskRow(Base):
    __tablename__ = "group_tasks"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)
    group_id = Column(String(36), ForeignKey("groups.id"), nullable=False, index=True)
    assignee_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("task_id", "group_id", name="uq_group_tasks_task_id_group_id"),
    )
