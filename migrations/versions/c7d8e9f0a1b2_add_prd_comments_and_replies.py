"""Add normalized prd_comments and prd_comment_replies tables.

Revision ID: c7d8e9f0a1b2
Revises: b8f1c2d3e4a5
Create Date: 2026-05-11 15:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'c7d8e9f0a1b2'
down_revision = 'b8f1c2d3e4a5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'prd_comments',
        sa.Column('id', postgresql.UUID(as_uuid=False), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('prd_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('section_id', sa.VARCHAR(length=255), nullable=False),
        sa.Column('section_title', sa.Text(), nullable=False),
        sa.Column('author', sa.VARCHAR(length=255), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['prd_id'], ['generated_prds.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_prd_comments_prd_id', 'prd_comments', ['prd_id'])

    op.create_table(
        'prd_comment_replies',
        sa.Column('id', postgresql.UUID(as_uuid=False), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('comment_id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('author', sa.VARCHAR(length=255), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('parent_id', postgresql.UUID(as_uuid=False), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['comment_id'], ['prd_comments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_id'], ['prd_comment_replies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_prd_comment_replies_comment_id', 'prd_comment_replies', ['comment_id'])


def downgrade() -> None:
    op.drop_index('ix_prd_comment_replies_comment_id', table_name='prd_comment_replies')
    op.drop_table('prd_comment_replies')
    op.drop_index('ix_prd_comments_prd_id', table_name='prd_comments')
    op.drop_table('prd_comments')
