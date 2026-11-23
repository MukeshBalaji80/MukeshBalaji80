/**
 * ESP32 Wi-Fi RSSI Monitor Firmware
 *
 * Measures Wi-Fi RSSI (dBm) and streams it over USB serial as CSV-style lines:
 *   TIME_MS,RSSI_DBM
 *   where TIME_MS = milliseconds since boot and RSSI_DBM = integer dBm.
 *
 * Debug/status messages always start with "#" so the dashboard can ignore them.
 *
 * Serial baud: 115200
 */

#include <WiFi.h>

// ===== Wi-Fi credentials (PLACEHOLDERS — replace with your network details) =====
const char* ssid = "YOUR_WIFI_SSID_HERE";
const char* password = "YOUR_WIFI_PASSWORD_HERE";

// ===== Sample interval (ms) — one reading per second =====
const unsigned long kPrintInterval = 1000;

// ===== Reconnect bookkeeping =====
unsigned long lastSampleTime = 0;   // last time we printed a sample
unsigned long reconnectAttemptTime = 0;
const unsigned long kReconnectInterval = 5000; // retry Wi-Fi every 5 s
bool wasConnected = false; // tracks connection transitions

void setup() {
  Serial.begin(115200);
  while (!Serial) {
    ; // Wait for USB serial to be ready (native USB only)
  }

  Serial.println("# ================================================");
  Serial.println("# ESP32 Wi-Fi RSSI Monitor");
  Serial.println("# ================================================");

  // Connect to Wi-Fi. If the credentials are placeholders the sketch will
  // simply keep retrying without ever printing a measurement — the dashboard
  // stays clean.
  if (strcmp(ssid, "YOUR_WIFI_SSID_HERE") == 0) {
    Serial.println("# ERROR: Set your Wi-Fi SSID and password in the sketch.");
  } else {
    Serial.print("# Connecting to Wi-Fi: ");
    Serial.println(ssid);
    WiFi.begin(ssid, password);
  }

  reconnectAttemptTime = millis();
}

void loop() {
  const bool nowConnected = (WiFi.status() == WL_CONNECTED);

  // Detect connection transitions and announce them.
  if (nowConnected && !wasConnected) {
    Serial.print("# Wi-Fi connected. IP: ");
    Serial.println(WiFi.localIP());
    lastSampleTime = millis(); // start the clock right when we connect
  } else if (!nowConnected && wasConnected) {
    Serial.println("# Wi-Fi lost — no measurements until reconnect.");
  }
  wasConnected = nowConnected;

  // Auto-reconnect while disconnected. While disconnected we print NOTHING
  // that looks like data, so the dashboard never records fake RSSI values.
  if (!nowConnected && (millis() - reconnectAttemptTime >= kReconnectInterval)) {
    Serial.println("# Wi-Fi disconnected — reconnecting...");
    WiFi.reconnect();
    reconnectAttemptTime = millis();
    delay(200);
    return;
  }

  // Only emit measurements while actually connected to Wi-Fi.
  if (nowConnected && (millis() - lastSampleTime >= kPrintInterval)) {
    lastSampleTime = millis();
    int rssi = WiFi.RSSI(); // current RSSI in dBm (negative number)
    // CSV-style output consumed by the Flask dashboard:
    Serial.print(millis());
    Serial.print(",");
    Serial.println(rssi);
  }

  delay(10); // small housekeeping delay
}