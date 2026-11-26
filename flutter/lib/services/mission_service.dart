import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'settings_service.dart';

/// Stan misji policzony na stacji naziemnej.
class MissionInfo {
  final String phase;
  final double? elapsed; // sekundy od startu w chwili pobrania
  final double? alt, vs, maxAlt;
  final String? src;
  final bool auto; // automatyczne zdjęcia
  final String? cs; // znak, którym sonda nadaje (z beaconu)
  final double? tcpu; // temperatura procesora RPi balonu
  final double? rxAge; // ile sekund temu stacja odebrała pakiet z balonu
  final double age; // ile sekund temu stacja odezwała się do serwera
  final List<(double, String)> events;
  final DateTime fetchedAt;

  MissionInfo._({
    required this.phase,
    required this.elapsed,
    required this.alt,
    required this.vs,
    required this.maxAlt,
    required this.src,
    required this.auto,
    required this.cs,
    required this.tcpu,
    required this.rxAge,
    required this.age,
    required this.events,
    required this.fetchedAt,
  });

  static double? _num(dynamic v) => v is num ? v.toDouble() : null;

  factory MissionInfo.fromJson(Map<String, dynamic> j) => MissionInfo._(
        phase: j['phase'] as String,
        elapsed: _num(j['elapsed']),
        alt: _num(j['alt']),
        vs: _num(j['vs']),
        maxAlt: _num(j['max_alt']),
        src: j['src'] as String?,
        auto: j['auto'] == true,
        cs: j['cs'] as String?,
        tcpu: _num(j['tcpu']),
        rxAge: _num(j['rx_age']),
        age: _num(j['age']) ?? 0,
        events: [
          for (final e in (j['events'] as List? ?? const []))
            if (e is List && e.length == 2 && e[0] is num)
              ((e[0] as num).toDouble(), e[1].toString())
        ],
        fetchedAt: DateTime.now(),
      );

  double get _since =>
      DateTime.now().difference(fetchedAt).inMilliseconds / 1000.0;

  bool get prep => phase == 'PRZYGOTOWANIE';

  /// T+ teraz (zegar tyka także między odczytami z serwera).
  double? get tPlus => elapsed == null ? null : elapsed! + _since;

  /// Sekundy od ostatniej wiadomości ze stacji / od ostatniego pakietu z balonu.
  double get stationAge => age + _since;
  double? get packetAge => rxAge == null ? null : rxAge! + _since;

  bool get stationOnline => stationAge < 30;
}

class MissionService extends ChangeNotifier {
  final SettingsService _settings;

  MissionInfo? info;

  /// Znak ustawiony w aplikacji (może jeszcze czekać na potwierdzenie z sondy).
  String? desiredCallsign;

  static final callsignRe = RegExp(r'^[A-Z0-9/]{3,10}(-[0-9]{1,2})?$');

  /// Wysyła nowy znak sondy przez serwer i stację. Zwraca komunikat błędu albo null.
  Future<String?> setCallsign(String cs) async {
    cs = cs.trim().toUpperCase();
    if (!callsignRe.hasMatch(cs)) return 'Zły znak (np. SP8DEV-1)';
    try {
      final r = await http
          .post(Uri.parse('${_settings.serverUrl}/api/callsign'),
              headers: {'Content-Type': 'application/json', 'X-API-Key': _settings.apiKey},
              body: jsonEncode({'cs': cs}))
          .timeout(const Duration(seconds: 5));
      if (r.statusCode != 202) return 'Serwer odpowiedział ${r.statusCode}';
      desiredCallsign = cs;
      notifyListeners();
      return null;
    } catch (_) {
      return 'Brak połączenia z serwerem';
    }
  }

  Future<void> _pollCallsign() async {
    try {
      final r = await http
          .get(Uri.parse('${_settings.serverUrl}/api/callsign'),
              headers: {'X-API-Key': _settings.apiKey})
          .timeout(const Duration(seconds: 5));
      if (r.statusCode == 200) {
        final d = jsonDecode(r.body)['desired'] as String?;
        if (d != desiredCallsign) {
          desiredCallsign = d;
          if (!_disposed) notifyListeners();
        }
      }
    } catch (_) {}
  }

  Timer? _timer;
  bool _disposed = false;
  bool _busy = false;

  MissionService(this._settings) {
    _poll();
    _pollCallsign();
    _timer = Timer.periodic(const Duration(seconds: 3), (t) {
      _poll();
      if (t.tick % 5 == 0) _pollCallsign();
    });
  }

  Future<void> _poll() async {
    if (_disposed || _busy) return;
    _busy = true;
    try {
      final res = await http
          .get(Uri.parse('${_settings.serverUrl}/api/mission'))
          .timeout(const Duration(seconds: 5));
      if (res.statusCode == 200) {
        final m = jsonDecode(utf8.decode(res.bodyBytes))['mission'];
        info = m == null
            ? null
            : MissionInfo.fromJson(m as Map<String, dynamic>);
        if (!_disposed) notifyListeners();
      }
    } catch (_) {
      // brak sieci: zostaje ostatni stan, a karta pokazuje jego wiek
    } finally {
      _busy = false;
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    super.dispose();
  }
}
