import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'settings_service.dart';

/// Sterowanie zasilaniem jedynej kamery ESP32-CAM na balonie.
class EspCamService extends ChangeNotifier {
  final SettingsService _settings;

  bool state = false;
  bool loading = false;

  EspCamService(this._settings) {
    _fetchState();
    Timer.periodic(const Duration(seconds: 5), (_) => _fetchState());
  }

  Future<void> _fetchState() async {
    try {
      final r = await http
          .get(Uri.parse('${_settings.serverUrl}/api/espcam/power/state'))
          .timeout(const Duration(seconds: 3));
      if (r.statusCode == 200) {
        final j = jsonDecode(r.body);
        state = j['on'] == true;
        notifyListeners();
      }
    } catch (_) {}
  }

  Future<void> setPower(bool on) async {
    loading = true;
    notifyListeners();
    try {
      await http.post(
        Uri.parse('${_settings.serverUrl}/api/espcam/power'),
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': _settings.apiKey,
        },
        body: jsonEncode({'on': on}),
      ).timeout(const Duration(seconds: 5));
      state = on; // Optimistic update
      notifyListeners();
    } catch (_) {
    } finally {
      loading = false;
      notifyListeners();
    }
  }
}
