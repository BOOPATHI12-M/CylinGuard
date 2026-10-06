from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.columns import UnsignedInt


class Setting(Base):
    """Per-cylinder tunables. Deliberately holds nothing secret - this row is
    exposed verbatim to the Settings page."""

    __tablename__ = "settings"
    __table_args__ = (
        UniqueConstraint("cylinder_id", name="uq_settings_cylinder"),
        CheckConstraint("gas_leakage_threshold > 0", name="ck_settings_gas"),
        CheckConstraint("measurement_interval > 0", name="ck_settings_interval"),
    )

    id: Mapped[int] = mapped_column(UnsignedInt, primary_key=True, autoincrement=True)
    cylinder_id: Mapped[int] = mapped_column(
        UnsignedInt,
        ForeignKey("cylinders.id", ondelete="CASCADE", name="fk_settings_cylinder"),
        nullable=False,
    )
    # percentage of capacity
    low_lpg_threshold: Mapped[Decimal] = mapped_column(
        DECIMAL(5, 2), nullable=False, default=Decimal("20.00"), server_default=text("20.00")
    )
    critical_lpg_threshold: Mapped[Decimal] = mapped_column(
        DECIMAL(5, 2), nullable=False, default=Decimal("10.00"), server_default=text("10.00")
    )
    # raw MQ-6 ADC value
    gas_leakage_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=700, server_default=text("700")
    )
    # percent above historical average that counts as abnormal
    anomaly_threshold: Mapped[Decimal] = mapped_column(
        DECIMAL(5, 2), nullable=False, default=Decimal("60.00"), server_default=text("60.00")
    )
    # Seconds between ESP32 transmissions. 30s is a live-monitoring cadence: gas
    # leak detection latency is bounded by this value, so it is deliberately
    # short. Not to be confused with the seeder's history sampling interval or
    # with DEMO_TICK_SECONDS - all three are different concepts.
    measurement_interval: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default=text("30")
    )
    # days-left value at which a refill is recommended
    prediction_threshold: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default=text("5")
    )
    demo_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"),
    )

    cylinder: Mapped["Cylinder"] = relationship(back_populates="setting")  # noqa: F821
