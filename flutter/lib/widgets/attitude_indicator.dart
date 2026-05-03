import 'dart:math' as math;
import 'package:flutter/material.dart';

class AttitudeIndicator extends StatelessWidget {
  final double roll;
  final double pitch;

  const AttitudeIndicator({super.key, required this.roll, required this.pitch});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white12),
      ),
      padding: const EdgeInsets.all(12),
      child: Column(
        children: [
          // header
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('SZTUCZNY HORYZONT',
                  style: TextStyle(color: Colors.white38, fontSize: 11, letterSpacing: 1.2)),
              Row(children: [
                _AngleChip('R', roll, Colors.cyanAccent),
                const SizedBox(width: 6),
                _AngleChip('P', pitch, Colors.orangeAccent),
              ]),
            ],
          ),
          const SizedBox(height: 8),
          // horizon instrument — fills remaining space
          Expanded(
            child: LayoutBuilder(builder: (ctx, bc) {
              final size = math.min(bc.maxWidth, bc.maxHeight);
              return Center(
                child: CustomPaint(
                  size: Size(size, size),
                  painter: _AIPainter(roll: roll, pitch: pitch),
                ),
              );
            }),
          ),
          const SizedBox(height: 8),
          // roll scale bar
          _RollScale(roll: roll),
        ],
      ),
    );
  }
}


class _AngleChip extends StatelessWidget {
  final String label;
  final double value;
  final Color color;
  const _AngleChip(this.label, this.value, this.color);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withOpacity(0.4)),
      ),
      child: Text(
        '$label ${value >= 0 ? '+' : ''}${value.toStringAsFixed(1)}°',
        style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.bold),
      ),
    );
  }
}


class _RollScale extends StatelessWidget {
  final double roll;
  const _RollScale({required this.roll});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 20,
      child: CustomPaint(
        size: const Size(double.infinity, 20),
        painter: _RollScalePainter(roll: roll),
      ),
    );
  }
}

class _RollScalePainter extends CustomPainter {
  final double roll;
  const _RollScalePainter({required this.roll});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = Colors.white24..strokeWidth = 1;
    final cx = size.width / 2;
    // ticks at 0, ±10, ±20, ±30, ±45, ±60 degrees
    for (final deg in [-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60]) {
      final x = cx + (deg / 60) * cx;
      final h = deg == 0 ? 14.0 : (deg.abs() % 30 == 0 ? 10.0 : 6.0);
      canvas.drawLine(Offset(x, 0), Offset(x, h), paint);
    }
    // roll indicator triangle
    final tri = Paint()..color = Colors.cyanAccent;
    final rx = cx - (roll / 60) * cx;
    final path = Path()
      ..moveTo(rx, 0)
      ..lineTo(rx - 5, 14)
      ..lineTo(rx + 5, 14)
      ..close();
    canvas.drawPath(path, tri);
  }

  @override
  bool shouldRepaint(_RollScalePainter old) => old.roll != roll;
}


class _AIPainter extends CustomPainter {
  final double roll;
  final double pitch;

  const _AIPainter({required this.roll, required this.pitch});

  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final cy = size.height / 2;
    final r  = math.min(cx, cy) - 4;

    canvas.clipPath(Path()..addOval(Rect.fromCircle(center: Offset(cx, cy), radius: r)));
    canvas.save();
    canvas.translate(cx, cy);
    canvas.rotate(-roll * math.pi / 180);

    final pitchOffset = pitch * r / 50;

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

    // pitch lines
    final linePaint = Paint()..color = Colors.white54..strokeWidth = 1;
    for (final deg in [-20, -10, 10, 20]) {
      final y = pitchOffset - deg * r / 50;
      final w = deg.abs() == 10 ? r * 0.4 : r * 0.6;
      canvas.drawLine(Offset(-w, y), Offset(w, y), linePaint);
      final tp = TextPainter(
        text: TextSpan(
          text: '${deg > 0 ? '+' : ''}$deg',
          style: const TextStyle(color: Colors.white54, fontSize: 10),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, Offset(w + 4, y - 6));
    }

    // horizon line
    canvas.drawLine(
      Offset(-r, pitchOffset),
      Offset(r, pitchOffset),
      Paint()..color = Colors.white..strokeWidth = 2,
    );

    canvas.restore();

    // fixed aircraft symbol
    final ap = Paint()
      ..color = Colors.yellowAccent
      ..strokeWidth = 2.5
      ..style = PaintingStyle.stroke;
    canvas.drawLine(Offset(cx - 35, cy), Offset(cx - 12, cy), ap);
    canvas.drawLine(Offset(cx + 12, cy), Offset(cx + 35, cy), ap);
    canvas.drawLine(Offset(cx, cy - 8), Offset(cx, cy + 8), ap);
    canvas.drawCircle(Offset(cx, cy), 4,
        Paint()..color = Colors.yellowAccent);

    // outer ring + bank angle ticks
    final ringPaint = Paint()
      ..color = Colors.white38
      ..strokeWidth = 1.5
      ..style = PaintingStyle.stroke;
    canvas.drawCircle(Offset(cx, cy), r, ringPaint);

    final tickPaint = Paint()..color = Colors.white54..strokeWidth = 1.5;
    for (final deg in [0, 10, 20, 30, 45, 60, -10, -20, -30, -45, -60]) {
      final angle = (deg - 90) * math.pi / 180;
      final len   = deg.abs() % 30 == 0 ? 12.0 : 7.0;
      canvas.drawLine(
        Offset(cx + (r - len) * math.cos(angle), cy + (r - len) * math.sin(angle)),
        Offset(cx + r * math.cos(angle), cy + r * math.sin(angle)),
        tickPaint,
      );
    }

    // roll pointer triangle at top
    final rollAngle = (-roll - 90) * math.pi / 180;
    final triPaint = Paint()..color = Colors.cyanAccent;
    final tx = cx + r * math.cos(rollAngle);
    final ty = cy + r * math.sin(rollAngle);
    final perpX = math.cos(rollAngle + math.pi / 2);
    final perpY = math.sin(rollAngle + math.pi / 2);
    canvas.drawPath(
      Path()
        ..moveTo(tx, ty)
        ..lineTo(tx - perpX * 7 + math.cos(rollAngle) * 12,
                 ty - perpY * 7 + math.sin(rollAngle) * 12)
        ..lineTo(tx + perpX * 7 + math.cos(rollAngle) * 12,
                 ty + perpY * 7 + math.sin(rollAngle) * 12)
        ..close(),
      triPaint,
    );
  }

  @override
  bool shouldRepaint(_AIPainter old) =>
      old.roll != roll || old.pitch != pitch;
}
