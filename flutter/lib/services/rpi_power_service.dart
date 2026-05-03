import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'settings_service.dart';

class RpiPowerService extends ChangeNotifier {
  final SettingsService _settings;

  bool rpiRunning = false;
  bool pending = false;
  bool? pendingOn;
  bool loading = false;

  RpiPowerService(this._settings) {
    _poll();
    Timer.periodic(const Duration(seconds: 3), (_) => _poll());
  }

  Future<void> _poll() async {
    try {
      final r = await http
          .get(Uri.parse('${_settings.serverUrl}/api/rpi_power/state'))
          .timeout(const Duration(seconds: 3));
      if (r.statusCode == 200) {
        final j = jsonDecode(r.body);
        rpiRunning = j['rpi_running'] as bool;
        pending    = j['pending']     as bool;
        pendingOn  = j['pending_on']  as bool?;
        notifyListeners();
      }
    } catch (_) {}
  }

  Future<void> setPower(bool on) async {
    loading = true;
    notifyListeners();
    try {
      await http.post(
        Uri.parse('${_settings.serverUrl}/api/rpi_power/set'),
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': _settings.apiKey,
        },
        body: jsonEncode({'on': on}),
      ).timeout(const Duration(seconds: 5));
      await _poll();
    } catch (_) {
    } finally {
      loading = false;
      notifyListeners();
    }
  }
}
