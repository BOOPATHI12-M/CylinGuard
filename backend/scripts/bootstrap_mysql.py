"""One-time MySQL bootstrap for the no-Docker local path.

Connects as an administrative user, creates the CylinGuard database and
application user, then grants it rights on that database only.

The admin password is read from the MYSQL_ROOT_PASSWORD environment variable
or prompted for interactively. It is never written to disk or logged.

Usage:
    python scripts/bootstrap_mysql.py
    python scripts/bootstrap_mysql.py --admin-user root --host 127.0.0.1 --port 3306
"""

import argparse
import getpass
import os
import pathlib
import sys
from urllib.parse import quote_plus

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import sqlalchemy  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-user", default="root")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "cylinguard"))
    parser.add_argument("--app-user", default=os.getenv("MYSQL_USER", "cylinguard_user"))
    parser.add_argument("--app-password", default=os.getenv("MYSQL_PASSWORD"))
    args = parser.parse_args()

    admin_password = os.getenv("MYSQL_ROOT_PASSWORD")
    if admin_password is None:
        admin_password = getpass.getpass(f"MySQL password for {args.admin_user}: ")

    app_password = args.app_password
    if not app_password:
        print(
            "ERROR: set MYSQL_PASSWORD (or pass --app-password) to the password "
            "the application should use.",
            file=sys.stderr,
        )
        return 1

    admin_url = (
        f"mysql+pymysql://{quote_plus(args.admin_user)}:{quote_plus(admin_password)}"
        f"@{args.host}:{args.port}/"
    )

    try:
        engine = create_engine(admin_url, pool_pre_ping=True)
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{args.database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            # Parameterised where MySQL allows it; identifiers must be inlined,
            # so they come from argparse defaults rather than untrusted input.
            conn.execute(
                text(
                    f"CREATE USER IF NOT EXISTS '{args.app_user}'@'%' "
                    "IDENTIFIED BY :pwd"
                ),
                {"pwd": app_password},
            )
            conn.execute(
                text(f"ALTER USER '{args.app_user}'@'%' IDENTIFIED BY :pwd"),
                {"pwd": app_password},
            )
            conn.execute(
                text(
                    f"GRANT ALL PRIVILEGES ON `{args.database}`.* "
                    f"TO '{args.app_user}'@'%'"
                )
            )
            conn.execute(text("FLUSH PRIVILEGES"))
    except sqlalchemy.exc.OperationalError as exc:
        print(f"ERROR: could not connect or authorise: {exc.orig}", file=sys.stderr)
        return 1

    print(
        f"OK - database '{args.database}' ready, user '{args.app_user}' granted.\n"
        f"Set DATABASE_URL=mysql+pymysql://{args.app_user}:***@"
        f"{args.host}:{args.port}/{args.database} in your .env"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
