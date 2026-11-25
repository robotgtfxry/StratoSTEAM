/*
 * StratoSTEAM — ESP32-CAM node
 * ─────────────────────────────────────────────────────────────────────────────
 * Ciągłe nagrywanie MJPEG AVI na kartę SD.
 * Plik dzielony co FILE_SPLIT_S sekund — przy utracie zasilania
 * tracisz max jeden segment, poprzednie pliki są kompletne.
 *
 * Płytka: AI-Thinker ESP32-CAM, czujnik OV3660 (na balonie jest jedna sztuka)
 * PlatformIO: pio run -t upload
 *
 * Bez karty SD kamera działa dalej (klatki są zliczane, nie zapisywane),
 * a karta jest wykrywana ponownie co SD_RETRY_MS — po włożeniu nagrywanie rusza samo.
 *
 * Status wysyłany przez U0TX (USB nakładki ESP32-CAM-MB → RPi5) co 5s, format:
 *   $S{"ok":1,"rec":1,"sd":1,"n":1234,"mb":7800,"fps":9.8}
 *   ok = kamera działa, sd = karta SD zamontowana, rec = trwa zapis,
 *   fps = średnia liczba klatek/s od poprzedniego statusu
 * RPi parsuje tylko linie zaczynające się od "$S".
 */

#include <Arduino.h>
#include "config.h"
#include "esp_camera.h"
#include "SD_MMC.h"
#include "FS.h"

// ─── Pinout AI-Thinker ESP32-CAM ─────────────────────────────────────────────
#define PWDN_GPIO_NUM   32
#define RESET_GPIO_NUM  -1
#define XCLK_GPIO_NUM    0
#define SIOD_GPIO_NUM   26
#define SIOC_GPIO_NUM   27
#define Y9_GPIO_NUM     35
#define Y8_GPIO_NUM     34
#define Y7_GPIO_NUM     39
#define Y6_GPIO_NUM     36
#define Y5_GPIO_NUM     21
#define Y4_GPIO_NUM     19
#define Y3_GPIO_NUM     18
#define Y2_GPIO_NUM      5
#define VSYNC_GPIO_NUM  25
#define HREF_GPIO_NUM   23
#define PCLK_GPIO_NUM   22

// ─── MJPEG AVI writer ─────────────────────────────────────────────────────────
// Minimalny valid AVI z jednym strumieniem MJPEG.
// Rozmiary w headerze aktualizowane przy zamknięciu pliku (seek + write).

class AviWriter {
public:
  bool     open(const char *path, uint16_t w, uint16_t h, uint8_t fps);
  bool     addFrame(const uint8_t *data, size_t len);
  void     close();
  bool     isOpen() const { return _f; }
  uint32_t frameCount() const { return _frames; }

private:
  File     _f;
  uint32_t _frames    = 0;
  uint32_t _moviStart = 0;   // offset początku bloku movi
  // Offsety pól uzupełnianych przy close() — zapamiętane podczas pisania nagłówka
  uint32_t _hdrlSizePos = 0, _strlSizePos = 0, _framesPos = 0, _lengthPos = 0;
  uint32_t _hdrlEnd = 0;
  uint16_t _w = 0, _h = 0;
  uint8_t  _fps = 0;

  void     _writeU16LE(uint16_t v);
  void     _writeU32LE(uint32_t v);
  void     _write4cc(const char *s);
  void     _patchU32(uint32_t offset, uint32_t v);
};

void AviWriter::_writeU16LE(uint16_t v) {
  uint8_t b[2] = {(uint8_t)(v), (uint8_t)(v >> 8)};
  _f.write(b, 2);
}
void AviWriter::_writeU32LE(uint32_t v) {
  uint8_t b[4] = {(uint8_t)(v), (uint8_t)(v>>8), (uint8_t)(v>>16), (uint8_t)(v>>24)};
  _f.write(b, 4);
}
void AviWriter::_write4cc(const char *s) {
  _f.write((uint8_t*)s, 4);
}
void AviWriter::_patchU32(uint32_t offset, uint32_t v) {
  uint32_t cur = _f.position();
  _f.seek(offset);
  _writeU32LE(v);
  _f.seek(cur);
}

bool AviWriter::open(const char *path, uint16_t w, uint16_t h, uint8_t fps) {
  _f = SD_MMC.open(path, FILE_WRITE);
  if (!_f) return false;
  _frames = 0;
  _w = w; _h = h; _fps = fps;

  // ── RIFF AVI header ──────────────────────────────────────────────────────
  _write4cc("RIFF");
  _writeU32LE(0);           // [4]  rozmiar RIFF — patch przy close
  _write4cc("AVI ");

  // LIST hdrl
  _write4cc("LIST");
  _hdrlSizePos = _f.position();
  _writeU32LE(0);           // rozmiar LIST hdrl — patch przy close
  _write4cc("hdrl");

  // avih (MainAVIHeader, 56 bajtów)
  _write4cc("avih");
  _writeU32LE(56);
  _writeU32LE(1000000 / fps);  // dwMicroSecPerFrame
  _writeU32LE(0);              // dwMaxBytesPerSec
  _writeU32LE(0);              // dwPaddingGranularity
  _writeU32LE(0);              // dwFlags (bez indeksu idx1)
  _framesPos = _f.position();
  _writeU32LE(0);              // dwTotalFrames — patch przy close
  _writeU32LE(0);              // dwInitialFrames
  _writeU32LE(1);              // dwStreams
  _writeU32LE(w * h * 3);      // dwSuggestedBufferSize
  _writeU32LE(w);              // dwWidth
  _writeU32LE(h);              // dwHeight
  _writeU32LE(0); _writeU32LE(0); _writeU32LE(0); _writeU32LE(0); // reserved

  // LIST strl
  _write4cc("LIST");
  _strlSizePos = _f.position();
  _writeU32LE(0);           // rozmiar LIST strl — patch przy close
  _write4cc("strl");

  // strh (AVIStreamHeader, 56 bajtów)
  _write4cc("strh");
  _writeU32LE(56);
  _write4cc("vids");        // fccType
  _write4cc("MJPG");        // fccHandler
  _writeU32LE(0);           // dwFlags
  _writeU16LE(0);           // wPriority
  _writeU16LE(0);           // wLanguage
  _writeU32LE(0);           // dwInitialFrames
  _writeU32LE(1);           // dwScale
  _writeU32LE(fps);         // dwRate
  _writeU32LE(0);           // dwStart
  _lengthPos = _f.position();
  _writeU32LE(0);           // dwLength — patch przy close
  _writeU32LE(w * h * 3);   // dwSuggestedBufferSize
  _writeU32LE(0);           // dwQuality
  _writeU32LE(0);           // dwSampleSize
  _writeU16LE(0); _writeU16LE(0); _writeU16LE(w); _writeU16LE(h); // rcFrame

  // strf (BITMAPINFOHEADER, 40 bajtów)
  _write4cc("strf");
  _writeU32LE(40);
  _writeU32LE(40);          // biSize
  _writeU32LE(w);           // biWidth
  _writeU32LE(h);           // biHeight
  _writeU16LE(1);           // biPlanes
  _writeU16LE(24);          // biBitCount
  _write4cc("MJPG");        // biCompression
  _writeU32LE(w * h * 3);   // biSizeImage
  _writeU32LE(0); _writeU32LE(0); _writeU32LE(0); _writeU32LE(0);

  _hdrlEnd = _f.position();

  // JUNK chunk — wyrównanie do 2048 bajtów (standard AVI)
  uint32_t pos = _f.position();
  uint32_t junkSize = 2048 - (pos + 8) % 2048;
  if (junkSize < 4) junkSize += 2048;
  _write4cc("JUNK");
  _writeU32LE(junkSize);
  for (uint32_t i = 0; i < junkSize; i++) _f.write((uint8_t)0);

  // LIST movi
  _write4cc("LIST");
  _writeU32LE(0);           // rozmiar movi — patch przy close
  _moviStart = _f.position();
  _write4cc("movi");

  return true;
}

bool AviWriter::addFrame(const uint8_t *data, size_t len) {
  if (!_f) return false;
  // Chunk 00dc = Video Data, Compressed
  _write4cc("00dc");
  _writeU32LE((uint32_t)len);
  if (_f.write(data, len) != len) return false;   // karta wyjęta / pełna
  // Padding do parzystego rozmiaru
  if (len % 2 != 0) _f.write((uint8_t)0);
  _frames++;
  return true;
}

void AviWriter::close() {
  if (!_f) return;

  uint32_t fileSize = _f.position();
  uint32_t moviSize = fileSize - _moviStart;

  // Patch rozmiarów w headerze
  _patchU32(4,   fileSize - 8);     // RIFF size
  _patchU32(_hdrlSizePos, _hdrlEnd - _hdrlSizePos - 4);  // LIST hdrl size
  _patchU32(_strlSizePos, _hdrlEnd - _strlSizePos - 4);  // LIST strl size
  _patchU32(_framesPos, _frames);   // avih dwTotalFrames
  _patchU32(_lengthPos, _frames);   // strh dwLength
  // Znajdź offset LIST movi: moviStart - 4 (przed "movi" tagiem)
  _patchU32(_moviStart - 4, moviSize);

  _f.close();
  _frames = 0;
}

// ─── Globals ─────────────────────────────────────────────────────────────────
static bool      g_cam_ok    = false;
static bool      g_sd_ok     = false;
static bool      g_recording = false;
static uint32_t  g_totalFrames = 0;
static uint32_t  g_fileCount   = 0;
static char      g_sessionDir[24] = "";
static AviWriter g_avi;

#define SD_RETRY_MS 30000   // co ile ponawiać wykrycie karty SD

bool createSessionDir();
bool openNextFile();

// ─── LED ─────────────────────────────────────────────────────────────────────
void ledBlink(int times, int onMs = 80, int offMs = 120) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_PIN, LED_ACTIVE);
    delay(onMs);
    digitalWrite(LED_PIN, !LED_ACTIVE);
    if (i < times - 1) delay(offMs);
  }
}

void heartbeat() {
  static unsigned long last = 0;
  unsigned long now = millis();
  if (now - last < 2000) return;
  last = now;
  if      (!g_cam_ok) ledBlink(3, 50, 100);
  else if (!g_sd_ok)  ledBlink(2, 50, 100);
  else                ledBlink(1, 30);
}

// ─── Kamera ──────────────────────────────────────────────────────────────────
bool initCamera() {
  camera_config_t cfg = {};          // wyzeruj — pola nieustawione nie mogą być śmieciami
  cfg.ledc_channel = LEDC_CHANNEL_0;
  cfg.ledc_timer   = LEDC_TIMER_0;
  cfg.pin_d0 = Y2_GPIO_NUM; cfg.pin_d1 = Y3_GPIO_NUM;
  cfg.pin_d2 = Y4_GPIO_NUM; cfg.pin_d3 = Y5_GPIO_NUM;
  cfg.pin_d4 = Y6_GPIO_NUM; cfg.pin_d5 = Y7_GPIO_NUM;
  cfg.pin_d6 = Y8_GPIO_NUM; cfg.pin_d7 = Y9_GPIO_NUM;
  cfg.pin_xclk     = XCLK_GPIO_NUM;
  cfg.pin_pclk     = PCLK_GPIO_NUM;
  cfg.pin_vsync    = VSYNC_GPIO_NUM;
  cfg.pin_href     = HREF_GPIO_NUM;
  cfg.pin_sscb_sda = SIOD_GPIO_NUM;
  cfg.pin_sscb_scl = SIOC_GPIO_NUM;
  cfg.pin_pwdn     = PWDN_GPIO_NUM;
  cfg.pin_reset    = RESET_GPIO_NUM;
  cfg.xclk_freq_hz = XCLK_FREQ_HZ;
  cfg.pixel_format = PIXFORMAT_JPEG;
  cfg.frame_size   = FRAMESIZE;
  cfg.jpeg_quality = JPEG_QUALITY;
  cfg.fb_count     = 2;
  cfg.fb_location  = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
  cfg.grab_mode    = CAMERA_GRAB_LATEST;   // zawsze najnowsza klatka, bez przepełnień

  if (esp_camera_init(&cfg) != ESP_OK) return false;

  sensor_t *s = esp_camera_sensor_get();
  if (s) {
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_wb_mode(s, 0);
    s->set_exposure_ctrl(s, 1);
    s->set_aec2(s, 1);
    s->set_gain_ctrl(s, 1);
    s->set_gainceiling(s, (gainceiling_t)6);
    s->set_raw_gma(s, 1);
    s->set_lenc(s, 1);
  }
  return true;
}

// ─── SD ──────────────────────────────────────────────────────────────────────
bool initSD() {
  if (!SD_MMC.begin("/sdcard", true)) return false;
  if (SD_MMC.cardType() == CARD_NONE) { SD_MMC.end(); return false; }
  return true;
}

// Karta OK → nowy katalog sesji + pierwszy plik AVI
bool startRecording() {
  if (!createSessionDir()) { Serial.println("[SD] no session slot"); return false; }
  if (!openNextFile())     { Serial.println("[AVI] cannot create file"); return false; }
  g_recording = true;
  Serial.println("[REC] nagrywanie na SD");
  return true;
}

bool createSessionDir() {
  const char *base = SESSION_ROOT;
  SD_MMC.mkdir(base);
  for (int i = 0; i < 1000; i++) {
    snprintf(g_sessionDir, sizeof(g_sessionDir), "%s/S%03d", base, i);
    if (!SD_MMC.exists(g_sessionDir)) {
      return SD_MMC.mkdir(g_sessionDir);
    }
  }
  return false;
}

// ─── Otwórz nowy plik AVI ────────────────────────────────────────────────────
bool openNextFile() {
  if (g_avi.isOpen()) g_avi.close();
  char path[48];
  snprintf(path, sizeof(path), "%s/%04lu.avi", g_sessionDir, g_fileCount++);
  bool ok = g_avi.open(path, CAM_WIDTH, CAM_HEIGHT, TARGET_FPS);
  if (ok) Serial.printf("[AVI] opened: %s\n", path);
  else    Serial.printf("[AVI] failed: %s\n", path);
  return ok;
}

// ─── Status → RPi ────────────────────────────────────────────────────────────
void sendStatus() {
  static uint32_t      lastFrames = 0;
  static unsigned long lastMs     = 0;
  unsigned long now = millis();
  float fps = lastMs ? (g_totalFrames - lastFrames) * 1000.0f / (now - lastMs) : 0.0f;
  lastFrames = g_totalFrames;
  lastMs     = now;

  uint64_t free_mb = g_sd_ok ? (SD_MMC.totalBytes() - SD_MMC.usedBytes()) / (1024 * 1024) : 0;
  Serial.printf("$S{\"ok\":%d,\"rec\":%d,\"sd\":%d,\"n\":%lu,\"mb\":%llu,\"fps\":%.1f}\n",
    g_cam_ok ? 1 : 0,
    g_recording ? 1 : 0,
    g_sd_ok ? 1 : 0,
    g_totalFrames,
    free_mb,
    fps
  );
}

// ─── Setup ───────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial.println("\n[BOOT] StratoSTEAM ESP32-CAM");

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, !LED_ACTIVE);
  pinMode(FLASH_PIN, OUTPUT);          // lampa błyskowa zawsze zgaszona
  digitalWrite(FLASH_PIN, LOW);

  g_sd_ok = initSD();
  if (!g_sd_ok) {
    Serial.println("[SD] brak karty — praca BEZ zapisu, ponawiam co 30 s");
    ledBlink(5, 100, 200);
  } else {
    uint64_t free_mb = (SD_MMC.totalBytes() - SD_MMC.usedBytes()) / (1024*1024);
    Serial.printf("[SD] OK  free=%lluMB\n", free_mb);
  }

  g_cam_ok = initCamera();
  if (!g_cam_ok) {
    Serial.println("[CAM] ERROR");
    ledBlink(3, 100, 200);
  } else {
    Serial.printf("[CAM] OK  %dx%d @ %dfps\n", CAM_WIDTH, CAM_HEIGHT, TARGET_FPS);
  }

  if (g_cam_ok && g_sd_ok && startRecording()) {
    ledBlink(2, 200, 100);
    Serial.println("[BOOT] OK — recording");
  } else if (g_cam_ok) {
    Serial.println("[BOOT] OK — kamera działa, BEZ nagrywania (brak SD)");
  } else {
    Serial.println("[BOOT] kamera nie działa — wysyłam tylko status");
  }
}

// ─── Loop ────────────────────────────────────────────────────────────────────
void loop() {
  unsigned long now = millis();

  // ── Capture klatki ──────────────────────────────────────────────────────
  static unsigned long lastCapture = 0;
  static uint32_t      fbFail      = 0;
  if (now - lastCapture >= CAPTURE_INTERVAL_MS) {
    lastCapture = now;

    camera_fb_t *fb = g_cam_ok ? esp_camera_fb_get() : nullptr;
    if (fb) {
      if (g_recording && !g_avi.addFrame(fb->buf, fb->len)) {
        // zapis padł (karta wyjęta / błąd) → przejdź w tryb bez SD
        Serial.println("[SD] błąd zapisu — przechodzę w tryb bez SD");
        g_avi.close();
        SD_MMC.end();
        g_recording = false;
        g_sd_ok     = false;
      }
      g_totalFrames++;
      esp_camera_fb_return(fb);
    } else if (g_cam_ok && (++fbFail % 50) == 1) {
      Serial.printf("[CAM] brak klatki (x%lu)\n", fbFail);
    }
  }

  // ── Podziel plik co FILE_SPLIT_S sekund ─────────────────────────────────
  static unsigned long fileStart = now;
  if (g_recording && now - fileStart >= (unsigned long)FILE_SPLIT_S * 1000UL) {
    fileStart = now;
    Serial.printf("[AVI] split  frames=%lu\n", g_avi.frameCount());
    openNextFile();
  }

  // ── Ponowne wykrywanie karty SD ─────────────────────────────────────────
  static unsigned long lastSdRetry = now;
  if (!g_sd_ok && now - lastSdRetry >= SD_RETRY_MS) {
    lastSdRetry = now;
    g_sd_ok = initSD();
    if (g_sd_ok) {
      Serial.println("[SD] karta wykryta");
      if (g_cam_ok && startRecording()) fileStart = now;
    }
  }

  // ── Status → RPi ────────────────────────────────────────────────────────
  static unsigned long lastStatus = 0;
  if (now - lastStatus >= STATUS_INTERVAL_MS) {
    lastStatus = now;
    sendStatus();
  }

  heartbeat();
}
