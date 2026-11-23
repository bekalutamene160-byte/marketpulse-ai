"""One-time bootstrap of the least-privilege application database role (ADR-0023).

Run ONCE per database, BEFORE the first ``alembic upgrade head``, against the DIRECT
(owner) connection string:

    MP_DATABASE_DIRECT_URL=postgresql://owner:pw@host/db \
    MP_DB_APP_PASSWORD=... \
    uv run python scripts/db/bootstrap_app_role.py

Creates ``marketpulse_app`` (or ``$MP_DB_APP_ROLE``) with ``LOGIN``, ``NOBYPASSRLS``
and the password from ``MP_DB_APP_PASSWORD``. Idempotent: re-running alters the
password and re-asserts ``NOBYPASSRLS``. Fails closed if the password is empty or
the role would have ``BYPASSRLS``.

The application role owns no tables (the owner/migration owns them) and has no
``BYPASSRLS``; row-level security is therefore enforced against it (ADR-0022). The
Phase 1 integration test asserts ``rolbypassrls = false`` as the exit gate requires.

The role name and password are composed with ``psycopg.sql`` identifiers/literals,
never f-strings, so a password containing quotes or semicolons cannot inject SQL.
"""

from __future__ import annotations

import re
import sys

import psycopg
from psycopg import sql

from marketpulse.config import Settings

_ROLE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


def main() -> int:
    settings = Settings()
    role = settings.db_app_role
    if not _ROLE_NAME.match(role):
        print(f"ERROR: MP_DB_APP_ROLE {role!r} is not a safe role name.", file=sys.stderr)
        return 2

    if settings.db_app_password is None or not settings.db_app_password.get_secret_value():
        print("ERROR: MP_DB_APP_PASSWORD is not set.", file=sys.stderr)
        return 2

    dsn = settings.database_direct_dsn or settings.database_dsn
    if dsn is None:
        print(
            "ERROR: MP_DATABASE_DIRECT_URL (or MP_DATABASE_URL) is not set.",
            file=sys.stderr,
        )
        return 2

    password = settings.db_app_password.get_secret_value()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        exists = cur.fetchone() is not None

        # Composed with sql.Identifier / sql.Literal so the password (which may
        # contain quotes, semicolons, etc.) is safely quoted, never interpolated.
        stmt = sql.SQL(
            "{create_or_alter} ROLE {role} WITH LOGIN NOBYPASSRLS PASSWORD {password}"
        ).format(
            create_or_alter=sql.SQL("CREATE" if not exists else "ALTER"),
            role=sql.Identifier(role),
            password=sql.Literal(password),
        )
        cur.execute(stmt)
        conn.commit()
        print(f"{'altered existing' if exists else 'created'} role {role}")

        # Re-assert the security property and fail closed if it is wrong.
        cur.execute("SELECT rolbypassrls FROM pg_roles WHERE rolname = %s", (role,))
        row = cur.fetchone()
        if row is None or row[0]:
            print(
                f"ERROR: role {role} missing or has BYPASSRLS=true; refusing to continue.",
                file=sys.stderr,
            )
            return 3
        print(f"OK: role {role} rolbypassrls=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
