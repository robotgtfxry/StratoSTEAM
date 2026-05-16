import 'package:flutter/material.dart';
import 'dart:ui' show FontFeature;
import 'package:provider/provider.dart';
import '../services/camera_service.dart';

class CameraCard extends StatelessWidget {
  const CameraCard({super.key});

  @override
  Widget build(BuildContext context) {
    final cam = context.watch<CameraService>();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.blueAccent.withOpacity(0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Nagłówek ──────────────────────────────────────────
          Row(children: [
            const Icon(Icons.videocam, color: Colors.blueAccent, size: 18),
            const SizedBox(width: 8),
            const Text(
              'Kamera',
              style: TextStyle(
                  color: Colors.blueAccent,
                  fontWeight: FontWeight.bold,
                  fontSize: 14),
            ),
            const SizedBox(width: 10),
            _RecBadge(recording: cam.recording),
            const Spacer(),
            // Toggle nagrywania
            _RecToggle(cam: cam),
          ]),
          const SizedBox(height: 14),

          // ── Licznik pamięci ───────────────────────────────────
          _DiskBar(cam: cam),
          const SizedBox(height: 14),

          // ── Przycisk zdjęcia ──────────────────────────────────
          SizedBox(
            width: double.infinity,
            height: 48,
            child: ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.blueAccent,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10)),
                elevation: 0,
              ),
              icon: cam.photoLoading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                          strokeWidth: 2.5, color: Colors.white),
                    )
                  : const Icon(Icons.camera_alt, size: 20),
              label: const Text(
                'Zrób zdjęcie',
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
              ),
              onPressed: cam.photoLoading ? null : cam.requestPhoto,
            ),
          ),

          // Status wysłania żądania
          if (cam.lastPhotoOk != null) ...[
            const SizedBox(height: 6),
            Row(children: [
              Icon(
                cam.lastPhotoOk!
                    ? Icons.check_circle_outline
                    : Icons.error_outline,
                color:
                    cam.lastPhotoOk! ? Colors.greenAccent : Colors.redAccent,
                size: 14,
              ),
              const SizedBox(width: 6),
              Flexible(
                child: Text(
                  cam.lastPhotoOk!
                      ? 'Żądanie wysłane — zdjęcie dotrze za ok. 1 min'
                      : 'Błąd wysyłania żądania',
                  style: TextStyle(
                    color: cam.lastPhotoOk!
                        ? Colors.white38
                        : Colors.redAccent,
                    fontSize: 11,
                  ),
                ),
              ),
            ]),
          ],

          // ── Podgląd ostatniego zdjęcia ────────────────────────
          if (cam.latestPhoto != null) ...[
            const SizedBox(height: 12),
            Row(children: [
              const Icon(Icons.image_outlined, color: Colors.white24, size: 13),
              const SizedBox(width: 5),
              Text(
                'Ostatnie zdjęcie • ${_fmtTs(cam.latestPhotoTs)}',
                style: const TextStyle(color: Colors.white38, fontSize: 11),
              ),
            ]),
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: Image.memory(
                cam.latestPhoto!,
                width: double.infinity,
                fit: BoxFit.contain,
                gaplessPlayback: true,
              ),
            ),
          ],
        ],
      ),
    );
  }

  String _fmtTs(DateTime? ts) {
    if (ts == null) return '—';
    return '${ts.hour.toString().padLeft(2, '0')}:'
        '${ts.minute.toString().padLeft(2, '0')}:'
        '${ts.second.toString().padLeft(2, '0')}';
  }
}


// ── Badge REC / STOP ──────────────────────────────────────────────────────────

class _RecBadge extends StatelessWidget {
  final bool recording;
  const _RecBadge({required this.recording});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
        decoration: BoxDecoration(
          color: recording
              ? Colors.redAccent.withOpacity(0.15)
              : Colors.white.withOpacity(0.05),
          borderRadius: BorderRadius.circular(5),
          border: Border.all(
              color: recording
                  ? Colors.redAccent.withOpacity(0.5)
                  : Colors.white12),
        ),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          if (recording)
            Container(
              width: 7,
              height: 7,
              margin: const EdgeInsets.only(right: 4),
              decoration: const BoxDecoration(
                  color: Colors.redAccent, shape: BoxShape.circle),
            ),
          Text(
            recording ? 'NAGRYWA' : 'STOP',
            style: TextStyle(
              color: recording ? Colors.redAccent : Colors.white38,
              fontSize: 10,
              fontWeight: FontWeight.bold,
              letterSpacing: 0.5,
            ),
          ),
        ]),
      );
}


// ── Przycisk stop / wznów nagrywanie ─────────────────────────────────────────

class _RecToggle extends StatelessWidget {
  final CameraService cam;
  const _RecToggle({required this.cam});

  @override
  Widget build(BuildContext context) => SizedBox(
        height: 34,
        child: ElevatedButton.icon(
          style: ElevatedButton.styleFrom(
            backgroundColor: cam.recording
                ? Colors.redAccent.withOpacity(0.12)
                : Colors.greenAccent.withOpacity(0.12),
            foregroundColor:
                cam.recording ? Colors.redAccent : Colors.greenAccent,
            side: BorderSide(
                color: cam.recording ? Colors.redAccent : Colors.greenAccent,
                width: 1),
            shape:
                RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
            elevation: 0,
            padding: const EdgeInsets.symmetric(horizontal: 12),
          ),
          icon: cam.recLoading
              ? const SizedBox(
                  width: 13,
                  height: 13,
                  child: CircularProgressIndicator(
                      strokeWidth: 1.5, color: Colors.white54),
                )
              : Icon(
                  cam.recording
                      ? Icons.stop_circle_outlined
                      : Icons.fiber_manual_record,
                  size: 15),
          label: Text(
            cam.recording ? 'Zatrzymaj' : 'Wznów',
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
          ),
          onPressed:
              cam.recLoading ? null : () => cam.setRecording(!cam.recording),
        ),
      );
}


// ── Pasek pamięci ─────────────────────────────────────────────────────────────

class _DiskBar extends StatelessWidget {
  final CameraService cam;
  const _DiskBar({required this.cam});

  @override
  Widget build(BuildContext context) {
    final hasData = cam.diskTotalGb != null;
    final pct     = (cam.diskUsedPct ?? 0) / 100.0;
    final barColor = pct > 0.9
        ? Colors.redAccent
        : pct > 0.7
            ? Colors.orangeAccent
            : Colors.greenAccent;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(children: [
          const Icon(Icons.storage_outlined, color: Colors.white38, size: 14),
          const SizedBox(width: 6),
          const Text('Pamięć RPi5',
              style: TextStyle(color: Colors.white54, fontSize: 12)),
          const Spacer(),
          Text(
            hasData
                ? '${cam.diskUsedGb!.toStringAsFixed(1)} / '
                  '${cam.diskTotalGb!.toStringAsFixed(1)} GB  '
                  '(${cam.diskUsedPct!.toStringAsFixed(0)}%)'
                : '— / — GB',
            style: TextStyle(
              color: hasData ? barColor : Colors.white24,
              fontSize: 12,
              fontWeight: FontWeight.bold,
              fontFeatures: const [FontFeature.tabularFigures()],
            ),
          ),
        ]),
        const SizedBox(height: 6),
        ClipRRect(
          borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(
            value: hasData ? pct.clamp(0.0, 1.0) : null,
            minHeight: 6,
            backgroundColor: Colors.white12,
            valueColor: AlwaysStoppedAnimation(barColor),
          ),
        ),
        if (hasData) ...[
          const SizedBox(height: 4),
          Text(
            'Wolne: ${cam.diskFreeGb!.toStringAsFixed(1)} GB',
            style: const TextStyle(color: Colors.white24, fontSize: 10),
          ),
        ],
      ],
    );
  }
}
