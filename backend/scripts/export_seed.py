"""Export the seeded database to database/seed.sql.

`seed.py` is the single source of truth for demo data (decision 2 in PROJECT_STATE). This
produces a plain-SQL copy of what it generated, for anyone who wants to load the demo data
without running Python. It is **generated, never hand-edited**: two independent seed sources
drift, and the one that drifts is always the one nobody runs.

`mysqldump` is not on PATH on the development machine, which is the other reason this is
Python rather than a shell one-liner.

The output is deliberately conservative SQL: no `mysqldump` header pragmas, no extended
inserts beyond a fixed batch size, every value a literal. It has to load through
`init_db.py`'s naive splitter as well as through a real client, and that splitter breaks on
a semicolon inside a string - so strings are escaped and no statement is allowed to contain
one accidentally.

Usage:
    python scripts/export_seed.py                 # -> database/seed.sql
    python scripts/export_seed.py --out other.sql
"""

import argparse
import datetime
import pathlib
import sys
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from _dbguard import guarded  # noqa: E402
from app.database import engine  # noqa: E402

DEFAULT_OUT = pathlib.Path(__file__).resolve().parents[2] / "database" / "seed.sql"

# Parent-first, so a foreign key always has its referent by the time it is inserted.
TABLES = [
    "users",
    "cylinders",
    "devices",
    "settings",
    "sensor_readings",
    "consumption_records",
    "predictions",
    "alerts",
    "safety_events",
]

# Rows per INSERT. One statement per row would make a ~2,900-row file take noticeably longer
# to load; one statement for everything would exceed max_allowed_packet and be unreadable.
BATCH = 200


def sql_literal(value) -> str:
    """Render one value as a MySQL literal.

    Escaping is explicit rather than delegated to a driver because this writes a file, not a
    parameterised statement - there is no placeholder to bind to.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, Decimal, float)):
        return str(value)
    if isinstance(value, datetime.datetime):
        return "'" + value.strftime("%Y-%m-%d %H:%M:%S") + "'"
    if isinstance(value, datetime.date):
        return "'" + value.strftime("%Y-%m-%d") + "'"
    if isinstance(value, (bytes, bytearray)):
        return "0x" + value.hex()

    escaped = (
        str(value)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        # A literal semicolon inside a string would be mistaken for a statement boundary by
        # init_db.py's splitter. \073 is the same character, invisible to the splitter.
        .replace(";", "\\073")
    )
    return "'" + escaped + "'"


def export(out_path: pathlib.Path) -> dict:
    counts: dict = {}
    lines = [
        "-- ============================================================",
        "-- CylinGuard demo data",
        "-- ============================================================",
        "-- GENERATED FILE - do not edit by hand.",
        "--   regenerate: python backend/scripts/export_seed.py",
        "--   source of truth: backend/scripts/seed.py",
        "--",
        f"-- exported: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "--",
        "-- Loads into a database that already has the schema from database/schema.sql.",
        "-- Assumes the target tables are empty: the explicit ids below would collide",
        "-- with existing rows otherwise.",
        "-- ============================================================",
        "",
        "SET NAMES utf8mb4;",
        # Rows are written parent-first, so this is belt to that braces - and it lets the
        # file load even if someone reorders it.
        "SET FOREIGN_KEY_CHECKS = 0;",
        "",
    ]

    with engine.connect() as conn:
        for table in TABLES:
            columns = [
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = DATABASE() AND table_name = :t "
                        "ORDER BY ordinal_position"
                    ),
                    {"t": table},
                )
            ]
            rows = list(conn.execute(text(f"SELECT * FROM `{table}`")))
            counts[table] = len(rows)

            lines.append(f"-- {table}: {len(rows)} rows")
            if not rows:
                lines.append("")
                continue

            column_list = ", ".join(f"`{name}`" for name in columns)
            for start in range(0, len(rows), BATCH):
                chunk = rows[start : start + BATCH]
                values = ",\n  ".join(
                    "(" + ", ".join(sql_literal(value) for value in row) + ")" for row in chunk
                )
                lines.append(f"INSERT INTO `{table}` ({column_list}) VALUES\n  {values};")
            lines.append("")

    lines += ["SET FOREIGN_KEY_CHECKS = 1;", ""]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    counts = export(args.out)
    total = sum(counts.values())
    if total == 0:
        print(
            "ERROR: the database is empty - run scripts/seed.py first, or this would export "
            "a file that seeds nothing.",
            file=sys.stderr,
        )
        return 1

    size_kb = args.out.stat().st_size / 1024
    print(f"Wrote {args.out} ({size_kb:.1f} KB, {total} rows)")
    for table, count in counts.items():
        print(f"  {table:22} {count:>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(guarded(main))
