import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.columns import UnsignedBigInt, UnsignedInt


class AlertSeverity(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_cylinder_created", "cylinder_id", "created_at"),
        Index("ix_alerts_unread", "cylinder_id", "is_read"),
    )

    id: Mapped[int] = mapped_column(UnsignedBigInt, primary_key=True, autoincrement=True)
    cylinder_id: Mapped[int] = mapped_column(
        UnsignedInt,
        ForeignKey("cylinders.id", ondelete="CASCADE", name="fk_alerts_cylinder"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(48), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, native_enum=True, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AlertSeverity.INFO,
        server_default=text("'INFO'"),
    )
    message: Mapped[str] = mapped_column(String(512), nullable=False)
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    cylinder: Mapped["Cylinder"] = relationship(back_populates="alerts")  # noqa: F821
