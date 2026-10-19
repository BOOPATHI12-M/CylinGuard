/*
 * CylinGuard GSM/LCD firmware variant
 *
 * Local behavior:
 *   - Displays gross load-cell weight and MQ-6 value on a 16x2 I2C LCD.
 *   - Sounds the buzzer for gas or low weight.
 *   - Sends an SMS and places a call on each alert transition, with cooldown.
 *
 * Backend behavior:
 *   - Uses ESP32 Wi-Fi to POST readings to /api/iot/sensor-data.
 *   - Sends weight in kilograms because that is the backend contract.
 *
 * This sketch is intentionally in its own folder. Do not place it beside another
 * sketch with setup() and loop(), because Arduino compiles all .ino files in one
 * sketch directory together.
 *
 * Verify the sensor calibration, MQ-6 threshold, relay/actuator safety, Wi-Fi
 * credentials, and GSM wiring on real hardware before deployment.
 */

#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <LiquidCrystal_I2C.h>
#include <WiFi.h>
#include <Wire.h>
#include "HX711.h"

// LCD 16x2 I2C
LiquidCrystal_I2C lcd(0x27, 16, 2);

// HX711 load cell
static const uint8_t HX711_DT = 18;
static const uint8_t HX711_SCK = 19;
HX711 scale;

// The factor must be calibrated for this load cell and library unit convention.
static const float CALIBRATION_FACTOR = 208.614f;

// MQ-6 analog input
static const uint8_t GAS_SENSOR = 34;
static const int GAS_THRESHOLD = 2000;

// GSM module
static const uint8_t GSM_RX = 26;
static const uint8_t GSM_TX = 27;
HardwareSerial gsm(1);
const char PHONE_NUMBER[] = "+<COUNTRY_CODE><PHONE_NUMBER>";

// Wi-Fi/backend
const char WIFI_SSID[] = "REPLACE_WITH_WIFI_SSID";
const char WIFI_PASSWORD[] = "REPLACE_WITH_WIFI_PASSWORD";
const char API_BASE[] = "http://192.168.1.100";
const char DEVICE_ID[] = "ESP32-CYL-001";
const char DEVICE_API_KEY[] = "";

// Buzzer and thresholds
static const uint8_t BUZZER = 13;
static const float LOW_WEIGHT_GRAMS = 300.0f;
static const unsigned long ALERT_COOLDOWN_MS = 60000UL;

// Timing and sampling
static const uint8_t WEIGHT_SAMPLES = 5;
static const uint8_t GAS_SAMPLES = 8;
static const unsigned long REPORT_INTERVAL_MS = 30000UL;
static const unsigned long WIFI_RETRY_INTERVAL_MS = 15000UL;
static const uint16_t HTTP_TIMEOUT_MS = 8000;

unsigned long lastGasAlert = 0;
unsigned long lastWeightAlert = 0;
unsigned long lastReport = 0;
unsigned long lastWiFiAttempt = 0;
unsigned long reportIntervalMs = REPORT_INTERVAL_MS;

void sendSMS(const char* message) {
  gsm.println("AT+CMGF=1");
  delay(500);
  gsm.print("AT+CMGS=\"");
  gsm.print(PHONE_NUMBER);
  gsm.println("\"");
  delay(1000);
  gsm.print(message);
  delay(300);
  gsm.write(26);
  delay(5000);
}

void makeCall() {
  gsm.print("ATD");
  gsm.print(PHONE_NUMBER);
  gsm.println(";");
  delay(15000);
  gsm.println("ATH");
  delay(1000);
}

void sendAlert(const char* message) {
  Serial.println(message);
  sendSMS(message);
  makeCall();
}

void connectWiFi(bool force) {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  unsigned long now = millis();
  if (!force && now - lastWiFiAttempt < WIFI_RETRY_INTERVAL_MS) {
    return;
  }
  lastWiFiAttempt = now;

  Serial.print("Connecting to Wi-Fi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long deadline = millis() + 6000UL;
  while (WiFi.status() != WL_CONNECTED && millis() < deadline) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("Wi-Fi connected: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("Wi-Fi unavailable; local monitoring continues");
  }
}

void adoptReportInterval(const String& response) {
  if (response.length() == 0) {
    return;
  }

  JsonDocument document;
  if (deserializeJson(document, response)) {
    Serial.println("Invalid backend response; keeping current interval");
    return;
  }

  unsigned long seconds = document["report_interval_seconds"] | 0UL;
  if (seconds < 5UL || seconds > 3600UL) {
    return;
  }
  reportIntervalMs = seconds * 1000UL;
}

bool postReading(float weightGrams, int gasValue) {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  JsonDocument document;
  document["device_id"] = DEVICE_ID;
  document["total_weight_kg"] = weightGrams / 1000.0f;
  document["gas_sensor_value"] = gasValue;
  document["wifi_status"] = "CONNECTED";
  document["firmware_version"] = "2.0.0-gsm-lcd";

  String body;
  serializeJson(document, body);

  HTTPClient http;
  String url = String(API_BASE) + "/api/iot/sensor-data";
  http.setTimeout(HTTP_TIMEOUT_MS);
  if (!http.begin(url)) {
    Serial.println("Could not start backend request");
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  if (strlen(DEVICE_API_KEY) > 0) {
    http.addHeader("X-Device-Key", DEVICE_API_KEY);
  }

  int statusCode = http.POST(body);
  if (statusCode >= 200 && statusCode < 300) {
    String response = http.getString();
    adoptReportInterval(response);
    Serial.printf("Uploaded %.1f g, gas %d, HTTP %d\n",
                  weightGrams, gasValue, statusCode);
    http.end();
    return true;
  }

  Serial.printf("Backend upload failed: HTTP %d\n", statusCode);
  http.end();
  return false;
}

float readWeightGrams(bool& ready) {
  ready = scale.is_ready();
  if (!ready) {
    return 0.0f;
  }
  return scale.get_units(WEIGHT_SAMPLES);
}

int readGasValue() {
  long total = 0;
  for (uint8_t sample = 0; sample < GAS_SAMPLES; sample++) {
    total += analogRead(GAS_SENSOR);
    delay(8);
  }
  return static_cast<int>(total / GAS_SAMPLES);
}

void updateLCD(float weightGrams, bool loadCellReady, int gasValue,
               bool gasDetected, bool lowWeight) {
  lcd.setCursor(0, 0);
  if (loadCellReady) {
    lcd.print("Weight:");
    lcd.print(weightGrams, 1);
    lcd.print("g   ");
  } else {
    lcd.print("Load cell error ");
  }

  lcd.setCursor(0, 1);
  if (gasDetected) {
    lcd.print("GAS WARNING!    ");
  } else if (lowWeight) {
    lcd.print("LOW WEIGHT!     ");
  } else {
    lcd.print("Gas:");
    lcd.print(gasValue);
    lcd.print(" Normal   ");
  }
}

void setup() {
  Serial.begin(115200);

  Wire.begin(21, 22);
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("CylinGuard");
  lcd.setCursor(0, 1);
  lcd.print("Starting...");
  delay(2000);

  pinMode(GAS_SENSOR, INPUT);
  analogReadResolution(12);

  pinMode(BUZZER, OUTPUT);
  digitalWrite(BUZZER, LOW);

  scale.begin(HX711_DT, HX711_SCK);
  scale.set_scale(CALIBRATION_FACTOR);
  if (scale.is_ready()) {
    lcd.clear();
    lcd.print("Remove weight");
    delay(2000);
    scale.tare();
  } else {
    Serial.println("HX711 is not ready");
  }

  gsm.begin(9600, SERIAL_8N1, GSM_RX, GSM_TX);
  delay(3000);
  gsm.println("AT");

  connectWiFi(true);

  lcd.clear();
  lcd.print("System Ready");
  delay(1000);
}

void loop() {
  int gasValue = readGasValue();
  bool loadCellReady = false;
  float weightGrams = readWeightGrams(loadCellReady);

  bool gasDetected = gasValue >= GAS_THRESHOLD;
  bool lowWeight = loadCellReady &&
                   weightGrams >= 0.0f &&
                   weightGrams < LOW_WEIGHT_GRAMS;

  digitalWrite(BUZZER, (gasDetected || lowWeight) ? HIGH : LOW);
  updateLCD(weightGrams, loadCellReady, gasValue, gasDetected, lowWeight);

  unsigned long now = millis();
  if (gasDetected &&
      (lastGasAlert == 0 || now - lastGasAlert >= ALERT_COOLDOWN_MS)) {
    sendAlert("CylinGuard: High gas sensor reading. Check immediately.");
    lastGasAlert = millis();
  }

  if (lowWeight &&
      (lastWeightAlert == 0 || now - lastWeightAlert >= ALERT_COOLDOWN_MS)) {
    sendAlert("CylinGuard: Weight below 300 grams.");
    lastWeightAlert = millis();
  }

  connectWiFi(false);
  if (loadCellReady && now - lastReport >= reportIntervalMs) {
    lastReport = now;
    if (!postReading(weightGrams, gasValue)) {
      Serial.println("Reading not uploaded; local monitoring continues");
    }
  }

  delay(500);
}
