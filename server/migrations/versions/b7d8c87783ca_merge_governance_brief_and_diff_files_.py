"""merge governance brief and diff files heads

Revision ID: b7d8c87783ca
Revises: c3d91b7a5e20, c4d81e7a2f56
Create Date: 2026-11-21 00:04:40.601300
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7d8c87783ca'
down_revision: Union[str, None] = ('c3d91b7a5e20', 'c4d81e7a2f56')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
