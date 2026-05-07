"""add_backlog_id_to_approval_events

Revision ID: 12345678abcd
Revises: 65b597a92e25
Create Date: 2026-05-07 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '12345678abcd'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add backlog_id column to approval_events table
    op.add_column('approval_events',
    sa.Column('backlog_id', sa.VARCHAR(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove backlog_id column from approval_events table
    op.drop_column('approval_events', 'backlog_id')
