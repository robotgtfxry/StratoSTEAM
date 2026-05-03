/**
 * StratoSTEAM — ESP32-S3 fallback node
 *
 * Zawsze włączony. Kontroluje zasilanie RPi przez MOSFET.
 * Gdy RPi działa  → ESP32 milczy na LoRa (RPi nadaje sama).
 * Gdy RPi wyłączona → ESP32 nadaje GPS + napięcie co BEACON_INTERVAL ms.
 *
 * Sygnały:
 *   RPI_PWR_PIN    HIGH = RPi zasilona (MOSFET gate driver)
 *   RPI_ALIVE_PIN  INPUT, HIGH = RPi żyje (z RPi GPIO26)
 *   RPI_SHTDN_PIN  OUTPUT, HIGH = prośba o shutdown do RPi (RPi GPIO6)
 */

#include <Arduino.h>
#include <HardwareSerial.h>
#include <TinyGPSPlus.h>
#include <SPI.h>
#include <LoRa.h>
#include <ArduinoJson.h>

// ── Piny ──────────────────────────────────────────────────────────────────────
#define GPS_RX_PIN     4    // UART1 RX ← GPS TX (GPS TX jest też podłączone do RPi)
#define LORA_SCK_PIN   12
#define LORA_MOSI_PIN  11
#define LORA_MISO_PIN  13
#define LORA_CS_PIN    10
#define LORA_DIO0_PIN  9
#define LORA_RST_PIN   8
#define RPI_PWR_PIN    5    // OUTPUT HIGH → NPN → P-MOSFET ON → RPi zasilona
#define RPI_ALIVE_PIN  6    // INPUT, HIGH = RPi działa (z RPi GPIO26)
#define RPI_SHTDN_PIN  7    // OUTPUT HIGH = prośba o shutdown (do RPi GPIO6)
#define BATT_ADC_PIN   1    // ADC1_CH0, przez dzielnik 100k+100k

// ── Konfiguracja ──────────────────────────────────────────────────────────────
#define LORA_FREQ        433E6
#define LORA_SF          10
#define LORA_BW          125E3
#define LORA_TX_POWER    17
#define BEACON_INTERVAL  10000   // ms — co ile nadajemy gdy RPi off
#define BATT_DIV_RATIO   2.0f    // 100k + 100k → ×2
#define BATT_VREF        3.3f
#define SHUTDOWN_WAIT_MS 20000   // ms czekamy na RPi po sygnale shutdown

// ── Obiekty globalne ──────────────────────────────────────────────────────────
HardwareSerial gpsSerial(1);
TinyGPSPlus    gps;

bool     rpiPowered   = false;
bool     shutdownReq  = false;
uint32_t lastBeacon   = 0;
uint32_t beaconSeq    = 0;
uint32_t shutdownAt   = 0;
uint32_t aliveDropAt  = 0;   // kiedy sygnał alive spadł
bool     aliveDropped = false;

// Po wykryciu braku alive czekamy tyle ms zanim zaczniemy nadawać —
// daje RPi czas na zakończenie trwającego pakietu LoRa (max ~2s przy SF10)
#define LORA_TAKEOVER_DELAY_MS 4000

// ── Odczyt baterii ────────────────────────────────────────────────────────────
float readBattery() {
    int raw = analogRead(BATT_ADC_PIN);
    return (raw / 4095.0f) * BATT_VREF * BATT_DIV_RATIO;
}

// ── Inicjalizacja LoRa ────────────────────────────────────────────────────────
bool initLoRa() {
    SPI.begin(LORA_SCK_PIN, LORA_MISO_PIN, LORA_MOSI_PIN, LORA_CS_PIN);
    LoRa.setPins(LORA_CS_PIN, LORA_RST_PIN, LORA_DIO0_PIN);
    if (!LoRa.begin(LORA_FREQ)) return false;
    LoRa.setSpreadingFactor(LORA_SF);
    LoRa.setSignalBandwidth(LORA_BW);
    LoRa.setTxPower(LORA_TX_POWER);
    return true;
}

// ── Odbierz komendę po beaconie (2s okno RX) ─────────────────────────────────
void listenForCommand() {
    LoRa.receive();
    uint32_t deadline = millis() + 2000;
    while (millis() < deadline) {
        int pktSize = LoRa.parsePacket();
        if (pktSize > 0) {
            String raw = "";
            while (LoRa.available()) raw += (char)LoRa.read();
            Serial.printf("[ESP32] RX cmd: %s\n", raw.c_str());

            // Parse {"cmd":"rpi_power","on":true/false}
            JsonDocument doc;
            if (deserializeJson(doc, raw) == DeserializationError::Ok) {
                if (strcmp(doc["cmd"] | "", "rpi_power") == 0) {
                    bool on = doc["on"] | false;
                    if (on && !rpiPowered) {
                        aliveDropped = false;
                        rpiPowerOn();
                    } else if (!on && rpiPowered) {
                        rpiRequestShutdown();
                    }
                }
            }
            break;
        }
        delay(10);
    }
    LoRa.idle();
}

// ── Nadaj beacon (gdy RPi off) ────────────────────────────────────────────────
void sendBeacon() {
    JsonDocument doc;
    doc["src"]  = "esp32";
    doc["seq"]  = beaconSeq++;
    doc["fix"]  = gps.location.isValid();
    doc["lat"]  = gps.location.isValid()  ? gps.location.lat()       : 0.0;
    doc["lon"]  = gps.location.isValid()  ? gps.location.lng()       : 0.0;
    doc["alt"]  = gps.altitude.isValid()  ? gps.altitude.meters()    : 0.0;
    doc["sat"]  = gps.satellites.isValid()? (int)gps.satellites.value() : 0;
    doc["vbat"] = readBattery();

    char buf[160];
    serializeJson(doc, buf);

    LoRa.beginPacket();
    LoRa.print(buf);
    LoRa.endPacket();
    Serial.printf("[ESP32] beacon seq=%lu lat=%.5f lon=%.5f vbat=%.2fV\n",
                  beaconSeq - 1,
                  doc["lat"].as<float>(),
                  doc["lon"].as<float>(),
                  doc["vbat"].as<float>());
}

// ── Zasilanie RPi ─────────────────────────────────────────────────────────────
void rpiPowerOn() {
    digitalWrite(RPI_SHTDN_PIN, LOW);
    digitalWrite(RPI_PWR_PIN, HIGH);
    rpiPowered   = true;
    shutdownReq  = false;
    Serial.println("[ESP32] RPi power ON");
}

void rpiRequestShutdown() {
    if (shutdownReq) return;
    Serial.println("[ESP32] Requesting RPi shutdown...");
    digitalWrite(RPI_SHTDN_PIN, HIGH);   // sygnał do RPi: zamknij się
    shutdownReq = true;
    shutdownAt  = millis();
}

void rpiCutPower() {
    digitalWrite(RPI_SHTDN_PIN, LOW);
    digitalWrite(RPI_PWR_PIN, LOW);
    rpiPowered  = false;
    shutdownReq = false;
    Serial.println("[ESP32] RPi power OFF");
}

// ── Setup ─────────────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(500);

    gpsSerial.begin(9600, SERIAL_8N1, GPS_RX_PIN, -1);

    pinMode(RPI_PWR_PIN,   OUTPUT);
    pinMode(RPI_SHTDN_PIN, OUTPUT);
    pinMode(RPI_ALIVE_PIN, INPUT);
    analogReadResolution(12);

    digitalWrite(RPI_PWR_PIN,   LOW);
    digitalWrite(RPI_SHTDN_PIN, LOW);

    if (!initLoRa()) {
        Serial.println("[ESP32] LoRa FAILED — check wiring");
        // nie blokujemy — GPS i power control działają bez LoRa
    } else {
        Serial.println("[ESP32] LoRa OK");
    }

    // Włącz RPi od razu przy starcie
    rpiPowerOn();
}

// ── Loop ──────────────────────────────────────────────────────────────────────
void loop() {
    // Zawsze parsuj GPS
    while (gpsSerial.available()) {
        gps.encode(gpsSerial.read());
    }

    bool rpiAlive = (digitalRead(RPI_ALIVE_PIN) == HIGH);
    uint32_t now  = millis();

    // ── Obsługa sekwencji shutdown ────────────────────────────────────────────
    if (shutdownReq) {
        if (rpiAlive) {
            // RPi jeszcze żyje — czekaj
            if (now - shutdownAt > SHUTDOWN_WAIT_MS) {
                Serial.println("[ESP32] Shutdown timeout — cutting power");
                rpiCutPower();
            }
        } else {
            // RPi opuściła sygnał alive — bezpiecznie odetnij zasilanie
            delay(2000);   // chwila na flush SD/log
            rpiCutPower();
        }
        return;
    }

    // ── Wykryj spadek sygnału alive ──────────────────────────────────────────
    if (rpiPowered && !rpiAlive && !aliveDropped) {
        Serial.println("[ESP32] RPi alive signal lost — waiting before LoRa takeover");
        aliveDropped = true;
        aliveDropAt  = now;
        digitalWrite(RPI_PWR_PIN, LOW);
        rpiPowered   = false;
    }

    // Jeśli alive wrócił zanim minął debounce (np. krótki glitch) — anuluj
    if (aliveDropped && rpiAlive) {
        Serial.println("[ESP32] RPi alive restored — cancelling takeover");
        aliveDropped = false;
        rpiPowered   = true;
        digitalWrite(RPI_PWR_PIN, HIGH);
    }

    // ── Przejmij LoRa dopiero po LORA_TAKEOVER_DELAY_MS od spadku alive ──────
    bool loraFree = !rpiPowered && aliveDropped
                    && (now - aliveDropAt >= LORA_TAKEOVER_DELAY_MS);

    if (loraFree) {
        if (now - lastBeacon >= BEACON_INTERVAL) {
            sendBeacon();
            listenForCommand();   // 2s RX window after each beacon
            lastBeacon = now;
        }
    }
}
