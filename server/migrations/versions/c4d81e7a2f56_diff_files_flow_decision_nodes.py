"""file-level diff, reading flow, decision nodes and outcome, link from a team PR row to its analysis

Revision ID: c4d81e7a2f56
Revises: a17c5e0d9b42
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c4d81e7a2f56"
down_revision: Union[str, None] = "a17c5e0d9b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("analyses", sa.Column("diff_files", postgresql.JSONB(astext_type=sa.Text()),
                                        server_default="[]", nullable=False))
    op.add_column("analyses", sa.Column("flow", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("decisions", sa.Column("node_ids", postgresql.JSONB(astext_type=sa.Text()),
                                         server_default="[]", nullable=False))
    op.add_column("decisions", sa.Column("outcome", sa.Text(), server_default="ok", nullable=False))
    op.add_column("team_prs", sa.Column("public_id", sa.String(32), nullable=True))
    op.add_column("gov_evidence", sa.Column("public_id", sa.String(32), nullable=True))
    op.add_column("gov_skill_rules", sa.Column("latest_public_id", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("gov_skill_rules", "latest_public_id")
    op.drop_column("gov_evidence", "public_id")
    op.drop_column("team_prs", "public_id")
    op.drop_column("decisions", "outcome")
    op.drop_column("decisions", "node_ids")
    op.drop_column("analyses", "flow")
    op.drop_column("analyses", "diff_files")
