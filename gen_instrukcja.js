const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, Header, Footer, PageNumber, TableOfContents,
} = require("docx");
const fs = require("fs");

const BLUE   = "1F4E79";
const LBLUE  = "D6E4F0";
const GRAY   = "F2F2F2";
const border = { style: BorderStyle.SINGLE, size: 1, color: "BBBBBB" };
const borders = { top: border, bottom: border, left: border, right: border };

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun({ text, bold: true, size: 32, color: BLUE, font: "Arial" })],
    spacing: { before: 360, after: 160 },
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [new TextRun({ text, bold: true, size: 26, color: "2E75B6", font: "Arial" })],
    spacing: { before: 280, after: 120 },
  });
}
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    children: [new TextRun({ text, bold: true, size: 22, font: "Arial" })],
    spacing: { before: 200, after: 80 },
  });
}
function p(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({ text, font: "Arial", size: 22, ...opts })],
    spacing: { before: 60, after: 60 },
  });
}
function bullet(text) {
  return new Paragraph({
    numbering: { reference: "bullets", level: 0 },
    children: [new TextRun({ text, font: "Arial", size: 22 })],
    spacing: { before: 40, after: 40 },
  });
}
function code(text) {
  return new Paragraph({
    children: [new TextRun({ text, font: "Courier New", size: 18, color: "333333" })],
    shading: { fill: "F0F0F0", type: ShadingType.CLEAR },
    spacing: { before: 60, after: 60 },
    indent: { left: 360 },
  });
}
function twoColRow(label, value, shade) {
  const fill = shade ? LBLUE : "FFFFFF";
  return new TableRow({
    children: [
      new TableCell({
        borders, width: { size: 3600, type: WidthType.DXA },
        shading: { fill, type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text: label, bold: true, font: "Arial", size: 20 })] })],
      }),
      new TableCell({
        borders, width: { size: 5760, type: WidthType.DXA },
        shading: { fill, type: ShadingType.CLEAR },
        margins: { top: 80, bottom: 80, left: 120, right: 120 },
        children: [new Paragraph({ children: [new TextRun({ text: value, font: "Arial", size: 20 })] })],
      }),
    ],
  });
}
function twoColTable(rows) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [3600, 5760],
    rows: rows.map((r, i) => twoColRow(r[0], r[1], i % 2 === 0)),
  });
}

// ── Tabela komponentów ──
function componentTable(rows) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2200, 2200, 4960],
    rows: [
      new TableRow({
        children: ["Komponent", "Interfejs / pin", "Opis"].map((h, i) =>
          new TableCell({
            borders,
            width: { size: [2200, 2200, 4960][i], type: WidthType.DXA },
            shading: { fill: "1F4E79", type: ShadingType.CLEAR },
            margins: { top: 80, bottom: 80, left: 120, right: 120 },
            children: [new Paragraph({ children: [new TextRun({ text: h, bold: true, color: "FFFFFF", font: "Arial", size: 20 })] })],
          })
        ),
      }),
      ...rows.map((r, ri) =>
        new TableRow({
          children: r.map((cell, ci) =>
            new TableCell({
              borders,
              width: { size: [2200, 2200, 4960][ci], type: WidthType.DXA },
              shading: { fill: ri % 2 === 0 ? GRAY : "FFFFFF", type: ShadingType.CLEAR },
              margins: { top: 80, bottom: 80, left: 120, right: 120 },
              children: [new Paragraph({ children: [new TextRun({ text: cell, font: "Arial", size: 20 })] })],
            })
          ),
        })
      ),
    ],
  });
}

const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }],
      },
      {
        reference: "steps",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }],
      },
    ],
  },
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial", color: BLUE },
        paragraph: { spacing: { before: 360, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: "2E75B6" },
        paragraph: { spacing: { before: 280, after: 120 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 22, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 200, after: 80 }, outlineLevel: 2 } },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 11906, height: 16838 },
        margin: { top: 1134, right: 1134, bottom: 1134, left: 1134 },
      },
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: "2E75B6", space: 1 } },
          children: [new TextRun({ text: "StratoSTEAM — Instrukcja obsługi systemu", font: "Arial", size: 18, color: "555555" })],
        })],
      }),
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          border: { top: { style: BorderStyle.SINGLE, size: 4, color: "2E75B6", space: 1 } },
          alignment: AlignmentType.RIGHT,
          children: [
            new TextRun({ text: "Strona ", font: "Arial", size: 18, color: "555555" }),
            new TextRun({ children: [PageNumber.CURRENT], font: "Arial", size: 18, color: "555555" }),
          ],
        })],
      }),
    },
    children: [

      // ── Strona tytułowa ──
      new Paragraph({ spacing: { before: 2000 } }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "StratoSTEAM", bold: true, size: 72, color: BLUE, font: "Arial" })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "Instrukcja obsługi systemu balonowego", size: 36, color: "444444", font: "Arial" })],
        spacing: { before: 120 },
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "Wersja produkcyjna — bez symulacji", size: 24, color: "888888", font: "Arial" })],
        spacing: { before: 80, after: 2000 },
      }),

      // ── Spis treści ──
      new TableOfContents("Spis treści", { hyperlink: true, headingStyleRange: "1-3" }),
      new Paragraph({ children: [new TextRun({ break: 1 })], pageBreakBefore: true }),

      // ══════════════════════════════════════════════════════════════
      // 1. PRZEGLĄD SYSTEMU
      // ══════════════════════════════════════════════════════════════
      h1("1. Przegląd systemu"),
      p("StratoSTEAM to system misji balonowej składający się z trzech warstw:"),
      bullet("rpi-air — węzeł powietrzny (balon): zbiera dane z czujników i przesyła je do naziemnej stacji kontrolnej przez LoRa"),
      bullet("rpi-ground — naziemna stacja kontrolna: odbiera telemetrię przez LoRa, przekazuje do backendu i wysyła komendy do balonu"),
      bullet("backend — serwer FastAPI (frog02.mikr.us:21124): przechowuje dane i udostępnia API dla aplikacji Flutter"),
      bullet("Aplikacja Flutter — interfejs operatora: podgląd telemetrii, mapy, sterowanie kamerą i aktywatorami"),
      p(""),

      h2("1.1 Schemat przepływu danych"),
      twoColTable([
        ["rpi-air (balon)", "Czujniki → ESP32 (UART) → LoRa TX"],
        ["Radio LoRa 433 MHz", "Pakiety JSON, SF10, BW125, CR4/5"],
        ["rpi-ground (ziemia)", "LoRa RX → backend HTTP POST"],
        ["Backend (VPS)", "FastAPI + SQLite, port 21124"],
        ["Aplikacja Flutter", "HTTP GET / WebSocket od backendu"],
      ]),
      p(""),

      // ══════════════════════════════════════════════════════════════
      // 2. SPRZĘT
      // ══════════════════════════════════════════════════════════════
      h1("2. Sprzęt"),

      h2("2.1 Węzeł powietrzny (rpi-air)"),
      componentTable([
        ["Raspberry Pi 5",       "—",              "Jednostka główna, uruchamia rpi-air/main.py"],
        ["ESP32-S3",             "UART (GPIO14)",   "GPS, LoRa TX, buzzer, LED RGB, nadzór zasilania"],
        ["BME280",               "I2C 0x76",        "Temperatura, ciśnienie, wilgotność"],
        ["MS5611",               "I2C 0x77",        "Ciśnienie barometryczne, wysokość bezwzględna"],
        ["BNO085",               "I2C 0x4A",        "IMU: roll, pitch, yaw, przyspieszenie"],
        ["INA219",               "I2C 0x40",        "Monitor baterii: napięcie, prąd, moc"],
        ["HX711 ×4",             "GPIO 12-25",      "Tensometry siły liny balonu (4 kierunki)"],
        ["Kamera RPi (cam0)",    "CSI",             "Nagrywanie H.264 4K (3840x2160), zdjecia LoRa 160x120"],
        ["ESP32-CAM",            "GPIO17 (pwr), GPIO4 (status RX)", "Wideo MJPEG AVI 640x480 10fps na SD, status przez UART TX"],
        ["RTL-SDR",              "USB",             "Odbiornik HF 7.1 MHz (eksperyment jonosferyczny)"],
      ]),
      p(""),

      h2("2.2 Stacja naziemna (rpi-ground)"),
      componentTable([
        ["Raspberry Pi (dowolny)", "—",           "Uruchamia rpi-ground/main.py"],
        ["Moduł LoRa RX",          "SPI0 CS0",    "Odbiór telemetrii z balonu, nadawanie komend"],
        ["AD9833 DDS",             "SPI1 CS1",    "Generator sygnału HF 7.1 MHz"],
        ["RD06HHF1",               "PTT GPIO24",  "Wzmacniacz HF do badań jonosferycznych"],
      ]),
      p(""),

      // ══════════════════════════════════════════════════════════════
      // 3. URUCHOMIENIE BACKENDU
      // ══════════════════════════════════════════════════════════════
      h1("3. Uruchomienie backendu"),
      p("Backend działa na serwerze frog02.mikr.us (Alpine Linux, VPS mikr.us)."),

      h2("3.1 Pierwsze uruchomienie"),
      p("Zaloguj się na serwer SSH i uruchom:"),
      code("ssh frog@frog02.mikr.us -p <port_SSH>"),
      code("cd ~/stratosteam-backend"),
      code("pip install -r requirements.txt"),
      code("uvicorn main:app --host 0.0.0.0 --port 21124"),
      p(""),

      h2("3.2 Uruchomienie w tle (zalecane)"),
      p("Użyj screen lub nohup żeby backend działał po zamknięciu sesji SSH:"),
      code("screen -S backend"),
      code("cd ~/stratosteam-backend && uvicorn main:app --host 0.0.0.0 --port 21124"),
      p("Odłącz screen: Ctrl+A, D. Powrót: screen -r backend"),
      p(""),

      h2("3.3 Weryfikacja"),
      p("Otwórz w przeglądarce:"),
      code("http://frog02.mikr.us:21124/api/telemetry/latest"),
      p("Poprawna odpowiedź to JSON z ostatnim rekordem telemetrii (lub 404 jeśli brak danych)."),
      p(""),
      p("Dokumentacja API (Swagger):"),
      code("http://frog02.mikr.us:21124/docs"),
      p(""),

      h2("3.4 Diagnoza"),
      twoColTable([
        ["Connection timed out",   "Backend nie działa — uruchom uvicorn"],
        ["Address already in use", "Backend już chodzi w tle — sprawdź: ps aux | grep uvicorn"],
        ["401 Unauthorized",       "Zły klucz API — sprawdź BACKEND_API_KEY w config.py"],
        ["404 Not Found na /",     "Backend działa poprawnie (FastAPI zwraca 404 na root)"],
      ]),
      p(""),

      // ══════════════════════════════════════════════════════════════
      // 4. URUCHOMIENIE WĘZŁA POWIETRZNEGO
      // ══════════════════════════════════════════════════════════════
      h1("4. Uruchomienie węzła powietrznego (rpi-air)"),

      h2("4.1 Konfiguracja"),
      p("Edytuj plik rpi-air/config.py i sprawdź:"),
      twoColTable([
        ["ESP_UART_PORT",      "/dev/ttyAMA0 — port UART do ESP32"],
        ["BME280_ADDR",        "0x76 — adres I2C czujnika BME280"],
        ["HX711_SENSORS",      "Piny GPIO dla 4 tensometrów (DT + SCK)"],
        ["SDR_ENABLED",        "True jeśli podłączony RTL-SDR, False w przeciwnym razie"],
        ["CAM_RECORD_DIR",     "/home/pi/stratosteam-video — katalog nagrań"],
        ["ESPCAM_PWR_PIN",     "17 — GPIO zasilania kamery ESP32-CAM"],
        ["ESPCAM_STATUS_PIN",  "4 — GPIO odczytu statusu kamery ESP32-CAM"],
      ]),
      p(""),

      h2("4.2 Uruchomienie"),
      code("cd ~/stratosteam"),
      code("python rpi-air/main.py"),
      p("Węzeł powietrzny powinien uruchomić się automatycznie przy starcie RPi. Dodaj do /etc/rc.local lub użyj systemd."),
      p(""),

      h2("4.3 Co dzieje się po uruchomieniu"),
      bullet("PowerSignal ustawia pin RPI_ALIVE_PIN (GPIO26) w stan HIGH — ESP32 wie że RPi działa"),
      bullet("Inicjalizacja wszystkich czujników (BME280, MS5611, BNO085, INA219, HX711×4)"),
      bullet("Kamera zaczyna nagrywać H.264 do CAM_RECORD_DIR"),
      bullet("Co 5 sekund: odczyt czujników, wysyłka do ESP32 przez UART"),
      bullet("ESP32 pakuje dane z GPS i wysyła pakiet LoRa do stacji naziemnej"),
      bullet("Opcjonalnie: RTL-SDR mierzy siłę sygnału HF co 10 sekund"),
      p(""),

      h2("4.4 Obsługa shutdown"),
      p("ESP32 może zażądać wyłączenia RPi (komenda z ziemi przez LoRa). Gdy GPIO ESP32_SHTDN_PIN (GPIO6) zostanie podniesiony, rpi-air wykona sudo shutdown -h now."),
      p(""),

      // ══════════════════════════════════════════════════════════════
      // 5. URUCHOMIENIE STACJI NAZIEMNEJ
      // ══════════════════════════════════════════════════════════════
      h1("5. Uruchomienie stacji naziemnej (rpi-ground)"),

      h2("5.1 Konfiguracja"),
      p("Edytuj rpi-ground/config.py:"),
      twoColTable([
        ["BACKEND_URL",             "http://frog02.mikr.us:21124"],
        ["BACKEND_API_KEY",         "Klucz API — musi zgadzać się z backendem"],
        ["LORA_FREQ",               "433.0 MHz — musi zgadzać się z rpi-air"],
        ["LORA_SF / LORA_BW",       "SF10, BW125000 — musi zgadzać się z rpi-air"],
        ["HF_DEFAULT_FREQ_HZ",      "7100000 — 7.1 MHz (pasmo 40m)"],
        ["OFFLINE_FLUSH_INTERVAL_S","10 — jak często retry przy braku backendu"],
      ]),
      p(""),

      h2("5.2 Uruchomienie"),
      code("cd ~/stratosteam"),
      code("python rpi-ground/main.py"),
      p(""),

      h2("5.3 Co dzieje się po uruchomieniu"),
      bullet("LoRa RX zaczyna nasłuchiwać na 433 MHz"),
      bullet("Uruchamiane są store-wątki: HfController, CommandStore, RpiPowerStore, CameraStore, EspCamStore"),
      bullet("Gdy nadejdzie pakiet telemetrii od balonu — jest parsowany i wysyłany HTTP POST do backendu"),
      bullet("Po odebraniu pakietu otwiera się okno uplink: stacja może wysłać jedną komendę do balonu"),
      bullet("Komendy są pobierane z backendu przez polling (CommandStore, CameraStore itd.)"),
      p(""),

      h2("5.4 Kolejność priorytetów komend uplink"),
      twoColTable([
        ["1 (najwyższy)", "Komenda exec (shell na RPi)"],
        ["2",             "Shutdown / power RPi"],
        ["3",             "Buzzer / LED RGB"],
        ["4",             "Foto kamery"],
        ["5",             "Start/stop nagrywania"],
        ["6 (najniższy)", "Zasilanie ESP32-CAM"],
      ]),
      p(""),

      h2("5.5 Obsługa trybu ESP32-only (RPi wyłączone)"),
      p("Gdy RPi na balonie jest wyłączone, ESP32 wysyła beacon z minimalną telemetrią (GPS, napięcie baterii). Stacja naziemna rozpoznaje pakiety z src=esp32 i obsługuje je osobno — można przez nie sterować zasilaniem RPi i kamerą."),
      p(""),

      // ══════════════════════════════════════════════════════════════
      // 6. APLIKACJA FLUTTER
      // ══════════════════════════════════════════════════════════════
      h1("6. Aplikacja Flutter"),

      h2("6.1 Instalacja APK"),
      bullet("Pobierz najnowszy artefakt z GitHub Actions: Build APK"),
      bullet("Zainstaluj APK na telefonie z systemem Android 9+"),
      bullet("Przy pierwszym uruchomieniu podaj URL backendu w ustawieniach"),
      p(""),

      h2("6.2 Konfiguracja URL backendu"),
      p("Domyślny URL jest wpisany w kodzie: http://frog02.mikr.us:21124"),
      p("Można go zmienić w aplikacji: Ustawienia → Backend URL"),
      p(""),

      h2("6.3 Dostępne funkcje"),
      twoColTable([
        ["Telemetria",        "Podgląd na żywo: temperatura, ciśnienie, IMU, bateria, GPS"],
        ["Mapa",              "Trasa lotu w czasie rzeczywistym, waypoints co 5 minut"],
        ["Kamera RPi",        "Podglad ostatniego zdj. (160x120 przez LoRa), zadanie nowego zdj., start/stop nagrywania 4K"],
        ["ESP32-CAM",         "Wlaczanie/wylaczanie kamery (MJPEG AVI na SD), podglad statusu: nagrywanie, klatki, wolne MB"],
        ["Buzzer / LED",      "Sterowanie sygnałem akustycznym i diodą RGB na balonie"],
        ["Shutdown RPi",      "Zdalne wyłączenie Raspberry Pi w balonie"],
        ["HF / SDR",          "Wykres siły sygnału jonosferycznego vs wysokość"],
        ["Waypoints",         "Historia pozycji zapisywana co 5 minut"],
      ]),
      p(""),

      // ══════════════════════════════════════════════════════════════
      // 7. KAMERY ESP32-CAM
      // ══════════════════════════════════════════════════════════════
      h1("7. Kamera ESP32-CAM"),
      p("Na balonie zamontowana jest jedna kamera ESP32-CAM, zasilana z płytki RPi przez tranzystor MOSFET (low-side switch). Dzięki temu można ją włączyć i wyłączyć zdalnie w trakcie lotu."),
      p(""),

      h2("7.1 Pin zasilania kamery"),
      twoColTable([
        ["Zasilanie (gate MOSFET)", "GPIO17 (pin 11) — przez rezystor 100 Ω"],
        ["Pull-down bramki",        "10 kΩ do masy — kamera OFF gdy RPi się uruchamia"],
        ["VCC kamery",              "5 V (pin 2 lub 4)"],
        ["Status (RX)",             "GPIO4 (pin 7) — z GPIO1 (U0TX) kamery"],
      ]),
      p("Piny sa skonfigurowane w rpi-air/config.py jako ESPCAM_PWR_PIN = 17 oraz ESPCAM_STATUS_PIN = 4."),
      p(""),

      h2("7.2 Sterowanie z aplikacji Flutter"),
      bullet("W aplikacji Flutter otwórz panel ESP32-CAM"),
      bullet("Przyciski Włącz kamerę / Wyłącz kamerę — akcja wymaga potwierdzenia PIN-em"),
      bullet("Obok widać stan: WYŁĄCZONA / OK / NAGRYWA / BRAK SYGNAŁU"),
      p("Komenda trafia do backendu, stacja naziemna odbiera ją przez polling i wysyła przez LoRa do ESP32-S3. ESP32-S3 przekazuje ją kablem UART do RPi, a RPi steruje pinem MOSFET."),
      p(""),

      h2("7.3 Kiedy używać kamery ESP32-CAM"),
      twoColTable([
        ["Start i wznoszenie",   "Włącz kamerę przed wypuszczeniem balonu — rejestruje widok z boku"],
        ["Apogeum",              "Kamera ON — unikalne ujęcia na granicy stratosfery"],
        ["Opad ze spadochronem", "Kamera ON — widoczny spadochron i opadanie"],
        ["Oszczędzanie energii", "Wyłącz kamerę gdy napięcie baterii spada poniżej 3.8 V"],
        ["Nocna misja",          "Wyłącz ESP32-CAM całkowicie — nie ma IR, tylko marnuje prąd"],
      ]),
      p(""),

      h2("7.4 Oprogramowanie ESP32-CAM"),
      p("Kamera uruchamia kod PlatformIO (espcam/src/main.cpp)."),
      p(""),
      bullet("Nagrywa ciagle wideo MJPEG AVI na karte SD — 640x480 @ 10 fps"),
      bullet("Plik dzielony co 5 minut — przy utracie zasilania tracisz max 5 min, poprzednie pliki kompletne"),
      bullet("Pliki: /CAM/S{sesja}/0000.avi, 0001.avi, ... — nowy katalog sesji przy kazdym starcie"),
      bullet("Bez WiFi — status wysylany kablem UART TX (GPIO1) do RPi GPIO4 co 5 sekund"),
      bullet("LED heartbeat: 1x blink co 2s = nagrywa OK, 2x = blad SD, 3x = blad kamery, 5x = fatal"),
      p(""),
      p("Wgrywanie przez PlatformIO:"),
      code("pio run -t upload"),
      p(""),

      h2("7.5 Polaczenie statusu UART"),
      p("Kamera wysyla co 5 s przez GPIO1 (U0TX, 115200 baud) linie JSON z prefiksem $S:"),
      code('$S{"ok":1,"rec":1,"n":1234,"mb":28000}'),
      p("RPi odbiera przez pigpio bit-bang serial. Linie bez prefiksu $S (debug, boot) sa ignorowane — dzieki temu smietnik podczas resetu kamery nie psuje odczytu."),
      twoColTable([
        ["ESP32-CAM GPIO1 (TX)", "RPi GPIO4 (pin 7)"],
        ["ESP32-CAM GND",        "RPi GND (masa wspolna)"],
      ]),
      p("Napiecia zgodne: ESP32-CAM 3.3V = RPi5 3.3V — bezposrednie polaczenie bez level-shiftera."),
      p("Wymagana usluga pigpiod na RPi: sudo systemctl enable pigpiod && sudo systemctl start pigpiod"),
      p("UWAGA: pigpio nie wspiera Raspberry Pi 5 — na RPi 5 odczyt statusu trzeba przeniesc na lgpio albo sprzetowy UART. Nagrywanie kamery dziala niezaleznie od tego odczytu."),
      p(""),

      h2("7.6 Status w aplikacji Flutter"),
      twoColTable([
        ["OK (zielony)",             "Kamera zasilona i nagrywa poprawnie"],
        ["REC (czerwona kropka)",    "Aktywne nagrywanie — kropka na ikonie"],
        ["NO SIGNAL (pomaranczowy)", "Kamera zasilona ale brak danych z UART — sprawdz kabel"],
        ["OFF (szary)",              "Kamera wylaoczona (MOSFET zablokowany)"],
        ["Liczba klatek",            "Laczna liczba klatek nagranych w tej sesji"],
        ["Wolne MB",                 "Wolne miejsce na SD — ostrzezenie przy < 200 MB"],
      ]),
      p(""),

      h2("7.7 Karta SD i czas nagrywania"),
      twoColTable([
        ["Format wideo",   "MJPEG AVI, 640x480, 10 fps"],
        ["Rozmiar pliku",  "ok. 100 KB/s = 360 MB/h"],
        ["8h nagrania",    "ok. 2.8 GB — karta 32 GB z duzym zapasem"],
        ["Zalecana karta", "32 GB microSD (klasa 10 / U1)"],
      ]),
      p("Pliki AVI odtwarzasz bezposrednio w VLC i innych odtwarzaczach bez konwersji."),
      p(""),

      h2("7.8 Uwagi techniczne"),
      bullet("Wideo nagrane lokalnie na SD kamery — dane dostepne po fizycznym odzysku balonu"),
      bullet("Wlaczanie/wylaczanie zdalne przez aplikacje Flutter (MOSFET GPIO na RPi)"),
      bullet("Przy wlaczeniu kamera pobiera ok. 200-300 mA z szyny 5 V"),
      bullet("Kamera RPi (camera.py) to osobny uklad nagrywajacy 4K H.264 — nie mylec z ESP32-CAM"),
      p(""),

      // ══════════════════════════════════════════════════════════════
      // 8. PROCEDURA MISJI
      // ══════════════════════════════════════════════════════════════
      h1("8. Procedura misji krok po kroku"),

      h2("8.1 Przed misją (D-1)"),
      bullet("Sprawdz czy backend dziala: http://frog02.mikr.us:21124/api/telemetry/latest"),
      bullet("Naladuj baterie RPi i ESP32 na balonie"),
      bullet("Sprawdz karty SD: RPi = karta 64 GB (nagrywanie 4K, 8h), ESP32-CAM = karta 32 GB (MJPEG AVI, 8h)"),
      bullet("Sprawdz kabel UART statusu: GPIO1 ESP32-CAM → RPi GPIO4 (pin 7)"),
      bullet("Przetestuj polaczenie LoRa na krotkim dystansie"),
      bullet("Skalibruj tensometry HX711 z odwaznikiem referencyjnym"),
      p(""),

      h2("8.2 Dzień misji — start"),
      new Paragraph({
        numbering: { reference: "steps", level: 0 },
        children: [new TextRun({ text: "Uruchom backend na VPS (jeśli nie działa w tle)", font: "Arial", size: 22 })],
        spacing: { before: 40, after: 40 },
      }),
      new Paragraph({
        numbering: { reference: "steps", level: 0 },
        children: [new TextRun({ text: "Uruchom rpi-ground/main.py na stacji naziemnej", font: "Arial", size: 22 })],
        spacing: { before: 40, after: 40 },
      }),
      new Paragraph({
        numbering: { reference: "steps", level: 0 },
        children: [new TextRun({ text: "Uruchom rpi-air/main.py na RPi w balonie", font: "Arial", size: 22 })],
        spacing: { before: 40, after: 40 },
      }),
      new Paragraph({
        numbering: { reference: "steps", level: 0 },
        children: [new TextRun({ text: "Otwórz aplikację Flutter — sprawdź czy telemetria napływa", font: "Arial", size: 22 })],
        spacing: { before: 40, after: 40 },
      }),
      new Paragraph({
        numbering: { reference: "steps", level: 0 },
        children: [new TextRun({ text: "Zweryfikuj lock GPS (min. 4 satelity, gps_fix=true)", font: "Arial", size: 22 })],
        spacing: { before: 40, after: 40 },
      }),
      new Paragraph({
        numbering: { reference: "steps", level: 0 },
        children: [new TextRun({ text: "Sprawdź napięcie baterii w aplikacji (≥34.2V)", font: "Arial", size: 22 })],
        spacing: { before: 40, after: 40 },
      }),
      new Paragraph({
        numbering: { reference: "steps", level: 0 },
        children: [new TextRun({ text: "Uruchom nagrywanie wideo (przycisk w aplikacji)", font: "Arial", size: 22 })],
        spacing: { before: 40, after: 40 },
      }),
      new Paragraph({
        numbering: { reference: "steps", level: 0 },
        children: [new TextRun({ text: "Wypuść balon", font: "Arial", size: 22 })],
        spacing: { before: 40, after: 40 },
      }),
      p(""),

      h2("8.3 W trakcie lotu"),
      bullet("Monitoruj telemetrię w aplikacji Flutter"),
      bullet("Waypoints są zapisywane automatycznie co 5 minut — mapa pokazuje trasę"),
      bullet("Zdjecia LoRa co 20 pakietow telemetrii (ok. co 1-2 minuty)"),
      bullet("Wlacz kamery ESP32-CAM przez aplikacje wedlug potrzeb"),
      p(""),

      h2("8.4 Apogeum i otwarcie spadochronu"),
      p("Apogeum to najwyzszy punkt lotu — balon peka i uklad przechodzi w faze opadania. Tensometry HX711 rejestruja ten moment jako gwaltowny spadek sily liny."),
      p(""),
      bullet("Na wykresie tensometrow zobaczysz: wysoka sila (~850g) podczas wznoszenia → bliskie zeru przy peknięciu balonu → skok do ~350g gdy spadochron sie otworzy i zalapie powietrze"),
      bullet("Przy otwarciu spadochronu roll i pitch (BNO085) gwaltownie skacza, a potem stabilizuja sie — to potwierdzenie ze platforma zwisa pionowo"),
      bullet("Predkosc opadania (speed_kmh) po otwarciu spada do ok. 20-30 km/h — jesli pozostaje powyzej 60 km/h, spadochron mogl sie nie otworzyc prawidlowo"),
      bullet("Cisnienie (MS5611) zaczyna rosnac — monitoruj altitude_m: powinna maleć jednostajnie ok. 5-8 m/s"),
      bullet("Temperatura wzrasta wraz z opadaniem — powrot do normalnych wartosci po przekroczeniu troposfery"),
      p(""),
      p("Co robic przy otwarciu spadochronu:"),
      bullet("Sledz ostatni waypoint na mapie — wyznacza przewidywane miejsce ladowania"),
      bullet("Jesli RTL-SDR aktywny — sygnal HF bedzie slabnal wraz z opadaniem (mniejszy kat refleksji jonosfery)"),
      bullet("NIE wlaczaj buzzera przy otwarciu spadochronu — sonda jest jeszcze wysoko, buzzer tylko rozladuje baterie. Wlacz go dopiero gdy alt < 500 m I sonda jest juz w fazie opadania (po apogeum) — inaczej uruchomilby sie rowniez przy starcie, gdy balon wznosi sie przez te same 500 m."),
      p(""),

      h2("8.5 Odzysk balonu"),
      bullet("Ostatnia znana pozycja GPS jest widoczna na mapie w aplikacji"),
      bullet("Aktywuj buzzer przez aplikację, aby ułatwić lokalizację"),
      bullet("Po odzysku — zatrzymaj nagrywanie wideo przez aplikację"),
      bullet("Skopiuj pliki H.264 z /home/pi/stratosteam-video"),
      p(""),

      // ══════════════════════════════════════════════════════════════
      // 8. PARAMETRY RADIA
      // ══════════════════════════════════════════════════════════════
      h1("9. Parametry radia LoRa"),
      twoColTable([
        ["Częstotliwość",  "433.0 MHz"],
        ["Spreading Factor", "SF10"],
        ["Bandwidth",      "125 kHz"],
        ["Coding Rate",    "4/5"],
        ["Moc TX (uplink)", "17 dBm"],
        ["Rozmiar pakietu", "~200-300 bajtów JSON"],
        ["Zasięg (szacunkowo)", "do 50 km przy LOS"],
        ["Interwał wysyłki", "5 sekund"],
      ]),
      p("Parametry muszą być identyczne po obu stronach. Zmiana jednego wymaga aktualizacji obu config.py."),
      p(""),

      // ══════════════════════════════════════════════════════════════
      // 9. RAMKI KOMUNIKACYJNE
      // ══════════════════════════════════════════════════════════════
      h1("10. Ramki komunikacyjne"),
      p("Wszystkie ramki to JSON kodowany w jednej linii (line-delimited JSON), zakonczony znakeim nowej linii."),
      p(""),

      h2("10.1 ESP32-CAM → RPi (UART TX, 115200 baud)"),
      p("Kamera wysyla co 5 sekund przez GPIO1 (U0TX). Linia musi zaczynac sie od $S — RPi ignoruje pozostale linie (debug, boot messages)."),
      code('$S{"ok":1,"rec":1,"n":1234,"mb":28500}'),
      twoColTable([
        ["ok",  "1 = kamera i SD dzialaja poprawnie, 0 = blad"],
        ["rec", "1 = aktywne nagrywanie AVI, 0 = zatrzymane"],
        ["n",   "Laczna liczba klatek nagranych w biezacej sesji"],
        ["mb",  "Wolne miejsce na karcie SD w MB"],
      ]),
      p(""),

      h2("10.2 RPi → ESP32-S3 (UART, 115200 baud)"),
      p("RPi wysyla co 5 sekund dane ze wszystkich czujnikow. ESP32-S3 dolacza GPS i nadaje przez LoRa."),
      code('{"temp":21.3,"hum":45.1,"pres":1013.2,"p2":1012.8,"alt2":120.5,'),
      code('"roll":-1.2,"pit":0.8,"yaw":145.3,"ax":0.02,"ay":-0.01,"az":9.81,'),
      code('"vbat":4.12,"imA":320.0,"dsku":1.2,"dskf":58.3,'),
      code('"hfdb":-62.5,"sg0":820.0,"sg1":835.0,"sg2":810.0,"sg3":825.0,'),
      code('"ec":[1,1,1234,28500]}'),
      twoColTable([
        ["temp / hum / pres", "BME280: temperatura [C], wilgotnosc [%], cisnienie [hPa]"],
        ["p2 / alt2",         "MS5611: cisnienie [hPa], wysokosc bezwzgledna [m]"],
        ["roll / pit / yaw",  "BNO085: orientacja [stopnie]"],
        ["ax / ay / az",      "BNO085: przyspieszenie [m/s2]"],
        ["vbat / imA",        "INA219: napiecie baterii [V], prad [mA]"],
        ["dsku / dskf",       "Dysk RPi: zajete / wolne [GB]"],
        ["hfdb",              "RTL-SDR: sila sygnalu HF [dBFS] (opcjonalne)"],
        ["sg0-sg3",           "HX711: tensometry [g] (opcjonalne)"],
        ["ec",                "ESP32-CAM status: [ok, rec, klatki, wolneMB] (opcjonalne)"],
      ]),
      p(""),
      p("Przy przesylaniu zdjecia (chunk obrazu) RPi wysyla osobna ramke:"),
      code('{"type":"img","id":5,"seq":0,"tot":12,"data":"<base64>"}'),
      twoColTable([
        ["id",   "Identyfikator zdjecia (1-255, cykliczny)"],
        ["seq",  "Numer chunku (od 0)"],
        ["tot",  "Laczna liczba chunkow w zzdjeciu"],
        ["data", "Dane JPEG zakodowane w base64 (140 bajtow surowych = 187 znakow base64)"],
      ]),
      p(""),

      h2("10.3 ESP32-S3 → RPi (UART, 115200 baud, komendy z ziemi)"),
      p("ESP32-S3 przekazuje komendy odebrane przez LoRa do RPi:"),
      twoColTable([
        ['{"cmd":"photo"}',                    "Wykonaj zdjecie kamera RPi i wyslij przez LoRa"],
        ['{"cmd":"cam_rec","on":true}',         "Start/stop nagrywania H.264 kamera RPi"],
        ['{"cmd":"espcam_pwr","on":true}',      "Wlacz/wylacz zasilanie ESP32-CAM"],
        ['{"cmd":"exec","sh":"ls /"}',          "Wykonaj polecenie shell na RPi"],
        ['{"cmd":"rpi_power","on":false}',      "Zgraceful shutdown RPi"],
      ]),
      p(""),

      h2("10.4 LoRa: balon → ziemia (downlink, 433 MHz SF10 BW125)"),
      p("ESP32-S3 nadaje co 5 sekund. Gdy RPi dziala — pelna telemetria. Gdy RPi wylaczone — beacon GPS-only."),
      p("Pelna telemetria (RPi ON):"),
      code('{"src":"esp32","seq":123,"fix":true,"lat":52.2297,"lon":21.0122,'),
      code('"alt":15200.0,"sat":12,"vbat":4.05,"imA":318.0,"temp":-54.2,'),
      code('"hum":18.3,"pres":91.2,"p2":91.0,"alt2":15198.5,'),
      code('"roll":-2.1,"pit":1.4,"yaw":178.2,"ax":0.01,"ay":0.02,"az":9.80,'),
      code('"dsku":1.2,"dskf":58.3,"hfdb":-61.0,'),
      code('"sg0":420.0,"sg1":435.0,"sg2":410.0,"sg3":425.0,'),
      code('"ec":[1,1,1234,28500]}'),
      p("Beacon GPS-only (RPi OFF):"),
      code('{"src":"esp32","seq":124,"fix":true,"lat":52.2297,"lon":21.0122,'),
      code('"alt":15200.0,"sat":12,"vbat":3.85}'),
      p("Chunk obrazu (przesylanie zdjecia):"),
      code('{"type":"img","id":5,"seq":3,"tot":12,"data":"<base64>"}'),
      p("Wynik komendy exec:"),
      code('{"type":"exec_result","rc":0,"out":"plik1.h264\\nplik2.h264","err":""}'),
      p(""),

      h2("10.5 LoRa: ziemia → balon (uplink, 433 MHz SF10 BW125)"),
      p("Stacja naziemna wysyla komende w oknie po odebraniu pakietu. Maksymalnie jedna komenda na pakiet telemetrii."),
      twoColTable([
        ['{"cmd":1,"buzzer":true,"led_r":255,"led_g":0,"led_b":0}', "Buzzer ON + LED czerwony"],
        ['{"cmd":"rpi_power","on":false}',                           "Shutdown RPi na balonie"],
        ['{"cmd":"photo"}',                                          "Zadanie zdjecia z kamery RPi"],
        ['{"cmd":"cam_rec","on":true}',                              "Start nagrywania H.264"],
        ['{"cmd":"espcam_pwr","on":true}',                           "Wlacz zasilanie ESP32-CAM"],
        ['{"cmd":"exec","sh":"df -h"}',                              "Wykonaj polecenie shell"],
      ]),
      p(""),

      // ══════════════════════════════════════════════════════════════
      // 10. DIAGNOSTYKA
      // ══════════════════════════════════════════════════════════════
      h1("11. Diagnostyka i typowe problemy"),

      h2("11.1 Brak telemetrii w aplikacji"),
      twoColTable([
        ["Backend nie działa",             "Sprawdź: http://frog02.mikr.us:21124/api/telemetry/latest"],
        ["rpi-ground nie odbiera pakietów", "Sprawdź log: /var/log/stratosteam-ground.log"],
        ["Zły klucz API",                  "BACKEND_API_KEY w rpi-ground/config.py musi zgadzać się z backendem"],
        ["Zła konfiguracja LoRa",          "LORA_FREQ/SF/BW muszą być identyczne w rpi-air i rpi-ground"],
      ]),
      p(""),

      h2("11.2 Brak GPS fix"),
      bullet("Daj ESP32 kilka minut na zimny start GPS (TTFF)"),
      bullet("Upewnij się że antena GPS ma widok nieba"),
      bullet("Sprawdź log rpi-air: powinno być satellites >= 4"),
      p(""),

      h2("11.3 Logi systemowe"),
      twoColTable([
        ["rpi-air",    "/var/log/stratosteam-air.log"],
        ["rpi-ground", "/var/log/stratosteam-ground.log"],
        ["Backend",    "stdout uvicorn (lub screen -r backend)"],
      ]),
      p(""),

      h2("11.4 Restart backendu"),
      code("pkill -f uvicorn"),
      code("cd ~/stratosteam-backend && uvicorn main:app --host 0.0.0.0 --port 21124"),
      p("Jeśli pkill nie działa (brak uprawnień), sprawdź PID: cat /proc/*/cmdline | tr '\\0' ' ' | grep uvicorn"),
      p(""),

      // ══════════════════════════════════════════════════════════════
      // 10. API BACKENDU
      // ══════════════════════════════════════════════════════════════
      h1("12. Kluczowe endpointy API"),
      twoColTable([
        ["GET  /api/telemetry/latest",  "Ostatni rekord telemetrii"],
        ["GET  /api/telemetry",         "Historia telemetrii (paginacja)"],
        ["POST /api/telemetry",         "Wstaw nowy rekord (rpi-ground)"],
        ["GET  /api/waypoints",         "Lista waypoints (co 5 min)"],
        ["GET  /api/camera/latest",     "Ostatnie zdjęcie (base64 JPEG)"],
        ["POST /api/camera/chunk",      "Wstaw chunk zdjęcia (rpi-ground)"],
        ["GET  /api/camera/storage",    "Stan dysku na balonie"],
        ["POST /api/commands",          "Wyślij komendę (buzzer, LED)"],
        ["POST /api/rpi-power",         "Sterowanie zasilaniem RPi"],
        ["POST /api/hf/measurement",    "Pomiar HF SDR"],
        ["GET  /api/hf/measurements",   "Historia pomiarów HF"],
        ["GET  /docs",                  "Interaktywna dokumentacja Swagger"],
      ]),
      p("Wszystkie endpointy zapisu wymagają nagłówka X-API-Key."),
      p(""),

    ],
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("D:\\StratoSTEAM\\Instrukcja_StratoSTEAM.docx", buf);
  console.log("OK: Instrukcja_StratoSTEAM.docx");
});
