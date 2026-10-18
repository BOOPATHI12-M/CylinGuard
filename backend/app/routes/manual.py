"""The manual weight-entry page (a phone standing in for the load cell).

Serves one HTML page, on port 8000 rather than through the frontend, so a phone on
the same network can type a cylinder weight before any hardware exists. It posts to
`POST /api/iot/sensor-data` - the same endpoint the ESP32 will use - so a typed
reading goes through the real pipeline: validation, smoothing, refill
classification, the anomaly ladder, the prediction, alerts and the WebSocket
broadcast. Nothing here duplicates that work, and nothing here bypasses it.

**Unauthenticated, deliberately.** The endpoint it posts to is itself
unauthenticated, so putting a login on this form would guard the form while leaving
the door it opens wide. The real gate is `DEVICE_API_KEY`: set it and both this page
and the device have to present it. On a shared network, set it.

The page is a single self-contained string because main.py mounts no StaticFiles and
the project has no template engine. One page did not justify adding either.
"""

import html
import json
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.services import ingest as ingest_service
from app.services import monitoring
from app.services.manual_entry import (
    MANUAL_DEVICE_CODE,
    MANUAL_FIRMWARE,
    MANUAL_GAS_SENSOR_VALUE,
    MANUAL_WIFI_STATUS,
)

router = APIRouter(tags=["manual"])


def _not_registered_page(device_code: str) -> HTMLResponse:
    """A 404 that says what to do about it.

    The phone is nowhere near a terminal, so the page carries the exact command
    rather than leaving the reader to guess which script registers a device.
    """
    safe = html.escape(device_code)
    return HTMLResponse(
        status_code=404,
        content=f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Device not registered</title>
<style>
  body {{ margin:0; padding:24px; background:#0b1020; color:#e8ecf8;
         font:16px/1.6 system-ui,-apple-system,Segoe UI,sans-serif; }}
  code {{ background:#161d35; padding:2px 6px; border-radius:6px;
          font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }}
  pre {{ background:#161d35; padding:14px; border-radius:10px; overflow-x:auto; }}
  h1 {{ font-size:19px; margin:0 0 12px; }}
</style></head><body>
<h1>Device <code>{safe}</code> is not registered</h1>
<p>The server refuses to create a device for an unknown code, because an endpoint
that did would let anyone on the network fill the database with records nobody
owns.</p>
<p>Register it on the laptop:</p>
<pre>cd backend
.venv\\Scripts\\python.exe scripts\\register_manual_device.py</pre>
<p>Then reload this page.</p>
</body></html>""",
    )


@router.get("/manual", response_class=HTMLResponse)
def manual_entry_page(
    device: Optional[str] = Query(
        default=None, description="device_code to post as; defaults to the phone device"
    ),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    device_code = (device or MANUAL_DEVICE_CODE).strip()

    try:
        _device_row, cylinder = ingest_service.resolve_device(db, device_code)
    except ingest_service.UnknownDeviceError:
        return _not_registered_page(device_code)

    setting = monitoring.get_settings_row(db, cylinder.id)
    reading = monitoring.latest_reading(db, cylinder.id)

    empty = float(cylinder.empty_weight_kg)
    capacity = float(cylinder.capacity_kg)

    # The config travels in the page rather than from a second fetch: the page is
    # unauthenticated and the dashboard endpoints are not, so there is nothing it
    # could call. json.dumps inside a JSON script tag keeps the escaping honest.
    config = {
        "device_code": device_code,
        "cylinder_code": cylinder.cylinder_code,
        "empty_weight_kg": empty,
        "capacity_kg": capacity,
        "low": float(setting.low_lpg_threshold) if setting else 20.0,
        "critical": float(setting.critical_lpg_threshold) if setting else 10.0,
        # Prefilled from the last real reading, so the first thing on screen is a
        # plausible gross weight rather than a blank field inviting "8".
        "prefill_weight": float(reading.total_weight_kg) if reading else round(empty + capacity, 3),
        "gas_value": MANUAL_GAS_SENSOR_VALUE,
        "wifi_status": MANUAL_WIFI_STATUS,
        "firmware_version": MANUAL_FIRMWARE,
        # Whether to show the key field at all. The key itself is never embedded:
        # anything on the LAN can fetch this page.
        "device_key_required": bool(settings.device_api_key),
    }

    return HTMLResponse(content=_PAGE.replace("__CONFIG__", json.dumps(config)))


_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CylinGuard manual entry</title>
<style>
  :root {
    --bg:#0b1020; --card:#121a33; --line:#24304f; --ink:#e8ecf8;
    --muted:#9aa7c7; --accent:#4da3ff; --safe:#35c26b; --warn:#ffa53a;
    --danger:#ff5d5d;
  }
  * { box-sizing:border-box; }
  body { margin:0; padding:16px; background:var(--bg); color:var(--ink);
         font:16px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
  .wrap { max-width:460px; margin:0 auto; }
  h1 { font-size:18px; margin:4px 0 2px; }
  .sub { color:var(--muted); font-size:13px; margin:0 0 16px; }
  .card { background:var(--card); border:1px solid var(--line);
          border-radius:14px; padding:16px; margin-bottom:14px; }
  label { display:block; font-size:13px; color:var(--muted); margin-bottom:6px; }
  input[type=text] {
    width:100%; padding:14px; font-size:30px; text-align:center;
    font-variant-numeric:tabular-nums; background:#0d1428; color:var(--ink);
    border:1px solid var(--line); border-radius:12px;
  }
  .tare { font-size:12px; color:var(--muted); margin-top:8px; }
  .row { display:flex; gap:8px; margin-top:10px; }
  .row button { flex:1; padding:12px 0; font-size:15px; background:#182341;
    color:var(--ink); border:1px solid var(--line);
    border-radius:10px; font-variant-numeric:tabular-nums; }
  .send { width:100%; padding:16px; margin-top:14px; font-size:17px;
          font-weight:600; background:var(--accent); color:#04122b;
          border:0; border-radius:12px; }
  .send:disabled { opacity:.5; }
  .derived { display:flex; justify-content:space-between; gap:10px; }
  .derived div { text-align:center; flex:1; }
  .big { font-size:24px; font-weight:600; font-variant-numeric:tabular-nums; }
  .k { font-size:11px; color:var(--muted); text-transform:uppercase;
       letter-spacing:.06em; }
  .pill { display:inline-block; padding:3px 10px; border-radius:999px;
          font-size:12px; font-weight:600; border:1px solid var(--line); }
  .ok { color:var(--safe); } .lo { color:var(--warn); } .cr { color:var(--danger); }
  .note { font-size:12px; color:var(--muted); border-top:1px solid var(--line);
          padding-top:12px; margin-top:4px; }
  pre { background:#0d1428; border:1px solid var(--line); border-radius:10px;
        padding:12px; font-size:12px; overflow-x:auto; white-space:pre-wrap;
        margin:0; }
  .hide { display:none; }
  input[type=password] { width:100%; padding:10px; background:#0d1428;
    color:var(--ink); border:1px solid var(--line); border-radius:10px; }
</style>
</head>
<body>
<script type="application/json" id="cfg">__CONFIG__</script>
<div class="wrap">

  <h1>Manual weight entry</h1>
  <p class="sub" id="who"></p>

  <div class="card">
    <label for="w">Gross weight &mdash; cylinder <strong>and</strong> gas</label>
    <input id="w" type="text" inputmode="decimal" autocomplete="off">
    <p class="tare" id="tare"></p>
    <div class="row">
      <button type="button" data-d="-1">&minus;1</button>
      <button type="button" data-d="-0.1">&minus;0.1</button>
      <button type="button" data-d="0.1">+0.1</button>
      <button type="button" data-d="1">+1</button>
    </div>
    <button class="send" id="send" type="button">Send reading</button>
  </div>

  <div class="card">
    <div class="derived">
      <div><div class="big" id="rem">&mdash;</div><div class="k">gas left</div></div>
      <div><div class="big" id="pct">&mdash;</div><div class="k">of capacity</div></div>
      <div><div class="big"><span class="pill" id="lvl">&mdash;</span></div>
           <div class="k">level</div></div>
    </div>
    <p class="tare">Computed here the same way the server computes it, so you see
      the result before you send it. The server&rsquo;s own figures are shown below
      after each send.</p>
  </div>

  <div class="card hide" id="keycard">
    <label for="key">Device key (<code>X-Device-Key</code>)</label>
    <input id="key" type="password" autocomplete="off">
    <p class="tare">Required because <code>DEVICE_API_KEY</code> is set on the
      server. Kept in this browser only.</p>
  </div>

  <div class="card">
    <div class="k" style="margin-bottom:8px">Server response</div>
    <pre id="out">Nothing sent yet.</pre>
  </div>

  <p class="note">
    This page sends <strong>gas sensor value 0</strong>, because the field is
    required and no gas sensor is connected. Zero cannot trip the leak threshold,
    so nothing you type here can command the buzzer or the valve. It does mean the
    dashboard will show gas <strong>SAFE</strong> for these readings &mdash; that is
    the absence of a measurement, not a safe measurement.
  </p>
  <p class="note">
    A weight typed here is stored as a real reading. It moves the consumption
    history and the prediction exactly as a sensor reading would.
  </p>
</div>

<script>
const CFG = JSON.parse(document.getElementById('cfg').textContent);
const $ = (id) => document.getElementById(id);
const KEY_STORE = 'cylinguard.deviceKey';

$('who').textContent = CFG.device_code + '  \\u2192  ' + CFG.cylinder_code;
$('tare').textContent =
  'Empty cylinder is ' + CFG.empty_weight_kg.toFixed(3) + ' kg, so that much is '
  + 'subtracted. A full ' + CFG.capacity_kg.toFixed(1) + ' kg cylinder weighs about '
  + (CFG.empty_weight_kg + CFG.capacity_kg).toFixed(1) + ' kg on the scale.';

if (CFG.device_key_required) {
  $('keycard').classList.remove('hide');
  try { $('key').value = localStorage.getItem(KEY_STORE) || ''; } catch (e) {}
  $('key').addEventListener('change', () => {
    try { localStorage.setItem(KEY_STORE, $('key').value); } catch (e) {}
  });
}

// Mirrors backend/app/services/lpg.py. Kept in step with it deliberately: a
// preview that disagreed with the server would be worse than no preview.
function derive(gross) {
  const remaining = Math.max(0, gross - CFG.empty_weight_kg);
  let pct = CFG.capacity_kg > 0 ? (remaining / CFG.capacity_kg) * 100 : 0;
  pct = Math.min(100, Math.max(0, pct));
  let word = 'NORMAL', cls = 'ok';
  if (pct <= CFG.critical) { word = 'CRITICAL'; cls = 'cr'; }
  else if (pct <= CFG.low) { word = 'LOW'; cls = 'lo'; }
  return { remaining, pct, word, cls };
}

function render() {
  const gross = parseFloat($('w').value);
  if (!isFinite(gross) || gross < 0) {
    $('rem').textContent = '\\u2014';
    $('pct').textContent = '\\u2014';
    $('lvl').textContent = '\\u2014';
    $('lvl').className = 'pill';
    $('send').disabled = true;
    return;
  }
  const d = derive(gross);
  $('rem').textContent = d.remaining.toFixed(2) + ' kg';
  $('pct').textContent = d.pct.toFixed(1) + '%';
  $('lvl').textContent = d.word;          // the word, never colour alone
  $('lvl').className = 'pill ' + d.cls;
  $('send').disabled = false;
}

$('w').value = CFG.prefill_weight.toFixed(2);
$('w').addEventListener('input', render);

for (const b of document.querySelectorAll('.row button')) {
  b.addEventListener('click', () => {
    const cur = parseFloat($('w').value);
    const next = (isFinite(cur) ? cur : CFG.prefill_weight) + parseFloat(b.dataset.d);
    $('w').value = Math.max(0, next).toFixed(2);
    render();
  });
}

async function send() {
  const gross = parseFloat($('w').value);
  if (!isFinite(gross)) return;

  $('send').disabled = true;
  $('out').textContent = 'Sending ' + gross.toFixed(3) + ' kg ...';

  const headers = { 'Content-Type': 'application/json' };
  if (CFG.device_key_required && $('key').value) {
    headers['X-Device-Key'] = $('key').value;
  }

  try {
    const res = await fetch('/api/iot/sensor-data', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        device_id: CFG.device_code,
        total_weight_kg: Number(gross.toFixed(3)),
        gas_sensor_value: CFG.gas_value,
        wifi_status: CFG.wifi_status,
        firmware_version: CFG.firmware_version
      })
      // No timestamp: the server stamps it, so a wrong phone clock cannot have
      // the reading rejected as skewed or stale.
    });

    const text = await res.text();
    let body = null;
    try { body = JSON.parse(text); } catch (e) {}

    if (res.status === 404) {
      $('out').textContent = 'HTTP 404 - device "' + CFG.device_code +
        '" is not registered. Run scripts/register_manual_device.py on the laptop.';
    } else if (res.status === 422 && body && Array.isArray(body.detail)) {
      $('out').textContent = 'HTTP 422 - rejected:\\n' + body.detail
        .map(e => '  ' + (e.loc || []).join('.') + ': ' + e.msg).join('\\n');
    } else if (!res.ok) {
      $('out').textContent = 'HTTP ' + res.status + '\\n' + text.slice(0, 400);
    } else {
      // The server's own numbers, not the preview's. websocket_clients_notified
      // is the line that explains a dashboard that did not move.
      $('out').textContent =
        'HTTP ' + res.status + '  reading #' + body.reading_id + '\\n\\n' +
        'stored        ' + body.total_weight_kg + ' kg gross\\n' +
        'gas left      ' + body.remaining_kg + ' kg  (' + body.percentage + '%)\\n' +
        'level         ' + body.level_status + '\\n' +
        'change        ' + body.delta_classification + '  ' + body.delta_kg + ' kg\\n' +
        'anomaly       ' + body.anomaly_state + '\\n' +
        'gas           ' + body.gas_status + '  (sent 0 - no sensor)\\n' +
        'prediction    ' + body.prediction_days + ' days  ' + body.prediction_method + '\\n' +
        'alerts raised ' + body.alerts_created + '\\n' +
        'dashboards    ' + body.websocket_clients_notified +
          (body.websocket_clients_notified ? ' updated live' : ' open - nothing to update');
    }
  } catch (err) {
    $('out').textContent = 'Could not reach the server.\\n' + err +
      '\\n\\nCheck the phone is on the same network and the laptop firewall allows ' +
      'inbound TCP 8000.';
  } finally {
    $('send').disabled = false;
  }
}

$('send').addEventListener('click', send);
render();
</script>
</body>
</html>"""
