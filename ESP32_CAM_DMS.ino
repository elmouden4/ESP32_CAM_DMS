#include "esp_camera.h"
#include <WiFi.h>
#include <WebServer.h>

// ESP32-CAM AI Thinker — no external camera_pins.h required.
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

const char *WIFI_SSID = "esp";
const char *WIFI_PASS = "00000000";

// GPIO 13 and 14 are on the ESP32-CAM module, but may not be accessible
// through the ESP32-CAM-MB adapter. Do not use a microSD card simultaneously.
const int LED_PIN = 13;
const int BUZZER_PIN = 14;
const bool BUZZER_ACTIVE_HIGH = true; // false for active-low buzzer modules
const uint32_t WATCHDOG_MS = 7000; // Loss of PC heartbeat -> alert (fail-safe)
WebServer server(80);
bool alarmOn = false;
bool monitoringStarted = false;
uint32_t lastHeartbeat = 0;

void setAlarm(bool on) {
  if (on == alarmOn) return;
  alarmOn = on;
  digitalWrite(LED_PIN, on ? HIGH : LOW);
  digitalWrite(BUZZER_PIN, on == BUZZER_ACTIVE_HIGH ? HIGH : LOW);
  Serial.println(on ? "ALARM ON" : "ALARM OFF");
}

void handleCapture() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) { server.send(503, "text/plain", "Camera capture failed"); return; }
  if (fb->format != PIXFORMAT_JPEG) {
    esp_camera_fb_return(fb);
    server.send(500, "text/plain", "Not JPEG");
    return;
  }
  WiFiClient client = server.client();
  client.printf("HTTP/1.1 200 OK\r\nContent-Type: image/jpeg\r\nContent-Length: %u\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n", (unsigned)fb->len);
  client.write(fb->buf, fb->len);
  client.flush();
  esp_camera_fb_return(fb);
}

void handleAlarm(bool on) {
  monitoringStarted = true;
  lastHeartbeat = millis();
  setAlarm(on);
  server.send(200, "text/plain", on ? "ALERT" : "SAFE");
}

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  // Explicit initial off state (setAlarm(false) would be a no-op).
  digitalWrite(LED_PIN, LOW);
  digitalWrite(BUZZER_PIN, BUZZER_ACTIVE_HIGH ? LOW : HIGH);

  camera_config_t c = {};
  c.ledc_channel = LEDC_CHANNEL_0; c.ledc_timer = LEDC_TIMER_0;
  c.pin_d0 = Y2_GPIO_NUM; c.pin_d1 = Y3_GPIO_NUM;
  c.pin_d2 = Y4_GPIO_NUM; c.pin_d3 = Y5_GPIO_NUM;
  c.pin_d4 = Y6_GPIO_NUM; c.pin_d5 = Y7_GPIO_NUM;
  c.pin_d6 = Y8_GPIO_NUM; c.pin_d7 = Y9_GPIO_NUM;
  c.pin_xclk = XCLK_GPIO_NUM; c.pin_pclk = PCLK_GPIO_NUM;
  c.pin_vsync = VSYNC_GPIO_NUM; c.pin_href = HREF_GPIO_NUM;
  c.pin_sccb_sda = SIOD_GPIO_NUM; c.pin_sccb_scl = SIOC_GPIO_NUM;
  c.pin_pwdn = PWDN_GPIO_NUM; c.pin_reset = RESET_GPIO_NUM;
  c.xclk_freq_hz = 20000000;
  c.pixel_format = PIXFORMAT_JPEG;
  c.frame_size = FRAMESIZE_VGA; // 640 x 480 for better eye landmarks
  c.jpeg_quality = 12;
  c.fb_count = 1;
  c.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  c.grab_mode = CAMERA_GRAB_WHEN_EMPTY;

  esp_err_t err = esp_camera_init(&c);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", (unsigned)err);
    // Allow serial inspection, do not start HTTP with broken camera.
    return;
  }

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500); Serial.print(".");
  }
  Serial.print("\nESP32-CAM IP: "); Serial.println(WiFi.localIP());
  server.on("/", HTTP_GET, []() { server.send(200, "text/plain", "DMS: /capture /alert /safe /status /stop"); });
  server.on("/capture", HTTP_GET, handleCapture);
  server.on("/alert", HTTP_GET, []() { handleAlarm(true); });
  server.on("/safe", HTTP_GET, []() { handleAlarm(false); });
  server.on("/status", HTTP_GET, []() { server.send(200, "text/plain", alarmOn ? "ALERT" : "SAFE"); });
  // Explicitly stops monitoring and the watchdog.
  server.on("/stop", HTTP_GET, []() { monitoringStarted = false; setAlarm(false); server.send(200, "text/plain", "STOPPED"); });
  server.begin();
  Serial.println("HTTP server ready");
}

void loop() {
  server.handleClient();
  if (monitoringStarted && (uint32_t)(millis() - lastHeartbeat) > WATCHDOG_MS) {
    setAlarm(true);
  }
  delay(1);
}
