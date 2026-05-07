"""add_prd_name_to_generated_prds

Revision ID: b8f1c2d3e4a5
Revises: 12345678abcd
Create Date: 2026-05-07 12:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b8f1c2d3e4a5"
down_revision: Union[str, Sequence[str], None] = "12345678abcd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "generated_prds",
        sa.Column("prd_name", sa.VARCHAR(length=255), nullable=False, server_default="Untitled PRD"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("generated_prds", "prd_name")
