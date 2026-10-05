from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import DECIMAL, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Cylinder(Base):
    __tablename__ = "cylinders"
    __table_args__ = (Index("ix_cylinders_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    cylinder_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    empty_weight_kg: Mapped[Decimal] = mapped_column(
        DECIMAL(6, 3), nullable=False, default=Decimal("15.000")
    )
    capacity_kg: Mapped[Decimal] = mapped_column(
        DECIMAL(6, 3), nullable=False, default=Decimal("14.200")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="cylinders")  # noqa: F821
    device: Mapped[Optional["Device"]] = relationship(  # noqa: F821
        back_populates="cylinder", cascade="all, delete-orphan", uselist=False
    )
    setting: Mapped[Optional["Setting"]] = relationship(  # noqa: F821
        back_populates="cylinder", cascade="all, delete-orphan", uselist=False
    )
    readings: Mapped[List["SensorReading"]] = relationship(  # noqa: F821
        back_populates="cylinder", cascade="all, delete-orphan"
    )
