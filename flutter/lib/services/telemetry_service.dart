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
