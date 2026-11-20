"""governance: decision brief on candidates, success target and health fields on policies

Revision ID: c3d91b7a5e20
Revises: a17c5e0d9b42
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c3d91b7a5e20"
down_revision: Union[str, None] = "a17c5e0d9b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CANDIDATE_COLS = ("brief JSONB",)
POLICY_COLS = ("target INTEGER", "review_on DATE", "weekly INTEGER[]", "checks_flagged INTEGER", "checks_wrong INTEGER")


def upgrade() -> None:
    for col in CANDIDATE_COLS:
        op.execute(f"ALTER TABLE gov_candidates ADD COLUMN IF NOT EXISTS {col}")
    for col in POLICY_COLS:
        op.execute(f"ALTER TABLE gov_policies ADD COLUMN IF NOT EXISTS {col}")


def downgrade() -> None:
    for col in CANDIDATE_COLS:
        op.execute(f"ALTER TABLE gov_candidates DROP COLUMN IF EXISTS {col.split()[0]}")
    for col in POLICY_COLS:
        op.execute(f"ALTER TABLE gov_policies DROP COLUMN IF EXISTS {col.split()[0]}")
