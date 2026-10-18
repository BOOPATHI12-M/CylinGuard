/*
 * CylinGuard ESP32 firmware
 * ============================================================================
 * Reads a load cell (HX711) and an MQ-6 gas sensor, posts both to the CylinGuard
 * API, and drives a buzzer and a shutoff relay when gas is detected.
 *
 * NOT VERIFIED. This was written on a machine with no ESP32 attached and no
 * Arduino toolchain installed, so it has never been compiled or run. Treat it as
 * a reviewed starting point: expect to adjust the pin map to your wiring and to
 * re-run the calibration step before trusting a single reading.
 *
 * ---------------------------------------------------------------------------
 * SAFETY
 * ---------------------------------------------------------------------------
 * The MQ-6 is a hobby gas sensor, not a certified LPG detector. It drifts, it
 * responds to other combustibles, and it needs minutes of warm-up before any
 * reading means anything. Do not rely on this to keep anyone safe. Fit a
 * certified detector as well.
 *
 * The relay is driven by this board. Whether gas actually stops flowing depends
 * on the valve, the wiring and the power - none of which the firmware can see.
 * It reports what it commanded, and the backend and UI repeat that wording
 * rather than claiming a shutoff happened.
 *
 * Mains wiring is out of scope. If your relay switches mains, have it done by
 * someone qualified.
 *
 * ---------------------------------------------------------------------------
 * HARDWARE
 * ---------------------------------------------------------------------------
 *   HX711       DOUT -> GPIO 16      SCK -> GPIO 4       VCC 3.3V  GND GND
 *   MQ-6        AOUT -> divider -> GPIO 34               VCC 5V    GND GND
 *   Buzzer      +    -> GPIO 26      active-high through a transistor
 *   Relay       IN   -> GPIO 27      most modules are active-LOW; see RELAY_ACTIVE_LOW
 *
 *   Load cell: 50 kg single-point, 4-wire, into the HX711's E+/E-/A+/A-. A 15 kg
 *   cylinder holding 14.2 kg weighs about 29 kg gross, so a 20 kg cell would sit
 *   near full scale with no headroom.
 *
 *   Power the HX711 from 3.3V, NOT 5V. Its DOUT swings to VCC, and the ESP32's
 *   GPIOs are 3.3V parts - at 5V you are driving an input above its absolute
 *   maximum. The HX711 works fine at 3.3V; it only costs a little range.
 *
 *   The MQ-6 needs 5V for its heater and cannot simply be run at 3.3V, so its AOUT
 *   can swing to about 5V. Put a divider between AOUT and GPIO 34 - two 10k
 *   resistors, AOUT -> 10k -> pin -> 10k -> GND - or you are over the ADC's input
 *   range. That halves the scale, so GAS_ALARM_THRESHOLD has to be re-derived
 *   against your own warmed-up sensor rather than trusted at its default.
 *
 *   GPIO 34 is on ADC1. Do not move the MQ-6 to a GPIO on ADC2 (0, 2, 4, 12-15,
 *   25-27): ADC2 is unavailable while WiFi is running, and analogRead() there
 *   returns garbage with no error.
 *
 * ---------------------------------------------------------------------------
 * LIBRARIES (Arduino Library Manager)
 * ---------------------------------------------------------------------------
 *   HX711 by Bogdan Necula          (bogde/HX711)
 *   ArduinoJson by Benoit Blanchon  (v7)
 *   WiFi, HTTPClient, Preferences   bundled with the ESP32 core
 *
 * ---------------------------------------------------------------------------
 * CALIBRATION - at runtime, over the serial monitor
 * ---------------------------------------------------------------------------
 * The calibration factor is stored in NVS (Preferences, namespace "cylguard",
 * key "calFactor"), so it survives a power cut and a reflash. Done once per
 * load cell, not once per build.
 *
 *   1. Power up with the platform EMPTY. The sketch tares itself and reports
 *      whether a saved factor was found.
 *   2. If none was found: place exactly KNOWN_CALIBRATION_WEIGHT_KG on the
 *      platform and type C in the serial monitor (115200).
 *   3. Check that the reference weight now reads back correctly.
 *   4. Type D at any time to delete the saved factor and start over.
 *
 * Until a factor is stored, readWeightKg() returns -1 and the sketch does not
 * post. An uncalibrated weight is worse than no weight: the backend derives
 * remaining gas, consumption, the prediction and the refill recommendation from
 * it, so a wrong number propagates everywhere while looking plausible.
 *
 * TWO LIMITATIONS OF THIS SCHEME, worth knowing before you rely on it:
 *
 *   - The tare offset is NOT persisted - only the factor is. The platform must
 *     therefore be empty at EVERY boot. If the cylinder is standing on it when
 *     the board resets - a power cut, a brownout, pressing EN - that weight
 *     becomes the new zero, and every reading afterwards is short by a full
 *     cylinder while looking entirely reasonable.
 *
 *   - A small reference weight on a 50 kg cell amplifies its own error. The
 *     factor derived from 500 g gets multiplied by roughly 58 to reach a full
 *     cylinder, and the error multiplies with it. A 5 kg reference is far more
 *     forgiving; set KNOWN_CALIBRATION_WEIGHT_KG to whatever you actually have.
 * ============================================================================
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include "HX711.h"
#include <Preferences.h>

// ===========================================================================
// CONFIGURATION - placeholders only. Replace before flashing.
// Nothing real is committed here: this file is in git, and a repository is not
// a secret store.
// ===========================================================================
static const char *WIFI_SSID      = "bm";
static const char *WIFI_PASSWORD  = "12345678";

// The CylinGuard API. Use the host's LAN address, not localhost - that means the
// ESP32 itself. Port 80 is the nginx edge; use :8000 to reach uvicorn directly.
static const char *API_BASE       = "http://192.168.1.100";
static const char *DEVICE_ID      = "ESP32-CYL-001";   // must already exist in `devices`
// Matches DEVICE_API_KEY in the server's .env. Leave empty if that is unset.
static const char *DEVICE_API_KEY = "";

static const bool CALIBRATION_MODE = false; // kept for compatibility
static const float KNOWN_CALIBRATION_WEIGHT_KG = 0.500f; // place exactly 500 g
static float HX711_OFFSET = 0.0f;
static float HX711_SCALE = 0.0f; // raw counts per kg; loaded from Preferences
static Preferences scalePrefs;
static bool weightCalibrated = false;

// Starting reporting interval, used until the first successful POST. The server owns
// this value (`measurement_interval` in the cylinder's settings row) and returns it in
// every ACK, so the device adopts the server's figure at runtime rather than needing
// this constant kept in sync by hand. Leak detection latency is bounded by the
// interval, so shorter is safer.
static const unsigned long REPORT_INTERVAL_MS = 30000UL;

// Guard rails on what the device will accept from the ACK. A server bug or a typo in
// Settings must not be able to silence the device for a day or melt it with a 10 ms
// loop, so an out-of-range value is logged and ignored rather than obeyed.
static const unsigned long MIN_REPORT_INTERVAL_MS = 5000UL;
static const unsigned long MAX_REPORT_INTERVAL_MS = 3600000UL;   // 1 hour

// Local alarm threshold, as a raw ADC value. The server has its own threshold and
// is the authority; this one exists so the buzzer still fires when WiFi is down.
//
// 700 is a starting point, not a calibrated figure. It assumes a 12-bit read of a
// 5V AOUT through the 2:1 divider described in the header - change the divider and
// this number means something else. Derive your own: let the sensor warm up for a
// few minutes in clean air, note the resting value, and set this well above it.
// Too low alarms on cooking fumes until nobody believes it; too high is worse.
static const int GAS_ALARM_THRESHOLD = 700;

// Most cheap relay modules energise on a LOW input. Get this wrong and the valve
// is driven backwards - closed when it should be open.
static const bool RELAY_ACTIVE_LOW = true;

// ===========================================================================
// PINS
// ===========================================================================
static const uint8_t PIN_HX711_DOUT = 16;
static const uint8_t PIN_HX711_SCK  = 4;
static const uint8_t PIN_MQ6        = 34;   // ADC1 only
static const uint8_t PIN_BUZZER     = 26;
static const uint8_t PIN_RELAY      = 27;

// ===========================================================================
// TUNING
// ===========================================================================
static const uint8_t  WEIGHT_SAMPLES     = 10;     // average 10 samples
static const uint8_t  GAS_SAMPLES        = 8;      // mean of successive ADC reads
static const uint32_t MQ6_WARMUP_MS      = 60000UL;// minimum before gas is trusted
static const uint8_t  MAX_POST_ATTEMPTS  = 3;
static const uint16_t POST_TIMEOUT_MS    = 8000;
static const uint32_t WIFI_RETRY_MS      = 15000UL;

HX711 scale;

static unsigned long lastReportAt = 0;
// Live reporting interval. Starts at the compiled-in value, then tracks the server.
static unsigned long reportIntervalMs = REPORT_INTERVAL_MS;
static unsigned long lastWifiAttemptAt = 0;
static unsigned long bootedAt = 0;
static bool alarmLatched = false;

// ===========================================================================
// WiFi
// ===========================================================================
void connectWifi(bool blocking) {
  if (WiFi.status() == WL_CONNECTED) return;

  unsigned long now = millis();
  if (!blocking && now - lastWifiAttemptAt < WIFI_RETRY_MS) return;
  lastWifiAttemptAt = now;

  Serial.printf("[wifi] connecting to %s\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  // The ESP32 persists credentials in flash and auto-reconnects to a stale AP
  // otherwise, which looks like a firmware bug when the SSID changes.
  WiFi.persistent(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  // Bounded even when blocking. An unreachable AP must not stop the sensor
  // reading and the local buzzer from working.
  unsigned long deadline = millis() + (blocking ? 20000UL : 6000UL);
  while (WiFi.status() != WL_CONNECTED && millis() < deadline) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[wifi] connected, ip ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("[wifi] not connected - will retry; sensing continues meanwhile");
  }
}

// ===========================================================================
// Sensors
// ===========================================================================

/*
 * Mean of WEIGHT_SAMPLES raw reads, converted to kg.
 *
 * Returns -1 when no calibration factor is stored, so the caller can decline to
 * post rather than send a number that looks like a measurement and is not.
 *
 * Note that a mean is sensitive to a single bad sample in a way a median is not:
 * one knock against the cylinder moves it. The backend smooths again over time
 * and classifies an implausible jump as a cylinder change rather than
 * consumption, so this is survivable - but a median of the same 10 samples would
 * reject the knock here, before it ever left the device.
 */
float readWeightKg() {
  // Take 10 readings and calculate their arithmetic mean.
  long long total = 0;
  for (uint8_t i = 0; i < WEIGHT_SAMPLES; i++) {
    total += scale.read();
    delay(12);
  }
  float averageRaw = (float)total / WEIGHT_SAMPLES;

  if (!weightCalibrated || HX711_SCALE == 0.0f) {
    Serial.printf("[weight] raw average of 10 samples: %.2f\n", averageRaw);
    return -1.0f; // not calibrated: do not report a fake kg value
  }

  float kg = (averageRaw - HX711_OFFSET) / HX711_SCALE;
  if (kg < 0.0f) kg = 0.0f;
  Serial.printf("[weight] 10-sample raw average: %.2f | Weight: %.3f kg\n",
                averageRaw, kg);
  return kg;
}

// At startup the platform MUST be empty. This records the zero offset.
// Calibration factor still requires a known reference weight; it cannot be
// physically inferred from an empty platform alone.
void initializeScaleCalibration() {
  if (!scale.wait_ready_timeout(3000)) {
    Serial.println("[weight] ERROR: HX711 not responding.");
    return;
  }

  Serial.println("[weight] Keep platform EMPTY and still for tare...");
  delay(3000);
  scale.tare(20);
  HX711_OFFSET = (float)scale.get_offset();

  scalePrefs.begin("cylguard", true);
  float savedFactor = scalePrefs.getFloat("calFactor", 0.0f);
  scalePrefs.end();

  if (savedFactor != 0.0f) {
    HX711_SCALE = savedFactor;
    weightCalibrated = true;
    Serial.printf("[weight] Saved calibration loaded: %.6f\n", HX711_SCALE);
    Serial.println("[weight] Weight measurement enabled.");
  } else {
    weightCalibrated = false;
    Serial.println("[weight] No saved calibration factor.");
    Serial.println("[weight] Place exactly 500 g on platform, then type C.");
    Serial.println("[weight] Type D to delete saved calibration.");
  }
}

void handleCalibrationSerial() {
  while (Serial.available()) {
    char command = Serial.read();
    if (command == 'C' || command == 'c') {
      if (!scale.wait_ready_timeout(2000)) {
        Serial.println("[calibration] HX711 not ready.");
        return;
      }
      Serial.println("[calibration] Keep the known 500 g weight still...");
      delay(1500);
      // scale.get_value() subtracts the current tare offset.
      long counts = scale.get_value(30);
      if (labs(counts) < 100) {
        Serial.println("[calibration] ERROR: counts too small. Check wiring and weight.");
        return;
      }
      HX711_SCALE = (float)counts / KNOWN_CALIBRATION_WEIGHT_KG;
      if (HX711_SCALE == 0.0f) {
        Serial.println("[calibration] ERROR: invalid factor.");
        return;
      }
      scalePrefs.begin("cylguard", false);
      scalePrefs.putFloat("calFactor", HX711_SCALE);
      scalePrefs.end();
      weightCalibrated = true;
      Serial.printf("[calibration] Saved factor: %.6f\n", HX711_SCALE);
      Serial.println("[calibration] Now check that 500 g displays about 0.500 kg.");
    } else if (command == 'D' || command == 'd') {
      scalePrefs.begin("cylguard", false);
      scalePrefs.remove("calFactor");
      scalePrefs.end();
      weightCalibrated = false;
      HX711_SCALE = 0.0f;
      Serial.println("[calibration] Saved factor deleted. Reset ESP32 with empty platform.");
    }
  }
}

int readGasRaw() {
  long total = 0;
  for (uint8_t i = 0; i < GAS_SAMPLES; i++) {
    total += analogRead(PIN_MQ6);
    delay(8);
  }
  return (int)(total / GAS_SAMPLES);
}

bool mq6Warm() {
  return millis() - bootedAt >= MQ6_WARMUP_MS;
}

// ===========================================================================
// Actuators
// ===========================================================================
void setBuzzer(bool on) {
  digitalWrite(PIN_BUZZER, on ? HIGH : LOW);
}

void setRelay(bool activated) {
  // `activated` means "command the shutoff", not "gas has stopped".
  bool level = RELAY_ACTIVE_LOW ? !activated : activated;
  digitalWrite(PIN_RELAY, level ? HIGH : LOW);
}

/*
 * Local alarm, independent of the server.
 *
 * Deliberately not waiting for the backend to agree: if WiFi is down or the API is
 * unreachable, the buzzer must still sound. The server runs the same comparison
 * against its own configurable threshold and is the authority for what is
 * recorded - this is the last-resort local copy.
 */
void applyLocalAlarm(int gasRaw) {
  if (!mq6Warm()) return;   // a warming MQ-6 reads high and would false-alarm

  bool shouldAlarm = gasRaw >= GAS_ALARM_THRESHOLD;
  if (shouldAlarm == alarmLatched) return;   // only act on a change

  alarmLatched = shouldAlarm;
  setBuzzer(shouldAlarm);
  setRelay(shouldAlarm);
  Serial.printf("[safety] gas %d %s threshold %d - buzzer %s, relay %s (commanded)\n",
                gasRaw, shouldAlarm ? ">=" : "<", GAS_ALARM_THRESHOLD,
                shouldAlarm ? "ON" : "OFF",
                shouldAlarm ? "ACTIVATED" : "NORMAL");
}

// ===========================================================================
// Reporting
// ===========================================================================

/*
 * Adopt the reporting interval the server asked for, if it is sane.
 *
 * The server owns `measurement_interval`; it is editable in Settings, so a firmware
 * constant that disagrees with it is how a device ends up reporting at one rate while
 * being judged offline at another. Only that one field is read - the rest of the ACK
 * is diagnostics - and a filter keeps the parse small, which matters on a board where
 * the JSON document competes with the WiFi buffers for heap.
 *
 * An out-of-range value is logged and ignored rather than obeyed: a typo in Settings
 * must not be able to silence the device for a day, and leak latency is bounded by
 * this interval.
 */
static void adoptServerInterval(const String &ackBody) {
  if (ackBody.length() == 0) return;

  JsonDocument filter;
  filter["report_interval_seconds"] = true;

  JsonDocument ack;
  if (deserializeJson(ack, ackBody, DeserializationOption::Filter(filter))) return;

  unsigned long seconds = ack["report_interval_seconds"] | 0UL;
  if (seconds == 0) return;   // field absent: an older server, so keep what we have

  unsigned long wanted = seconds * 1000UL;
  if (wanted < MIN_REPORT_INTERVAL_MS || wanted > MAX_REPORT_INTERVAL_MS) {
    Serial.printf("[post] ignoring out-of-range interval %lus from server\n", seconds);
    return;
  }
  if (wanted != reportIntervalMs) {
    Serial.printf("[post] reporting interval %lums -> %lums (server)\n",
                  reportIntervalMs, wanted);
    reportIntervalMs = wanted;
  }
}


/*
 * POST one reading. Returns true on 2xx.
 *
 * No timestamp is sent. The ESP32 has no battery-backed clock, so after a power
 * cut its time is 1970 - and the server rejects a timestamp more than 7 days old.
 * Omitting it lets the server stamp the reading with its own clock, which is
 * correct far more often than the device's.
 */
bool postReading(float weightKg, int gasRaw) {
  if (WiFi.status() != WL_CONNECTED) return false;

  String url = String(API_BASE) + "/api/iot/sensor-data";

  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  // Three decimals: the column is DECIMAL(7,3), and more would be rounded anyway.
  doc["total_weight_kg"] = serialized(String(weightKg, 3));
  doc["gas_sensor_value"] = gasRaw;
  doc["wifi_status"] = "CONNECTED";
  doc["firmware_version"] = "1.0.0";

  String body;
  serializeJson(doc, body);

  for (uint8_t attempt = 1; attempt <= MAX_POST_ATTEMPTS; attempt++) {
    HTTPClient http;
    http.setTimeout(POST_TIMEOUT_MS);
    if (!http.begin(url)) {
      Serial.println("[post] could not begin request");
      return false;
    }
    http.addHeader("Content-Type", "application/json");
    if (strlen(DEVICE_API_KEY) > 0) {
      http.addHeader("X-Device-Key", DEVICE_API_KEY);
    }

    int code = http.POST(body);
    if (code >= 200 && code < 300) {
      Serial.printf("[post] %.3f kg, gas %d -> HTTP %d\n", weightKg, gasRaw, code);
      adoptServerInterval(http.getString());
      http.end();
      return true;
    }

    // 4xx is our fault and will not fix itself: an unregistered device_id, a bad
    // key, a value the server considers implausible. Retrying wastes power and
    // floods the log. 5xx and network errors are worth another go.
    Serial.printf("[post] attempt %d/%d failed: HTTP %d %s\n",
                  attempt, MAX_POST_ATTEMPTS, code,
                  code > 0 ? http.getString().c_str() : http.errorToString(code).c_str());
    http.end();

    if (code >= 400 && code < 500) return false;
    delay(400UL * attempt);   // back off a little between tries
  }
  return false;
}

// ===========================================================================
// Arduino entry points
// ===========================================================================
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n[boot] CylinGuard ESP32");
  Serial.println("[boot] MQ-6 is a prototype sensor, not a certified detector.");

  bootedAt = millis();

  pinMode(PIN_BUZZER, OUTPUT);
  pinMode(PIN_RELAY, OUTPUT);
  // Known-safe state before anything else: silent, and the valve left open. A
  // relay that defaults to activated would cut the gas on every reset.
  setBuzzer(false);
  setRelay(false);

  // 12-bit, 0-4095, matching MAX_PLAUSIBLE_GAS_VALUE on the server.
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_MQ6, ADC_11db);

  scale.begin(PIN_HX711_DOUT, PIN_HX711_SCK);
  initializeScaleCalibration();

  connectWifi(true);

  if (CALIBRATION_MODE) {
    Serial.println("[calib] CALIBRATION MODE - not reporting to the API");
  } else if (!weightCalibrated) {
    // Checked against weightCalibrated, not against the old sentinel values:
    // HX711_SCALE now starts at 0 and is loaded from NVS, so comparing it to 1.0f
    // would never fire and this warning would never appear.
    Serial.println("[warn] HX711 is UNCALIBRATED - no weight will be reported.");
    Serial.println("[warn] Place the reference weight and type C; see the file header.");
  }
  Serial.printf("[boot] MQ-6 warm-up: %lus before gas readings are trusted\n",
                MQ6_WARMUP_MS / 1000UL);
}

void loop() {
  handleCalibrationSerial();

  if (CALIBRATION_MODE) {
    long total = 0;
    for (uint8_t i = 0; i < 20; i++) { total += scale.read(); delay(50); }
    Serial.printf("[calib] raw average: %ld\n", total / 20);
    delay(1000);
    return;
  }

  int gasRaw = readGasRaw();
  // Every cycle, not only when reporting: the local alarm must not wait on the
  // report interval.
  applyLocalAlarm(gasRaw);

  connectWifi(false);

  unsigned long now = millis();
  // Subtraction, not `>`: millis() overflows after ~49 days and unsigned
  // subtraction stays correct across the wrap. Comparing absolute values would
  // leave the device silent until the next reboot.
  if (now - lastReportAt >= reportIntervalMs) {
    lastReportAt = now;
    float weightKg = readWeightKg();
    if (weightKg < 0.0f) {
      Serial.println("[weight] Weight unavailable: calibration required.");
    } else if (!postReading(weightKg, gasRaw)) {
      Serial.println("[post] giving up on this cycle; the server will mark the device OFFLINE");
    }
  }

  delay(500);
}
