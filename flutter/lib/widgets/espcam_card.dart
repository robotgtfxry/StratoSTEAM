import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/espcam_service.dart';
import '../services/espcam_status_service.dart';
import 'pin_dialog.dart';

/// Panel jedynej kamery ESP32-CAM: włącznik zasilania + status nagrywania.
class EspCamCard extends StatelessWidget {
  const EspCamCard({super.key});

  @override
  Widget build(BuildContext context) {
    final svc    = context.watch<EspCamService>();
    final status = context.watch<EspCamStatusService>();
    final cam    = status.camera;
    final on     = svc.state;

    final Color color;
    if (!on) {
      color = Colors.white24;
    } else if (cam.reachable && cam.ok) {
      color = Colors.tealAccent;
    } else if (!cam.reachable) {
      color = Colors.orangeAccent;   // zasilona ale nie odpowiada
    } else {
      color = Colors.redAccent;      // błąd kamery lub karty SD
    }

    final String stateLabel = on
        ? (cam.reachable ? (cam.recording ? 'NAGRYWA' : 'OK') : 'BRAK SYGNAŁU')
        : 'WYŁĄCZONA';

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.tealAccent.withValues(alpha: 0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Nagłówek ─────────────────────────────────────────────────────
          Row(children: [
            const Icon(Icons.camera_alt, color: Colors.tealAccent, size: 18),
            const SizedBox(width: 8),
            const Text('ESP32-CAM',
                style: TextStyle(
                    color: Colors.tealAccent,
                    fontWeight: FontWeight.bold,
                    fontSize: 14)),
            const Spacer(),
            if (svc.loading)
              const SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(
                      strokeWidth: 1.5, color: Colors.tealAccent)),
          ]),
          const SizedBox(height: 14),

          // ── Stan kamery ──────────────────────────────────────────────────
          Container(
            padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 14),
            decoration: BoxDecoration(
              color: on
                  ? color.withValues(alpha: 0.10)
                  : Colors.white.withValues(alpha: 0.04),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: color.withValues(alpha: 0.5)),
            ),
            child: Row(children: [
              Stack(
                alignment: Alignment.topRight,
                children: [
                  Icon(on ? Icons.videocam : Icons.videocam_off,
                      color: color, size: 26),
                  if (cam.recording)
                    Container(
                      width: 8, height: 8,
                      decoration: const BoxDecoration(
                        color: Colors.redAccent,
                        shape: BoxShape.circle,
                      ),
                    ),
                ],
              ),
              const SizedBox(width: 14),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(stateLabel,
                      style: TextStyle(
                          color: color,
                          fontSize: 13,
                          fontWeight: FontWeight.bold)),
                  if (on && cam.reachable) ...[
                    const SizedBox(height: 2),
                    Text('${cam.frames} klatek',
                        style: const TextStyle(
                            color: Colors.white38, fontSize: 11)),
                    Text('${cam.freeMb} MB wolne na karcie',
                        style: TextStyle(
                          color: cam.freeMb < 200
                              ? Colors.orangeAccent
                              : Colors.white38,
                          fontSize: 11,
                        )),
                  ],
                ],
              ),
            ]),
          ),
          const SizedBox(height: 10),

          // ── Włącz / wyłącz ────────────────────────────────────────────────
          Row(children: [
            Expanded(
              child: _PowerButton(
                label: 'Włącz kamerę',
                color: Colors.tealAccent,
                icon: Icons.power,
                onTap: (svc.loading || on)
                    ? null
                    : () async {
                        if (!await requirePin(context)) return;
                        svc.setPower(true);
                      },
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _PowerButton(
                label: 'Wyłącz kamerę',
                color: Colors.redAccent,
                icon: Icons.power_off,
                onTap: (svc.loading || !on)
                    ? null
                    : () async {
                        if (!await requirePin(context)) return;
                        svc.setPower(false);
                      },
              ),
            ),
          ]),
        ],
      ),
    );
  }
}


class _PowerButton extends StatelessWidget {
  final String label;
  final Color color;
  final IconData icon;
  final VoidCallback? onTap;

  const _PowerButton({
    required this.label,
    required this.color,
    required this.icon,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final active = onTap != null;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: color.withValues(alpha: active ? 0.08 : 0.03),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: active ? 0.3 : 0.12)),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icon, color: color.withValues(alpha: active ? 1 : 0.4), size: 14),
            const SizedBox(width: 6),
            Text(label,
                style: TextStyle(
                    color: color.withValues(alpha: active ? 1 : 0.4),
                    fontSize: 11,
                    fontWeight: FontWeight.bold)),
          ],
        ),
      ),
    );
  }
}
