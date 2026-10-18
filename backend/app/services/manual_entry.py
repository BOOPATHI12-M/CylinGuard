"""Constants for the manual weight-entry page.

A weight somebody typed on a phone is not a measurement, and the few fields that
can carry that distinction are defined here rather than repeated as string
literals across the route, the registration script, the offline sweep and the
tests. `sensor_readings` has no device column, so these values are the only
trace a typed reading leaves anywhere a reader can see it.
"""

# The device a typed reading is attributed to. Registered on a cylinder alongside
# the real ESP32, so the dashboard's device card names the phone after you type a
# value instead of implying a board reported.
MANUAL_DEVICE_CODE = "PHONE-MANUAL-001"

# Sent as `firmware_version` and `wifi_status`. Both are stored on the device row
# and shown on the dashboard, which makes them the one place the UI can say this
# number came from a person.
MANUAL_FIRMWARE = "manual"
MANUAL_WIFI_STATUS = "MANUAL"

# `gas_sensor_value` is required by SensorPacket and the schema forbids extra or
# missing fields, so the page has to send something. Zero is the only value that
# cannot manufacture a safety conclusion: the leak check is `value >= threshold`
# (700 by default), so at 0 the anomaly ladder can never escalate past
# UNUSUAL_CONSUMPTION and no buzzer or relay is ever commanded from a typed
# number. What it cannot fix is that `gas.status` still reads SAFE for these
# readings, asserting a measurement nobody made - which is why the page says so
# in plain words.
MANUAL_GAS_SENSOR_VALUE = 0
