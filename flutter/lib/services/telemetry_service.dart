import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import '../models/telemetry.dart';
import 'settings_service.dart';

class TelemetryService extends ChangeNotifier {
  final SettingsService _settings;

  final List<Telemetry> history = [];
  Telemetry? latest;
  bool connected = false;

  // ── Auto-buzzer ───────────────────────────────────────────────────────────
  /// Callback wywoływany raz gdy spełniony warunek: alt < 500 m i faza opadania.
  /// Podpięty w main.dart do CommandService.sendBuzzerAuto().
  void Function()? onAutoBuzzer;

  double _peakAlt = 0.0;
  bool _autoBuzzerFired = false;

  /// Najwyższa zarejestrowana wysokość w tej sesji.
  double get peakAlt => _peakAlt;

  /// True gdy balon przekroczył apogeum i opada (peakAlt > 1000 m i climbRate < 0).
  bool get isDescending =>
      _peakAlt > 1000.0 && (climbRate ?? 0) < 0;

  WebSocketChannel? _ws;
  StreamSubscription? _sub;
  bool _disposed = false;

  TelemetryService(this._settings) {
    _connect();
    _fetchHistory();
  }

  Future<void> _fetchHistory() async {
    try {
      final res = await http.get(
        Uri.parse('${_settings.serverUrl}/api/telemetry?limit=200'),
      );
      if (res.statusCode == 200) {
        final list = jsonDecode(res.body) as List;
        history
          ..clear()
          ..addAll(list.map((e) => Telemetry.fromJson(e)).toList().reversed);
        if (history.isNotEmpty) latest = history.last;
        notifyListeners();
      }
    } catch (_) {}
  }

  void _connect() {
    if (_disposed) return;
    try {
      _sub?.cancel();
      _ws?.sink.close();
      _ws = WebSocketChannel.connect(Uri.parse(_settings.wsUrl));
      connected = true;
      notifyListeners();
      _sub = _ws!.stream.listen(
        (raw) {
          final j = jsonDecode(raw as String) as Map<String, dynamic>;
          if (j.containsKey('ping')) return;
          final t = Telemetry.fromJson(j);
          history.add(t);
          if (history.length > 500) history.removeAt(0);
          latest = t;

          // ── Śledź peak altitude ──────────────────────────────────────────
          if (t.alt != null && t.alt! > _peakAlt) _peakAlt = t.alt!;

          // ── Auto-buzzer: alt < 500 m, faza opadania, jeszcze nie wysłano ─
          if (!_autoBuzzerFired &&
              t.alt != null &&
              t.alt! < 500.0 &&
              isDescending) {
            _autoBuzzerFired = true;
            onAutoBuzzer?.call();
          }

          notifyListeners();
        },
        onDone: () {
          connected = false;
          notifyListeners();
          if (!_disposed) Future.delayed(const Duration(seconds: 5), _connect);
        },
        onError: (_) {
          connected = false;
          notifyListeners();
          if (!_disposed) Future.delayed(const Duration(seconds: 5), _connect);
        },
      );
    } catch (_) {
      connected = false;
      notifyListeners();
      if (!_disposed) Future.delayed(const Duration(seconds: 5), _connect);
    }
  }

  /// Vertical speed in m/s (positive = ascending, negative = descending).
  /// Computed from the last two history entries with valid altitude.
  double? get climbRate {
    if (history.length < 2) return null;
    final a = history[history.length - 2];
    final b = history[history.length - 1];
    if (a.alt == null || b.alt == null) return null;
    final dt = (b.ts - a.ts).toDouble();
    if (dt <= 0) return null;
    return (b.alt! - a.alt!) / dt;
  }

  /// Called after settings change — reconnects and reloads history.
  void reconnect() {
    history.clear();
    latest = null;
    _connect();
    _fetchHistory();
  }

  @override
  void dispose() {
    _disposed = true;
    _sub?.cancel();
    _ws?.sink.close();
    super.dispose();
  }
}
