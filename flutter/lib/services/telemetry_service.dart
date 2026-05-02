import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import '../models/telemetry.dart';

class TelemetryService extends ChangeNotifier {
  static const _baseUrl = 'http://localhost:8000'; // change for production
  static const _wsUrl  = 'ws://localhost:8000/ws/telemetry';

  final List<Telemetry> history = [];
  Telemetry? latest;
  bool connected = false;

  WebSocketChannel? _ws;
  StreamSubscription? _sub;

  TelemetryService() {
    _connect();
    _fetchHistory();
  }

  Future<void> _fetchHistory() async {
    try {
      final res = await http.get(Uri.parse('$_baseUrl/api/telemetry?limit=200'));
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
    try {
      _ws = WebSocketChannel.connect(Uri.parse(_wsUrl));
      connected = true;
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
          Future.delayed(const Duration(seconds: 5), _connect);
        },
        onError: (_) {
          connected = false;
          notifyListeners();
          Future.delayed(const Duration(seconds: 5), _connect);
        },
      );
    } catch (_) {
      connected = false;
      Future.delayed(const Duration(seconds: 5), _connect);
    }
  }

  @override
  void dispose() {
    _sub?.cancel();
    _ws?.sink.close();
    super.dispose();
  }
}
