<div align="center">

# CylinGuard

### Smart LPG Monitoring & Safety System

**`MONITOR • PREDICT • PROTECT`**

*An IoT platform that knows how much cooking gas you have left, tells you when it will run out,
and warns you if it starts leaking.*

</div>

---

## The problem

A domestic LPG cylinder is a black box. You cannot see inside it, so you find out it is empty the
moment the flame dies — usually mid-meal, often at night, always inconveniently. People resort to
shaking the cylinder, pouring hot water down the side, or simply keeping a spare that sits unused
for months.

The second problem is more serious. A slow LPG leak from a worn regulator, a cracked hose or a
burner knob left half-open is invisible and odour-fatiguing. By the time it is obvious, the room
has already filled.

Both problems have the same root cause: **nobody is measuring anything.**

## The idea

Put the cylinder on a scale and put a gas sensor next to it.

Weight tells you everything about quantity. A cylinder has a known empty weight stamped on its
collar, so whatever it weighs above that number *is* the gas. Track that weight over time and you
get consumption. Track consumption over weeks and you can predict depletion. Compare today's
consumption against the household's own history and you can spot the moment something goes wrong.

The gas sensor covers what weight cannot: a leak downstream of the cylinder, where the gas has
already left the bottle and is sitting in the room.

Together they answer the three questions that matter:

| Question | Answered by |
| --- | --- |
| *How much gas do I have?* | Load cell — weight above the cylinder's empty weight |
| *When will it run out?* | Consumption history + machine-learned prediction |
| *Is it safe right now?* | MQ-6 gas sensor + abnormal-consumption detection |

---

## How it works

```
                         USER
                           |
                     ┌─────────────┐
                     │   Browser   │
                     │  React UI   │
                     └──────┬──────┘
                            │ HTTP / WebSocket
                     ┌──────┴──────┐
                     │    NGINX    │  reverse proxy
                     └──────┬──────┘
              ┌─────────────┴─────────────┐
              │                           │
        ┌─────┴─────┐              ┌──────┴──────┐
        │   React   │              │   FastAPI   │
        │ dashboard │              │   backend   │
        └───────────┘              └──────┬──────┘
                          ┌───────────────┼───────────────┐
                    ┌─────┴─────┐  ┌──────┴─────┐  ┌──────┴─────┐
                    │   MySQL   │  │ ML Engine  │  │ WebSocket  │
                    │  history  │  │ prediction │  │  realtime  │
                    └───────────┘  └────────────┘  └────────────┘

   PHYSICAL DEVICE
   ┌──────────────────────────────────────┐
   │  ESP32                               │
   │   ├── Load Cell + HX711   weight     │
   │   ├── MQ-6                gas        │
   │   ├── Buzzer              alarm      │
   │   └── Relay               cutoff     │
   └───────────────┬──────────────────────┘
                   │  HTTP POST every 30s
                   └──> NGINX ──> FastAPI
```

An ESP32 sits under the cylinder. It reads the load cell through an HX711 amplifier, samples the
MQ-6 sensor, and POSTs a small JSON packet to the server. How often is the server's decision, not
the firmware's: the reporting interval is a setting, returned in every response, and the device
adopts it on its next report.

The backend then runs one pipeline, in order:

```
receive → validate → store → calculate LPG → calculate consumption → smooth
   → detect anomaly → check leakage → update prediction → raise alerts → broadcast
```

The last step pushes the new state to every open dashboard over WebSocket, so the screen updates
without anyone refreshing it.

---

## What it does

**Monitor**
Live cylinder weight, LPG remaining in kilograms and as a percentage, gas sensor reading, and
device connectivity. Daily, weekly and monthly consumption, with full searchable history.

**Predict**
Estimated days remaining and an expected depletion date, with a confidence figure attached. A
smart refill recommendation that fires early enough to actually act on.

**Protect**
Leak detection from the MQ-6, abnormal-consumption detection from the household's own usage
pattern, buzzer and relay status, and a safety event log. Critical events turn the whole dashboard
red and push an alert immediately.

---

## The measurements

### Remaining gas

```
remaining_lpg = total_weight - empty_cylinder_weight     (floored at 0)
percentage    = remaining_lpg / capacity * 100           (clamped to 0-100)
```

A 14.2 kg cylinder with a 15.0 kg tare weighing 21.4 kg holds 6.4 kg of gas — 45% full. A negative
figure is never displayed.

### Consumption

Consumption is the drop in weight between readings. In practice a raw difference is useless: load
cells drift with temperature, and someone leaning on the counter registers as a reading.

So readings pass through a rolling median, and any change smaller than a configurable threshold is
discarded as noise rather than recorded as gas burned. A large *positive* jump is recognised as a
refill, not as negative consumption.

### Prediction

A `RandomForestRegressor` trained on the household's own history, over seven features: current
remaining kg, average daily consumption, 7-day average, 30-day average, recent consumption,
consumption variance, and day of week. It learns that weekends differ from weekdays, and that this
kitchen is not the average kitchen.

**When there is not enough history, CylinGuard says so.** It falls back to plain arithmetic —
`remaining_lpg / average_daily_consumption` — reports low confidence, and labels the result
`ESTIMATE`. Every prediction carries a confidence value derived from sample count and variance.
None of them are promises.

### Abnormal consumption

Today's usage is compared against the household's own established average. A kitchen that normally
burns 0.50 kg/day and suddenly burns 1.40 kg/day is 180% above its own baseline — that is worth
flagging, whatever the absolute number.

Four states, escalating:

```
NORMAL  →  UNUSUAL CONSUMPTION  →  POSSIBLE LEAK  →  CRITICAL LEAK
```

High consumption on its own only ever reaches `UNUSUAL CONSUMPTION`, reported with its possible
causes: a burner left on, a regulator fault, or a genuinely busy day. Escalation beyond that
requires the gas sensor to agree.

---

## Safety: what this does and does not claim

The MQ-6 is an inexpensive prototype sensor, not a certified gas analyser. CylinGuard treats it as
one signal among several, measured against a configurable experimental threshold.

- Abnormal consumption **alone** is never reported as a leak.
- Buzzer and relay states shown on screen are only ever what the backend commanded or the device
  reported back. **CylinGuard never claims a physical gas shutoff happened** because it assumed one
  did.
- A prediction is an estimate with a confidence figure, never a guarantee.

**Do not use this prototype as your only gas-safety measure.** It is built to catch problems
earlier than a human nose would, not to replace a certified detector.

---

## Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18, Vite, Tailwind CSS, React Router, Recharts, Lucide, Axios |
| Backend | Python 3.13, FastAPI, Uvicorn, SQLAlchemy 2, Pydantic v2, PyMySQL |
| Database | MySQL 8 |
| ML | scikit-learn `RandomForestRegressor`, with an arithmetic fallback |
| Auth | JWT, bcrypt password hashing |
| Realtime | WebSocket, with automatic reconnect |
| IoT | ESP32, HX711 load-cell amplifier, MQ-6 gas sensor, buzzer, relay |
| DevOps | Docker, Docker Compose, NGINX |

---

## The dashboard

Seven screens, built as a dark glassmorphic interface rather than another white admin template —
the visual language should read as *smart, safe, real-time, industrial*.

| Screen | Shows |
| --- | --- |
| **Dashboard** | Animated cylinder, LPG level, live sensors, today's usage, prediction, safety, alerts |
| **Consumption** | Today / 7-day / 30-day / monthly, with daily and trend charts |
| **Prediction** | Days left, depletion date, radial confidence visualisation |
| **Safety** | Large status indicator, gas value vs threshold, buzzer, relay, event history |
| **History** | Full searchable, filterable, paginated reading log |
| **Alerts** | INFO / WARNING / CRITICAL, with read tracking |
| **Settings** | Cylinder dimensions and every detection threshold |

Status is never communicated by colour alone — a green dot always carries the word `SAFE` beside
it, so the interface works for colour-blind users and in screenshots.

### Demo mode

Hardware is not always on the table — during a presentation, or while developing. In demo mode the
backend generates realistic readings that drift gradually, exactly as a real cylinder would, with
three scenarios available on demand:

| Scenario | Demonstrates |
| --- | --- |
| **Normal** | Healthy cylinder, safe gas levels, device online |
| **Low LPG** | Depletion warning and the refill recommendation |
| **Leak detected** | Full emergency path: alarm, alert, red dashboard, live WebSocket push |

A `DEMO MODE` indicator stays visible the whole time, and the instant real ESP32 data arrives the
simulation yields to it.

---

## Database

Nine tables, defined in [`database/schema.sql`](database/schema.sql).

| Table | Holds |
| --- | --- |
| `users` | Accounts. Passwords are bcrypt hashes, never plaintext |
| `cylinders` | Cylinder registry: code, empty weight, capacity |
| `devices` | One ESP32 per cylinder: code, wifi status, last seen, firmware |
| `sensor_readings` | Every reading: weight, gas value, device status |
| `consumption_records` | One row per cylinder per day: kg used, running average |
| `predictions` | Days left, depletion date, confidence, and which method produced it |
| `alerts` | INFO / WARNING / CRITICAL notifications with a read flag |
| `safety_events` | Gas value vs threshold, plus buzzer and relay state |
| `settings` | Per-cylinder tunables. Deliberately holds nothing secret |

Indexes cover the access patterns that matter: `(cylinder_id, timestamp)` on the two high-volume
tables, `(cylinder_id, created_at)` on alerts and safety events. History is paginated and charts
are date-filtered, so no query ever drags the full dataset into memory.

---

## Project structure

```
cylinguard/
├── backend/
│   ├── app/
│   │   ├── config.py          # every tunable, read from env exactly once
│   │   ├── database.py        # SQLAlchemy engine + session factory
│   │   ├── models/            # 9 models mirroring database/schema.sql
│   │   ├── schemas/           # Pydantic request/response validation
│   │   ├── routes/            # REST + WebSocket endpoints
│   │   ├── services/          # LPG, consumption, anomaly, safety, refill
│   │   ├── security/          # password hashing, JWT
│   │   ├── ml/                # prediction model
│   │   └── websocket/         # connection manager
│   ├── scripts/               # bootstrap_mysql, init_db, seed
│   ├── tests/
│   └── requirements.txt
├── frontend/src/
│   ├── components/  pages/  layouts/  charts/
│   ├── hooks/  context/  utils/
│   └── services/              # api.js, websocket.js
├── database/schema.sql
├── nginx/nginx.conf
├── iot/esp32/cylinguard_esp32.ino
├── docker-compose.yml
└── .env.example
```

---

## Getting started

> **Status:** the data layer is in place — schema, models and seed data all work. The API,
> dashboard and Docker stack are under active development, so the steps below currently take you
> as far as a populated database.

### Prerequisites

- Python 3.11+ (developed on 3.13)
- MySQL 8+ reachable on `127.0.0.1:3306`
- Node.js 18+

### 1. Configure

```bash
cd cylinguard
cp .env.example .env
```

Edit `.env` and set `MYSQL_PASSWORD`, `JWT_SECRET`, and `DATABASE_URL`:

```
DATABASE_URL=mysql+pymysql://cylinguard_user:your_app_password@127.0.0.1:3306/cylinguard
```

`.env` is gitignored and must never be committed.

### 2. Install

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

On macOS/Linux use `.venv/bin/python` throughout.

### 3. Create the database

```powershell
$env:MYSQL_PASSWORD = "your_app_password"
.\.venv\Scripts\python.exe scripts\bootstrap_mysql.py
.\.venv\Scripts\python.exe scripts\init_db.py
```

`bootstrap_mysql.py` prompts for your MySQL `root` password, creates the `cylinguard` database and
grants `cylinguard_user` rights on that database only. The password is used for that one
connection and never written to disk.

### 4. Seed demo data

```powershell
.\.venv\Scripts\python.exe scripts\seed.py
```

```
email:    demo@cylinguard.local
password: cylinguard123
```

Change those before CylinGuard goes anywhere but your own machine.

Re-running is safe — the seeder detects existing data and stops. To regenerate:

```powershell
.\.venv\Scripts\python.exe scripts\seed.py --reset
```

> `--reset` truncates all nine tables and destroys any real data collected.

### What the seed data simulates

Not random noise — a plausible household:

- Gas drawn in bursts around three meal windows, not evenly across the day
- **0.20–0.50 kg/day**, averaging **~0.46 kg/day**
- **±15 g** of load-cell noise per reading, giving the smoother real work to do
- One **refill event**: a single +13.7 kg step the consumption engine must not read as negative usage
- Ends at roughly **8.3 kg (~58%)**, about 18 days left

Fixed random seed, so the demo is identical every run.

---

## Deployment

CylinGuard runs as four containers — `frontend`, `backend`, `mysql`, `nginx` — on a shared
`cylinguard_network`, with MySQL on a persistent `cylinguard_mysql_data` volume.

> **Not yet verified.** The compose stack was written and reviewed against the spec on a machine
> with no Docker installed, so `docker compose up --build` has never actually run. Expect to fix
> something the first time. The no-Docker path below *is* verified and is what the project has been
> developed against.

### Before the first run

`.env` must exist at the repository root with at least `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD` and
`JWT_SECRET` — compose refuses to start without them, and the backend refuses to boot on the
placeholder secret. The quickest way to get a valid file is to run the local bootstrap once:

```bash
cd backend
MYSQL_PASSWORD="choose-one" python scripts/bootstrap_mysql.py   # writes ../.env for you
```

Then add `MYSQL_ROOT_PASSWORD` to that file by hand — the bootstrap deliberately never writes an
admin password to disk.

### Commands

| Command | What it does |
| --- | --- |
| `docker compose up --build` | Build images and start all four services in the foreground |
| `docker compose up -d` | Same, detached |
| `docker compose ps` | List services and their health |
| `docker compose logs -f backend` | Follow one service's logs |
| `docker compose exec backend python scripts/seed.py --reset` | Rebuild the demo dataset |
| `docker compose restart backend` | Restart the API after an env change |
| `docker compose down` | Stop everything. **The database survives.** |
| `docker compose down -v` | Stop and **delete the volumes** — see the warning below |

Then open **http://localhost** for the dashboard and **http://localhost/docs** for the API
reference.

> ### ⚠️ `docker compose down -v` destroys your data
> The `-v` flag deletes the `cylinguard_mysql_data` volume — every reading, every alert, every
> consumption record — and `cylinguard_ml_artifacts`, so any trained model goes too. There is no
> undo and no prompt. Plain `docker compose down` is the safe one; use `-v` only when you
> deliberately want a clean slate.

### How the pieces fit

NGINX is the only service published to the host. It routes `/` to the React build, `/api/` to the
backend, `/ws/` to the WebSocket endpoint with the `Upgrade`/`Connection` handshake headers, and
`/health` explicitly — that last one matters, because without its own rule `/health` falls through
to the single-page app and returns the HTML shell with a **200**, giving you a health check that
can never fail.

The backend waits for MySQL to report healthy before it starts, via `mysqladmin ping` rather than a
port check: the port accepts connections well before the server will answer a query, and the API
fails fast on an unreachable database by design.

The schema is applied by the MySQL container from `database/schema.sql` on first start. Demo data
is seeded by `scripts/seed.py`, which is idempotent, so it runs on every container start without
duplicating anything. `database/seed.sql` is a **generated** plain-SQL copy of that data for anyone
who wants it without Python — regenerate it with `python backend/scripts/export_seed.py`, and never
edit it by hand.

The ESP32 is physical hardware and is **not** containerised. It reaches the server over the local
network — point `API_BASE` in the sketch at the host's LAN address, not `localhost`, which inside
the ESP32 means the ESP32.

### Running the tests

```bash
cd backend  && python -m pytest                      # 179 tests
cd frontend && npm test                              # 48 tests
cd backend  && python scripts/check_schema_parity.py # models vs schema.sql, no database needed
```

Backend tests run against the real MySQL schema inside a transaction that is always rolled back, so
they exercise real constraints and real cascades without leaving a row behind.

---

## Configuration

All tunables live in `.env` and are read once by `backend/app/config.py`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | — | SQLAlchemy connection string |
| `JWT_SECRET` | `change_this_secret` | Token signing key. **Change this** |
| `JWT_EXPIRE_MINUTES` | `1440` | Token lifetime |
| `CORS_ORIGINS` | `http://localhost` | Comma-separated allowed origins |
| `DEVICE_API_KEY` | *(blank)* | Optional shared secret sent as `X-Device-Key`. Blank disables the check |
| `DEVICE_OFFLINE_SECONDS` | `120` | Silence before a device is marked OFFLINE |
| `MIN_MEANINGFUL_DELTA_KG` | `0.02` | Weight changes below this are load-cell noise |
| `REFILL_DELTA_KG` | `2.0` | A positive jump at or above this is a refill |
| `SMOOTHING_WINDOW` | `5` | Readings in the rolling-median smoother |
| `DEMO_MODE_DEFAULT` | `true` | Whether new cylinders start in demo mode |

Secrets never reach the frontend or the Settings page. The Settings screen exposes cylinder
dimensions and detection thresholds, and nothing else.

---

## Security

- JWT authentication; users can only reach their own cylinders and data
- bcrypt password hashing — plaintext passwords are never stored or logged
- Pydantic validation on every input; malformed sensor packets are rejected and logged
- SQLAlchemy ORM throughout, so queries are parameterised
- All credentials in environment variables; `.env` is gitignored
- Optional device API key for ESP32 authentication

---

## Hardware

| Component | Spec | Role |
| --- | --- | --- |
| ESP32 | WROOM-32, 30- or 38-pin | WiFi microcontroller, reads sensors and posts to the server |
| Load cell | **50 kg**, single-point, 4-wire | Measures total cylinder weight |
| HX711 | breakout, powered at **3.3V** | 24-bit amplifier that makes the load cell readable |
| MQ-6 | module with analogue `AOUT`, 5V | LPG gas sensor — MQ-6 specifically, not MQ-2 or MQ-5 |
| Buzzer | 5V active + NPN transistor | Local audible alarm, independent of the network |
| Relay | 1-channel, 5V, opto-isolated | Actuator output for a solenoid cutoff valve |
| Supply | 5V 2A | ESP32 WiFi peaks plus the MQ-6 heater |

A 15 kg cylinder holding 14.2 kg weighs about **29 kg gross**, so a 20 kg load cell would sit at
full scale with no headroom — 50 kg is the right size, not over-specification.

Two supply details that are easy to get wrong and damage the board:

- **Power the HX711 from 3.3V, not 5V.** Its `DOUT` swings to whatever `VCC` is, and the ESP32's
  GPIOs are 3.3V parts. At 5V you are driving an input above its absolute maximum.
- **Divide the MQ-6's `AOUT`.** The heater needs 5V, so `AOUT` can reach ~5V, which is over the
  ADC's input range. Two 10 kΩ resistors (`AOUT → 10k → pin → 10k → GND`) brings it in range —
  and halves the scale, so `GAS_ALARM_THRESHOLD` has to be re-derived against your own warmed-up
  sensor rather than left at its default.

The pin map, the calibration procedure and these notes are all in the header of
[`iot/esp32/cylinguard_esp32.ino`](iot/esp32/cylinguard_esp32.ino).

The firmware connects to WiFi, reads both sensors, builds a JSON payload and POSTs it to
`/api/iot/sensor-data` at a configurable interval. WiFi credentials, server URL and device ID live
in a clearly marked config block at the top of the sketch — no real credentials are committed.

```json
{
  "device_id": "ESP32-CYL-001",
  "total_weight_kg": 21.4,
  "gas_sensor_value": 420,
  "wifi_status": "CONNECTED",
  "firmware_version": "1.0.0"
}
```

No timestamp is sent. The ESP32 has no battery-backed clock, so after a power cut its time is 1970
— and the server rejects anything more than 7 days old. Omitting it lets the server stamp the
reading with its own clock, which is right far more often than the device's guess. The field is
still accepted from a device that does keep time.

The buzzer and relay are driven locally by the ESP32 as well as by the server, so the alarm still
sounds if the network is down.

---

## Troubleshooting

**`Access denied for user ...`**
Wrong MySQL password, or the user does not exist. Re-run `scripts/bootstrap_mysql.py`.

**`Can't connect to MySQL server on '127.0.0.1'`**
MySQL is not running. On Windows: `Get-Service MySQL80`, then `Start-Service MySQL80`.

**`Demo user already exists - nothing to do`**
The seeder found existing data and stopped. Use `--reset` to regenerate.

**`ModuleNotFoundError: No module named 'app'`**
Run the scripts from `backend/`, not from the repo root.

**Schema changes are not appearing**
`init_db.py` uses `CREATE TABLE IF NOT EXISTS` and will not alter an existing table. Drop the
database and re-run setup.

**Dashboard shows DEVICE OFFLINE**
No packet has arrived within `DEVICE_OFFLINE_SECONDS`. Check the ESP32's WiFi and that `SERVER_URL`
points at the machine running CylinGuard.

---

## License

MIT — see [LICENSE](LICENSE).
