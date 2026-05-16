/**
 * StratoSTEAM — ESP32-S3 węzeł radiowy
 *
 * Rola: GPS + LoRa. RPi5 jest węzłem pomiarowym.
 *   RPi ON  → ESP32 odbiera dane czujników przez UART2 i nadaje przez LoRa
 *   RPi OFF → ESP32 nadaje beacon GPS-only co BEACON_INTERVAL ms
 *
 * Dane z RPi5 przychodzone przez UART2 (GPIO3 RX) jako line-delimited JSON.
 * Dane są uznawane za świeże przez RPI_DATA_TIMEOUT_MS od ostatniego odbioru.
 *
 * Piny:
 *   RPI_PWR_PIN    OUTPUT HIGH → NPN → P-MOSFET ON → RPi zasilona
 *   RPI_ALIVE_PIN  INPUT  HIGH = RPi działa (z RPi GPIO26)
 *   RPI_SHTDN_PIN  OUTPUT HIGH = prośba o shutdown (do RPi GPIO6)
 *   RPI_RX_PIN     INPUT  UART2 RX — dane czujników z RPi5 (GPIO14 TX)
 */

#include <Arduino.h>
#include <HardwareSerial.h>
#include <TinyGPSPlus.h>
#include <SPI.h>
#include <LoRa.h>
#include <ArduinoJson.h>

// ── Piny ──────────────────────────────────────────────────────────────────────
#define GPS_RX_PIN     4
#define RPI_RX_PIN     3    // UART2 RX — dane czujników z RPi5
#define LORA_SCK_PIN   12
#define LORA_MOSI_PIN  11
#define LORA_MISO_PIN  13
#define LORA_CS_PIN    10
#define LORA_DIO0_PIN  9
#define LORA_RST_PIN   8
#define RPI_PWR_PIN    5
#define RPI_ALIVE_PIN  6
#define RPI_SHTDN_PIN  7
#define RPI_TX_PIN     14   // UART2 TX → RPi GPIO15 (RX)
#define BATT_ADC_PIN   1
#define BUZZER_PIN     2
#define LED_R_PIN      17
#define LED_G_PIN      18
#define LED_B_PIN      20

// LEDC kanały PWM
#define CH_BUZZ  0
#define CH_R     1
#define CH_G     2
#define CH_B     3
#define PWM_FREQ   5000
#define PWM_BITS   8

// ── Konfiguracja ──────────────────────────────────────────────────────────────
#define LORA_FREQ              433E6
#define LORA_SF                10
#define LORA_BW                125E3
#define LORA_TX_POWER          17
#define BEACON_INTERVAL_MS     5000     // interwał beacona (=ESP_SEND_INTERVAL_S RPi5)
#define IMG_CHUNK_DELAY_MS     2200     // min. odstęp między nadaniem kolejnych chunków obrazu
#define SHUTDOWN_WAIT_MS       20000
#define LORA_TAKEOVER_DELAY_MS 4000
#define RPI_AUTO_RESTART_MS    1800000UL
#define RPI_DATA_TIMEOUT_MS    15000    // dane starsze niż 15s = RPi5 nieosiągalna
#define BATT_DIV_RATIO         2.0f
#define BATT_VREF              3.3f

// ── Forward declarations ──────────────────────────────────────────────────────
void rpiPowerOn();
void rpiRequestShutdown();
void rpiCutPower();

// ── Globals ───────────────────────────────────────────────────────────────────
HardwareSerial gpsSerial(1);
HardwareSerial rpiSerial(2);
TinyGPSPlus    gps;

// Ostatnie dane z RPi5
struct RpiData {
    float temp, hum, pres;   // BME280
    float p2, alt2;           // MS5611
    float roll, pit, yaw;     // BNO085
    float ax, ay, az;
    float vbat, imA;          // INA219
    bool  fresh = false;
} rpi;

uint32_t rpiLastRx   = 0;
String   rpiLineBuf  = "";
uint32_t lastImgChunk = 0;   // timestamp ostatnio wysłanego chunk obrazu

bool     rpiPowered      = false;
bool     shutdownReq     = false;
bool     aliveDropped    = false;
bool     firstBoot       = true;
uint32_t shutdownAt      = 0;
uint32_t aliveDropAt     = 0;
uint32_t shutdownConfirmAt = 0;
uint32_t lastBeacon      = 0;
uint32_t beaconSeq       = 0;

// ── Battery ADC ───────────────────────────────────────────────────────────────
float readBattAdc() {
    return (analogRead(BATT_ADC_PIN) / 4095.0f) * BATT_VREF * BATT_DIV_RATIO;
}

// ── Buzzer ────────────────────────────────────────────────────────────────────
void setBuzzer(bool on) {
    ledcWriteTone(CH_BUZZ, on ? 2800 : 0);
}

// ── LED RGB ───────────────────────────────────────────────────────────────────
void setLed(int r, int g, int b) {
    ledcWrite(CH_R, r);
    ledcWrite(CH_G, g);
    ledcWrite(CH_B, b);
}

// ── Retransmisja chunk obrazu przez LoRa ──────────────────────────────────────
void forwardImgChunk(const String& line) {
    uint32_t now = millis();
    // wymuszamy minimalny odstęp między chunkami
    if (now - lastImgChunk < IMG_CHUNK_DELAY_MS) {
        delay(IMG_CHUNK_DELAY_MS - (now - lastImgChunk));
    }
    LoRa.beginPacket();
    LoRa.print(line);
    LoRa.endPacket();
    LoRa.receive();
    lastImgChunk = millis();

    JsonDocument dbg;
    deserializeJson(dbg, line);
    Serial.printf("[LoRa] img id=%d seq=%d/%d\n",
                  (int)(dbg["id"] | 0), (int)(dbg["seq"] | 0), (int)(dbg["tot"] | 0));
}

// ── Parser danych z RPi5 (line-delimited JSON) ────────────────────────────────
void parseRpiLine(const String& line) {
    if (line.length() < 5) return;
    JsonDocument doc;
    if (deserializeJson(doc, line) != DeserializationError::Ok) return;

    // chunk obrazu — retransmituj przez LoRa bez parsowania
    if (strcmp(doc["type"] | "", "img") == 0) {
        forwardImgChunk(line);
        return;
    }

    rpi.temp = doc["temp"] | 0.0f;
    rpi.hum  = doc["hum"]  | 0.0f;
    rpi.pres = doc["pres"] | 0.0f;
    rpi.p2   = doc["p2"]   | 0.0f;
    rpi.alt2 = doc["alt2"] | 0.0f;
    rpi.roll = doc["roll"] | 0.0f;
    rpi.pit  = doc["pit"]  | 0.0f;
    rpi.yaw  = doc["yaw"]  | 0.0f;
    rpi.ax   = doc["ax"]   | 0.0f;
    rpi.ay   = doc["ay"]   | 0.0f;
    rpi.az   = doc["az"]   | 0.0f;
    rpi.vbat = doc["vbat"] | 0.0f;
    rpi.imA  = doc["imA"]  | 0.0f;
    rpi.fresh = true;
    rpiLastRx = millis();

    Serial.printf("[RPi5] temp=%.1f hum=%.1f pres=%.1f alt2=%.0f vbat=%.2f\n",
                  rpi.temp, rpi.hum, rpi.pres, rpi.alt2, rpi.vbat);
}

// ── Odczyt UART z RPi5 ────────────────────────────────────────────────────────
void readRpiSerial() {
    while (rpiSerial.available()) {
        char c = (char)rpiSerial.read();
        if (c == '\n') {
            parseRpiLine(rpiLineBuf);
            rpiLineBuf = "";
        } else if (rpiLineBuf.length() < 400) {
            rpiLineBuf += c;
        }
    }
    // oznacz dane jako nieświeże po przekroczeniu timeoutu
    if (rpi.fresh && (millis() - rpiLastRx > RPI_DATA_TIMEOUT_MS)) {
        rpi.fresh = false;
    }
}

// ── LoRa init ─────────────────────────────────────────────────────────────────
bool initLoRa() {
    SPI.begin(LORA_SCK_PIN, LORA_MISO_PIN, LORA_MOSI_PIN, LORA_CS_PIN);
    LoRa.setPins(LORA_CS_PIN, LORA_RST_PIN, LORA_DIO0_PIN);
    if (!LoRa.begin(LORA_FREQ)) return false;
    LoRa.setSpreadingFactor(LORA_SF);
    LoRa.setSignalBandwidth(LORA_BW);
    LoRa.setTxPower(LORA_TX_POWER);
    LoRa.receive();
    return true;
}

// ── Beacon TX ─────────────────────────────────────────────────────────────────
void sendBeacon() {
    JsonDocument doc;
    doc["src"] = "esp32";
    doc["seq"] = beaconSeq++;
    doc["fix"] = gps.location.isValid();
    doc["lat"] = gps.location.isValid()   ? gps.location.lat()         : 0.0;
    doc["lon"] = gps.location.isValid()   ? gps.location.lng()         : 0.0;
    doc["alt"] = gps.altitude.isValid()   ? gps.altitude.meters()      : 0.0;
    doc["sat"] = gps.satellites.isValid() ? (int)gps.satellites.value(): 0;

    if (rpi.fresh) {
        // pełna telemetria z RPi5
        doc["vbat"] = rpi.vbat;
        doc["imA"]  = rpi.imA;
        doc["temp"] = rpi.temp;
        doc["hum"]  = rpi.hum;
        doc["pres"] = rpi.pres;
        doc["p2"]   = rpi.p2;
        doc["alt2"] = rpi.alt2;
        doc["roll"] = rpi.roll;
        doc["pit"]  = rpi.pit;
        doc["yaw"]  = rpi.yaw;
        doc["ax"]   = rpi.ax;
        doc["ay"]   = rpi.ay;
        doc["az"]   = rpi.az;
    } else {
        // RPi5 nieosiągalna — tylko napięcie z ADC
        doc["vbat"] = readBattAdc();
    }

    char buf[300];
    serializeJson(doc, buf);

    LoRa.beginPacket();
    LoRa.print(buf);
    LoRa.endPacket();
    LoRa.receive();

    Serial.printf("[LoRa] seq=%lu rpi=%s fix=%d lat=%.5f lon=%.5f alt=%.0f\n",
                  beaconSeq - 1, rpi.fresh ? "OK" : "—",
                  gps.location.isValid(),
                  doc["lat"].as<float>(), doc["lon"].as<float>(),
                  doc["alt"].as<float>());
}

// ── Obsługa odebranego pakietu ────────────────────────────────────────────────
void handleIncoming() {
    int pktSize = LoRa.parsePacket();
    if (pktSize == 0) return;

    String raw = "";
    while (LoRa.available()) raw += (char)LoRa.read();

    JsonDocument doc;
    if (deserializeJson(doc, raw) != DeserializationError::Ok) return;

    const char* cmd = doc["cmd"] | "";

    if (strcmp(cmd, "1") == 0 || doc["cmd"] == 1) {
        bool buz = doc["buzzer"] | false;
        int  r   = doc["led_r"] | 0;
        int  g   = doc["led_g"] | 0;
        int  b   = doc["led_b"] | 0;
        setBuzzer(buz);
        setLed(r, g, b);
        Serial.printf("[ESP32] buzzer=%d led=(%d,%d,%d)\n", buz, r, g, b);
        return;
    }

    if (strcmp(cmd, "rpi_power") == 0) {
        bool on = doc["on"] | false;
        Serial.printf("[ESP32] rpi_power on=%d\n", on);
        if (on  && !rpiPowered) { aliveDropped = false; rpiPowerOn(); }
        if (!on &&  rpiPowered) { rpiRequestShutdown(); }
        return;
    }

    // ── Komendy kamery — forward do RPi przez UART2 TX ────────────────────────
    if (strcmp(cmd, "photo") == 0) {
        Serial.println("[ESP32] photo cmd → RPi");
        rpiSerial.println("{\"cmd\":\"photo\"}");
        return;
    }

    if (strcmp(cmd, "cam_rec") == 0) {
        bool on = doc["on"] | false;
        Serial.printf("[ESP32] cam_rec on=%d → RPi\n", on);
        String fwd = String("{\"cmd\":\"cam_rec\",\"on\":") + (on ? "true" : "false") + "}";
        rpiSerial.println(fwd);
        return;
    }
}

// ── RPi power control ─────────────────────────────────────────────────────────
void rpiPowerOn() {
    digitalWrite(RPI_SHTDN_PIN, LOW);
    digitalWrite(RPI_PWR_PIN,   HIGH);
    rpiPowered   = true;
    shutdownReq  = false;
    aliveDropped = false;
    Serial.println("[ESP32] RPi power ON");
}

void rpiRequestShutdown() {
    if (shutdownReq) return;
    digitalWrite(RPI_SHTDN_PIN, HIGH);
    shutdownReq = true;
    shutdownAt  = millis();
    Serial.println("[ESP32] Shutdown requested → RPi GPIO6 HIGH");
}

void rpiCutPower() {
    digitalWrite(RPI_SHTDN_PIN, LOW);
    digitalWrite(RPI_PWR_PIN,   LOW);
    rpiPowered   = false;
    shutdownReq  = false;
    aliveDropped = true;
    aliveDropAt  = millis();
    Serial.println("[ESP32] RPi power OFF");
}

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(500);

    gpsSerial.begin(9600,    SERIAL_8N1, GPS_RX_PIN, -1);
    rpiSerial.begin(115200,  SERIAL_8N1, RPI_RX_PIN, RPI_TX_PIN);

    ledcAttach(BUZZER_PIN, PWM_FREQ, PWM_BITS);
    ledcAttach(LED_R_PIN,  PWM_FREQ, PWM_BITS);
    ledcAttach(LED_G_PIN,  PWM_FREQ, PWM_BITS);
    ledcAttach(LED_B_PIN,  PWM_FREQ, PWM_BITS);

    pinMode(RPI_PWR_PIN,   OUTPUT);
    pinMode(RPI_SHTDN_PIN, OUTPUT);
    pinMode(RPI_ALIVE_PIN, INPUT);
    analogReadResolution(12);
    digitalWrite(RPI_PWR_PIN,   LOW);
    digitalWrite(RPI_SHTDN_PIN, LOW);

    if (initLoRa()) {
        Serial.println("[ESP32] LoRa OK");
    } else {
        Serial.println("[ESP32] LoRa FAILED");
    }

    rpiPowerOn();
}

// ── Loop ──────────────────────────────────────────────────────────────────────
void loop() {
    while (gpsSerial.available()) gps.encode(gpsSerial.read());
    readRpiSerial();

    bool     rpiAlive = (digitalRead(RPI_ALIVE_PIN) == HIGH);
    uint32_t now      = millis();

    if (firstBoot && rpiAlive) firstBoot = false;

    // ── Obsługa shutdown ──────────────────────────────────────────────────────
    if (shutdownReq) {
        handleIncoming();
        if (!rpiAlive) {
            if (shutdownConfirmAt == 0) shutdownConfirmAt = now;
            if (now - shutdownConfirmAt >= 2000) {
                shutdownConfirmAt = 0;
                rpiCutPower();
            }
        } else if (now - shutdownAt > SHUTDOWN_WAIT_MS) {
            Serial.println("[ESP32] Shutdown timeout — cutting power");
            rpiCutPower();
        }
        // nadal nadajemy beacon podczas shutdown
    }

    // ── Wykryj utratę sygnału alive ───────────────────────────────────────────
    if (!shutdownReq && rpiPowered && !rpiAlive) {
        Serial.println("[ESP32] RPi alive lost");
        aliveDropped = true;
        aliveDropAt  = now;
        digitalWrite(RPI_PWR_PIN, LOW);
        rpiPowered = false;
    }

    // ── Glitch debounce ───────────────────────────────────────────────────────
    if (aliveDropped && rpiAlive && (now - aliveDropAt < LORA_TAKEOVER_DELAY_MS)) {
        Serial.println("[ESP32] RPi alive restored (glitch)");
        rpiPowerOn();
    }

    // ── Auto-restart RPi po 30 min ────────────────────────────────────────────
    if (!rpiPowered && aliveDropped && (now - aliveDropAt >= RPI_AUTO_RESTART_MS)) {
        Serial.println("[ESP32] Auto-restart RPi after 30 min");
        rpiPowerOn();
    }

    // ── Beacon LoRa (zawsze aktywny) ──────────────────────────────────────────
    handleIncoming();
    if (!firstBoot && (now - lastBeacon >= BEACON_INTERVAL_MS)) {
        delay(random(0, 100));
        sendBeacon();
        lastBeacon = now;
    }
}
