"""Runs as the App Platform pre-deploy Job component (decision #6) — replaces
the old "SSH in and run it by hand" migration step. The new version only goes
live if this exits 0."""

import glob
import os

import psycopg


def grant_app_privileges() -> None:
    """Postgres 15+ revokes CREATE on the public schema from new roles by
    default. Runs once (idempotently — GRANT is safe to repeat) using an
    admin connection, only if one is provided, so the app's own migration
    connection never needs elevated privileges."""
    admin_conninfo = os.environ.get("ADMIN_DATABASE_URL")
    if not admin_conninfo:
        return
    app_user = os.environ["APP_DB_USER"]
    with psycopg.connect(admin_conninfo, autocommit=True) as conn:
        conn.execute(f"GRANT USAGE, CREATE ON SCHEMA public TO {app_user}")
    print(f"granted USAGE, CREATE on schema public to {app_user}")


def main() -> None:
    grant_app_privileges()

    conninfo = os.environ["DATABASE_URL"]
    migration_dir = os.path.join(os.path.dirname(__file__), "migrations")

    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   filename TEXT PRIMARY KEY,
                   applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
               )"""
        )
        applied = {row[0] for row in conn.execute("SELECT filename FROM schema_migrations").fetchall()}

        for path in sorted(glob.glob(os.path.join(migration_dir, "*.sql"))):
            filename = os.path.basename(path)
            if filename in applied:
                print(f"skip {filename} (already applied)")
                continue
            print(f"applying {filename}")
            with open(path) as f:
                conn.execute(f.read())
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (filename,))

    print("migrations complete")


if __name__ == "__main__":
    main()
