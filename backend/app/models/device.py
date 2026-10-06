from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.columns import UnsignedInt


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("device_code", name="uq_devices_code"),
        Index("ix_devices_cylinder", "cylinder_id"),
        Index("ix_devices_last_seen", "last_seen"),
    )

    id: Mapped[int] = mapped_column(UnsignedInt, primary_key=True, autoincrement=True)
    cylinder_id: Mapped[int] = mapped_column(
        UnsignedInt,
        ForeignKey("cylinders.id", ondelete="CASCADE", name="fk_devices_cylinder"),
        nullable=False,
    )
    device_code: Mapped[str] = mapped_column(String(64), nullable=False)
    wifi_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="UNKNOWN", server_default=text("'UNKNOWN'")
    )
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    firmware_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    cylinder: Mapped["Cylinder"] = relationship(back_populates="device")  # noqa: F821

    def status_at(self, now: datetime, offline_after_seconds: int) -> str:
        """ONLINE / OFFLINE derived from last_seen - never stored stale."""
        if self.last_seen is None:
            return "OFFLINE"
        age = (now - self.last_seen).total_seconds()
        return "ONLINE" if age <= offline_after_seconds else "OFFLINE"
