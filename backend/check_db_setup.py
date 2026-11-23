"""check_db_setup.py — 10-second self-diagnosis for MarketPulse Phase 1 setup.

Put this file in the backend folder (next to pyproject.toml) and run:

    uv run python check_db_setup.py

It reads your .env (printing NO secrets), checks every value the app needs,
connects to Neon as both roles, pings Redis, and prints plain-language verdicts
with the exact fix for anything that fails.
"""
from __future__ import annotations

import sys
from pathlib import Path

PASS, FAIL, WARN = "[OK]", "[X]", "[!]"
_PG_PREFIXES = ("postgresql://", "postgres://")
_REDIS_PREFIXES = ("redis://", "rediss://")


def _safe_url(url: str) -> str:
    """URL with the password part masked, safe to print."""
    if "@" in url and "://" in url:
        head, tail = url.split("://", 1)
        creds, rest = tail.split("@", 1)
        user = creds.split(":", 1)[0]
        return f"{head}://{user}:****@{rest}"
    return url


def _typo_hints(name: str, value: str) -> list[str]:
    hints: list[str] = []
    if value.startswith(("REDIS_URL=", '"', "'")) or '"' in value:
        hints.append(
            f"{name}: the value contains quotes or a REDIS_URL= wrapper. "
            "Dashboards show a shell snippet like  REDIS_URL=\"rediss://...\"  — "
            "keep ONLY the rediss://... part, no quotes, no REDIS_URL=."
        )
    if "<" in value or ">" in value:
        hints.append(
            f"{name}: the value contains < or >. Those are placeholder punctuation "
            "from instructions — they are NOT part of the password. Delete them."
        )
    return hints


def check_env_file() -> dict[str, str]:
    print("1) Reading .env ...")
    env_path = Path(".env")
    if not env_path.exists():
        print(f"  {FAIL} No .env file here. Run this from the backend folder "
              "(the one with pyproject.toml).")
        sys.exit(1)
    try:
        from dotenv import dotenv_values
    except ImportError:
        print(f"  {FAIL} python-dotenv not installed — run: uv sync")
        sys.exit(1)
    values = {k: v for k, v in dotenv_values(env_path).items() if v}
    required = [
        "MP_DATABASE_DIRECT_URL", "MP_DATABASE_URL",
        "MP_DB_APP_PASSWORD", "MP_REDIS_URL",
    ]
    missing = [k for k in required if k not in values]
    if missing:
        print(f"  {FAIL} Missing keys: {', '.join(missing)}")
        sys.exit(1)
    print(f"  {PASS} .env found with all required keys")
    hints: list[str] = []
    for key in ("MP_DATABASE_DIRECT_URL", "MP_DATABASE_URL", "MP_REDIS_URL"):
        hints.extend(_typo_hints(key, values[key]))
    for hint in hints:
        print(f"  {FAIL} {hint}")
    if hints:
        sys.exit(1)

    for key in ("MP_DATABASE_DIRECT_URL", "MP_DATABASE_URL"):
        if not values[key].startswith(_PG_PREFIXES):
            print(f"  {FAIL} {key} must start with postgresql://")
            sys.exit(1)
        direct = key == "MP_DATABASE_DIRECT_URL"
        hostpart = values[key].split("@", 1)[1]
        host = hostpart.split("/", 1)[0]
        db = hostpart.split("/", 1)[1].split("?", 1)[0] if "/" in hostpart else ""
        if direct and "-pooler" in host:
            print(f"  {FAIL} MP_DATABASE_DIRECT_URL host has '-pooler' — use the "
                  "NON-pooled host (the one without -pooler) for this line.")
            sys.exit(1)
        if not direct and "-pooler" not in host:
            print(f"  {FAIL} MP_DATABASE_URL host has no '-pooler' — use the pooled host.")
            sys.exit(1)
        if db != "neondb":
            print(f"  {WARN} {key} uses database '{db}'. If Alembic ever says "
                  "'permission denied for schema public', switch to '/neondb'.")
        print(f"  {PASS} {key} = {_safe_url(values[key])}")

    redis_url = values["MP_REDIS_URL"]
    if not redis_url.startswith(_REDIS_PREFIXES):
        print(f"  {FAIL} MP_REDIS_URL must start with redis:// or rediss://")
        sys.exit(1)
    print(f"  {PASS} MP_REDIS_URL = {_safe_url(redis_url)}")
    return values


def check_owner(dsn: str) -> bool:
    print("2) Connecting as the OWNER (direct host) ...")
    try:
        import psycopg

        with psycopg.connect(dsn, autocommit=True, connect_timeout=20) as conn, \
                conn.cursor() as cur:
            cur.execute("SELECT current_user, current_database()")
            user, db = cur.fetchone()  # type: ignore[misc]
            print(f"  {PASS} connected as {user!r} to database {db!r}")
            cur.execute("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            can_create = bool(cur.fetchone()[0])
            if not can_create:
                print(f"  {FAIL} This role may NOT create tables in schema public. "
                      "Use database '/neondb' in both MP_DATABASE_* URLs.")
                return False
            cur.execute("CREATE TABLE IF NOT EXISTS _mp_doctor_probe (id int)")
            cur.execute("DROP TABLE _mp_doctor_probe")
            print(f"  {PASS} CREATE/DROP probe table works (the exact operation "
                  "that was failing before)")
            return True
    except Exception as exc:  # noqa: BLE001
        print(f"  {FAIL} {type(exc).__name__}: {exc}")
        if "password authentication failed" in str(exc):
            print("      -> The password in MP_DATABASE_DIRECT_URL is wrong. Neon console "
                  "-> Roles -> neondb_owner -> Reset password, then update .env.")
        return False


def check_worker(dsn: str) -> bool:
    print("3) Connecting as the WORKER marketpulse_app (pooled host) ...")
    try:
        import psycopg

        with psycopg.connect(dsn, autocommit=True, connect_timeout=20) as conn, \
                conn.cursor() as cur:
            cur.execute("SELECT current_user")
            print(f"  {PASS} connected as {cur.fetchone()[0]!r}")
            cur.execute("SELECT rolbypassrls FROM pg_roles WHERE rolname = current_user")
            bypass = bool(cur.fetchone()[0])
            if bypass:
                print(f"  {FAIL} rolbypassrls is TRUE — run "
                      "scripts\\db\\bootstrap_app_role.py to re-assert the lock.")
            else:
                print(f"  {PASS} rolbypassrls = false (security lock is on)")
            return not bypass
    except Exception as exc:  # noqa: BLE001
        print(f"  {FAIL} {type(exc).__name__}: {exc}")
        if "password authentication failed" in str(exc):
            print("      -> MP_DATABASE_URL password must be the SAME value as "
                  "MP_DB_APP_PASSWORD (the one bootstrap_app_role.py sets).")
        return False


def check_redis(dsn: str) -> bool:
    print("4) Pinging Redis ...")
    try:
        import redis

        client = redis.Redis.from_url(dsn, socket_connect_timeout=20)
        print(f"  {PASS} PING returned {client.ping()}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"  {FAIL} {type(exc).__name__}: {exc}")
        return False


if __name__ == "__main__":
    vals = check_env_file()
    ok = check_owner(vals["MP_DATABASE_DIRECT_URL"])
    ok = check_worker(vals["MP_DATABASE_URL"]) and ok
    ok = check_redis(vals["MP_REDIS_URL"]) and ok
    print("-" * 60)
    if ok:
        print("ALL CHECKS PASSED. Now run, in order:")
        print("  uv run python scripts\\db\\bootstrap_app_role.py")
        print("  uv run alembic upgrade head")
        print("  uv run pytest -m integration")
    else:
        print("Fix the [X] items above, then run this script again until all pass.")