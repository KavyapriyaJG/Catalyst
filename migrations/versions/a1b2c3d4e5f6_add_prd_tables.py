"""Add PRD tables.

Revision ID: a1b2c3d4e5f6
Revises: 65b597a92e25
Create Date: 2026-05-06 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '65b597a92e25'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create PRD tables."""
    # Create generated_prds table
    op.create_table(
        'generated_prds',
        sa.Column('id', postgresql.UUID(as_uuid=False), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('source_files', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('status', sa.VARCHAR(length=32), server_default='draft', nullable=False),
        sa.Column('prd_content', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('reviewed_by', sa.VARCHAR(length=255), nullable=True),
        sa.Column('review_comment', sa.Text(), nullable=True),
        sa.Column('reviewed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Drop PRD tables."""
    op.drop_table('generated_prds')
