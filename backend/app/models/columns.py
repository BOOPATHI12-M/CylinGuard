"""Shared column types.

`database/schema.sql` declares every primary key and foreign key as UNSIGNED.
SQLAlchemy's generic `Integer` / `BigInteger` emit *signed* columns, so without
these aliases the models would describe a different table than the one the
database actually has.

schema.sql remains the single source of DDL truth - `Base.metadata.create_all()`
is deliberately never called. These aliases exist so the models do not *lie*
about the schema, which matters to anyone reading them.
"""

from sqlalchemy.dialects.mysql import BIGINT, INTEGER

#: INT UNSIGNED - the PK of users/cylinders/devices/settings, and every FK to them.
UnsignedInt = INTEGER(unsigned=True)

#: BIGINT UNSIGNED - the PK of the high-volume tables (readings, consumption,
#: predictions, alerts, safety_events).
UnsignedBigInt = BIGINT(unsigned=True)
