"""Create the CylinGuard database objects from database/schema.sql.

Used by the no-Docker local path. The mysql container runs schema.sql
automatically via its docker-entrypoint-initdb.d mount instead.

Usage:
    python scripts/init_db.py
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import engine  # noqa: E402

SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[2] / "database" / "schema.sql"


def split_statements(sql: str) -> list[str]:
    """Split a schema file into executable statements.

    schema.sql contains no stored routines, so a plain semicolon split is
    sufficient once comments are stripped.
    """
    without_comments = re.sub(r"^\s*--.*$", "", sql, flags=re.MULTILINE)
    return [s.strip() for s in without_comments.split(";") if s.strip()]


def main() -> int:
    if not SCHEMA_PATH.exists():
        print(f"ERROR: schema not found at {SCHEMA_PATH}", file=sys.stderr)
        return 1

    statements = split_statements(SCHEMA_PATH.read_text(encoding="utf-8"))
    # Hide the password when echoing the target.
    safe_url = re.sub(r"//([^:]+):[^@]*@", r"//\1:***@", settings.database_url)
    print(f"Applying {len(statements)} statements to {safe_url}")

    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))

    with engine.connect() as conn:
        tables = [r[0] for r in conn.execute(text("SHOW TABLES"))]
    print(f"OK - {len(tables)} tables present: {', '.join(sorted(tables))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
