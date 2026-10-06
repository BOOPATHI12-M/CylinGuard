from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DECIMAL,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.columns import UnsignedBigInt, UnsignedInt


class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = (
        Index("ix_predictions_cylinder_ts", "cylinder_id", "timestamp"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_predictions_conf"),
    )

    id: Mapped[int] = mapped_column(UnsignedBigInt, primary_key=True, autoincrement=True)
    cylinder_id: Mapped[int] = mapped_column(
        UnsignedInt,
        ForeignKey("cylinders.id", ondelete="CASCADE", name="fk_predictions_cylinder"),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    remaining_kg: Mapped[Decimal] = mapped_column(DECIMAL(7, 3), nullable=False)
    remaining_days: Mapped[Decimal] = mapped_column(DECIMAL(6, 2), nullable=False)
    predicted_depletion_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    confidence: Mapped[Decimal] = mapped_column(
        DECIMAL(4, 3), nullable=False, default=Decimal("0.000"), server_default=text("0.000")
    )
    # "ML" when the RandomForest produced the estimate, "FALLBACK" when the
    # arithmetic estimate was used because history was too thin.
    method: Mapped[str] = mapped_column(
        String(16), nullable=False, default="FALLBACK", server_default=text("'FALLBACK'")
    )
    sample_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )

    cylinder: Mapped["Cylinder"] = relationship(back_populates="predictions")  # noqa: F821
