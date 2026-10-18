"""API routers.

Collected in one place so main.py registers them with a loop rather than a list of
imports that has to be edited twice whenever a router is added.
"""

from app.routes import (
    alerts,
    auth,
    consumption,
    cylinders,
    dashboard,
    demo,
    history,
    iot,
    manual,
    ml,
    prediction,
    safety,
    settings,
    ws,
)

# Order is the order they appear in /docs.
ROUTERS = [
    auth.router,
    cylinders.router,
    dashboard.router,
    consumption.router,
    prediction.router,
    safety.router,
    history.router,
    alerts.router,
    settings.router,
    demo.router,
    ml.router,
    iot.router,
    ws.router,
    # Last: a human page, not an API. Keeps it out of the way in /docs.
    manual.router,
]

__all__ = ["ROUTERS"]
