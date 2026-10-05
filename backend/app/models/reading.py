from datetime import datetime
from decimal import Decimal

from sqlalchemy import DECIMAL, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (
        Index("ix_readings_cylinder_ts", "cylinder_id", "timestamp"),
        Index("ix_readings_ts", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cylinder_id: Mapped[int] = mapped_column(
        ForeignKey("cylinders.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_weight_kg: Mapped[Decimal] = mapped_column(DECIMAL(7, 3), nullable=False)
    gas_sensor_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    device_status: Mapped[str] = mapped_column(String(16), nullable=False, default="ONLINE")
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    cylinder: Mapped["Cylinder"] = relationship(back_populates="readings")  # noqa: F821
