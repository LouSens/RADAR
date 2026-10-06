"""Assets found from the user's holdings rather than configured.

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assets",
        sa.Column("discovered", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("assets", "discovered")
