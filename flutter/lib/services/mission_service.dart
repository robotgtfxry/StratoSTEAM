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

  Timer? _timer;
  bool _disposed = false;
  bool _busy = false;

  MissionService(this._settings) {
    _poll();
    _timer = Timer.periodic(const Duration(seconds: 3), (_) => _poll());
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
