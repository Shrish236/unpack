"""structured history and rejected reason columns on function_reasons

Revision ID: 2a4f8b9c1d3e
Revises: 19c3f5677b8a
Create Date: 2026-11-20 06:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "2a4f8b9c1d3e"
down_revision: Union[str, None] = "19c3f5677b8a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE function_reasons "
        "ALTER COLUMN history TYPE jsonb "
        "USING CASE "
        "  WHEN history IS NULL OR btrim(history) = '' THEN '[]'::jsonb "
        "  ELSE jsonb_build_array(jsonb_build_object('turn', '', 'text', history)) "
        "END"
    )
    op.alter_column(
        "function_reasons",
        "history",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'[]'::jsonb"),
    )
    op.add_column(
        "function_reasons",
        sa.Column("rejected", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("function_reasons", "rejected")
    op.alter_column(
        "function_reasons",
        "history",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=True,
        server_default=None,
    )
    op.execute(
        "ALTER TABLE function_reasons "
        "ALTER COLUMN history TYPE text "
        "USING CASE "
        "  WHEN history IS NULL OR history = '[]'::jsonb THEN NULL "
        "  ELSE history::text "
        "END"
    )
