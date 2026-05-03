import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'settings_service.dart';

enum MsgType { input, ok, error, info, system }

class TerminalMsg {
  final String text;
  final MsgType type;
  final DateTime time;
  TerminalMsg(this.text, this.type) : time = DateTime.now();
}

class TerminalService extends ChangeNotifier {
  final SettingsService _settings;
  final List<TerminalMsg> log = [];

  TerminalService(this._settings) {
    _sys('StratoSTEAM terminal — wpisz "help" po listę komend');
  }

  // ── Public API ─────────────────────────────────────────────────────────────
  Future<void> run(String raw) async {
    final input = raw.trim();
    if (input.isEmpty) return;
    _add('> $input', MsgType.input);

    final parts = input.toLowerCase().split(RegExp(r'\s+'));
    final cmd   = parts[0];

    switch (cmd) {
      case 'help':
        _printHelp();
      case 'clear':
        log.clear();
        notifyListeners();
      case 'buzzer':
        await _cmdBuzzer(parts);
      case 'led':
        await _cmdLed(parts, raw.trim());
      case 'rpi':
        await _cmdRpi(parts);
      case 'aprs':
        await _cmdAprs(parts);
      default:
        // Wszystko inne → wykonaj na RPi przez LoRa
        await _cmdExec(input);
    }
  }

  // ── Komendy ─────────────────────────────────────────────────────────────────
  Future<void> _cmdBuzzer(List<String> p) async {
    if (p.length < 2 || (p[1] != 'on' && p[1] != 'off')) {
      _err('Użycie: buzzer on|off');
      return;
    }
    final on = p[1] == 'on';
    final ok = await _post('/api/commands/send', {
      'buzzer': on, 'led_r': 0, 'led_g': 0, 'led_b': 0,
    });
    ok ? _ok('Buzzer ${on ? "ON" : "OFF"} — w kolejce') : _err('Błąd wysyłania');
  }

  Future<void> _cmdLed(List<String> p, String raw) async {
    int r = 0, g = 0, b = 0;
    // led #rrggbb
    if (p.length == 2 && p[1].startsWith('#')) {
      final hex = p[1].replaceFirst('#', '');
      if (hex.length != 6) { _err('Zły hex, oczekiwano #rrggbb'); return; }
      r = int.parse(hex.substring(0, 2), radix: 16);
      g = int.parse(hex.substring(2, 4), radix: 16);
      b = int.parse(hex.substring(4, 6), radix: 16);
    }
    // led r g b
    else if (p.length == 4) {
      r = int.tryParse(p[1]) ?? -1;
      g = int.tryParse(p[2]) ?? -1;
      b = int.tryParse(p[3]) ?? -1;
      if ([r, g, b].any((v) => v < 0 || v > 255)) {
        _err('Wartości RGB muszą być 0-255');
        return;
      }
    } else {
      _err('Użycie: led <r> <g> <b>  lub  led #rrggbb');
      return;
    }
    final ok = await _post('/api/commands/send', {
      'buzzer': false, 'led_r': r, 'led_g': g, 'led_b': b,
    });
    ok ? _ok('LED rgb($r,$g,$b) — w kolejce') : _err('Błąd wysyłania');
  }

  Future<void> _cmdRpi(List<String> p) async {
    if (p.length < 2 || (p[1] != 'on' && p[1] != 'off')) {
      _err('Użycie: rpi on|off');
      return;
    }
    final on = p[1] == 'on';
    final ok = await _post('/api/rpi_power/set', {'on': on});
    ok ? _ok('RPi ${on ? "ON" : "OFF"} — komenda wysłana do ESP32') : _err('Błąd wysyłania');
  }

  Future<void> _cmdAprs(List<String> p) async {
    if (p.length < 2 || (p[1] != 'on' && p[1] != 'off')) {
      _err('Użycie: aprs on|off');
      return;
    }
    final on = p[1] == 'on';
    final ok = await _post('/api/commands/send', {
      'buzzer': false, 'led_r': 0, 'led_g': 0, 'led_b': 0,
      'aprs': on,
    });
    ok ? _ok('APRS ${on ? "ON" : "OFF"} — w kolejce') : _err('Błąd wysyłania');
  }

  Future<void> _cmdExec(String sh) async {
    _add('  → wysyłam do RPi...', MsgType.info);
    final sent = await _post('/api/exec/send', {'sh': sh});
    if (!sent) { _err('Błąd wysyłania komendy'); return; }

    // Poll for result — max 40s (rpi-air cycle ~5s + LoRa propagation)
    _add('  ⏳ czekam na wynik (~5-15s)...', MsgType.info);
    final deadline = DateTime.now().add(const Duration(seconds: 40));
    while (DateTime.now().isBefore(deadline)) {
      await Future.delayed(const Duration(seconds: 2));
      try {
        final r = await http
            .get(Uri.parse('${_settings.serverUrl}/api/exec/result'))
            .timeout(const Duration(seconds: 4));
        if (r.statusCode == 200) {
          final j = jsonDecode(r.body);
          if (j['ready'] == true) {
            final rc  = j['rc'] as int;
            final out = (j['out'] as String).trim();
            final err = (j['err'] as String).trim();
            if (out.isNotEmpty) {
              for (final line in out.split('\n')) {
                _add(line, MsgType.ok);
              }
            }
            if (err.isNotEmpty) {
              for (final line in err.split('\n')) {
                _add(line, MsgType.error);
              }
            }
            _add('  [rc=$rc]', rc == 0 ? MsgType.info : MsgType.error);
            return;
          }
        }
      } catch (_) {}
    }
    _err('Timeout — brak odpowiedzi od RPi (>40s)');
  }

  // ── HTTP helper ─────────────────────────────────────────────────────────────
  Future<bool> _post(String path, Map<String, dynamic> body) async {
    try {
      final r = await http.post(
        Uri.parse('${_settings.serverUrl}$path'),
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': _settings.apiKey,
        },
        body: jsonEncode(body),
      ).timeout(const Duration(seconds: 6));
      return r.statusCode < 300;
    } catch (e) {
      _err('Połączenie: $e');
      return false;
    }
  }

  // ── Log helpers ─────────────────────────────────────────────────────────────
  void _ok(String t)  => _add(t, MsgType.ok);
  void _err(String t) => _add(t, MsgType.error);
  void _sys(String t) => _add(t, MsgType.system);

  void _add(String text, MsgType type) {
    log.add(TerminalMsg(text, type));
    if (log.length > 300) log.removeAt(0);
    notifyListeners();
  }

  void _printHelp() {
    const lines = [
      'Komendy wbudowane:',
      '  buzzer on|off          — buzzer na balonie',
      '  led <r> <g> <b>        — LED RGB (0-255)',
      '  led #rrggbb            — LED kolor hex',
      '  rpi on|off             — zasilanie RPi (przez ESP32)',
      '  aprs on|off            — nośna APRS 144.800 MHz',
      '  clear / help',
      '',
      'Dowolna inna komenda → wykonywana na RPi przez bash:',
      '  ls /var/log',
      '  cat /proc/uptime',
      '  systemctl status stratosteam-air',
      '  df -h',
      '',
      'Uwaga: wynik obcięty do ~160 znaków, opóźnienie ~5-15s.',
      'Komendy interaktywne (nano, top) nie działają.',
    ];
    for (final l in lines) _add(l, MsgType.info);
  }
}
