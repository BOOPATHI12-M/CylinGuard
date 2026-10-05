from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ConsumptionRecord(Base):
    """One row per cylinder per day."""

    __tablename__ = "consumption_records"
    __table_args__ = (
        UniqueConstraint("cylinder_id", "record_date", name="uq_consumption_cyl_date"),
        Index("ix_consumption_cylinder_ts", "cylinder_id", "timestamp"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cylinder_id: Mapped[int] = mapped_column(
        ForeignKey("cylinders.id", ondelete="CASCADE"), nullable=False
    )
    record_date: Mapped[date] = mapped_column(Date, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumption_kg: Mapped[Decimal] = mapped_column(
        DECIMAL(7, 3), nullable=False, default=Decimal("0.000")
    )
    daily_average_kg: Mapped[Decimal] = mapped_column(
        DECIMAL(7, 3), nullable=False, default=Decimal("0.000")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
