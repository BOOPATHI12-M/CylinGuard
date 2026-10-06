"""In-process demo state, per cylinder.

A separate module from both `simulator` and `ingest` on purpose: the ingest pipeline
has to be able to say "a real packet arrived, stop simulating this cylinder", and the
simulator has to read that. If either owned the registry the two would import each
other.

What lives here is *process* state, and it resets when the server restarts:

* **scenario** - which of the three demo stories is playing. Persisting it would need
  a schema change for something that only matters while a demo is on screen.
* **suspension** - whether real hardware has taken over.

What does *not* live here is `settings.demo_mode`, the product-facing on/off switch,
which is a real column because a user expects it to survive a restart.

Suspension is deliberately sticky: once a genuine ESP32 packet arrives for a
cylinder, simulation stays off for the rest of the process unless demo mode is
explicitly re-enabled. The alternative - resuming after a quiet period - would have
the simulator start fighting a device that is merely offline, and invented readings
would appear exactly when the user most needs to see that their hardware stopped
reporting.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

NORMAL = "NORMAL"
LOW_LPG = "LOW_LPG"
LEAK_DETECTED = "LEAK_DETECTED"

SCENARIOS = (NORMAL, LOW_LPG, LEAK_DETECTED)


@dataclass
class DemoState:
    scenario: str = NORMAL
    suspended: bool = False
    suspended_at: Optional[datetime] = None
    # Set when a scenario is selected, so the simulator applies its one-off setup
    # (such as dropping to a low level) on the next tick and not on every tick.
    scenario_pending: bool = False
    ticks: int = 0
    last_tick_at: Optional[datetime] = None


_states: Dict[int, DemoState] = {}
# The registry is touched by the simulator task, by request handlers and by the
# ingest pipeline running in a threadpool, so mutations are guarded.
_lock = threading.Lock()


def state_for(cylinder_id: int) -> DemoState:
    with _lock:
        return _states.setdefault(cylinder_id, DemoState())


def note_real_packet(cylinder_id: int) -> bool:
    """Record that genuine hardware reported. Returns True if this suspended it now."""
    with _lock:
        state = _states.setdefault(cylinder_id, DemoState())
        if state.suspended:
            return False
        state.suspended = True
        state.suspended_at = datetime.now()
        return True


def resume(cylinder_id: int) -> None:
    """Clear suspension - only ever called by an explicit demo-mode enable."""
    with _lock:
        state = _states.setdefault(cylinder_id, DemoState())
        state.suspended = False
        state.suspended_at = None


def set_scenario(cylinder_id: int, scenario: str) -> DemoState:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}")
    with _lock:
        state = _states.setdefault(cylinder_id, DemoState())
        state.scenario = scenario
        state.scenario_pending = True
        return state


def note_tick(cylinder_id: int) -> None:
    with _lock:
        state = _states.setdefault(cylinder_id, DemoState())
        state.ticks += 1
        state.last_tick_at = datetime.now()
        state.scenario_pending = False


def reset(cylinder_id: Optional[int] = None) -> None:
    """Forget state. Used by tests; a whole-registry reset has no product trigger."""
    with _lock:
        if cylinder_id is None:
            _states.clear()
        else:
            _states.pop(cylinder_id, None)
