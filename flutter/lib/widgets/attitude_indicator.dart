import 'dart:math' as math;
import 'package:flutter/material.dart';

class AttitudeIndicator extends StatelessWidget {
  final double roll;    // degrees
  final double pitch;   // degrees

  const AttitudeIndicator({super.key, required this.roll, required this.pitch});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Text('Attitude', style: TextStyle(color: Colors.white38, fontSize: 12)),
          const SizedBox(height: 12),
          CustomPaint(
            size: const Size(160, 160),
            painter: _AIPainter(roll: roll, pitch: pitch),
          ),
          const SizedBox(height: 8),
          Text(
            'R ${roll.toStringAsFixed(1)}°  P ${pitch.toStringAsFixed(1)}°',
            style: const TextStyle(color: Colors.white54, fontSize: 12),
          ),
        ],
      ),
    );
  }
}


class _AIPainter extends CustomPainter {
  final double roll;
  final double pitch;

  const _AIPainter({required this.roll, required this.pitch});

  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final cy = size.height / 2;
    final r = math.min(cx, cy) - 4;

    // clip to circle
    canvas.clipPath(Path()..addOval(Rect.fromCircle(center: Offset(cx, cy), radius: r)));
    canvas.save();
    canvas.translate(cx, cy);
    canvas.rotate(-roll * math.pi / 180);

    final pitchOffset = pitch * r / 60;  // 60° = full half

    // sky
    canvas.drawRect(
      Rect.fromLTWH(-r, -r * 2 + pitchOffset, r * 2, r * 2),
      Paint()..color = const Color(0xFF1565C0),
    );
    // ground
    canvas.drawRect(
      Rect.fromLTWH(-r, pitchOffset, r * 2, r * 2),
      Paint()..color = const Color(0xFF5D4037),
    );
    // horizon line
    canvas.drawLine(
      Offset(-r, pitchOffset),
      Offset(r, pitchOffset),
      Paint()..color = Colors.white..strokeWidth = 2,
    );

    canvas.restore();

    // fixed aircraft symbol
    final ap = Paint()..color = Colors.white..strokeWidth = 2..style = PaintingStyle.stroke;
    canvas.drawLine(Offset(cx - 30, cy), Offset(cx - 10, cy), ap);
    canvas.drawLine(Offset(cx + 10, cy), Offset(cx + 30, cy), ap);
    canvas.drawLine(Offset(cx, cy - 6), Offset(cx, cy + 6), ap);

    // border
    canvas.drawCircle(Offset(cx, cy), r,
        Paint()..color = Colors.white24..style = PaintingStyle.stroke..strokeWidth = 2);
  }

  @override
  bool shouldRepaint(_AIPainter old) => old.roll != roll || old.pitch != pitch;
}
