"""create_links_table

Revision ID: fde258dee458
Revises: 
Create Date: 2026-04-27 13:51:25.905885

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'fde258dee458'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        'links',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('shortcode', sa.String(length=12), nullable=False),
        sa.Column('original_url', sa.Text(), nullable=False),
        sa.Column('click_count', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_links_shortcode', 'links', ['shortcode'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_links_shortcode', table_name='links')
    op.drop_table('links')