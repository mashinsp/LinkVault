"""add_operational_indexes

Revision ID: ca189fdef2fc
Revises: fde258dee458
Create Date: 2026-04-27 13:54:52.709591

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ca189fdef2fc'
down_revision: Union[str, Sequence[str], None] = 'fde258dee458'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # For querying active links (admin dashboard, cleanup jobs)
    op.create_index(
        'ix_links_is_active',
        'links',
        ['is_active'],
        postgresql_where=sa.text('is_active = true'),
    )

    # For expiry cleanup job (Phase 3 worker will use this)
    op.create_index(
        'ix_links_expires_at',
        'links',
        ['expires_at'],
        postgresql_where=sa.text('expires_at IS NOT NULL'),
    )

    # For time-based queries on the stats endpoint
    op.create_index(
        'ix_links_created_at',
        'links',
        ['created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_links_created_at', table_name='links')
    op.drop_index('ix_links_expires_at', table_name='links')
    op.drop_index('ix_links_is_active', table_name='links')
