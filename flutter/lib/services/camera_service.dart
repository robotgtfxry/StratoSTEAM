import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'settings_service.dart';

class CameraService extends ChangeNotifier {
  final SettingsService _settings;

  bool recording = true;   // kamera startuje z nagrywaniem
  bool photoLoading = false;
  bool? lastPhotoOk;
  bool recLoading = false;

  Uint8List? latestPhoto;
  DateTime? latestPhotoTs;
  int _latestId = -1;

  // Disk usage
  double? diskUsedGb;
  double? diskFreeGb;
  double? diskTotalGb;
  double? diskUsedPct;

  Timer? _pollTimer;
  Timer? _storagePollTimer;

  CameraService(this._settings) {
    _pollTimer = Timer.periodic(const Duration(seconds: 3), (_) => _fetchLatest());
    _storagePollTimer = Timer.periodic(const Duration(seconds: 10), (_) => _fetchStorage());
  }

  Map<String, String> get _headers => {
        'Content-Type': 'application/json',
        'X-API-Key': _settings.apiKey,
      };

  /// Wyślij żądanie zdjęcia do backendu.
  Future<void> requestPhoto() async {
    photoLoading = true;
    lastPhotoOk = null;
    notifyListeners();
    try {
      final r = await http
          .post(
            Uri.parse('${_settings.serverUrl}/api/camera/photo'),
            headers: _headers,
          )
          .timeout(const Duration(seconds: 5));
      lastPhotoOk = r.statusCode == 202;
    } catch (_) {
      lastPhotoOk = false;
    } finally {
      photoLoading = false;
      notifyListeners();
    }
  }

  /// Włącz / wyłącz nagrywanie.
  Future<void> setRecording(bool on) async {
    recLoading = true;
    notifyListeners();
    try {
      await http
          .post(
            Uri.parse('${_settings.serverUrl}/api/camera/record'),
            headers: _headers,
            body: jsonEncode({'on': on}),
          )
          .timeout(const Duration(seconds: 5));
      recording = on;
    } catch (_) {}
    recLoading = false;
    notifyListeners();
  }

  Future<void> _fetchStorage() async {
    try {
      final r = await http
          .get(
            Uri.parse('${_settings.serverUrl}/api/camera/storage'),
            headers: {'X-API-Key': _settings.apiKey},
          )
          .timeout(const Duration(seconds: 3));
      if (r.statusCode == 200) {
        final d = jsonDecode(r.body) as Map<String, dynamic>;
        diskUsedGb  = (d['used_gb']  as num).toDouble();
        diskFreeGb  = (d['free_gb']  as num).toDouble();
        diskTotalGb = (d['total_gb'] as num).toDouble();
        diskUsedPct = (d['used_pct'] as num).toDouble();
        notifyListeners();
      }
    } catch (_) {}
  }

  Future<void> _fetchLatest() async {
    try {
      final r = await http
          .get(
            Uri.parse('${_settings.serverUrl}/api/camera/latest'),
            headers: {'X-API-Key': _settings.apiKey},
          )
          .timeout(const Duration(seconds: 3));
      if (r.statusCode == 200) {
        final data = jsonDecode(r.body) as Map<String, dynamic>;
        final newId = data['id'] as int;
        if (newId != _latestId) {
          _latestId = newId;
          latestPhoto = base64Decode(data['b64'] as String);
          latestPhotoTs = DateTime.now();
          notifyListeners();
        }
      }
    } catch (_) {}
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    _storagePollTimer?.cancel();
    super.dispose();
  }
}
