"""add group_id to tasks

Revision ID: b86979a31d5a
Revises: f24972e8b68b
Create Date: 2026-07-05 14:15:37.230282

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b86979a31d5a'
down_revision: Union[str, None] = 'f24972e8b68b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tasks', sa.Column('group_id', sa.String(length=36), nullable=True))
    op.create_foreign_key(None, 'tasks', 'groups', ['group_id'], ['id'])
    op.create_index(op.f('ix_tasks_group_id'), 'tasks', ['group_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_tasks_group_id'), table_name='tasks')
    op.drop_constraint('tasks_group_id_fkey', 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'group_id')
