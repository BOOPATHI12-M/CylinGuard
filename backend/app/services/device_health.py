"""Device offline detection (spec §33).

A device is offline when it has not reported for longer than its own expected
reporting interval allows. That state is *derived* from `last_seen` on every read
rather than stored, so a crashed process cannot leave a device showing ONLINE
forever.

The threshold is **per device**, not global. `DEVICE_OFFLINE_SECONDS` alone cannot
work: the Settings page lets a user set `measurement_interval` as high as 86,400s,
and a device legitimately reporting once an hour would be declared offline within
two minutes - a false alert on every sweep, forever. So the threshold is whichever
is longer: the global floor, or `OFFLINE_INTERVAL_MULTIPLE` reporting intervals.
Missing several consecutive reports is the thing that actually means offline, and
that is a multiple of the interval, not a constant.

What does need recording is whether the user has already been told. The rule is **one
alert per offline episode, not one per sweep**: at a 30-second sweep a device
unplugged overnight would otherwise generate 1,440 identical warnings, and an alert
list that cries wolf gets ignored - including when it reports a leak.

That is decided without any extra state. An alert has already been raised for the
current episode if a DEVICE_OFFLINE alert exists with `created_at` later than the
device's `last_seen`. When the device reports again, `last_seen` moves forward, every
old alert falls behind it, and the next episode can alert once more. The coming-back
direction is handled in the ingest pipeline, because arriving data *is* that
transition.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import session_scope
from app.models import Alert, AlertSeverity, Device, Setting
from app.services.manual_entry import MANUAL_DEVICE_CODE

logger = logging.getLogger("cylinguard.devices")

ALERT_TYPE = "DEVICE_OFFLINE"

# How many reports a device may miss before it counts as offline. Four is chosen so a
# single dropped packet - a brief WiFi reassociation, one failed POST retry - is never
# enough on its own. One missed report is normal; four in a row is a fault.
OFFLINE_INTERVAL_MULTIPLE = 4


def offline_threshold_seconds(interval: Optional[int]) -> int:
    """How long this device may stay quiet before it is offline.

    `interval` is the cylinder's `measurement_interval`, or None when no settings row
    exists - in which case only the global floor applies.
    """
    floor = settings.device_offline_seconds
    if interval is None or interval <= 0:
        return floor
    return max(floor, interval * OFFLINE_INTERVAL_MULTIPLE)


def already_alerted(db: Session, device: Device) -> bool:
    """Whether this offline episode has already produced an alert."""
    if device.last_seen is None:
        # Never reported at all. One alert is still owed, so look for any at all.
        return (
            db.execute(
                select(Alert.id)
                .where(Alert.cylinder_id == device.cylinder_id, Alert.type == ALERT_TYPE)
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )

    return (
        db.execute(
            select(Alert.id)
            .where(
                Alert.cylinder_id == device.cylinder_id,
                Alert.type == ALERT_TYPE,
                Alert.created_at > device.last_seen,
            )
            .limit(1)
        ).scalar_one_or_none()
        is not None
    )


def sweep(
    db: Session,
    now: Optional[datetime] = None,
    cylinder_ids: Optional[Sequence[int]] = None,
) -> List[Alert]:
    """Raise one alert per newly-offline device. Returns the alerts created.

    `now` is injectable so a caller can ask "what would this look like in an hour"
    without touching the clock. `cylinder_ids` narrows the scan; the background loop
    passes neither and sweeps everything.
    """
    now = now or datetime.now()
    # Pre-filter at the global floor. The real threshold is per device and never
    # shorter than the floor, so anything offline by its own threshold is offline by
    # this one too - the SQL narrows the scan without deciding the outcome.
    floor_cutoff = now - timedelta(seconds=settings.device_offline_seconds)

    # Devices that have gone quiet, including those that never reported at all.
    where = [(Device.last_seen.is_(None)) | (Device.last_seen < floor_cutoff)]
    if cylinder_ids is not None:
        where.append(Device.cylinder_id.in_(list(cylinder_ids)))

    # The manual-entry device is a person with a phone, not hardware that can be
    # unplugged. It is quiet between entries by definition, so sweeping it would
    # raise an alert per typing session telling the user to "check power and WiFi"
    # on a device that has neither - and an alert list that cries wolf gets ignored,
    # including when it reports a leak.
    where.append(Device.device_code != MANUAL_DEVICE_CODE)

    # Outer join: a cylinder with no settings row still has a device worth sweeping.
    candidates = list(
        db.execute(
            select(Device, Setting.measurement_interval)
            .outerjoin(Setting, Setting.cylinder_id == Device.cylinder_id)
            .where(*where)
        )
    )

    created: List[Alert] = []
    for device, interval in candidates:
        threshold = offline_threshold_seconds(interval)

        if device.last_seen is not None and device.last_seen >= now - timedelta(
            seconds=threshold
        ):
            # Quiet, but not yet beyond what its own reporting interval allows.
            continue

        if already_alerted(db, device):
            continue

        if device.last_seen is None:
            detail = "has never reported"
        else:
            quiet_for = int((now - device.last_seen).total_seconds())
            detail = f"last reported {quiet_for}s ago"

        alert = Alert(
            cylinder_id=device.cylinder_id,
            type=ALERT_TYPE,
            severity=AlertSeverity.WARNING,
            message=(
                f"Device {device.device_code} is offline - {detail}, beyond the "
                f"{threshold}s threshold. Readings shown are the "
                "last received, not current. Check power and WiFi."
            ),
        )
        # wifi_status is the device's own last report, so it is marked unknown rather
        # than claimed to be disconnected - we cannot see the device's radio, only its
        # silence.
        device.wifi_status = "UNKNOWN"
        db.add(alert)
        created.append(alert)
        logger.info("cylinder=%s device %s offline", device.cylinder_id, device.device_code)

    if created:
        db.flush()
    return created


def sweep_once() -> int:
    """Run one sweep in its own session. Returns how many alerts were raised."""
    with session_scope() as db:
        return len(sweep(db))
