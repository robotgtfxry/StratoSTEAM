import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'settings_service.dart';

class EspCamService extends ChangeNotifier {
  final SettingsService _settings;

  List<bool> state = [false, false, false, false];
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
        final list = (j['state'] as List).cast<bool>();
        state = list;
        notifyListeners();
      }
    } catch (_) {}
  }

  Future<void> setPower(int cam, bool on) async {
    loading = true;
    notifyListeners();
    try {
      await http.post(
        Uri.parse('${_settings.serverUrl}/api/espcam/power'),
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': _settings.apiKey,
        },
        body: jsonEncode({'cam': cam, 'on': on}),
      ).timeout(const Duration(seconds: 5));
      // Optimistic update
      if (cam == -1) {
        state = List.filled(4, on);
      } else if (cam >= 0 && cam < 4) {
        state = List.from(state)..[cam] = on;
      }
      notifyListeners();
    } catch (_) {
    } finally {
      loading = false;
      notifyListeners();
    }
  }
}
