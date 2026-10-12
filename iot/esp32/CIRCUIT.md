# CylinGuard — circuit and how it works

Wiring guide for the sensor node: one ESP32 under an LPG cylinder, reading weight and gas,
reporting to the CylinGuard server, and driving a local alarm.

Firmware: [`cylinguard_esp32.ino`](cylinguard_esp32.ino)

> **None of this has been built.** The firmware has never been compiled — no board and no Arduino
> toolchain on the machine it was written on — and this circuit has never been assembled. The
> voltages and limits below come from the datasheets and the ESP32's electrical specification, not
> from a bench. Check them with a multimeter before you trust them.

---

## Safety, before anything else

**The MQ-6 is a hobby sensor, not a certified LPG detector.** It drifts with temperature and
humidity, it responds to other combustibles, and it needs minutes of warm-up before a reading means
anything. Do not let anyone rely on this to stay safe. Fit a certified detector as well.

**The relay reports what it commanded, not what happened.** Whether gas actually stopped depends on
the valve, the wiring and the power — none of which the firmware can see. That is why the code, the
API and the UI all say *commanded*.

**Gas fittings and mains wiring are out of scope.** If the relay switches mains, or the solenoid
goes into a gas line, have that part done by someone qualified. Build and test the whole thing with
an LED standing in for the valve first.

---

## What you need

| Part | Spec | Notes |
| --- | --- | --- |
| ESP32 dev board | ESP32-WROOM-32, 30- or 38-pin | Any WROOM-32 works; the code uses WiFi + ADC1 |
| Load cell | **50 kg**, single-point, 4-wire | See the sizing note below |
| HX711 module | green breakout | Powered at **3.3V**, not 5V |
| MQ-6 module | 4-pin, with analogue `AOUT` | **MQ-6** specifically — not MQ-2 (generic) or MQ-5 |
| Buzzer | 5V active | Plus NPN transistor (BC547 / 2N2222) and a 1 kΩ resistor |
| Relay module | 1-channel, 5V, opto-isolated | Most are active-**LOW** — verify yours |
| Resistors | 2 × 10 kΩ | Divider for the MQ-6 output |
| Power supply | 5V, 2A | ESP32 WiFi peaks plus the MQ-6 heater |
| Mechanical | flat plate or platform | The cylinder's full weight must pass through the load cell |

Optional, and the whole reason the relay exists: a **12V normally-open, LPG-rated brass solenoid
valve** and a 12V supply for it.

### Why 50 kg and not 20 kg

The cylinder itself weighs about 15 kg empty and holds 14.2 kg of gas, so a full one is roughly
**29 kg gross**. A 20 kg cell would be past full scale before the cylinder was even half full. A
50 kg cell puts 29 kg at under 60% of range, which is where a load cell is most linear.

The trade-off is resolution: a 50 kg cell spreads its output over more range, so each gram is a
smaller signal. That is fine here — the HX711 is a 24-bit amplifier, and the firmware's noise floor
(20 g, set server-side) is far above anything the cell's resolution limits.

---

## The circuit

```
                        ┌──────────────────┐
     5V 2A ─────────────┤ 5V / VIN         │
       GND ─────────────┤ GND              │
                        │                  │
   ┌────────────────────┤ 3.3V             │
   │                    │   ESP32-WROOM-32 │
   │   ┌────────────────┤ GPIO 16   (DOUT) │
   │   │   ┌────────────┤ GPIO  4   (SCK)  │
   │   │   │            │                  │
   │   │   │   ┌────────┤ GPIO 34   (ADC1) │
   │   │   │   │   ┌────┤ GPIO 26  (buzzer)│
   │   │   │   │   │ ┌──┤ GPIO 27   (relay)│
   │   │   │   │   │ │  └──────────────────┘
   │   │   │   │   │ │
   │   │   │   │   │ │   ── weight ────────────────────────────────
   │   │   │   │   │ │
   │   │   │   │   │ │     ┌───────────────┐      ┌──────────────┐
   │   │   │   │   │ │     │ HX711         │      │ 50 kg cell   │
   └───┼───┼───┼───┼─┼─────┤ VCC  (3.3V)   │      │              │
       └───┼───┼───┼─┼─────┤ DOUT      E+ ─┼──────┤ red          │
           └───┼───┼─┼─────┤ SCK       E− ─┼──────┤ black        │
               │   │ │     │           A+ ─┼──────┤ green        │
               │   │ │     │           A− ─┼──────┤ white        │
               │   │ │     │ GND → GND     │      │              │
               │   │ │     └───────────────┘      └──────────────┘
               │   │ │
               │   │ │   ── gas ───────────────────────────────────
               │   │ │
               │   │ │     ┌──────────┐
               │   │ │     │ MQ-6     │  VCC → 5V
               └───┼─┼─────┤ AOUT     │  GND → GND
                   │ │     └──────────┘
                   │ │     GPIO 34 taps AOUT through a 2x10k divider,
                   │ │     never directly - see "Two mistakes" below.
                   │ │
                   │ │   ── alarm ─────────────────────────────────
                   │ │
                   │ │     1kΩ      ┌─ NPN ─┐        ┌──────────┐
                   └─┼──────────────┤ base  │        │ Buzzer   │
                     │              │ emit ─┼── GND  │  +  → 5V │
                     │              │ coll ─┼────────┤  −       │
                     │              └───────┘        └──────────┘
                     │
                     │   ── shutoff ──────────────────────────────
                     │
                     │        ┌───────────────┐
                     └────────┤ IN            │   VCC → 5V
                              │  relay module │   GND → GND
                              │               │
                              │  COM ─── 12V+ │   dry contacts only:
                              │  NO  ─── sol. │   a SEPARATE 12V supply,
                              └───────────────┘   isolated from the logic
```

### Connections, module by module

**HX711 → ESP32**

| HX711 | ESP32 | Note |
| --- | --- | --- |
| `VCC` | **3.3V** | Not 5V — see below |
| `GND` | `GND` | |
| `DOUT` | `GPIO 16` | data out of the HX711 |
| `SCK` | `GPIO 4` | clock, driven by the ESP32 |

**Load cell → HX711** — a 4-wire cell, commonly red/black/green/white:

| Wire (typical) | HX711 | Function |
| --- | --- | --- |
| red | `E+` | excitation + |
| black | `E−` | excitation − |
| green | `A+` | signal + |
| white | `A−` | signal − |

Colour conventions vary between manufacturers, so **measure rather than assume**: across the
excitation pair you read the bridge's input resistance (often ~1 kΩ or 350 Ω) and across the signal
pair a slightly different value. The pair with the *higher* resistance is excitation. Swapping `A+`
and `A−` only inverts the sign — the weight will decrease as you add load, which is obvious and
harmless. Swapping excitation for signal will not work at all.

**MQ-6 → ESP32**

| MQ-6 | Goes to | Note |
| --- | --- | --- |
| `VCC` | 5V | the heater needs 5V |
| `GND` | `GND` | |
| `AOUT` | 10 kΩ → `GPIO 34` → 10 kΩ → `GND` | **divider required** |

**Buzzer** — `GPIO 26` → 1 kΩ → NPN base; emitter to `GND`; collector to buzzer `−`; buzzer `+` to
5V. The transistor is not optional: a GPIO can source about 20 mA comfortably and a buzzer wants
more. If yours is a magnetic type rather than a self-driving active module, put a flyback diode
across it.

**Relay module** — `VCC` 5V, `GND` to ground, `IN` to `GPIO 27`. The valve goes on the **dry
contacts** (`COM` / `NO`) with its own 12V supply, never through the ESP32.

---

## Power and grounding

One 5V 2A supply feeds the ESP32's `5V`/`VIN` pin, the MQ-6, the buzzer and the relay module's
logic side. The HX711 runs from the ESP32's **3.3V** output, which its onboard regulator provides;
the HX711 draws about 1.5 mA, so there is plenty of headroom.

**Every ground must be common** — ESP32, HX711, MQ-6, buzzer, relay. An analogue reading is a
voltage *relative to ground*; if the MQ-6's ground and the ESP32's ground sit at different
potentials, the ADC reads the difference as signal and you get drift you cannot explain.

The solenoid's 12V supply is the exception: it connects only to the relay's dry contacts and shares
nothing with the logic side. That isolation is the point of an opto-isolated relay module.

### Two mistakes that damage the board

**1. The HX711 at 5V.** Its `DOUT` swings to whatever `VCC` is. At 5V you are putting 5V onto
`GPIO 16`, and the ESP32 is a 3.3V part — that is above its absolute maximum rating, not merely
out of spec. Power the HX711 at 3.3V. It costs a little range and nothing else.

**2. The MQ-6's output straight to the ADC.** The heater needs 5V, so you cannot just run the
module at 3.3V and be done — it reads unreliably. But that means `AOUT` can swing to about 5V,
which is again over the ADC's input range. Two 10 kΩ resistors fix it:

```
AOUT ──┬── 10kΩ ──┬── GPIO 34
       │          │
       │        10kΩ
       │          │
       └──────── GND     (AOUT, 10k, pin, 10k, GND in series)
```

That halves the voltage — and therefore halves the numbers the firmware sees. **`GAS_ALARM_THRESHOLD`
must be re-derived**, not left at its default of 700. Let the sensor warm up for several minutes in
clean air, read the resting value off the serial monitor, and set the threshold well above it. Too
low and it alarms on cooking fumes until nobody believes it; too high is worse.

### One pin choice that is not negotiable

The MQ-6 must stay on **`GPIO 34`**, or another pin on **ADC1**. The ESP32's ADC2 is unavailable
while the WiFi radio is running, and `analogRead()` on an ADC2 pin returns *garbage with no error* —
plausible-looking numbers that mean nothing. Avoid GPIO 0, 2, 4, 12–15, 25–27 for anything analogue.

---

## How it works

### At boot

```
Serial at 115200
  ↓
buzzer OFF, relay NOT activated     ← known-safe state first
  ↓
ADC: 12-bit (0–4095), 11 dB attenuation
  ↓
HX711 begins on GPIO 16 / 4
  ↓
WiFi connect (blocking, 20 s ceiling)
  ↓
warn if HX711 looks uncalibrated
```

The actuators are set **before** anything else. A relay that defaulted to activated would cut the
gas on every reset — including resets you did not intend, like a brownout.

The WiFi attempt is bounded even when blocking. An unreachable access point must not stop the
sensor reading and the local buzzer from working; being offline is a reporting problem, not a
safety one.

### Every loop pass (~every 0.5 s)

```
read gas  ──►  local alarm decision  ──►  WiFi upkeep  ──►  report, if due
   8 reads,         edge-triggered,         non-blocking      interval from
   mean             needs warm-up           retry             the server
```

**Gas is read and acted on every pass**, not only when reporting. If the alarm waited for the
report interval, a leak detected one second after a report would sit undetected for the rest of the
interval. Reporting is for the server; the buzzer is for the room.

**The alarm is local and independent.** The firmware compares against its own
`GAS_ALARM_THRESHOLD`, so the buzzer sounds with WiFi down and the server unreachable. The server
runs the same comparison against its own configurable threshold and remains the authority for what
gets *recorded* — this is the last-resort copy, not the primary.

Two details in that decision:

- **It is ignored during warm-up.** For the first 60 seconds the MQ-6 reads high as its heater
  comes up. Without the warm-up gate, every single boot would false-alarm.
- **It acts on changes only.** The code latches state and acts on the transition, so a sustained
  alarm does not re-drive the buzzer and re-log every half second.

**Weight is read only when reporting**, because it is slow: the HX711 runs at 10 samples/second by
default, so 10 samples plus the inter-sample delays takes roughly a second. The firmware takes the
**median** of those 10, not the mean — one knock against the cylinder shifts a mean and barely
moves a median. The server smooths again over time, but a wild value should not leave the device at
all.

### Reporting

```
POST /api/iot/sensor-data
{
  "device_id": "ESP32-CYL-001",
  "total_weight_kg": 21.4,
  "gas_sensor_value": 420,
  "wifi_status": "CONNECTED",
  "firmware_version": "1.0.0"
}
```

**No timestamp.** The ESP32 has no battery-backed clock, so after a power cut its time is 1970 —
and the server rejects anything more than 7 days old. Omitting it lets the server stamp the reading,
which is right far more often than the device's guess.

**Retries distinguish whose fault it is.** A 5xx or a network error gets up to 3 attempts with a
short backoff. A **4xx does not get retried at all** — an unregistered `device_id`, a bad key, or a
value the server considers implausible will not fix itself, and hammering it wastes power and floods
the log.

**The reply sets the pace.** The response carries `report_interval_seconds`, and the device adopts
it. The server owns how often this device reports; the firmware constant is only what it uses before
the first successful POST. A value outside 5–3600 s is logged and ignored rather than obeyed, so a
typo in the web UI cannot silence the device. This matters because the server also derives its
*offline* threshold from that same setting — if the two disagreed, a device reporting perfectly
would be flagged as missing.

**`millis()` is compared by subtraction**, which stays correct across its ~49-day overflow.
`now > last + interval` would leave the device silently dead until someone power-cycled it.

---

## Calibrate before you trust a single reading

Everything downstream derives from the weight: remaining gas, the consumption history, the
prediction, the refill recommendation. An uncalibrated HX711 makes all of it meaningless.

1. Set `CALIBRATION_MODE = true`, flash, leave the scale **empty**.
2. Open Serial at 115200. It prints a raw average — that is your **`HX711_OFFSET`**.
3. Put a known weight on it (a 5 kg bag of rice is fine). Note the new raw average.
4. `HX711_SCALE = (loaded_raw − HX711_OFFSET) / known_kg`
5. Put both numbers in the config block, set `CALIBRATION_MODE = false`, reflash.

Weight going *down* as you add load means `A+` and `A−` are swapped. Either swap the wires or negate
`HX711_SCALE`.

---

## Bring-up order

Do these in sequence. Each one isolates a different failure, and the last one is the only one that
can hurt anybody.

1. **Bare board.** Flash, open Serial, confirm it boots and joins WiFi.
2. **HX711 alone.** `CALIBRATION_MODE = true`. Raw values should move when you press on the cell
   and settle when you let go. Noisy or stuck values usually mean a bad solder joint or a swapped
   excitation pair.
3. **Calibrate.** The five steps above. Check a second known weight afterwards.
4. **MQ-6 alone.** Measure `AOUT` and the divider output with a meter before connecting
   `GPIO 34` — confirm the pin side stays under 3.3V. Then watch the serial readings settle over a
   few minutes and note the resting value.
5. **Set the threshold** from that resting value.
6. **Buzzer.** Hold a gas lighter near the sensor — unlit, just the valve — and confirm it sounds.
7. **Relay with an LED**, not a valve. Confirm `RELAY_ACTIVE_LOW` is right: the LED must be **off**
   at boot and **on** when the alarm fires. Backwards means the valve would be driven closed when
   it should be open.
8. **Register the device.** `DEVICE_ID` must already exist in the server's `devices` table; the
   server returns 404 and refuses to auto-create one, so nobody can fill the database with records
   that have no owner.
9. **Only then**, if at all, the solenoid — wired by someone qualified.

---

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| Weight is wild or stuck | Bad joint, or excitation and signal pairs swapped |
| Weight decreases under load | `A+`/`A−` swapped, or negate `HX711_SCALE` |
| Weight plausible but wrong | Not calibrated, or calibrated with a wrong known weight |
| Gas value pinned near 4095 | No divider — `AOUT` is over the ADC's range |
| Gas value plausible but meaningless | Sensor on an ADC2 pin; move it to `GPIO 34` |
| Alarms on every boot | Warm-up gate removed, or threshold below the resting value |
| `HTTP 404` on every POST | `DEVICE_ID` is not in the `devices` table |
| `HTTP 422` on every POST | Weight or gas outside what the server considers plausible |
| Connects, then stops reporting | Server marked it offline; check the reporting interval setting |
| Valve closed when it should be open | `RELAY_ACTIVE_LOW` is wrong for your module |
| Random resets under WiFi load | 5V supply cannot hold current; use 2A |

---

## Where things are defined

| What | Where |
| --- | --- |
| Pin map, tuning constants, config block | [`cylinguard_esp32.ino`](cylinguard_esp32.ino) |
| Accepted reporting interval (5–3600 s) | `min/max_report_interval_seconds` in `backend/app/config.py` |
| Packet validation and rejection rules | `backend/app/schemas/ingest.py` |
| What the server does with a packet | `backend/app/services/ingest.py` |
| Offline threshold derivation | `backend/app/services/device_health.py` |
