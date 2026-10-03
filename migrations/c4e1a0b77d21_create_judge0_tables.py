"""Create the Judge0 challenge tables.

Revision ID: c4e1a0b77d21
Revises:
Create Date: 2026-10-03

"""

import sqlalchemy as sa

from CTFd.plugins.migrations import get_all_tables

revision = "c4e1a0b77d21"
down_revision = None
branch_labels = None
depends_on = None


def upgrade(op=None):
    tables = set(get_all_tables(op))
    # An older install still has judge0_*. The next revision renames those.
    # Creating empty ctfd_code_* here would make that rename skip the data.
    if "judge0_challenge" in tables:
        return

    if "ctfd_code_challenge" not in tables:
        op.create_table(
            "ctfd_code_challenge",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("ctfd_code_url", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("cpu_time_limit", sa.Float(), nullable=False, server_default="2"),
            sa.Column("memory_limit", sa.Integer(), nullable=False, server_default="128000"),
            sa.Column("allowed_languages", sa.JSON(), nullable=True),
            sa.Column("starter_code", sa.JSON(), nullable=True),
            sa.Column(
                "comparison_mode",
                sa.String(length=32),
                nullable=False,
                server_default="trim",
            ),
            sa.ForeignKeyConstraint(["id"], ["challenges.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    if "ctfd_code_test_case" not in tables:
        op.create_table(
            "ctfd_code_test_case",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("challenge_id", sa.Integer(), nullable=False),
            sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("name", sa.String(length=80), nullable=False, server_default=""),
            sa.Column("stdin", sa.Text(), nullable=False),
            sa.Column("expected_output", sa.Text(), nullable=False),
            sa.Column("is_sample", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.ForeignKeyConstraint(
                ["challenge_id"], ["ctfd_code_challenge.id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_ctfd_code_test_case_challenge_id",
            "ctfd_code_test_case",
            ["challenge_id"],
        )


def downgrade(op=None):
    tables = set(get_all_tables(op))
    if "ctfd_code_test_case" in tables:
        op.drop_index("ix_ctfd_code_test_case_challenge_id", table_name="ctfd_code_test_case")
        op.drop_table("ctfd_code_test_case")
    if "ctfd_code_challenge" in tables:
        op.drop_table("ctfd_code_challenge")
