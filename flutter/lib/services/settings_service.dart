import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class SettingsService extends ChangeNotifier {
  static const _keyServerUrl   = 'server_url';
  static const _keyApiKey      = 'api_key';
  static const _keyCallsign    = 'callsign';
  static const _keyMinVoltage  = 'min_voltage';
  static const _keyMinSats     = 'min_sats';
  static const _keyLoraFreq    = 'lora_freq';
  static const _keyLoraSf      = 'lora_sf';

  String serverUrl  = 'http://frog02.mikr.us:21124';
  String apiKey     = 'change-me-in-production';
  String callsign   = 'SP0STR-11';
  double minVoltage = 3.5;
  int    minSats    = 4;
  double loraFreq   = 433.0;
  int    loraSf     = 10;

  String get wsUrl => serverUrl
      .replaceFirst('https://', 'wss://')
      .replaceFirst('http://', 'ws://') + '/ws/telemetry';

  Future<void> load() async {
    final p = await SharedPreferences.getInstance();
    serverUrl  = p.getString(_keyServerUrl)  ?? serverUrl;
    apiKey     = p.getString(_keyApiKey)     ?? apiKey;
    callsign   = p.getString(_keyCallsign)   ?? callsign;
    minVoltage = p.getDouble(_keyMinVoltage) ?? minVoltage;
    minSats    = p.getInt(_keyMinSats)       ?? minSats;
    loraFreq   = p.getDouble(_keyLoraFreq)   ?? loraFreq;
    loraSf     = p.getInt(_keyLoraSf)        ?? loraSf;
    notifyListeners();
  }

  Future<void> save({
    String? serverUrl,
    String? apiKey,
    String? callsign,
    double? minVoltage,
    int?    minSats,
    double? loraFreq,
    int?    loraSf,
  }) async {
    final p = await SharedPreferences.getInstance();
    if (serverUrl  != null) { this.serverUrl  = serverUrl;  await p.setString(_keyServerUrl, serverUrl); }
    if (apiKey     != null) { this.apiKey     = apiKey;     await p.setString(_keyApiKey, apiKey); }
    if (callsign   != null) { this.callsign   = callsign;   await p.setString(_keyCallsign, callsign); }
    if (minVoltage != null) { this.minVoltage = minVoltage; await p.setDouble(_keyMinVoltage, minVoltage); }
    if (minSats    != null) { this.minSats    = minSats;    await p.setInt(_keyMinSats, minSats); }
    if (loraFreq   != null) { this.loraFreq   = loraFreq;   await p.setDouble(_keyLoraFreq, loraFreq); }
    if (loraSf     != null) { this.loraSf     = loraSf;     await p.setInt(_keyLoraSf, loraSf); }
    notifyListeners();
  }

  Future<void> reset() async {
    final p = await SharedPreferences.getInstance();
    await p.clear();
    serverUrl  = 'http://frog02.mikr.us:21124';
    apiKey     = 'change-me-in-production';
    callsign   = 'SP0STR-11';
    minVoltage = 3.5;
    minSats    = 4;
    loraFreq   = 433.0;
    loraSf     = 10;
    notifyListeners();
  }
}
