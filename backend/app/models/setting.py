from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DECIMAL,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Setting(Base):
    """Per-cylinder tunables. Deliberately holds nothing secret - this row is
    exposed verbatim to the Settings page."""

    __tablename__ = "settings"
    __table_args__ = (UniqueConstraint("cylinder_id", name="uq_settings_cylinder"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cylinder_id: Mapped[int] = mapped_column(
        ForeignKey("cylinders.id", ondelete="CASCADE"), nullable=False
    )
    # percentage of capacity
    low_lpg_threshold: Mapped[Decimal] = mapped_column(
        DECIMAL(5, 2), nullable=False, default=Decimal("20.00")
    )
    critical_lpg_threshold: Mapped[Decimal] = mapped_column(
        DECIMAL(5, 2), nullable=False, default=Decimal("10.00")
    )
    # raw MQ-6 ADC value
    gas_leakage_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=700)
    # percent above historical average that counts as abnormal
    anomaly_threshold: Mapped[Decimal] = mapped_column(
        DECIMAL(5, 2), nullable=False, default=Decimal("60.00")
    )
    # seconds between ESP32 transmissions
    measurement_interval: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    # days-left value at which a refill is recommended
    prediction_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    demo_mode: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    cylinder: Mapped["Cylinder"] = relationship(back_populates="setting")  # noqa: F821
