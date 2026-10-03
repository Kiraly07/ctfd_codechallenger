"""Rename judge0 tables and challenge type to ctfd_code.

Revision ID: b7c2e91a04d8
Revises: c4e1a0b77d21
Create Date: 2026-10-03

Installs that already ran c4e1a0b77d21 keep their rows. Fresh installs
created ctfd_code_* in that revision and skip every rename here.
"""

revision = "b7c2e91a04d8"
down_revision = "c4e1a0b77d21"
branch_labels = None
depends_on = None


def upgrade(op=None):
    conn = op.get_bind()

    def has(name):
        row = conn.exec_driver_sql(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = %(name)s",
            {"name": name},
        ).scalar()
        return bool(row)

    if has("judge0_challenge") and not has("ctfd_code_challenge"):
        conn.exec_driver_sql(
            "RENAME TABLE judge0_challenge TO ctfd_code_challenge, "
            "judge0_test_case TO ctfd_code_test_case"
        )
        conn.exec_driver_sql(
            "ALTER TABLE ctfd_code_challenge "
            "CHANGE judge0_url ctfd_code_url VARCHAR(255) NOT NULL DEFAULT ''"
        )
        conn.exec_driver_sql(
            "ALTER TABLE ctfd_code_test_case "
            "DROP INDEX ix_judge0_test_case_challenge_id, "
            "ADD INDEX ix_ctfd_code_test_case_challenge_id (challenge_id)"
        )
        conn.exec_driver_sql(
            "UPDATE challenges SET type = 'ctfd_code' WHERE type = 'judge0'"
        )
        conn.exec_driver_sql(
            "UPDATE config SET `key` = 'ctfd_code_url' WHERE `key` = 'judge0_url'"
        )
        conn.exec_driver_sql(
            "UPDATE config SET `key` = 'ctfd_code_api_token' "
            "WHERE `key` = 'judge0_api_token'"
        )
        conn.exec_driver_sql(
            "UPDATE submissions SET provided = REPLACE(provided, 'judge0:', 'ctfd_code:') "
            "WHERE provided LIKE 'judge0:%'"
        )


def downgrade(op=None):
    return None
