import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'settings_service.dart';

class HfMeasurement {
  final double ts;
  final double alt;
  final double dbfs;
  const HfMeasurement({required this.ts, required this.alt, required this.dbfs});
}

class HfService extends ChangeNotifier {
  final SettingsService _settings;

  bool hwActive = false;
  int hwFreqHz = 0;
  String pendingAction = 'stop';
  int pendingFreqHz = 7100000;
  bool _loading = false;
  List<HfMeasurement> measurements = [];

  bool get loading => _loading;

  static const List<Map<String, dynamic>> bands = [
    {'label': '40m  7.1 MHz',  'freq': 7100000},
    {'label': '20m 14.2 MHz',  'freq': 14200000},
    {'label': '17m 18.1 MHz',  'freq': 18100000},
    {'label': '15m 21.2 MHz',  'freq': 21200000},
    {'label': '10m 28.5 MHz',  'freq': 28500000},
  ];

  HfService(this._settings) {
    _pollState();
    _pollMeasurements();
    Timer.periodic(const Duration(seconds: 2), (_) => _pollState());
    Timer.periodic(const Duration(seconds: 10), (_) => _pollMeasurements());
  }

  Future<void> _pollState() async {
    try {
      final r = await http
          .get(Uri.parse('${_settings.serverUrl}/api/hf/state'))
          .timeout(const Duration(seconds: 3));
      if (r.statusCode == 200) {
        final j = jsonDecode(r.body);
        hwActive      = j['hw_status']['active'] as bool;
        hwFreqHz      = j['hw_status']['freq_hz'] as int;
        pendingAction = j['command']['action'] as String;
        pendingFreqHz = j['command']['freq_hz'] as int;
        notifyListeners();
      }
    } catch (_) {}
  }

  Future<void> _pollMeasurements() async {
    try {
      final r = await http
          .get(Uri.parse('${_settings.serverUrl}/api/hf/measurements'))
          .timeout(const Duration(seconds: 5));
      if (r.statusCode == 200) {
        final list = jsonDecode(r.body) as List<dynamic>;
        measurements = list.map((e) => HfMeasurement(
          ts:   (e['ts']   as num).toDouble(),
          alt:  (e['alt']  as num).toDouble(),
          dbfs: (e['dbfs'] as num).toDouble(),
        )).toList();
        notifyListeners();
      }
    } catch (_) {}
  }

  Future<void> sendCommand(String action, int freqHz) async {
    _loading = true;
    notifyListeners();
    try {
      await http.post(
        Uri.parse('${_settings.serverUrl}/api/hf/control'),
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': _settings.apiKey,
        },
        body: jsonEncode({'action': action, 'freq_hz': freqHz}),
      ).timeout(const Duration(seconds: 5));
      await _pollState();
    } catch (_) {
    } finally {
      _loading = false;
      notifyListeners();
    }
  }
}
