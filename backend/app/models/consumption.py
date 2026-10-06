from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.columns import UnsignedBigInt, UnsignedInt


class ConsumptionRecord(Base):
    """One row per cylinder per day."""

    __tablename__ = "consumption_records"
    __table_args__ = (
        UniqueConstraint("cylinder_id", "record_date", name="uq_consumption_cyl_date"),
        Index("ix_consumption_cylinder_ts", "cylinder_id", "timestamp"),
        CheckConstraint("consumption_kg >= 0", name="ck_consumption_nonneg"),
    )

    id: Mapped[int] = mapped_column(UnsignedBigInt, primary_key=True, autoincrement=True)
    cylinder_id: Mapped[int] = mapped_column(
        UnsignedInt,
        ForeignKey("cylinders.id", ondelete="CASCADE", name="fk_consumption_cylinder"),
        nullable=False,
    )
    record_date: Mapped[date] = mapped_column(Date, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumption_kg: Mapped[Decimal] = mapped_column(
        DECIMAL(7, 3), nullable=False, default=Decimal("0.000"), server_default=text("0.000")
    )
    daily_average_kg: Mapped[Decimal] = mapped_column(
        DECIMAL(7, 3), nullable=False, default=Decimal("0.000"), server_default=text("0.000")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    cylinder: Mapped["Cylinder"] = relationship(  # noqa: F821
        back_populates="consumption_records"
    )
