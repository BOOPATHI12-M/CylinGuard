"""Register the phone manual-entry device on a cylinder.

A weight typed at /manual is posted as a device, and the ingest endpoint refuses an
unregistered device_code rather than creating one - so this has to exist before the
page will work. It is a separate script rather than part of seed.py because seed.py
produces the demo dataset everyone gets, and a bench workaround does not belong in
it.

The device sits alongside the real ESP32 on the same cylinder, which is legal:
ix_devices_cylinder is non-unique. It does mean `monitoring.get_device` must already
handle two devices - without that it raises MultipleResultsFound and takes out the
dashboard, the cylinder list and the WebSocket frame together.

Usage:
    python scripts/register_manual_device.py
    python scripts/register_manual_device.py --cylinder-id 2
    python scripts/register_manual_device.py --device-code PHONE-KITCHEN
"""

import argparse
import pathlib
import socket
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from _dbguard import guarded  # noqa: E402
from app.database import session_scope  # noqa: E402
from app.models import Cylinder, Device  # noqa: E402
from app.services.manual_entry import (  # noqa: E402
    MANUAL_DEVICE_CODE,
    MANUAL_FIRMWARE,
)


def lan_address() -> str:
    """This machine's address on the LAN, for the URL to open on the phone.

    Connecting a UDP socket sends nothing; it just asks the routing table which
    local address would be used to reach the outside, which is the one the phone
    can reach. `gethostbyname(gethostname())` returns 127.0.0.1 on many Windows
    setups, which is exactly the answer that does not help here.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        return probe.getsockname()[0]
    except OSError:
        return "<laptop-ip>"
    finally:
        probe.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cylinder-id", type=int, default=1)
    parser.add_argument("--device-code", default=MANUAL_DEVICE_CODE)
    args = parser.parse_args()

    code = args.device_code.strip()
    if not code:
        print("ERROR: --device-code must not be blank", file=sys.stderr)
        return 1

    with session_scope() as db:
        cylinder = db.get(Cylinder, args.cylinder_id)
        if cylinder is None:
            print(
                f"ERROR: no cylinder with id {args.cylinder_id}. Run scripts/seed.py "
                "first, or pass --cylinder-id.",
                file=sys.stderr,
            )
            return 1

        existing = db.execute(
            select(Device).where(Device.device_code == code)
        ).scalar_one_or_none()

        if existing is not None:
            if existing.cylinder_id != cylinder.id:
                # Re-pointing it would silently move every future typed reading to a
                # different cylinder, so this stops instead.
                print(
                    f"ERROR: device {code} already exists on cylinder "
                    f"{existing.cylinder_id}, not {cylinder.id}. Delete it or pass a "
                    "different --device-code.",
                    file=sys.stderr,
                )
                return 1
            print(f"Device {code} is already registered on cylinder {cylinder.id}.")
        else:
            db.add(
                Device(
                    cylinder_id=cylinder.id,
                    device_code=code,
                    wifi_status="UNKNOWN",
                    # Deliberately NULL: it has never reported, so the dashboard
                    # keeps showing the ESP32 until something is actually typed.
                    last_seen=None,
                    firmware_version=MANUAL_FIRMWARE,
                )
            )
            db.flush()
            print(f"Registered {code} on cylinder {cylinder.id}.")

        empty = float(cylinder.empty_weight_kg)
        capacity = float(cylinder.capacity_kg)

        print()
        print(f"  cylinder        {cylinder.cylinder_code} (id {cylinder.id})")
        print(f"  empty weight    {empty:.3f} kg")
        print(f"  capacity        {capacity:.3f} kg")
        print(f"  a full cylinder weighs about {empty + capacity:.1f} kg on the scale")
        print()
        print("  The page asks for GROSS weight - cylinder and gas together. Anything")
        print(f"  at or below {empty:.1f} kg reads as 0% because that is the empty")
        print("  cylinder, not gas.")
        print()
        print("Open this on the phone (same network as the laptop):")
        print(f"  http://{lan_address()}:8000/manual")
        print()
        print("The backend must be running with --host 0.0.0.0, and Windows Firewall")
        print("must allow inbound TCP 8000 on the private profile.")

    return 0


if __name__ == "__main__":
    raise SystemExit(guarded(main))
