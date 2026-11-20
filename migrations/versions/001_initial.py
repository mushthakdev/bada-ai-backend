"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-11-20

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tables are created via SQLAlchemy metadata.create_all in development.
    # This revision anchors Alembic history for production deployments.
    pass


def downgrade() -> None:
    pass
