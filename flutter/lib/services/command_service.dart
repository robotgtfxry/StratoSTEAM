import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'settings_service.dart';

class CommandService extends ChangeNotifier {
  final SettingsService _settings;

  bool buzzer = false;
  int ledR = 0;
  int ledG = 0;
  int ledB = 0;
  double brightness = 1.0;
  bool loading = false;
  bool? lastSendOk;

  CommandService(this._settings);

  Future<void> send() async {
    loading = true;
    notifyListeners();
    try {
      final r = await http.post(
        Uri.parse('${_settings.serverUrl}/api/commands/send'),
        headers: {
          'Content-Type': 'application/json',
          'X-API-Key': _settings.apiKey,
        },
        body: jsonEncode({
          'buzzer': buzzer,
          'led_r': ledR,
          'led_g': ledG,
          'led_b': ledB,
        }),
      ).timeout(const Duration(seconds: 5));
      lastSendOk = r.statusCode == 202;
    } catch (_) {
      lastSendOk = false;
    } finally {
      loading = false;
      notifyListeners();
    }
  }

  void setBuzzer(bool v) {
    buzzer = v;
    notifyListeners();
  }

  void setColor(int r, int g, int b) {
    ledR = r;
    ledG = g;
    ledB = b;
    notifyListeners();
  }

  void setBrightness(double v) {
    brightness = v;
    // scale current colour
    notifyListeners();
  }
}
