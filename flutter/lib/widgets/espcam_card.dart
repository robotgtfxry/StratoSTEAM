import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/espcam_service.dart';

class EspCamCard extends StatelessWidget {
  const EspCamCard({super.key});

  @override
  Widget build(BuildContext context) {
    final svc = context.watch<EspCamService>();

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
            const Text('ESP32-CAM — zasilanie',
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

          // ── Przyciski CAM 0-3 ─────────────────────────────────────────────
          Row(
            children: List.generate(4, (i) => Expanded(
              child: Padding(
                padding: EdgeInsets.only(right: i < 3 ? 8 : 0),
                child: _CamButton(
                  index: i,
                  on: i < svc.state.length ? svc.state[i] : false,
                  loading: svc.loading,
                  onTap: () => svc.setPower(i, !(i < svc.state.length && svc.state[i])),
                ),
              ),
            )),
          ),
          const SizedBox(height: 10),

          // ── Wszystkie ON / OFF ────────────────────────────────────────────
          Row(children: [
            Expanded(
              child: _AllButton(
                label: 'Wszystkie ON',
                color: Colors.tealAccent,
                icon: Icons.power,
                onTap: svc.loading ? null : () => svc.setPower(-1, true),
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: _AllButton(
                label: 'Wszystkie OFF',
                color: Colors.redAccent,
                icon: Icons.power_off,
                onTap: svc.loading ? null : () => svc.setPower(-1, false),
              ),
            ),
          ]),
        ],
      ),
    );
  }
}


class _CamButton extends StatelessWidget {
  final int index;
  final bool on;
  final bool loading;
  final VoidCallback onTap;

  const _CamButton({
    required this.index,
    required this.on,
    required this.loading,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final color = on ? Colors.tealAccent : Colors.white24;
    return GestureDetector(
      onTap: loading ? null : onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: on
              ? Colors.tealAccent.withValues(alpha: 0.12)
              : Colors.white.withValues(alpha: 0.04),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: color.withValues(alpha: 0.5)),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              on ? Icons.videocam : Icons.videocam_off,
              color: color,
              size: 20,
            ),
            const SizedBox(height: 4),
            Text('CAM $index',
                style: TextStyle(
                    color: color,
                    fontSize: 10,
                    fontWeight: FontWeight.bold)),
            Text(on ? 'ON' : 'OFF',
                style: TextStyle(color: color.withValues(alpha: 0.7), fontSize: 9)),
          ],
        ),
      ),
    );
  }
}


class _AllButton extends StatelessWidget {
  final String label;
  final Color color;
  final IconData icon;
  final VoidCallback? onTap;

  const _AllButton({
    required this.label,
    required this.color,
    required this.icon,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) => GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: color.withValues(alpha: 0.3)),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, color: color, size: 14),
              const SizedBox(width: 6),
              Text(label,
                  style: TextStyle(
                      color: color,
                      fontSize: 11,
                      fontWeight: FontWeight.bold)),
            ],
          ),
        ),
      );
}
