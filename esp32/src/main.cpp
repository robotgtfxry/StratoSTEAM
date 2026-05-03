/**
 * StratoSTEAM — ESP32-S3 fallback node
 *
 * Zasada: radio (LoRa) tylko gdy RPi jest WYŁĄCZONA.
 *   RPi ON  → ESP32 milczy, RPi robi wszystko przez swój moduł LoRa
 *   RPi OFF → ESP32 nadaje beacon GPS co BEACON_INTERVAL ms, brak RX
 *
 * Brak odbierania komend przez ESP32 — upraszcza logikę i eliminuje kolizje.
 * RPi wraca do życia automatycznie po RPI_AUTO_RESTART_MS od wyłączenia.
 *
 * Piny:
 *   RPI_PWR_PIN    OUTPUT HIGH → NPN → P-MOSFET ON → RPi zasilona
 *   RPI_ALIVE_PIN  INPUT  HIGH = RPi działa (z RPi GPIO26)
 *   RPI_SHTDN_PIN  OUTPUT HIGH = prośba o shutdown (do RPi GPIO6)
 */

#include <Arduino.h>
#include <HardwareSerial.h>
#include <TinyGPSPlus.h>
#include <SPI.h>
#include <Wire.h>
#include <LoRa.h>
#include <ArduinoJson.h>
#include <Adafruit_BME280.h>
#include <Adafruit_INA219.h>

// ── Piny ──────────────────────────────────────────────────────────────────────
#define GPS_RX_PIN     4
#define LORA_SCK_PIN   12
#define LORA_MOSI_PIN  11
#define LORA_MISO_PIN  13
#define LORA_CS_PIN    10
#define LORA_DIO0_PIN  9
#define LORA_RST_PIN   8
#define RPI_PWR_PIN    5
#define RPI_ALIVE_PIN  6
#define RPI_SHTDN_PIN  7
#define BATT_ADC_PIN   1
#define I2C_SDA_PIN    15
#define I2C_SCL_PIN    16
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
#define LORA_FREQ             433E6
#define LORA_SF               10
#define LORA_BW               125E3
#define LORA_TX_POWER         17
#define BEACON_INTERVAL_MS    10000   // co ile beacon gdy RPi off
#define SHUTDOWN_WAIT_MS      20000   // max czas na graceful shutdown RPi
#define LORA_TAKEOVER_DELAY_MS 4000   // debounce przed przejęciem LoRa
#define RPI_AUTO_RESTART_MS   1800000UL // 30 min — auto-restart RPi jeśli off
#define BATT_DIV_RATIO        2.0f
#define BATT_VREF             3.3f

// ── Globals ───────────────────────────────────────────────────────────────────
HardwareSerial  gpsSerial(1);
TinyGPSPlus     gps;
Adafruit_BME280 bme;
Adafruit_INA219 ina(0x40);
bool bmeOk = false;
bool inaOk = false;

bool     rpiPowered    = false;
bool     shutdownReq   = false;
bool     aliveDropped  = false;
uint32_t shutdownAt    = 0;
uint32_t aliveDropAt   = 0;
uint32_t lastBeacon    = 0;
uint32_t beaconSeq     = 0;

// ── Battery ADC ───────────────────────────────────────────────────────────────
float readBattAdc() {
    return (analogRead(BATT_ADC_PIN) / 4095.0f) * BATT_VREF * BATT_DIV_RATIO;
}

// ── Buzzer ────────────────────────────────────────────────────────────────────
void setBuzzer(bool on) {
    if (on) {
        ledcWriteTone(CH_BUZZ, 2800);
    } else {
        ledcWriteTone(CH_BUZZ, 0);
    }
}

// ── LED RGB ───────────────────────────────────────────────────────────────────
void setLed(int r, int g, int b) {
    ledcWrite(CH_R, r);
    ledcWrite(CH_G, g);
    ledcWrite(CH_B, b);
}

// ── LoRa init ─────────────────────────────────────────────────────────────────
bool initLoRa() {
    SPI.begin(LORA_SCK_PIN, LORA_MISO_PIN, LORA_MOSI_PIN, LORA_CS_PIN);
    LoRa.setPins(LORA_CS_PIN, LORA_RST_PIN, LORA_DIO0_PIN);
    if (!LoRa.begin(LORA_FREQ)) return false;
    LoRa.setSpreadingFactor(LORA_SF);
    LoRa.setSignalBandwidth(LORA_BW);
    LoRa.setTxPower(LORA_TX_POWER);
    LoRa.receive();   // RX_CONT od razu
    return true;
}

// ── Beacon TX, po wysłaniu wraca do RX_CONT ───────────────────────────────────
void sendBeacon() {
    JsonDocument doc;
    doc["src"]  = "esp32";
    doc["seq"]  = beaconSeq++;
    doc["fix"]  = gps.location.isValid();
    doc["lat"]  = gps.location.isValid()   ? gps.location.lat()         : 0.0;
    doc["lon"]  = gps.location.isValid()   ? gps.location.lng()         : 0.0;
    doc["alt"]  = gps.altitude.isValid()   ? gps.altitude.meters()      : 0.0;
    doc["sat"]  = gps.satellites.isValid() ? (int)gps.satellites.value(): 0;

    // INA219 — napięcie i prąd (priorytet nad ADC)
    if (inaOk) {
        doc["vbat"] = ina.getBusVoltage_V() + ina.getShuntVoltage_mV() / 1000.0f;
        doc["imA"]  = ina.getCurrent_mA();
    } else {
        doc["vbat"] = readBattAdc();
    }

    // BME280 — temperatura, ciśnienie, wilgotność
    if (bmeOk) {
        doc["temp"] = bme.readTemperature();
        doc["pres"] = bme.readPressure() / 100.0f;   // hPa
        doc["hum"]  = bme.readHumidity();
    }

    char buf[160];
    serializeJson(doc, buf);

    LoRa.beginPacket();
    LoRa.print(buf);
    LoRa.endPacket();
    LoRa.receive();   // z powrotem do RX_CONT

    Serial.printf("[ESP32] beacon seq=%lu fix=%d lat=%.5f lon=%.5f vbat=%.2fV temp=%.1fC\n",
                  beaconSeq - 1, gps.location.isValid(),
                  doc["lat"].as<float>(), doc["lon"].as<float>(),
                  doc["vbat"].as<float>(), doc["temp"].as<float>());
}

// ── Obsługa odebranego pakietu (zawsze aktywna) ───────────────────────────────
void handleIncoming() {
    int pktSize = LoRa.parsePacket();
    if (pktSize == 0) return;

    String raw = "";
    while (LoRa.available()) raw += (char)LoRa.read();

    JsonDocument doc;
    if (deserializeJson(doc, raw) != DeserializationError::Ok) return;

    const char* cmd = doc["cmd"] | "";

    // Buzzer + LED — zawsze obsługiwane przez ESP32
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

    // RPi power — tylko ESP32 może to zrobić
    if (strcmp(cmd, "rpi_power") == 0) {
        bool on = doc["on"] | false;
        Serial.printf("[ESP32] rpi_power on=%d\n", on);
        if (on  && !rpiPowered) { aliveDropped = false; rpiPowerOn(); }
        if (!on &&  rpiPowered) { rpiRequestShutdown(); }
        return;
    }
    // exec i inne — ignoruj, RPi je obsłuży swoim modułem
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

    gpsSerial.begin(9600, SERIAL_8N1, GPS_RX_PIN, -1);

    Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
    bmeOk = bme.begin(0x76, &Wire);
    inaOk = ina.begin(&Wire);
    Serial.printf("[ESP32] BME280=%s INA219=%s\n",
                  bmeOk ? "OK" : "FAIL", inaOk ? "OK" : "FAIL");

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
        Serial.println("[ESP32] LoRa OK (TX-only when RPi off)");
    } else {
        Serial.println("[ESP32] LoRa FAILED");
    }

    rpiPowerOn();
}

// ── Loop ──────────────────────────────────────────────────────────────────────
void loop() {
    while (gpsSerial.available()) gps.encode(gpsSerial.read());

    bool     rpiAlive = (digitalRead(RPI_ALIVE_PIN) == HIGH);
    uint32_t now      = millis();

    // ── 1. Obsługa shutdown ───────────────────────────────────────────────────
    if (shutdownReq) {
        if (!rpiAlive) {
            delay(2000);
            rpiCutPower();
        } else if (now - shutdownAt > SHUTDOWN_WAIT_MS) {
            Serial.println("[ESP32] Shutdown timeout — cutting power");
            rpiCutPower();
        }
        return;
    }

    // ── 2. Wykryj utratę sygnału alive ───────────────────────────────────────
    if (rpiPowered && !rpiAlive) {
        Serial.println("[ESP32] RPi alive lost");
        aliveDropped = true;
        aliveDropAt  = now;
        digitalWrite(RPI_PWR_PIN, LOW);
        rpiPowered = false;
    }

    // ── 3. Glitch — alive wrócił w ciągu debounce ─────────────────────────────
    if (aliveDropped && rpiAlive && (now - aliveDropAt < LORA_TAKEOVER_DELAY_MS)) {
        Serial.println("[ESP32] RPi alive restored (glitch)");
        rpiPowerOn();
        return;
    }

    // ── 4. RPi wyłączona — praca ESP32 ───────────────────────────────────────
    if (!rpiPowered && aliveDropped && (now - aliveDropAt >= LORA_TAKEOVER_DELAY_MS)) {

        // Zawsze nasłuchuj — handleIncoming() sprawdza czy coś przyszło
        handleIncoming();

        // Beacon GPS co BEACON_INTERVAL_MS
        if (now - lastBeacon >= BEACON_INTERVAL_MS) {
            sendBeacon();
            lastBeacon = now;
        }

        // Auto-restart RPi po RPI_AUTO_RESTART_MS
        if (now - aliveDropAt >= RPI_AUTO_RESTART_MS) {
            Serial.println("[ESP32] Auto-restart RPi after 30 min");
            rpiPowerOn();
        }
    }
}
