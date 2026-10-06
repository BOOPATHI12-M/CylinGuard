"""Assert the SQLAlchemy models describe exactly the schema in database/schema.sql.

`schema.sql` is the single source of DDL truth - `Base.metadata.create_all()` is
deliberately never called anywhere in this project. That means nothing would
otherwise notice if a model drifted away from the table it claims to map, so this
script is the check that keeps the models honest.

It compares, for all 9 tables: the column set, nullability, UNSIGNED-ness,
server-side defaults, and the presence of every named index, unique key, check
constraint and foreign key.

Needs no database connection.

Usage:
    python scripts/check_schema_parity.py        # exit 0 = no drift
"""

import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy.dialects import mysql  # noqa: E402
from sqlalchemy.orm import configure_mappers  # noqa: E402

from app.database import Base  # noqa: E402
import app.models  # noqa: E402,F401  (registers every model on Base.metadata)

SCHEMA = pathlib.Path(__file__).resolve().parents[2] / "database" / "schema.sql"

# Lines inside a CREATE TABLE body that declare something other than a column.
NOT_A_COLUMN = ("PRIMARY KEY", "UNIQUE KEY", "KEY ", "CONSTRAINT", "REFERENCES")

DEFAULT_RE = re.compile(r"DEFAULT\s+(CURRENT_TIMESTAMP|'[^']*'|[-\d.]+)")
KEY_NAME_RE = re.compile(r"(?:UNIQUE KEY|KEY|CONSTRAINT)\s+(\w+)")


def parse_table(sql: str, table: str) -> tuple[dict[str, str], list[str]]:
    """Return ({column: rest-of-definition}, [named key declarations])."""
    match = re.search(
        r"CREATE TABLE IF NOT EXISTS " + table + r" \((.*?)\n\) ENGINE", sql, re.S
    )
    if match is None:
        raise AssertionError(f"{table} not found in schema.sql")

    columns: dict[str, str] = {}
    keys: list[str] = []
    for raw in match.group(1).splitlines():
        line = raw.strip().rstrip(",")
        if not line:
            continue
        if line.upper().startswith(NOT_A_COLUMN):
            keys.append(line)
            continue
        name, _, rest = line.partition(" ")
        columns[name] = rest.strip().upper()
    return columns, keys


def normalise_default(value: str | None) -> str | None:
    """'0.000' and '0' are the same default; so are 'INFO' and INFO."""
    if value is None:
        return None
    value = value.strip().strip("'").upper()
    try:
        return f"{float(value):g}"
    except ValueError:
        return value


def schema_default(definition: str) -> str | None:
    found = DEFAULT_RE.search(definition)
    return normalise_default(found.group(1)) if found else None


def model_default(column) -> str | None:
    if column.server_default is None:
        return None
    text = str(column.server_default.arg).strip()
    found = re.match(r"(CURRENT_TIMESTAMP|'[^']*'|[-\d.]+)", text)
    return normalise_default(found.group(1) if found else text)


def main() -> int:
    configure_mappers()
    dialect = mysql.dialect()
    sql = SCHEMA.read_text(encoding="utf-8")
    drift: list[str] = []

    for table_name, table in sorted(Base.metadata.tables.items()):
        columns, keys = parse_table(sql, table_name)

        only_schema = set(columns) - {c.name for c in table.columns}
        only_model = {c.name for c in table.columns} - set(columns)
        drift += [f"{table_name}.{c}: in schema.sql, not in the model" for c in sorted(only_schema)]
        drift += [f"{table_name}.{c}: in the model, not in schema.sql" for c in sorted(only_model)]

        for column in table.columns:
            definition = columns.get(column.name)
            if definition is None:
                continue

            want, got = schema_default(definition), model_default(column)
            if want != got:
                drift.append(f"{table_name}.{column.name}: default schema={want!r} model={got!r}")

            if ("NOT NULL" not in definition) != column.nullable:
                drift.append(f"{table_name}.{column.name}: nullability differs")

            compiled = column.type.compile(dialect=dialect).upper()
            if ("UNSIGNED" in definition) != ("UNSIGNED" in compiled):
                drift.append(f"{table_name}.{column.name}: UNSIGNED differs")

        declared = (
            {index.name for index in table.indexes}
            | {constraint.name for constraint in table.constraints}
            | {fk.constraint.name for col in table.columns for fk in col.foreign_keys}
        )
        for key in keys:
            found = KEY_NAME_RE.match(key)
            if found and found.group(1) not in declared:
                drift.append(f"{table_name}: named key {found.group(1)} missing from the model")

    tables = len(Base.metadata.tables)
    if drift:
        print(f"DRIFT - {len(drift)} difference(s) across {tables} tables:\n")
        for line in drift:
            print(f"  {line}")
        return 1

    print(f"OK - {tables} tables match database/schema.sql (columns, defaults, nullability, UNSIGNED, named keys)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
