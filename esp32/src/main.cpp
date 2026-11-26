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
#include <mbedtls/base64.h>

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
#define IMG_MAX_BYTES          16384
#define IMG_DATA               240      // bajtów obrazu w pakiecie (+4 nagłówka)
#define IMG_ROUND_MS           14000    // najdłuższa seria bez beacona
#define IMG_GAP_MS             4500     // okno na komendy z ziemi między seriami
#define SHUTDOWN_WAIT_MS       20000
#define RPI_AUTO_RESTART_MS    1800000UL
#define RPI_ALIVE_LOST_MS      60000UL  // ALIVE musi zniknąć na tyle, zanim odetniemy zasilanie
                                        // (restart usługi rpi-air trwa > 5 s)
#define RPI_HALT_DELAY_MS      10000UL  // czas na domknięcie systemu po opadnięciu ALIVE
#define LORA_MAX_PAYLOAD       255      // limit SX1278
#define RPI_DATA_TIMEOUT_MS    15000    // dane starsze niż 15s = RPi5 nieosiągalna
#define GPS_FIX_MAX_AGE_MS     10000    // starsza pozycja = brak fixa
#define LORA_TX_TIMEOUT_MS     4000     // 255 B przy SF10 nadaje się ~2.3 s
#define WDT_TIMEOUT_MS         40000    // zawieszona pętla → restart S3
#define LORA_RETRY_MS          30000    // co ile ponawiać init LoRa, gdy modułu brak
#define STATUS_INTERVAL_MS     5000     // status ESP → RPi przez UART
#define GPS_TO_RPI_MS          1000     // pozycja GPS → RPi (dziennik lotu na karcie)
#define NOLORA_BLINK_MS        2000     // okres mrugania LED gdy brak LoRa
#define BATT_DIV_RATIO         2.0f
#define BATT_VREF              3.3f

// ── Forward declarations ──────────────────────────────────────────────────────
void rpiPowerOn();
void rpiRequestShutdown();
void rpiCutPower();
void sendToRpi(const String& line);

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
    float tcpu = -999.0f;     // temperatura procesora RPi (-999 = brak)
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
uint32_t lastGpsToRpi  = 0;
bool     ledOverride   = false; // LED ustawiony komendą z ziemi
String   rpiLineBuf  = "";   // UART2
String   usbLineBuf  = "";   // USB (Serial)

// Zdjęcie: całe w pamięci S3, nadawane seriami pakietów; braki dosyłane na prośbę ziemi
uint8_t* imgBuf      = nullptr;
uint16_t imgLen      = 0, imgGot = 0;
uint32_t imgCrc      = 0;
uint8_t  imgId       = 0, imgN = 0;
uint8_t  imgSf       = 10;             // SF serii — wybiera ziemia według jakości łącza
bool     imgReady    = false;
uint8_t  imgTodo[16] = {0};            // mapa bitowa pakietów do nadania
uint32_t imgNextRound = 0;

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

// ── Zdjęcie: odbiór z RPi ─────────────────────────────────────────────────────
uint32_t crc32(const uint8_t* d, size_t n) {      // zgodne z zlib.crc32
    uint32_t v = 0xFFFFFFFF;
    while (n--) {
        v ^= *d++;
        for (int k = 0; k < 8; k++) v = (v >> 1) ^ (0xEDB88320 & -(v & 1));
    }
    return ~v;
}

void imgFromRpi(const char* type, JsonDocument& doc) {
    if (!imgBuf) return;
    if (strcmp(type, "imgb") == 0) {
        imgReady = false;
        memset(imgTodo, 0, sizeof(imgTodo));
        imgId  = doc["id"]  | 0;
        imgLen = doc["len"] | 0;
        imgCrc = doc["crc"] | 0UL;
        imgGot = 0;
        if (imgLen > IMG_MAX_BYTES) imgLen = 0;
    } else if (strcmp(type, "imgd") == 0) {
        const uint32_t off = doc["o"] | 0UL;
        const char* b64 = doc["d"] | "";
        size_t out = 0;
        if ((doc["id"] | -1) != imgId || off >= imgLen) return;
        if (mbedtls_base64_decode(imgBuf + off, imgLen - off, &out,
                                  (const uint8_t*)b64, strlen(b64)) == 0) imgGot += out;
    } else if (strcmp(type, "imge") == 0) {
        const bool ok = imgLen && imgGot == imgLen && crc32(imgBuf, imgLen) == imgCrc;
        if (ok) {
            imgN = (imgLen + IMG_DATA - 1) / IMG_DATA;
            for (int i = 0; i < imgN; i++) imgTodo[i / 8] |= 1 << (i % 8);
            imgReady     = true;
            imgNextRound = 0;
        }
        Serial.printf("[ESP32] zdjęcie id=%d %u/%u B %s\n", imgId, imgGot, imgLen, ok ? "OK" : "BŁĄD");
        sendToRpi(String("{\"type\":\"imgst\",\"id\":") + imgId + ",\"ok\":" + (ok ? "true" : "false") + "}");
    }
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

    // zdjęcie z RPi: imgb (początek) → imgd (dane) → imge (koniec, kontrola CRC)
    const char* type = doc["type"] | "";
    if (strncmp(type, "img", 3) == 0) {
        imgFromRpi(type, doc);
        return;
    }
    if (type[0]) return;

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
    rpi.tcpu = doc["tcpu"] | -999.0f;
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
void loraListen();

bool initLoRa() {
    SPI.begin(LORA_SCK_PIN, LORA_MISO_PIN, LORA_MOSI_PIN, LORA_CS_PIN);
    LoRa.setPins(LORA_CS_PIN, LORA_RST_PIN, LORA_DIO0_PIN);
    if (!LoRa.begin(LORA_FREQ)) return false;
    LoRa.setSpreadingFactor(LORA_SF);
    LoRa.setSignalBandwidth(LORA_BW);
    LoRa.setTxPower(LORA_TX_POWER);
    LoRa.enableCrc();     // bez CRC przekłamany pakiet przechodzi jako poprawny
    loraListen();
    return true;
}

// ── Odbiór GPS + diagnostyka ──────────────────────────────────────────────────
// TinyGPS++ nie podaje siły sygnału ani liczby widocznych satelitów — wyciągamy je z GSV.
#define GPS_RAW_MS 90000UL       // tyle po starcie surowe NMEA idą na USB (linie "$...")
String   gpsLine     = "";
uint8_t  gpsView     = 0;        // satelity widoczne (suma systemów) w ostatniej sekundzie
uint8_t  gpsSnrMax   = 0;        // najsilniejszy sygnał [dBHz]
uint8_t  gpsViewAcc  = 0, gpsSnrAcc = 0;

static String nmeaField(const String& s, int n) {
    int from = 0;
    while (n-- > 0) { from = s.indexOf(',', from); if (from < 0) return ""; from++; }
    int to = from;
    while (to < (int)s.length() && s[to] != ',' && s[to] != '*') to++;
    return s.substring(from, to);
}

void gpsParseLine(const String& s) {
    if (millis() < GPS_RAW_MS) Serial.println(s);
    if (s.length() < 8 || s[0] != '$') return;
    const String type = s.substring(3, 6);
    if (type == "RMC") {                       // początek nowego cyklu
        gpsView = gpsViewAcc;  gpsSnrMax = gpsSnrAcc;
        gpsViewAcc = gpsSnrAcc = 0;
    } else if (type == "GSV") {
        if (nmeaField(s, 2) == "1") gpsViewAcc += nmeaField(s, 3).toInt();
        for (int f = 7; f <= 19; f += 4) {
            const int snr = nmeaField(s, f).toInt();
            if (snr > gpsSnrAcc && snr < 100) gpsSnrAcc = snr;
        }
    }
}

void readGps() {
    while (gpsSerial.available()) {
        const char c = (char)gpsSerial.read();
        gps.encode(c);
        if (c == '\n') { gpsParseLine(gpsLine); gpsLine = ""; }
        else if (c != '\r' && gpsLine.length() < 100) gpsLine += c;
    }
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

void loraWriteReg(uint8_t addr, uint8_t val) {
    SPI.beginTransaction(SPISettings(8000000, MSBFIRST, SPI_MODE0));
    digitalWrite(LORA_CS_PIN, LOW);
    SPI.transfer(addr | 0x80);
    SPI.transfer(val);
    digitalWrite(LORA_CS_PIN, HIGH);
    SPI.endTransaction();
}

// Nasłuch. Stan odbioru i nadawania czytamy z rejestru IRQ, więc linia DIO0 jest zbędna:
// DIO0 na CadDone (nie występuje), bo podniesienie DIO0 przy odebraniu pakietu wyłączało moduł.
void loraListen() {
    LoRa.receive();
    loraWriteReg(0x40, 0x80);
}

// Po zaniku zasilania układ wraca do ustawień fabrycznych: FSK, 434 MHz
bool loraAlive() {
    const uint32_t frf  = ((uint32_t)loraReg(0x06) << 16) | ((uint32_t)loraReg(0x07) << 8) | loraReg(0x08);
    const uint32_t want = (uint32_t)(((uint64_t)LORA_FREQ << 19) / 32000000);
    return loraReg(0x42) == 0x12 && (loraReg(0x01) & 0x80) && frf == want;
}

void loraLost(const char* why) {
    Serial.printf("[ESP32] LoRa: %s (ver=%02X op=%02X frf=%02X%02X%02X) — inicjalizuję od nowa\n", why,
                  loraReg(0x42), loraReg(0x01), loraReg(0x06), loraReg(0x07), loraReg(0x08));
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
        readGps();
        readRpiSerial();
        delay(2);
    }
    LoRa.beginPacket();                               // biblioteka kasuje flagę TxDone
    loraListen();
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
//   b [vbat,imA,tcpu]  d [dsku,dskf]  h hfdb  c [ok,rec,klatki,MB]
//   q [id, pakiety, bajty, crc] zdjęcie gotowe do odbioru
//   g [widoczne, maxSNR, zdania ok, zdania złe]
//   x 1 = część pól pominięta, żeby zmieścić się w LORA_MAX_PAYLOAD
static double rnd(double v, double scale) { return round(v * scale) / scale; }

// Pozycja dla dziennika lotu na karcie RPi — zapisuje się także bez łączności z ziemią.
// {"type":"gps","fix":true,"lat":..,"lon":..,"alt":..,"spd":..,"hdg":..,"sat":..,"hdop":..,"view":..,"snr":..,"t":"...Z"}
void sendGpsToRpi() {
    JsonDocument st;
    st["type"] = "gps";
    st["fix"]  = gpsFix();
    if (gps.location.isValid()) {
        st["lat"] = rnd(gps.location.lat(), 1e6);
        st["lon"] = rnd(gps.location.lng(), 1e6);
    }
    if (gps.altitude.isValid()) st["alt"] = rnd(gps.altitude.meters(), 10);
    if (gps.speed.isValid())    st["spd"] = rnd(gps.speed.kmph(), 10);
    if (gps.course.isValid())   st["hdg"] = rnd(gps.course.deg(), 10);
    st["sat"] = gps.satellites.isValid() ? (int)gps.satellites.value() : 0;
    if (gps.hdop.isValid())     st["hdop"] = rnd(gps.hdop.hdop(), 10);
    st["view"] = gpsView;
    st["snr"]  = gpsSnrMax;
    if (gps.date.isValid() && gps.time.isValid() && gps.date.year() > 2020) {
        char t[24];
        snprintf(t, sizeof(t), "%04d-%02d-%02dT%02d:%02d:%02dZ", gps.date.year(), gps.date.month(),
                 gps.date.day(), gps.time.hour(), gps.time.minute(), gps.time.second());
        st["t"] = t;
    }
    char buf[256];
    serializeJson(st, buf, sizeof(buf));
    sendToRpi(buf);
}

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
    if (imgReady) {                           // zdjęcie czeka na potwierdzenie z ziemi
        JsonArray q = doc["q"].to<JsonArray>();
        q.add(imgId);  q.add(imgN);  q.add(imgLen);  q.add(imgCrc);
    }
    JsonArray g = doc["g"].to<JsonArray>();   // diagnostyka GPS
    g.add(gpsView);  g.add(gpsSnrMax);
    g.add(gps.passedChecksum() % 10000);  g.add(gps.failedChecksum() % 10000);

    if (rpi.fresh) {
        // pełna telemetria z RPi5
        JsonArray b = doc["b"].to<JsonArray>();
        b.add(rnd(rpi.vbat, 100));  b.add((long)lround(rpi.imA));
        if (rpi.tcpu > -999.0f) b.add((int)lround(rpi.tcpu));
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
    for (const char* key : {"g", "d", "i", "c", "h"}) {
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
    Serial.printf("[ESP32] LoRa RX %d B rssi=%d snr=%.1f: %.60s\n", pktSize, LoRa.packetRssi(),
                  LoRa.packetSnr(), raw.c_str());

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
        imgSf = constrain((int)(doc["sf"] | LORA_SF), 7, 12);
        Serial.printf("[ESP32] photo cmd sf=%d → RPi\n", imgSf);
        sendToRpi(String("{\"cmd\":\"photo\",\"sf\":") + imgSf + "}");
        return;
    }

    // ziemia prosi o brakujące pakiety: "m" = mapa bitowa szesnastkowo
    if (strcmp(cmd, "img_req") == 0) {
        if (!imgReady || (doc["id"] | -1) != imgId) return;
        imgSf = constrain((int)(doc["sf"] | (int)imgSf), 7, 12);
        const String m = doc["m"] | "";
        memset(imgTodo, 0, sizeof(imgTodo));
        for (int i = 0; i + 1 < (int)m.length() && i / 2 < 16; i += 2)
            imgTodo[i / 2] = (uint8_t)strtol(m.substring(i, i + 2).c_str(), nullptr, 16);
        imgNextRound = 0;
        Serial.printf("[ESP32] dosyłam zdjęcie id=%d mapa=%s\n", imgId, m.c_str());
        return;
    }

    if (strcmp(cmd, "img_ok") == 0) {
        if ((doc["id"] | -1) == imgId) { imgReady = false; memset(imgTodo, 0, sizeof(imgTodo)); }
        Serial.printf("[ESP32] zdjęcie id=%d odebrane na ziemi\n", imgId);
        return;
    }

    // start / koniec lotu (RPi blokuje ostrość kamery na nieskończoność)
    if (strcmp(cmd, "flight") == 0) {
        bool on = doc["on"] | false;
        Serial.printf("[ESP32] flight on=%d → RPi\n", on);
        sendToRpi(String("{\"cmd\":\"flight\",\"on\":") + (on ? "true" : "false") + "}");
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

// ── Zdjęcie → LoRa, jedna seria ───────────────────────────────────────────────
void serviceDelay(uint32_t ms) {
    const uint32_t t0 = millis();
    while (millis() - t0 < ms) { readGps(); readRpiSerial(); delay(2); }
}

bool imgPending() {
    for (uint8_t b : imgTodo) if (b) return true;
    return false;
}

// Zapowiedź na zwykłym SF, potem pakiety na imgSf, potem powrót na zwykły SF.
// Pakiet: 0xA5, id, numer, liczba pakietów, dane
void sendImgRound() {
    const uint8_t  id = imgId;
    const uint32_t restarts = loraRestarts;
    // przybliżony czas pakietu 244 B: SF7 0.38 s, każdy SF wyżej ~1.8× dłużej
    uint32_t pktMs = 420;
    for (int f = 7; f < imgSf; f++) pktMs = pktMs * 18 / 10;
    int todo = 0;
    for (int i = 0; i < imgN; i++) if (imgTodo[i / 8] >> (i % 8) & 1) todo++;
    const int count = min(todo, max(1, (int)(IMG_ROUND_MS / pktMs)));

    char ann[128];
    const int annLen = snprintf(ann, sizeof(ann),
        "{\"t\":\"ph\",\"id\":%u,\"len\":%u,\"n\":%u,\"crc\":%lu,\"sf\":%u,\"m\":%d}",
        id, imgLen, imgN, (unsigned long)imgCrc, imgSf, count);
    if (!loraSend((const uint8_t*)ann, annLen)) return;
    Serial.printf("[LoRa] zdjęcie id=%u: seria %d z %d pakietów, SF%u\n", id, count, todo, imgSf);
    serviceDelay(400);                          // ziemia przełącza odbiornik
    LoRa.idle();
    LoRa.setSpreadingFactor(imgSf);

    uint8_t pkt[4 + IMG_DATA];
    int sent = 0;
    for (int i = 0; i < imgN && sent < count; i++) {
        if (!(imgTodo[i / 8] >> (i % 8) & 1)) continue;
        if (!imgReady || imgId != id) break;    // RPi właśnie podmienia zdjęcie
        const size_t off = (size_t)i * IMG_DATA;
        const size_t len = min((size_t)IMG_DATA, (size_t)imgLen - off);
        pkt[0] = 0xA5;  pkt[1] = id;  pkt[2] = i;  pkt[3] = imgN;
        memcpy(pkt + 4, imgBuf + off, len);
        const bool ok = loraSend(pkt, len + 4);
        if (loraRestarts != restarts) return;   // moduł podniesiony od nowa — już na zwykłym SF
        if (!ok) break;
        imgTodo[i / 8] &= ~(1 << (i % 8));
        sent++;
    }
    LoRa.idle();
    LoRa.setSpreadingFactor(LORA_SF);
    loraListen();
    serviceDelay(300);
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

    Serial.setRxBufferSize(8192);
    imgBuf = (uint8_t*)malloc(IMG_MAX_BYTES);
    Serial.begin(115200);
    delay(500);

    // Nadawanie LoRa blokuje pętlę na ~2 s — domyślne 256 B by się przepełniło
    gpsSerial.setRxBufferSize(4096);
    rpiSerial.setRxBufferSize(8192);
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
    readGps();
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
    if (now - lastGpsToRpi >= GPS_TO_RPI_MS) {
        lastGpsToRpi = now;
        sendGpsToRpi();
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
        delay(random(0, 100));
        sendBeacon();
        lastBeacon = now;
    } else if (imgReady && imgPending() && loraOk && now >= imgNextRound) {
        sendImgRound();
        lastBeacon   = millis() - BEACON_INTERVAL_MS;   // po serii od razu beacon i okno na komendy
        imgNextRound = millis() + IMG_GAP_MS;
    }
}
