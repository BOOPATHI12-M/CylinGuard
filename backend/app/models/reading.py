from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.columns import UnsignedBigInt, UnsignedInt


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (
        Index("ix_readings_cylinder_ts", "cylinder_id", "timestamp"),
        Index("ix_readings_ts", "timestamp"),
        CheckConstraint("total_weight_kg >= 0", name="ck_readings_weight"),
        CheckConstraint("gas_sensor_value >= 0", name="ck_readings_gas"),
    )

    id: Mapped[int] = mapped_column(UnsignedBigInt, primary_key=True, autoincrement=True)
    cylinder_id: Mapped[int] = mapped_column(
        UnsignedInt,
        ForeignKey("cylinders.id", ondelete="CASCADE", name="fk_readings_cylinder"),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_weight_kg: Mapped[Decimal] = mapped_column(DECIMAL(7, 3), nullable=False)
    gas_sensor_value: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    device_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ONLINE", server_default=text("'ONLINE'")
    )
    is_simulated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    cylinder: Mapped["Cylinder"] = relationship(back_populates="readings")  # noqa: F821
