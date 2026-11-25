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
#include <esp_task_wdt.h>

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
#define RPI_AUTO_RESTART_MS    1800000UL
#define RPI_ALIVE_LOST_MS      60000UL  // ALIVE musi zniknąć na tyle, zanim odetniemy zasilanie
                                        // (restart usługi rpi-air trwa > 5 s)
#define RPI_HALT_DELAY_MS      10000UL  // czas na domknięcie systemu po opadnięciu ALIVE
#define LORA_MAX_PAYLOAD       255      // limit SX1278
#define RPI_DATA_TIMEOUT_MS    15000    // dane starsze niż 15s = RPi5 nieosiągalna
#define GPS_FIX_MAX_AGE_MS     10000    // starsza pozycja = brak fixa
#define LORA_TX_TIMEOUT_MS     4000     // 255 B przy SF10 nadaje się ~2.3 s
#define WDT_TIMEOUT_MS         20000    // zawieszona pętla → restart S3
#define LORA_RETRY_MS          30000    // co ile ponawiać init LoRa, gdy modułu brak
#define STATUS_INTERVAL_MS     5000     // status ESP → RPi przez UART
#define NOLORA_BLINK_MS        2000     // okres mrugania LED gdy brak LoRa
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
    float dsku = 0.0f;        // disk used GB
    float dskf = 0.0f;        // disk free GB
    float hfdb = -999.0f;     // SDR pomiar dBFS (-999 = brak pomiaru)
    // ESP32-CAM: [ok, rec, klatki, wolne MB] — pole "ec" z telemetrii RPi
    bool  ecValid = false;
    int   ecOk = 0, ecRec = 0;
    long  ecFrames = 0, ecFreeMb = 0;
    bool  fresh = false;
} rpi;

uint32_t rpiLastRx   = 0;
uint32_t rpiRxLines  = 0;
uint32_t rpiRxBytes  = 0;     // surowe bajty z UART RPi
uint32_t rpiRxBad    = 0;     // linie, których nie dało się sparsować     // licznik poprawnych linii z RPi (diagnostyka UART)

// Stan LoRa — gdy moduł nie odpowiada, ESP działa dalej bez radia
bool     loraOk        = false;
uint32_t loraRestarts  = 0;     // ile razy moduł trzeba było podnieść
uint32_t lastLoraRetry = 0;
uint32_t lastStatus    = 0;
bool     ledOverride   = false; // LED ustawiony komendą z ziemi
String   rpiLineBuf  = "";   // UART2
String   usbLineBuf  = "";   // USB (Serial)

// Kolejka chunków obrazu — max 1 oczekujący (RPi wysyła co 3s, więc 1 wystarczy)
String   pendingImgLine  = "";
bool     imgChunkReady   = false;
uint32_t lastImgChunk    = 0;

bool     rpiPowered      = false;
bool     shutdownReq     = false;
bool     aliveDropped    = false;
bool     aliveSeen       = false;  // ALIVE był HIGH od ostatniego włączenia RPi
uint32_t aliveLostAt     = 0;      // od kiedy ALIVE jest LOW (0 = jest HIGH)
uint32_t shutdownAt      = 0;
uint32_t aliveDropAt     = 0;
uint32_t shutdownConfirmAt = 0;
uint32_t lastBeacon      = 0;
uint32_t beaconSeq       = 0;

// ── Battery ADC ───────────────────────────────────────────────────────────────
// Pomiar przez ESP32 niezależnie od RPi5 (INA219). Kalibrowany odczyt eFuse
// (analogReadMilliVolts), tłumienie 11 dB (~0–3.1 V na pinie), średnia z 16 próbek.
// Wynik zaokrąglony do 0.01 V (krótszy pakiet LoRa).
#define BATT_SAMPLES 16
float readBattAdc() {
    uint32_t mv = 0;
    for (int i = 0; i < BATT_SAMPLES; i++) mv += analogReadMilliVolts(BATT_ADC_PIN);
    float v = (mv / (float)BATT_SAMPLES) / 1000.0f * BATT_DIV_RATIO;
    return roundf(v * 100.0f) / 100.0f;
}

// ── Buzzer ────────────────────────────────────────────────────────────────────
// Arduino-ESP32 3.x: ledcAttach/ledcWrite/ledcWriteTone przyjmują NUMER PINU, nie kanał
uint32_t buzzOffAt = 0;   // millis() automatycznego wyłączenia buzzera (0 = brak)

void setBuzzer(bool on) {
    ledcWriteTone(BUZZER_PIN, on ? 2800 : 0);
    if (!on) buzzOffAt = 0;
}

// ── LED RGB ───────────────────────────────────────────────────────────────────
void setLed(int r, int g, int b) {
    ledcWrite(LED_R_PIN, r);
    ledcWrite(LED_G_PIN, g);
    ledcWrite(LED_B_PIN, b);
}

// ── Komenda buzzer/LED: {"cmd":1,"buzzer":true,"ms":3000,"led_r":0,...} ───────
// "ms" (opcjonalnie) — automatyczne wyłączenie buzzera po tylu milisekundach.
// Przychodzi przez LoRa (z ziemi) albo przez UART (z RPi5).
void applyBuzzerLed(JsonDocument& doc, const char* src) {
    bool     buz = doc["buzzer"] | false;
    uint32_t ms  = doc["ms"]     | 0;
    int      r   = doc["led_r"]  | 0;
    int      g   = doc["led_g"]  | 0;
    int      b   = doc["led_b"]  | 0;
    setBuzzer(buz);
    if (buz && ms > 0) buzzOffAt = (millis() + ms) | 1;
    setLed(r, g, b);
    ledOverride = (r || g || b || buz);
    Serial.printf("[ESP32] %s: buzzer=%d ms=%lu led=(%d,%d,%d)\n",
                  src, buz, (unsigned long)ms, r, g, b);
}

// ── Linia do RPi — na oba łącza; RPi czyta tylko jedno ───────────────────────
void sendToRpi(const String& line) {
    rpiSerial.println(line);
    Serial.println(line);
}

// ── Parser danych z RPi5 (line-delimited JSON) ────────────────────────────────
void parseRpiLine(const String& line) {
    if (line.length() < 5) return;
    JsonDocument doc;
    if (deserializeJson(doc, line) != DeserializationError::Ok) {
        rpiRxBad++;
        Serial.printf("[RPi5] zła linia (%u B): %.60s\n", line.length(), line.c_str());
        return;
    }

    // komenda buzzer/LED z RPi5 (np. test, sygnał po lądowaniu)
    if (doc["cmd"] == 1 || strcmp(doc["cmd"] | "", "1") == 0) {
        applyBuzzerLed(doc, "RPi");
        return;
    }

    // inna komenda (np. ping z testera) — to nie są dane czujników
    if (!doc["cmd"].isNull()) return;

    // chunk obrazu — odłóż do głównej pętli, nie blokuj tutaj
    if (strcmp(doc["type"] | "", "img") == 0) {
        pendingImgLine  = line;
        imgChunkReady   = true;
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
    rpi.dsku = doc["dsku"] | 0.0f;
    rpi.dskf = doc["dskf"] | 0.0f;
    rpi.hfdb = doc["hfdb"] | -999.0f;

    // Status ESP32-CAM: "ec":[ok, rec, klatki, wolne MB]
    JsonArrayConst ec = doc["ec"];
    if (!ec.isNull() && ec.size() >= 4) {
        rpi.ecOk     = ec[0] | 0;
        rpi.ecRec    = ec[1] | 0;
        rpi.ecFrames = ec[2] | 0L;
        rpi.ecFreeMb = ec[3] | 0L;
        rpi.ecValid  = true;
    }

    rpi.fresh = true;
    rpiLastRx = millis();
    rpiRxLines++;

    Serial.printf("[RPi5] temp=%.1f hum=%.1f pres=%.1f alt2=%.0f vbat=%.2f\n",
                  rpi.temp, rpi.hum, rpi.pres, rpi.alt2, rpi.vbat);
}

// ── Odczyt UART z RPi5 ────────────────────────────────────────────────────────
void readRpiPort(Stream& port, String& buf) {
    while (port.available()) {
        char c = (char)port.read();
        rpiRxBytes++;
        if (c == '\n') {
            const String line = buf;   // parser może trwać — bufor od razu wolny
            buf = "";
            parseRpiLine(line);
        } else if (buf.length() < 512) {
            buf += c;
        }
    }
}

// RPi może być podłączone przewodami (UART2) albo kablem USB (Serial) — słuchaj obu
void readRpiSerial() {
    readRpiPort(rpiSerial, rpiLineBuf);
    readRpiPort(Serial, usbLineBuf);
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
    LoRa.enableCrc();     // bez CRC przekłamany pakiet przechodzi jako poprawny
    LoRa.receive();
    return true;
}

// ── Nadawanie LoRa z limitem czasu ────────────────────────────────────────────
// LoRa.endPacket() bez "async" czeka na TxDone w nieskończoność — gdy moduł zgubi zasilanie
// w trakcie nadawania, cały S3 by się zawiesił. Tu czekamy najwyżej LORA_TX_TIMEOUT_MS
// i w tym czasie dalej odbieramy GPS i UART.
uint8_t loraReg(uint8_t addr) {
    SPI.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
    digitalWrite(LORA_CS_PIN, LOW);
    SPI.transfer(addr & 0x7F);
    uint8_t v = SPI.transfer(0);
    digitalWrite(LORA_CS_PIN, HIGH);
    SPI.endTransaction();
    return v;
}

// Po zaniku zasilania układ wraca do ustawień fabrycznych: FSK, 434 MHz
bool loraAlive() {
    const uint32_t frf  = ((uint32_t)loraReg(0x06) << 16) | ((uint32_t)loraReg(0x07) << 8) | loraReg(0x08);
    const uint32_t want = (uint32_t)(((uint64_t)LORA_FREQ << 19) / 32000000);
    return loraReg(0x42) == 0x12 && (loraReg(0x01) & 0x80) && frf == want;
}

void loraLost(const char* why) {
    Serial.printf("[ESP32] LoRa: %s — inicjalizuję od nowa\n", why);
    loraOk = initLoRa();
    loraRestarts++;
    lastLoraRetry = millis();
}

bool loraSend(const uint8_t* data, size_t len) {
    if (!loraAlive()) loraLost("moduł się zresetował");
    if (!loraOk || !LoRa.beginPacket()) return false;
    LoRa.write(data, len);
    LoRa.endPacket(true);
    const uint32_t t0 = millis();
    while (!(loraReg(0x12) & 0x08)) {                 // TxDone
        if (millis() - t0 > LORA_TX_TIMEOUT_MS) {
            loraLost("brak potwierdzenia nadania");
            return false;
        }
        while (gpsSerial.available()) gps.encode(gpsSerial.read());
        readRpiSerial();
        delay(2);
    }
    LoRa.beginPacket();                               // biblioteka kasuje flagę TxDone
    LoRa.receive();
    return true;
}

// ── GPS fix ───────────────────────────────────────────────────────────────────
// Samo isValid() po pierwszym fixie już nigdy nie wraca do false.
bool gpsFix() {
    return gps.location.isValid() && gps.location.age() < GPS_FIX_MAX_AGE_MS;
}

// ── Beacon TX ─────────────────────────────────────────────────────────────────
// Format kompaktowy — dekoduje go rpi-ground/beacon.py (zmieniaj oba razem!):
//   p [lat,lon,alt,sat,fix]  e [temp,hum,pres,p2,alt2]  i [roll,pit,yaw,ax,ay,az]
//   b [vbat,imA]  d [dsku,dskf]  h hfdb  c [ok,rec,klatki,MB]
//   x 1 = część pól pominięta, żeby zmieścić się w LORA_MAX_PAYLOAD
static double rnd(double v, double scale) { return round(v * scale) / scale; }

void sendBeacon() {
    JsonDocument doc;
    const float vbe = readBattAdc();   // napięcie baterii mierzone przez ESP32 (zawsze)
    const bool  fix = gpsFix();

    doc["src"] = "esp32";
    doc["seq"] = beaconSeq++;
    JsonArray p = doc["p"].to<JsonArray>();
    p.add(fix ? rnd(gps.location.lat(), 1e6) : 0.0);
    p.add(fix ? rnd(gps.location.lng(), 1e6) : 0.0);
    p.add(gps.altitude.isValid()   ? (long)lround(gps.altitude.meters()) : 0L);
    p.add(gps.satellites.isValid() ? (int)gps.satellites.value()         : 0);
    p.add(fix ? 1 : 0);
    doc["vbe"] = rnd(vbe, 100);

    if (rpi.fresh) {
        // pełna telemetria z RPi5
        JsonArray b = doc["b"].to<JsonArray>();
        b.add(rnd(rpi.vbat, 100));  b.add((long)lround(rpi.imA));
        JsonArray e = doc["e"].to<JsonArray>();
        e.add(rnd(rpi.temp, 10));   e.add(rnd(rpi.hum, 10));
        e.add(rnd(rpi.pres, 100));  e.add(rnd(rpi.p2, 100));
        e.add((long)lround(rpi.alt2));
        JsonArray im = doc["i"].to<JsonArray>();
        im.add(rnd(rpi.roll, 10));  im.add(rnd(rpi.pit, 10));  im.add(rnd(rpi.yaw, 10));
        im.add(rnd(rpi.ax, 100));   im.add(rnd(rpi.ay, 100));  im.add(rnd(rpi.az, 100));
        JsonArray d = doc["d"].to<JsonArray>();
        d.add(rnd(rpi.dsku, 10));   d.add(rnd(rpi.dskf, 10));
        if (rpi.hfdb > -999.0f) doc["h"] = rnd(rpi.hfdb, 10);
        if (rpi.ecValid) {
            JsonArray c = doc["c"].to<JsonArray>();
            c.add(rpi.ecOk);  c.add(rpi.ecRec);  c.add(rpi.ecFrames);  c.add(rpi.ecFreeMb);
        }
    }

    // Pakiet nie może przekroczyć 255 B — ucięty JSON jest bezużyteczny.
    // Odrzucaj najmniej ważne grupy; pozycja i zasilanie zostają zawsze.
    for (const char* key : {"d", "i", "c", "h"}) {
        if (measureJson(doc) <= LORA_MAX_PAYLOAD) break;
        if (doc[key].isNull()) continue;
        doc.remove(key);
        doc["x"] = 1;
    }

    char buf[LORA_MAX_PAYLOAD + 1];
    const size_t len = serializeJson(doc, buf, sizeof(buf));

    if (loraOk) {
        loraSend((const uint8_t*)buf, len);
    }

    Serial.printf("%s seq=%lu len=%u rpi=%s rx=%lu rxb=%lu bad=%lu gps=%lu alive=%d lr=%lu vbe=%.2fV fix=%d lat=%.5f lon=%.5f alt=%ld\n",
                  loraOk ? "[LoRa]" : "[NO-LoRa] (nie nadano)",
                  (unsigned long)(beaconSeq - 1), (unsigned)len, rpi.fresh ? "OK" : "—",
                  (unsigned long)rpiRxLines, (unsigned long)rpiRxBytes, (unsigned long)rpiRxBad,
                  (unsigned long)gps.charsProcessed(), digitalRead(RPI_ALIVE_PIN),
                  (unsigned long)loraRestarts, vbe, fix,
                  p[0].as<double>(), p[1].as<double>(), p[2].as<long>());
}

// ── Obsługa odebranego pakietu ────────────────────────────────────────────────
void handleIncoming() {
    if (!loraOk) return;
    int pktSize = LoRa.parsePacket();
    if (pktSize == 0) return;

    String raw = "";
    while (LoRa.available()) raw += (char)LoRa.read();

    JsonDocument doc;
    if (deserializeJson(doc, raw) != DeserializationError::Ok) return;

    const char* cmd = doc["cmd"] | "";

    if (strcmp(cmd, "1") == 0 || doc["cmd"] == 1) {
        applyBuzzerLed(doc, "LoRa");
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
        sendToRpi("{\"cmd\":\"photo\"}");
        return;
    }

    if (strcmp(cmd, "cam_rec") == 0) {
        bool on = doc["on"] | false;
        Serial.printf("[ESP32] cam_rec on=%d → RPi\n", on);
        String fwd = String("{\"cmd\":\"cam_rec\",\"on\":") + (on ? "true" : "false") + "}";
        sendToRpi(fwd);
        return;
    }

    // Zasilanie ESP32-CAM — przekazywane do RPi (przy zasilaniu bezpośrednim z 5V RPi tylko je loguje)
    if (strcmp(cmd, "espcam_pwr") == 0) {
        bool on = doc["on"] | false;
        Serial.printf("[ESP32] espcam_pwr on=%d → RPi\n", on);
        String fwd = String("{\"cmd\":\"espcam_pwr\",\"on\":") + (on ? "true" : "false") + "}";
        sendToRpi(fwd);
        return;
    }
}

// ── Chunk obrazu → LoRa (lub odrzucenie gdy brak LoRa) ────────────────────────
void sendImgChunk() {
    const String chunk = pendingImgLine;   // w trakcie nadawania UART może podstawić następny
    imgChunkReady = false;
    JsonDocument dbg;
    deserializeJson(dbg, chunk);
    int id = dbg["id"] | 0, seq = dbg["seq"] | 0, tot = dbg["tot"] | 0;
    if (loraOk) {
        Serial.printf("[LoRa] img id=%d seq=%d/%d\n", id, seq, tot);
        loraSend((const uint8_t*)chunk.c_str(), chunk.length());
    } else {
        Serial.printf("[NO-LoRa] img id=%d seq=%d/%d odrzucony\n", id, seq, tot);
    }
    lastImgChunk  = millis();
}

// ── Status ESP → RPi (UART) ───────────────────────────────────────────────────
// {"type":"esp_status","lora":false,"rx":123,"fix":false,"sat":0,"vbe":7.41}
void sendStatusToRpi() {
    JsonDocument st;
    st["type"] = "esp_status";
    st["lora"] = loraOk;
    st["rx"]   = rpiRxLines;
    st["rxb"]  = rpiRxBytes;
    st["bad"]  = rpiRxBad;
    st["fix"]  = gpsFix();
    st["sat"]  = gps.satellites.isValid() ? (int)gps.satellites.value() : 0;
    st["vbe"]  = readBattAdc();
    char buf[160];
    serializeJson(st, buf);
    sendToRpi(buf);
}

// ── Sygnalizacja braku LoRa: krótkie czerwone mignięcie co 2 s ────────────────
void updateNoLoraLed(uint32_t now) {
    if (loraOk || ledOverride) return;
    setLed((now % NOLORA_BLINK_MS) < 150 ? 255 : 0, 0, 0);
}

// ── Ponawianie inicjalizacji LoRa ─────────────────────────────────────────────
void retryLoRa(uint32_t now) {
    if (loraOk || now - lastLoraRetry < LORA_RETRY_MS) return;
    lastLoraRetry = now;
    loraOk = initLoRa();
    if (loraOk) {
        Serial.println("[ESP32] LoRa OK (moduł wykryty po ponowieniu)");
        if (!ledOverride) setLed(0, 0, 0);
    } else {
        Serial.println("[ESP32] LoRa nadal niedostępna — praca bez radia");
    }
}

// ── RPi power control ─────────────────────────────────────────────────────────
void rpiPowerOn() {
    digitalWrite(RPI_SHTDN_PIN, LOW);
    digitalWrite(RPI_PWR_PIN,   HIGH);
    rpiPowered   = true;
    aliveSeen    = false;   // RPi dopiero startuje — brak ALIVE jest normalny
    aliveLostAt  = 0;
    shutdownConfirmAt = 0;
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
    // Najpierw zasilanie RPi — restart S3 ma je przerwać na jak najkrócej
    pinMode(RPI_PWR_PIN, OUTPUT);
    digitalWrite(RPI_PWR_PIN, HIGH);

    Serial.setRxBufferSize(2048);
    Serial.begin(115200);
    delay(500);

    // Nadawanie LoRa blokuje pętlę na ~2 s — domyślne 256 B by się przepełniło
    gpsSerial.setRxBufferSize(4096);
    rpiSerial.setRxBufferSize(2048);
    gpsSerial.begin(9600,    SERIAL_8N1, GPS_RX_PIN, -1);
    rpiSerial.begin(115200,  SERIAL_8N1, RPI_RX_PIN, RPI_TX_PIN);

    ledcAttach(BUZZER_PIN, PWM_FREQ, PWM_BITS);
    ledcAttach(LED_R_PIN,  PWM_FREQ, PWM_BITS);
    ledcAttach(LED_G_PIN,  PWM_FREQ, PWM_BITS);
    ledcAttach(LED_B_PIN,  PWM_FREQ, PWM_BITS);

    pinMode(RPI_SHTDN_PIN, OUTPUT);
    pinMode(RPI_ALIVE_PIN, INPUT_PULLDOWN);   // niepodłączona linia nie może udawać ALIVE
    analogReadResolution(12);
    analogSetPinAttenuation(BATT_ADC_PIN, ADC_11db);
    digitalWrite(RPI_SHTDN_PIN, LOW);

    loraOk = initLoRa();
    lastLoraRetry = millis();
    if (loraOk) {
        Serial.println("[ESP32] LoRa OK");
    } else {
        Serial.println("[ESP32] LoRa FAILED — praca BEZ radia (UART/GPS/RPi działają), ponawiam co 30 s");
    }

    rpiPowerOn();

    esp_task_wdt_config_t wdt = {};
    wdt.timeout_ms    = WDT_TIMEOUT_MS;
    wdt.trigger_panic = true;
    esp_task_wdt_reconfigure(&wdt);
    enableLoopWDT();
}

// ── Loop ──────────────────────────────────────────────────────────────────────
void loop() {
    while (gpsSerial.available()) gps.encode(gpsSerial.read());
    readRpiSerial();

    bool     rpiAlive = (digitalRead(RPI_ALIVE_PIN) == HIGH);
    uint32_t now      = millis();

    retryLoRa(now);
    if (buzzOffAt && (int32_t)(now - buzzOffAt) >= 0) setBuzzer(false);
    updateNoLoraLed(now);
    if (now - lastStatus >= STATUS_INTERVAL_MS) {
        lastStatus = now;
        sendStatusToRpi();
    }

    // ── Obsługa shutdown ──────────────────────────────────────────────────────
    if (shutdownReq) {
        handleIncoming();
        if (!rpiAlive) {
            if (shutdownConfirmAt == 0) shutdownConfirmAt = now;
            if (now - shutdownConfirmAt >= RPI_HALT_DELAY_MS) {
                shutdownConfirmAt = 0;
                rpiCutPower();
            }
        } else {
            shutdownConfirmAt = 0;
            if (now - shutdownAt > SHUTDOWN_WAIT_MS) {
                Serial.println("[ESP32] Shutdown timeout — cutting power");
                rpiCutPower();
            }
        }
        // nadal nadajemy beacon podczas shutdown
    }

    // ── Utrata sygnału alive ──────────────────────────────────────────────────
    // Dopóki ALIVE nie pojawił się po włączeniu, RPi startuje (albo usługa rpi-air
    // nie działa) — zasilania nie ruszamy. Potem odcinamy dopiero po
    // RPI_ALIVE_LOST_MS ciągłego braku sygnału.
    if (rpiPowered && rpiAlive) {
        aliveSeen   = true;
        aliveLostAt = 0;
    } else if (!shutdownReq && rpiPowered && aliveSeen) {
        if (aliveLostAt == 0) {
            aliveLostAt = now | 1;
            Serial.println("[ESP32] RPi alive lost — czekam");
        } else if ((int32_t)(now - aliveLostAt) >= (int32_t)RPI_ALIVE_LOST_MS) {
            rpiCutPower();
        }
    }

    // ── Auto-restart RPi po 30 min ────────────────────────────────────────────
    if (!rpiPowered && aliveDropped && (now - aliveDropAt >= RPI_AUTO_RESTART_MS)) {
        Serial.println("[ESP32] Auto-restart RPi after 30 min");
        rpiPowerOn();
    }

    // ── Beacon LoRa ───────────────────────────────────────────────────────────
    handleIncoming();
    // Beacon idzie zawsze — także gdy RPi nigdy nie wstała (GPS musi działać)
    if (now - lastBeacon >= BEACON_INTERVAL_MS) {
        // chunk obrazu ma pierwszeństwo jeśli jest gotowy i minął min. odstęp
        if (imgChunkReady && (now - lastImgChunk >= IMG_CHUNK_DELAY_MS)) {
            sendImgChunk();
            // nie aktualizuj lastBeacon — beacon wyśle się przy następnej iteracji
        } else {
            delay(random(0, 100));
            sendBeacon();
            lastBeacon = now;
        }
    } else if (imgChunkReady && (now - lastImgChunk >= IMG_CHUNK_DELAY_MS)) {
        // Chunk gotowy, a beacon jeszcze nie — wyślij chunk między beaconami
        sendImgChunk();
    }
}
