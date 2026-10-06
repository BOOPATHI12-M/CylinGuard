"""One-time MySQL bootstrap for the no-Docker local path.

Connects as an administrative user, creates the CylinGuard database and
application user, grants it rights on that database only, writes the resulting
credentials into the project's gitignored .env, and then proves the application
user can actually log in.

That last pair of steps matters. The earlier version only printed "set
DATABASE_URL in your .env" and left it to the operator, so init_db.py fell back
to the hardcoded `change_me` default in app/config.py and died with MySQL error
1045. The script that chooses the password is the one that should record it.

The admin password is read from MYSQL_ROOT_PASSWORD or prompted for
interactively, and is never written to disk or logged.

Usage:
    python scripts/bootstrap_mysql.py
    python scripts/bootstrap_mysql.py --admin-user root --host 127.0.0.1 --port 3306
    python scripts/bootstrap_mysql.py --no-write-env     # print, do not touch .env
"""

import argparse
import getpass
import os
import pathlib
import secrets
import sys
from urllib.parse import quote_plus

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import sqlalchemy  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"

# Values that mean "not configured yet", so overwriting them is safe.
PLACEHOLDERS = {"", "change_me", "change_this_secret", "change_root_password"}


def merge_env_file(path: pathlib.Path, updates: dict, keep: set) -> list:
    """Write `updates` into a KEY=VALUE file, preserving every other line.

    A key listed in `keep` is left alone when it already holds a real value, so
    re-running this script never rotates an existing JWT secret. Returns the
    keys actually written.
    """
    existing = {}
    lines = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            existing[key.strip()] = value.strip()

    to_write = {
        key: value
        for key, value in updates.items()
        if not (key in keep and existing.get(key, "") not in PLACEHOLDERS)
    }

    out = []
    seen = set()
    for line in lines:
        stripped = line.strip()
        key = stripped.partition("=")[0].strip() if "=" in stripped else None
        if key in to_write and not stripped.startswith("#"):
            out.append(f"{key}={to_write[key]}")
            seen.add(key)
        else:
            out.append(line)

    missing = [k for k in to_write if k not in seen]
    if missing:
        if out and out[-1].strip():
            out.append("")
        out.append("# Written by scripts/bootstrap_mysql.py")
        out += [f"{k}={to_write[k]}" for k in missing]

    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return sorted(to_write)


def provision(admin_url: str, database: str, app_user: str, app_password: str, hosts) -> None:
    """Create the database and the application account, idempotently."""
    engine = create_engine(admin_url, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            # Parameterised where MySQL allows it; identifiers must be inlined,
            # so they come from argparse defaults rather than untrusted input.
            for host in hosts:
                conn.execute(
                    text(
                        f"CREATE USER IF NOT EXISTS '{app_user}'@'{host}' IDENTIFIED BY :pwd"
                    ),
                    {"pwd": app_password},
                )
                conn.execute(
                    text(f"ALTER USER '{app_user}'@'{host}' IDENTIFIED BY :pwd"),
                    {"pwd": app_password},
                )
                conn.execute(
                    text(
                        f"GRANT ALL PRIVILEGES ON `{database}`.* TO '{app_user}'@'{host}'"
                    )
                )
            conn.execute(text("FLUSH PRIVILEGES"))
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admin-user", default="root")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--database", default=os.getenv("MYSQL_DATABASE", "cylinguard"))
    parser.add_argument("--app-user", default=os.getenv("MYSQL_USER", "cylinguard_user"))
    parser.add_argument("--app-password", default=os.getenv("MYSQL_PASSWORD"))
    parser.add_argument("--env-file", type=pathlib.Path, default=DEFAULT_ENV_FILE)
    parser.add_argument(
        "--no-write-env",
        action="store_true",
        help="do not touch .env; print the DATABASE_URL instead",
    )
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
    # The app connects over TCP to 127.0.0.1, which MySQL resolves back to
    # 'localhost' unless skip_name_resolve is set, so the account is granted for
    # both hosts. A host-specific row also cannot then be shadowed by a leftover
    # anonymous account, which would win on host specificity and produce a
    # confusing 1045.
    app_hosts = ("%", "localhost")

    try:
        provision(admin_url, args.database, args.app_user, app_password, app_hosts)
    except sqlalchemy.exc.OperationalError as exc:
        print(f"ERROR: could not connect or authorise: {exc.orig}", file=sys.stderr)
        return 1

    app_url = (
        f"mysql+pymysql://{quote_plus(args.app_user)}:{quote_plus(app_password)}"
        f"@{args.host}:{args.port}/{args.database}"
    )
    safe_url = f"mysql+pymysql://{args.app_user}:***@{args.host}:{args.port}/{args.database}"

    # Prove the account works before anything else is allowed to depend on it.
    try:
        app_engine = create_engine(app_url, pool_pre_ping=True)
        with app_engine.connect() as conn:
            who = conn.execute(text("SELECT CURRENT_USER()")).scalar()
        app_engine.dispose()
    except sqlalchemy.exc.OperationalError as exc:
        print(
            f"ERROR: the app user was created but cannot log in: {exc.orig}\n"
            "       Nothing was written to .env. Look for a conflicting account:\n"
            "       SELECT user, host, plugin FROM mysql.user "
            f"WHERE user IN ('{args.app_user}', '');",
            file=sys.stderr,
        )
        return 1

    print(f"OK - database '{args.database}' ready; connected as {who}")

    if args.no_write_env:
        print(
            "\nAdd this to your .env (nothing was written, --no-write-env):\n"
            f"  DATABASE_URL={app_url}"
        )
        return 0

    written = merge_env_file(
        args.env_file,
        {
            "MYSQL_DATABASE": args.database,
            "MYSQL_USER": args.app_user,
            "MYSQL_PASSWORD": app_password,
            "DATABASE_URL": app_url,
            "JWT_SECRET": secrets.token_urlsafe(48),
        },
        keep={"JWT_SECRET"},
    )
    print(
        f"Wrote {args.env_file} ({', '.join(written)})\n"
        f"DATABASE_URL -> {safe_url}\n"
        "That file is gitignored, and the admin password was not written to it."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
