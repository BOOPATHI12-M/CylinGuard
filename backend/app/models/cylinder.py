from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    DECIMAL,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.columns import UnsignedInt


class Cylinder(Base):
    __tablename__ = "cylinders"
    __table_args__ = (
        UniqueConstraint("cylinder_code", name="uq_cylinders_code"),
        Index("ix_cylinders_user", "user_id"),
        CheckConstraint("capacity_kg > 0", name="ck_cylinders_capacity"),
        CheckConstraint("empty_weight_kg >= 0", name="ck_cylinders_empty"),
    )

    id: Mapped[int] = mapped_column(UnsignedInt, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        UnsignedInt,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_cylinders_user"),
        nullable=False,
    )
    cylinder_code: Mapped[str] = mapped_column(String(64), nullable=False)
    empty_weight_kg: Mapped[Decimal] = mapped_column(
        DECIMAL(6, 3), nullable=False, default=Decimal("15.000"), server_default=text("15.000")
    )
    capacity_kg: Mapped[Decimal] = mapped_column(
        DECIMAL(6, 3), nullable=False, default=Decimal("14.200"), server_default=text("14.200")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="cylinders")  # noqa: F821
    device: Mapped[Optional["Device"]] = relationship(  # noqa: F821
        back_populates="cylinder",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    setting: Mapped[Optional["Setting"]] = relationship(  # noqa: F821
        back_populates="cylinder",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    readings: Mapped[List["SensorReading"]] = relationship(  # noqa: F821
        back_populates="cylinder", cascade="all, delete-orphan", passive_deletes=True
    )
    consumption_records: Mapped[List["ConsumptionRecord"]] = relationship(  # noqa: F821
        back_populates="cylinder", cascade="all, delete-orphan", passive_deletes=True
    )
    predictions: Mapped[List["Prediction"]] = relationship(  # noqa: F821
        back_populates="cylinder", cascade="all, delete-orphan", passive_deletes=True
    )
    alerts: Mapped[List["Alert"]] = relationship(  # noqa: F821
        back_populates="cylinder", cascade="all, delete-orphan", passive_deletes=True
    )
    safety_events: Mapped[List["SafetyEvent"]] = relationship(  # noqa: F821
        back_populates="cylinder", cascade="all, delete-orphan", passive_deletes=True
    )
