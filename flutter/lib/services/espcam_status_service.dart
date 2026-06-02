import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'settings_service.dart';

class EspCamStatusEntry {
  final int cam;
  final bool ok;
  final bool recording;
  final int frames;
  final int freeMb;
  final bool reachable;
  final DateTime? updatedAt;

  const EspCamStatusEntry({
    required this.cam,
    required this.ok,
    required this.recording,
    required this.frames,
    required this.freeMb,
    required this.reachable,
    this.updatedAt,
  });

  factory EspCamStatusEntry.empty(int cam) => EspCamStatusEntry(
        cam: cam,
        ok: false,
        recording: false,
        frames: 0,
        freeMb: 0,
        reachable: false,
      );

  factory EspCamStatusEntry.fromJson(Map<String, dynamic> j) =>
      EspCamStatusEntry(
        cam:       j['cam'] ?? 0,
        ok:        j['ok']        == true || j['ok']        == 1,
        recording: j['recording'] == true || j['recording'] == 1,
        frames:    j['frames']    ?? 0,
        freeMb:    j['free_mb']   ?? 0,
        reachable: j['reachable'] == true || j['reachable'] == 1,
        updatedAt: j['updated_at'] != null
            ? DateTime.fromMillisecondsSinceEpoch(
                (j['updated_at'] * 1000).toInt())
            : null,
      );

  /// Czy status jest świeży (< 30 s)
  bool get fresh {
    if (updatedAt == null) return false;
    return DateTime.now().difference(updatedAt!).inSeconds < 30;
  }
}

class EspCamStatusService extends ChangeNotifier {
  final SettingsService _settings;

  List<EspCamStatusEntry> cameras = List.generate(
      4, (i) => EspCamStatusEntry.empty(i));

  Timer? _timer;
  bool _disposed = false;

  EspCamStatusService(this._settings) {
    _poll();
    _timer = Timer.periodic(const Duration(seconds: 10), (_) => _poll());
  }

  Future<void> _poll() async {
    if (_disposed) return;
    try {
      final res = await http
          .get(Uri.parse('${_settings.serverUrl}/api/espcam/status'))
          .timeout(const Duration(seconds: 5));
      if (res.statusCode == 200) {
        final j = jsonDecode(res.body) as Map<String, dynamic>;
        final list = (j['cameras'] as List?) ?? [];
        cameras = List.generate(4, (i) {
          final match = list.firstWhere(
            (e) => (e['cam'] ?? -1) == i,
            orElse: () => <String, dynamic>{},
          );
          return match.isEmpty
              ? EspCamStatusEntry.empty(i)
              : EspCamStatusEntry.fromJson(match as Map<String, dynamic>);
        });
        if (!_disposed) notifyListeners();
      }
    } catch (_) {}
  }

  @override
  void dispose() {
    _disposed = true;
    _timer?.cancel();
    super.dispose();
  }
}
