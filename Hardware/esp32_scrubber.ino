/*
 * Hardware/esp32_scrubber.ino
 * Project S.A.A.S. — Active Atmospheric Scrubber Node Firmware
 * ============================================================
 * ESP32-WROOM-32 + GP2Y1010AU0F Optical Dust Sensor + High-Pressure Pump
 *
 * Features:
 *   - MQTT subscriber: receives commands from Python backend (FieldAgent)
 *   - Stokes Number optimization: adjusts pump pressure for 10–50 μm droplets
 *   - Yaw-pitch wind alignment: rotates nozzle into wind vector for max dwell time
 *   - GP2Y1010 dust sensor: local PM validation to cross-check bridge state
 *   - OTA firmware updates via ArduinoOTA
 *   - Watchdog timer: auto-restart if MQTT heartbeat lost > 5 min
 *
 * MQTT Topics:
 *   Subscribe: saas/wards/{WARD_ID}/scrubber/cmd     — activation commands
 *   Subscribe: saas/met/wind_bearing                 — wind vector updates
 *   Publish:   saas/wards/{WARD_ID}/scrubber/status  — heartbeat + sensor data
 *   Publish:   saas/wards/{WARD_ID}/sensor/pm25      — local PM2.5 reading
 *
 * Calibration: sensor_calibration.h
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <ArduinoOTA.h>
#include <ESP32Servo.h>
#include "sensor_calibration.h"

// ── Configuration ─────────────────────────────────────────────────────────────
#define WARD_ID          "Narela"        // Change per deployment
#define WIFI_SSID        "SAAS_MESH"
#define WIFI_PASSWORD    "saas_secure_2026"
#define MQTT_BROKER      "192.168.1.100"
#define MQTT_PORT        1883
#define MQTT_USER        "saas_node"
#define MQTT_PASS        "saas_mqtt_pass"

// ── Pin Definitions ───────────────────────────────────────────────────────────
#define DUST_LED_PIN     4     // GP2Y1010 LED drive
#define DUST_AOUT_PIN    34    // GP2Y1010 analog output (ADC1)
#define PUMP_PWM_PIN     25    // High-pressure pump PWM (MOSFET gate)
#define SERVO_YAW_PIN    26    // Nozzle yaw servo
#define SERVO_PITCH_PIN  27    // Nozzle pitch servo
#define STATUS_LED_PIN   2     // Onboard LED

// ── Stokes Number Constants ───────────────────────────────────────────────────
// Optimal droplet range: 10–50 μm
// Pump frequency ↔ droplet size mapping (empirically calibrated)
// Lower PWM duty → lower pressure → larger droplets
#define PUMP_DUTY_18UM   140   // 18 μm: fine mist (low PM)
#define PUMP_DUTY_28UM   180   // 28 μm: standard scrubbing
#define PUMP_DUTY_42UM   220   // 42 μm: aggressive washout (heavy PM)
#define PUMP_DUTY_OFF    0

// ── Servo Angles ──────────────────────────────────────────────────────────────
#define SERVO_CENTER_YAW   90
#define SERVO_CENTER_PITCH 60
#define SERVO_RANGE_YAW    45   // ±45° from center
#define SERVO_RANGE_PITCH  30   // ±30° from center

// ── Watchdog ─────────────────────────────────────────────────────────────────
#define WATCHDOG_TIMEOUT_MS  300000  // 5 minutes

// ── State ─────────────────────────────────────────────────────────────────────
WiFiClient   wifiClient;
PubSubClient mqttClient(wifiClient);
Servo        servoYaw;
Servo        servoPitch;

bool    scrubberActive    = false;
float   currentDropletUm  = 28.0;
float   currentWindBearing = 270.0;
unsigned long lastHeartbeat = 0;
unsigned long lastMqttMsg   = 0;

char cmdTopic[64];
char windTopic[]    = "saas/met/wind_bearing";
char statusTopic[64];
char pm25Topic[64];


// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  Serial.println("[S.A.A.S. Node] Booting — Ward: " WARD_ID);

  pinMode(DUST_LED_PIN,  OUTPUT);
  pinMode(PUMP_PWM_PIN,  OUTPUT);
  pinMode(STATUS_LED_PIN, OUTPUT);
  digitalWrite(DUST_LED_PIN, LOW);
  analogWrite(PUMP_PWM_PIN, PUMP_DUTY_OFF);

  servoYaw.attach(SERVO_YAW_PIN);
  servoPitch.attach(SERVO_PITCH_PIN);
  centerNozzle();

  snprintf(cmdTopic,    sizeof(cmdTopic),    "saas/wards/%s/scrubber/cmd",    WARD_ID);
  snprintf(statusTopic, sizeof(statusTopic), "saas/wards/%s/scrubber/status", WARD_ID);
  snprintf(pm25Topic,   sizeof(pm25Topic),   "saas/wards/%s/sensor/pm25",     WARD_ID);

  connectWiFi();
  setupOTA();

  mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
  connectMQTT();

  lastHeartbeat = millis();
  Serial.println("[S.A.A.S. Node] Ready.");
}


// ── Main Loop ─────────────────────────────────────────────────────────────────
void loop() {
  ArduinoOTA.handle();

  if (!mqttClient.connected()) {
    connectMQTT();
  }
  mqttClient.loop();

  // Watchdog: if no MQTT message in 5 min, publish fault and restart
  if (millis() - lastMqttMsg > WATCHDOG_TIMEOUT_MS) {
    Serial.println("[WATCHDOG] MQTT timeout — restarting");
    publishStatus("fault", "mqtt_timeout");
    delay(500);
    ESP.restart();
  }

  // Heartbeat publish every 30 seconds
  if (millis() - lastHeartbeat > 30000) {
    float pm25 = readDustSensor();
    publishPM25(pm25);
    publishStatus(scrubberActive ? "active" : "standby", "");
    lastHeartbeat = millis();
    blinkStatus(scrubberActive ? 2 : 1);
  }
}


// ── MQTT Callback ─────────────────────────────────────────────────────────────
void mqttCallback(char* topic, byte* payload, unsigned int length) {
  lastMqttMsg = millis();

  String topicStr(topic);
  String msg;
  for (unsigned int i = 0; i < length; i++) msg += (char)payload[i];

  StaticJsonDocument<512> doc;
  DeserializationError err = deserializeJson(doc, msg);
  if (err) {
    Serial.printf("[MQTT] JSON parse error: %s\n", err.c_str());
    return;
  }

  // ── Scrubber command ────────────────────────────────────────────────────────
  if (topicStr == cmdTopic) {
    const char* action     = doc["action"];
    float droplet_um       = doc["droplet_um"] | 28.0;
    float wind_bearing_deg = doc["wind_bearing_deg"] | 270.0;

    if (strcmp(action, "activate") == 0) {
      // Validate Stokes range
      if (droplet_um < 5.0 || droplet_um > 100.0) {
        Serial.printf("[SCRUBBER] REJECT: droplet %.1fμm outside safe Stokes range\n", droplet_um);
        publishStatus("rejected", "stokes_violation");
        return;
      }
      activateScrubber(droplet_um, wind_bearing_deg);
    } else if (strcmp(action, "deactivate") == 0) {
      deactivateScrubber();
    } else {
      Serial.printf("[SCRUBBER] Unknown action: %s\n", action);
    }
  }

  // ── Wind vector update ──────────────────────────────────────────────────────
  else if (topicStr == windTopic) {
    float city_bearing = doc["city_bearing_deg"] | 270.0;
    // Check ward-specific override
    JsonObject wards   = doc["wards"];
    if (wards.containsKey(WARD_ID)) {
      currentWindBearing = wards[WARD_ID]["wind_bearing_deg"] | city_bearing;
    } else {
      currentWindBearing = city_bearing;
    }
    if (scrubberActive) {
      alignNozzleToWind(currentWindBearing);
    }
    Serial.printf("[MET] Wind bearing updated: %.0f°\n", currentWindBearing);
  }
}


// ── Scrubber Control ──────────────────────────────────────────────────────────
void activateScrubber(float droplet_um, float wind_bearing_deg) {
  currentDropletUm = droplet_um;

  // Map droplet size to pump PWM duty
  int pumpDuty;
  if (droplet_um <= 20.0)      pumpDuty = PUMP_DUTY_18UM;
  else if (droplet_um <= 32.0) pumpDuty = PUMP_DUTY_28UM;
  else                          pumpDuty = PUMP_DUTY_42UM;

  analogWrite(PUMP_PWM_PIN, pumpDuty);
  alignNozzleToWind(wind_bearing_deg);

  scrubberActive = true;
  Serial.printf("[SCRUBBER] ACTIVE — droplet=%.0fμm duty=%d bearing=%.0f°\n",
                droplet_um, pumpDuty, wind_bearing_deg);
  publishStatus("active", "");
}


void deactivateScrubber() {
  analogWrite(PUMP_PWM_PIN, PUMP_DUTY_OFF);
  centerNozzle();
  scrubberActive = false;
  Serial.println("[SCRUBBER] DEACTIVATED");
  publishStatus("standby", "");
}


// ── Nozzle Alignment (Yaw-Pitch into Wind Vector) ────────────────────────────
void alignNozzleToWind(float bearing_deg) {
  // Convert meteorological bearing to servo angle
  // Wind from 270° (west) → nozzle faces west → yaw = center - 45°
  float delta = bearing_deg - 270.0;  // deviation from default westerly
  if (delta > 180)  delta -= 360;
  if (delta < -180) delta += 360;

  int yawAngle   = SERVO_CENTER_YAW   + constrain((int)(delta * 0.5), -SERVO_RANGE_YAW, SERVO_RANGE_YAW);
  int pitchAngle = SERVO_CENTER_PITCH; // Fixed pitch; extend with elevation sensor if available

  servoYaw.write(yawAngle);
  servoPitch.write(pitchAngle);
  Serial.printf("[NOZZLE] Yaw=%d° Pitch=%d° (wind=%.0f°)\n", yawAngle, pitchAngle, bearing_deg);
}


void centerNozzle() {
  servoYaw.write(SERVO_CENTER_YAW);
  servoPitch.write(SERVO_CENTER_PITCH);
}


// ── Dust Sensor (GP2Y1010AU0F) ────────────────────────────────────────────────
float readDustSensor() {
  // GP2Y1010 read sequence: pulse LED, wait 280μs, read ADC, wait 40μs, LED off
  digitalWrite(DUST_LED_PIN, HIGH);
  delayMicroseconds(280);
  int raw = analogRead(DUST_AOUT_PIN);
  delayMicroseconds(40);
  digitalWrite(DUST_LED_PIN, LOW);
  delayMicroseconds(9680);

  // Voltage → dust density (mg/m³) using calibration constants from sensor_calibration.h
  float voltage = (raw / 4095.0) * 3.3;
  float dustMg  = max(0.0f, (voltage - DUST_SENSOR_ZERO_V) * DUST_SENSOR_SENSITIVITY);

  // mg/m³ → μg/m³ → approximate PM2.5 (empirical factor for Delhi ambient conditions)
  float pm25 = dustMg * 1000.0 * DELHI_PM25_CORRECTION_FACTOR;
  return constrain(pm25, 0.0, 999.0);
}


// ── MQTT Publish ──────────────────────────────────────────────────────────────
void publishStatus(const char* status, const char* fault) {
  StaticJsonDocument<256> doc;
  doc["ward"]          = WARD_ID;
  doc["status"]        = status;
  doc["active"]        = scrubberActive;
  doc["droplet_um"]    = currentDropletUm;
  doc["wind_bearing"]  = currentWindBearing;
  if (strlen(fault) > 0) doc["fault"] = fault;
  doc["uptime_s"]      = millis() / 1000;

  char buf[256];
  serializeJson(doc, buf);
  mqttClient.publish(statusTopic, buf, true);
}


void publishPM25(float pm25) {
  StaticJsonDocument<128> doc;
  doc["ward"]    = WARD_ID;
  doc["pm25"]    = pm25;
  doc["unit"]    = "ug/m3";
  doc["sensor"]  = "GP2Y1010AU0F";

  char buf[128];
  serializeJson(doc, buf);
  mqttClient.publish(pm25Topic, buf);
}


// ── Connectivity ──────────────────────────────────────────────────────────────
void connectWiFi() {
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("[WiFi] Connecting");
  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 30) {
    delay(500);
    Serial.print(".");
    retries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("\n[WiFi] Connected — IP: %s\n", WiFi.localIP().toString().c_str());
  } else {
    Serial.println("\n[WiFi] FAILED — continuing offline");
  }
}


void connectMQTT() {
  while (!mqttClient.connected()) {
    Serial.print("[MQTT] Connecting...");
    String clientId = "SAAS-" + String(WARD_ID) + "-" + String(random(0xffff), HEX);
    if (mqttClient.connect(clientId.c_str(), MQTT_USER, MQTT_PASS)) {
      Serial.println(" connected.");
      mqttClient.subscribe(cmdTopic);
      mqttClient.subscribe(windTopic);
      publishStatus("online", "");
      lastMqttMsg = millis();
    } else {
      Serial.printf(" failed (rc=%d) — retry in 5s\n", mqttClient.state());
      delay(5000);
    }
  }
}


void setupOTA() {
  ArduinoOTA.setHostname("saas-scrubber-" WARD_ID);
  ArduinoOTA.onStart([]() { Serial.println("[OTA] Start"); });
  ArduinoOTA.onEnd([]()   { Serial.println("\n[OTA] End"); });
  ArduinoOTA.onError([](ota_error_t error) {
    Serial.printf("[OTA] Error[%u]\n", error);
  });
  ArduinoOTA.begin();
}


// ── Utilities ─────────────────────────────────────────────────────────────────
void blinkStatus(int times) {
  for (int i = 0; i < times; i++) {
    digitalWrite(STATUS_LED_PIN, HIGH);
    delay(100);
    digitalWrite(STATUS_LED_PIN, LOW);
    delay(100);
  }
}
