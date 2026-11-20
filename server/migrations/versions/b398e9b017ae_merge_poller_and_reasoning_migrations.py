"""merge poller and reasoning migrations

Revision ID: b398e9b017ae
Revises: 2a4f8b9c1d3e, 412bc53b2425
Create Date: 2026-11-20 07:26:29.387771
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b398e9b017ae'
down_revision: Union[str, None] = ('2a4f8b9c1d3e', '412bc53b2425')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
