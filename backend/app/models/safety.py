from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SafetyEvent(Base):
    """A recorded safety state change.

    buzzer_status / relay_status record what the backend actually commanded or
    the device actually reported - never an assumption about the physical world.
    """

    __tablename__ = "safety_events"
    __table_args__ = (Index("ix_safety_cylinder_created", "cylinder_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cylinder_id: Mapped[int] = mapped_column(
        ForeignKey("cylinders.id", ondelete="CASCADE"), nullable=False
    )
    gas_value: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False)
    buzzer_status: Mapped[str] = mapped_column(String(16), nullable=False, default="OFF")
    relay_status: Mapped[str] = mapped_column(String(16), nullable=False, default="NORMAL")
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
