"""add_backlog_tables

Revision ID: f600436ed980
Revises: 
Create Date: 2026-05-06 14:07:54.808074

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'f600436ed980'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'backlogs',
        sa.Column('id', sa.UUID(as_uuid=False), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('prompt', sa.Text(), nullable=False),
        sa.Column('status', sa.VARCHAR(length=32), server_default='generated', nullable=False),
        sa.Column('source_files', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'generated_epics',
        sa.Column('id', sa.UUID(as_uuid=False), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('backlog_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('epic_id', sa.Text(), nullable=False),
        sa.Column('epic_name', sa.Text(), nullable=False),
        sa.Column('epic_summary', sa.Text(), nullable=False),
        sa.Column('business_value', sa.Text(), nullable=False),
        sa.Column('scope', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('out_of_scope', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('assumptions', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('acceptance_criteria', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('risks_and_dependencies', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('status', sa.VARCHAR(length=32), server_default='draft', nullable=False),
        sa.Column('jira_key', sa.VARCHAR(length=128), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['backlog_id'], ['backlogs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_generated_epics_backlog_id', 'generated_epics', ['backlog_id'], unique=False)
    op.create_table(
        'generated_stories',
        sa.Column('id', sa.UUID(as_uuid=False), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('epic_record_id', sa.UUID(as_uuid=False), nullable=False),
        sa.Column('story_id', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('priority', sa.Text(), nullable=False),
        sa.Column('acceptance_criteria', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('status', sa.VARCHAR(length=32), server_default='draft', nullable=False),
        sa.Column('jira_key', sa.VARCHAR(length=128), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['epic_record_id'], ['generated_epics.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_generated_stories_epic_record_id', 'generated_stories', ['epic_record_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_generated_stories_epic_record_id', table_name='generated_stories')
    op.drop_table('generated_stories')
    op.drop_index('ix_generated_epics_backlog_id', table_name='generated_epics')
    op.drop_table('generated_epics')
    op.drop_table('backlogs')
