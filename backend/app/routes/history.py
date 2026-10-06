"""Paginated reading history.

Pagination is server-side and non-negotiable here: `sensor_readings` already holds
2,882 rows after one seeded month and grows by one row every measurement interval
in production. The LIMIT/OFFSET and the COUNT both execute in MySQL.

Each row is enriched with the derived remaining kg, percentage and gas word, so the
table does not duplicate the tare-weight arithmetic in the frontend.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_owned_cylinder
from app.models import Cylinder
from app.schemas.monitoring import HistoryPage, ReadingResponse
from app.services import lpg, monitoring

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/{cylinder_id}", response_model=HistoryPage)
def get_history(
    cylinder: Cylinder = Depends(get_owned_cylinder),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=50, ge=1, le=200, description="Rows per page"),
    since: Optional[datetime] = Query(
        default=None, description="Only readings at or after this timestamp"
    ),
    db: Session = Depends(get_db),
) -> HistoryPage:
    setting = monitoring.get_settings_row(db, cylinder.id)
    threshold = int(setting.gas_leakage_threshold) if setting else 700

    rows, total = monitoring.history_page(db, cylinder.id, page, size, since)

    items = []
    for row in rows:
        remaining = lpg.remaining_kg(row.total_weight_kg, cylinder.empty_weight_kg)
        items.append(
            ReadingResponse(
                id=row.id,
                timestamp=row.timestamp,
                total_weight_kg=row.total_weight_kg,
                remaining_kg=remaining,
                percentage=lpg.percentage(remaining, cylinder.capacity_kg),
                gas_sensor_value=row.gas_sensor_value,
                gas_status=monitoring.gas_status_word(row.gas_sensor_value, threshold),
                device_status=row.device_status,
                is_simulated=row.is_simulated,
            )
        )

    return HistoryPage(
        cylinder_id=cylinder.id,
        items=items,
        total=total,
        page=page,
        size=size,
        # Ceiling division, and at least 1 so an empty result still reports page 1 of 1.
        pages=max(1, -(-total // size)),
    )
