"""API routers.

Collected in one place so main.py registers them with a loop rather than a list of
imports that has to be edited twice whenever a router is added.
"""

from app.routes import (
    alerts,
    auth,
    consumption,
    dashboard,
    demo,
    history,
    iot,
    prediction,
    safety,
    settings,
    ws,
)

# Order is the order they appear in /docs.
ROUTERS = [
    auth.router,
    dashboard.router,
    consumption.router,
    prediction.router,
    safety.router,
    history.router,
    alerts.router,
    settings.router,
    demo.router,
    iot.router,
    ws.router,
]

__all__ = ["ROUTERS"]
