"""decisions, session signals, and a source column on dashboard rows

Revision ID: a17c5e0d9b42
Revises: 83dfe2664e14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a17c5e0d9b42"
down_revision: Union[str, None] = "83dfe2664e14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SOURCE_TABLES = ("team_prs", "gov_candidates", "gov_evidence", "gov_skill_rules")


def upgrade() -> None:
    op.create_table(
        "decisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("analysis_id", sa.BigInteger(), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("proposal", sa.Text(), nullable=False),
        sa.Column("choice", sa.Text(), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=True),
        sa.Column("rule_followed", sa.Boolean(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_decisions_analysis", "decisions", ["analysis_id"])
    op.create_table(
        "session_signals",
        sa.Column("analysis_id", sa.BigInteger(), nullable=False),
        sa.Column("signals", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("highlights", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("steering", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("analysis_id"),
    )
    for table in SOURCE_TABLES:
        op.add_column(table, sa.Column("source", sa.Text(), server_default="sample", nullable=False))


def downgrade() -> None:
    for table in SOURCE_TABLES:
        op.drop_column(table, "source")
    op.drop_table("session_signals")
    op.drop_index("ix_decisions_analysis", table_name="decisions")
    op.drop_table("decisions")
