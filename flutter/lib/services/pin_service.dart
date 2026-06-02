import 'package:flutter/foundation.dart';
import 'settings_service.dart';

class PinService extends ChangeNotifier {
  final SettingsService _settings;
  bool _authenticated = false;

  PinService(this._settings);

  bool get authenticated => _authenticated;

  bool verify(String input) {
    if (input == _settings.pin) {
      _authenticated = true;
      notifyListeners();
      return true;
    }
    return false;
  }
}
