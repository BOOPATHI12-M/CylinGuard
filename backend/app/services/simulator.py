"""Demo simulator: plausible readings with no hardware attached.

The simulator does not write to the database directly. It builds a `SensorPacket` and
feeds it through `ingest.process(..., simulated=True)`, so demo data goes through the
same validation, smoothing, refill detection, anomaly ladder, safety transitions and
prediction as a real ESP32 packet. A simulator with its own shortcut path would drift
from the real one and the demo would stop proving anything.

**Time is compressed, deliberately.** A real household burns about 0.46 kg a day,
which at a five-second tick is 0.000027 kg - invisible, and far below the 0.02 kg
noise floor, so it would be discarded as jitter and the dashboard would never move.
Each tick therefore represents a longer stretch of simulated time and consumes
0.03-0.08 kg. Every individual step stays well inside the plausible band: above the
noise floor so it registers, and far below the 2 kg threshold that marks a refill or
an implausible drop. Nothing the simulator emits is a jump a real cylinder could not
make between two readings.

Three scenarios, switched live:

* `NORMAL` - steady draw with meal-time weighting and load-cell jitter.
* `LOW_LPG` - drops the cylinder to just under the low threshold, then continues
  normally, so the LOW badge and the refill card can be shown.
* `LEAK_DETECTED` - holds the MQ-6 above its threshold, which drives the safety
  transition, the critical alert and the emergency banner.

The `LOW_LPG` setup step is a large one-off fall. The pipeline classifies that as
`IMPLAUSIBLE_DROP` and refuses to count it as consumption, which is exactly right:
the level on screen moves, the daily average and the depletion estimate stay honest.
"""

import asyncio
import logging
import random
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.database import session_scope
from app.models import Cylinder, Device, Setting
from app.schemas.ingest import SensorPacket
from app.services import demo_state, ingest, monitoring
from app.websocket.manager import manager

logger = logging.getLogger("cylinguard.simulator")

# Per-tick consumption band, in kg. Above MIN_MEANINGFUL_DELTA_KG (0.02) so it is not
# filtered as noise; far below REFILL_DELTA_KG (2.0) so it is never mistaken for a
# cylinder change.
TICK_MIN_KG = 0.030
TICK_MAX_KG = 0.080

# Clean-air MQ-6 baseline, matching the seeder, and the leak-scenario reading.
BASELINE_GAS = 180
GAS_JITTER = 18
LEAK_GAS = 820

# Load-cell jitter, in kg. Same order as the real hardware the seeder models.
NOISE_SIGMA = 0.015

# How close to the low threshold the LOW_LPG scenario parks the cylinder.
LOW_SCENARIO_MARGIN = Decimal("0.90")

_rng = random.Random()
_task: Optional[asyncio.Task] = None


def meal_weighting(now: datetime) -> float:
    """Heavier draw around 7am, noon and 7pm, so the chart has a shape."""
    peaks = (7, 12, 19)
    closeness = min(abs(now.hour - peak) for peak in peaks)
    return {0: 1.6, 1: 1.2}.get(closeness, 0.7)


def next_weight(
    current_total: Decimal, empty_weight: Decimal, now: datetime
) -> Decimal:
    """One plausible step down, floored at the empty cylinder weight."""
    burn = _rng.uniform(TICK_MIN_KG, TICK_MAX_KG) * meal_weighting(now)
    noise = _rng.gauss(0, NOISE_SIGMA)
    nxt = Decimal(f"{float(current_total) - burn + noise:.3f}")
    return max(Decimal(empty_weight), nxt)


def eligible_cylinders(db: Session) -> List[Tuple[Cylinder, Device, Setting]]:
    """Cylinders with demo mode on, a registered device, and no real hardware yet."""
    rows = db.execute(
        select(Cylinder, Device, Setting)
        .join(Device, Device.cylinder_id == Cylinder.id)
        .join(Setting, Setting.cylinder_id == Cylinder.id)
        .where(Setting.demo_mode.is_(True))
    ).all()
    return [
        (cylinder, device, setting)
        for cylinder, device, setting in rows
        if not demo_state.state_for(cylinder.id).suspended
    ]


def build_packet(
    db: Session, cylinder: Cylinder, device: Device, setting: Setting
) -> SensorPacket:
    """The next simulated reading for one cylinder."""
    state = demo_state.state_for(cylinder.id)
    now = datetime.now()

    latest = monitoring.latest_reading(db, cylinder.id)
    current = (
        Decimal(latest.total_weight_kg)
        if latest is not None
        # Nothing recorded yet: start a little under full, as the seeder does.
        else Decimal(cylinder.empty_weight_kg) + Decimal(cylinder.capacity_kg) * Decimal("0.95")
    )

    gas = max(0, int(_rng.gauss(BASELINE_GAS, GAS_JITTER)))

    if state.scenario == demo_state.LEAK_DETECTED:
        # Hold the MQ-6 above its threshold. Weight keeps draining normally - a leak
        # does not stop the burner.
        gas = max(int(setting.gas_leakage_threshold) + 60, LEAK_GAS)

    if state.scenario == demo_state.LOW_LPG and state.scenario_pending:
        # One-off setup: park just under the low threshold so the LOW badge shows.
        target_percent = Decimal(setting.low_lpg_threshold) * LOW_SCENARIO_MARGIN
        remaining = Decimal(cylinder.capacity_kg) * target_percent / Decimal("100")
        weight = (Decimal(cylinder.empty_weight_kg) + remaining).quantize(Decimal("0.001"))
    else:
        weight = next_weight(current, cylinder.empty_weight_kg, now)

    # An empty cylinder would otherwise sit at 0% forever and the demo would stall.
    if weight <= Decimal(cylinder.empty_weight_kg) + Decimal("0.050"):
        weight = (
            Decimal(cylinder.empty_weight_kg) + Decimal(cylinder.capacity_kg) * Decimal("0.98")
        ).quantize(Decimal("0.001"))
        logger.info("cylinder=%s demo cylinder exhausted - simulating a refill", cylinder.id)

    return SensorPacket(
        device_id=device.device_code,
        total_weight_kg=float(weight),
        gas_sensor_value=gas,
        timestamp=now,
    )


def tick_once() -> int:
    """Generate and ingest one reading per eligible cylinder. Returns how many.

    Synchronous, so the caller runs it in a threadpool: SQLAlchemy is blocking and the
    event loop also has WebSocket frames to deliver.
    """
    processed = 0
    with session_scope() as db:
        for cylinder, device, setting in eligible_cylinders(db):
            packet = build_packet(db, cylinder, device, setting)
            try:
                ingest.process(db, packet, simulated=True)
            except Exception:
                logger.exception("simulator tick failed for cylinder=%s", cylinder.id)
                continue
            demo_state.note_tick(cylinder.id)
            processed += 1
    return processed


def cylinders_to_broadcast() -> List[int]:
    with session_scope() as db:
        return [c.id for c, _, _ in eligible_cylinders(db)]


async def run_forever() -> None:
    """The background loop. Cancelled on shutdown by the app lifespan."""
    interval = max(1, settings.demo_tick_seconds)
    logger.info("demo simulator started, tick=%ss", interval)
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                targets = await run_in_threadpool(cylinders_to_broadcast)
                if not targets:
                    continue
                await run_in_threadpool(tick_once)

                # Push the new state to anyone watching, exactly as the ingest route
                # does, so a demo dashboard updates without polling.
                for cylinder_id in targets:
                    payload = await run_in_threadpool(_dashboard_for, cylinder_id)
                    if payload is not None:
                        await manager.broadcast(cylinder_id, payload)
            except Exception:
                # A failed tick must not kill the loop, or demo mode would silently
                # stop for the rest of the process.
                logger.exception("demo simulator tick failed")
    except asyncio.CancelledError:
        logger.info("demo simulator stopped")
        raise


def _dashboard_for(cylinder_id: int) -> Optional[dict]:
    with session_scope() as db:
        cylinder = db.get(Cylinder, cylinder_id)
        if cylinder is None:
            return None
        payload = monitoring.build_dashboard(db, cylinder)
        return payload.model_dump(mode="json") if payload is not None else None


def start() -> Optional[asyncio.Task]:
    """Start the loop, unless it is switched off or already running."""
    global _task
    if not settings.demo_simulator_enabled:
        logger.info(
            "demo simulator disabled (DEMO_SIMULATOR_ENABLED is false) - no readings "
            "will be generated"
        )
        return None
    if _task is not None and not _task.done():
        return _task
    _task = asyncio.create_task(run_forever(), name="demo-simulator")
    return _task


async def stop() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except asyncio.CancelledError:
        pass
    _task = None


def is_running() -> bool:
    return _task is not None and not _task.done()
