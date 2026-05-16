import 'dart:math' as math;
import 'package:flutter/material.dart';

class HeadingIndicator extends StatefulWidget {
  final double yaw;
  final double roll;
  final double pitch;

  const HeadingIndicator({
    super.key,
    required this.yaw,
    required this.roll,
    required this.pitch,
  });

  @override
  State<HeadingIndicator> createState() => _HeadingState();
}

class _HeadingState extends State<HeadingIndicator>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _yawAnim;
  late Animation<double> _rollAnim;
  late Animation<double> _pitchAnim;

  /// Returns the shortest angular delta in [-180, 180].
  static double _shortestDelta(double from, double to) {
    double d = (to - from) % 360;
    if (d > 180)  d -= 360;
    if (d < -180) d += 360;
    return d;
  }

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 450),
    );
    _yawAnim   = AlwaysStoppedAnimation(widget.yaw);
    _rollAnim  = AlwaysStoppedAnimation(widget.roll);
    _pitchAnim = AlwaysStoppedAnimation(widget.pitch);
  }

  @override
  void didUpdateWidget(HeadingIndicator old) {
    super.didUpdateWidget(old);
    if (old.yaw   != widget.yaw  ||
        old.roll  != widget.roll ||
        old.pitch != widget.pitch) {
      // Yaw: animate via shortest arc (handles 350°→10° correctly).
      final yawFrom = _yawAnim.value;
      final yawTo   = yawFrom + _shortestDelta(yawFrom, widget.yaw);

      _yawAnim = Tween<double>(begin: yawFrom, end: yawTo)
          .animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeOut));
      _rollAnim = Tween<double>(begin: _rollAnim.value, end: widget.roll)
          .animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeOut));
      _pitchAnim = Tween<double>(begin: _pitchAnim.value, end: widget.pitch)
          .animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeOut));
      _ctrl.forward(from: 0);
    }
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (_, __) => _buildBody(
        _yawAnim.value % 360,
        _rollAnim.value,
        _pitchAnim.value,
      ),
    );
  }

  Widget _buildBody(double yaw, double roll, double pitch) {
    // Normalise to [0, 360)
    final dispYaw = yaw < 0 ? yaw + 360 : yaw;

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white12),
      ),
      padding: const EdgeInsets.all(12),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('ORIENTACJA SONDY',
                  style: TextStyle(
                      color: Colors.white38, fontSize: 11, letterSpacing: 1.2)),
              Row(children: [
                _Chip('R', roll, Colors.cyanAccent),
                const SizedBox(width: 6),
                _Chip('P', pitch, Colors.orangeAccent),
                const SizedBox(width: 6),
                _Chip('Y', dispYaw, Colors.greenAccent, forcePositive: true),
              ]),
            ],
          ),
          const SizedBox(height: 8),
          Expanded(
            child: LayoutBuilder(builder: (ctx, bc) {
              final size = math.min(bc.maxWidth, bc.maxHeight);
              return Center(
                child: CustomPaint(
                  size: Size(size, size),
                  painter: _CompassPainter(yaw: dispYaw, roll: roll),
                ),
              );
            }),
          ),
          const SizedBox(height: 8),
          _HeadingText(dispYaw),
        ],
      ),
    );
  }
}


// ── Small angle chip ─────────────────────────────────────────────────────────

class _Chip extends StatelessWidget {
  final String label;
  final double value;
  final Color color;
  final bool forcePositive;
  const _Chip(this.label, this.value, this.color,
      {this.forcePositive = false});

  @override
  Widget build(BuildContext context) {
    final text = forcePositive
        ? '$label ${value.toStringAsFixed(0)}°'
        : '$label ${value >= 0 ? '+' : ''}${value.toStringAsFixed(1)}°';
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: color.withOpacity(0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withOpacity(0.4)),
      ),
      child: Text(text,
          style: TextStyle(
              color: color, fontSize: 11, fontWeight: FontWeight.bold)),
    );
  }
}


// ── Heading readout ──────────────────────────────────────────────────────────

class _HeadingText extends StatelessWidget {
  final double yaw;
  const _HeadingText(this.yaw);

  String _cardinalPoint(double deg) {
    const pts = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
    final idx = ((deg + 22.5) / 45).floor() % 8;
    return pts[idx];
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text(
          '${yaw.toStringAsFixed(1)}°',
          style: const TextStyle(
              color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
        ),
        const SizedBox(width: 8),
        Container(
          padding:
              const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          decoration: BoxDecoration(
            color: Colors.greenAccent.withOpacity(0.15),
            borderRadius: BorderRadius.circular(6),
            border:
                Border.all(color: Colors.greenAccent.withOpacity(0.4)),
          ),
          child: Text(_cardinalPoint(yaw),
              style: const TextStyle(
                  color: Colors.greenAccent,
                  fontSize: 12,
                  fontWeight: FontWeight.bold)),
        ),
      ],
    );
  }
}


// ── Compass CustomPainter ─────────────────────────────────────────────────────

class _CompassPainter extends CustomPainter {
  final double yaw;
  final double roll;
  const _CompassPainter({required this.yaw, required this.roll});

  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final cy = size.height / 2;
    final r  = math.min(cx, cy) - 4;

    // outer ring
    canvas.drawCircle(
      Offset(cx, cy),
      r,
      Paint()
        ..color = Colors.white12
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5,
    );

    // ── rotating compass rose ──
    canvas.save();
    canvas.translate(cx, cy);
    canvas.rotate(-yaw * math.pi / 180);

    // degree ticks
    final tickN = Paint()..color = Colors.white38..strokeWidth = 1;
    final tickM = Paint()..color = Colors.white60..strokeWidth = 1.5;
    for (int deg = 0; deg < 360; deg += 5) {
      final angle = deg * math.pi / 180;
      final isMaj = deg % 30 == 0;
      final len   = isMaj ? 10.0 : 5.0;
      final cos = math.cos(angle - math.pi / 2);
      final sin = math.sin(angle - math.pi / 2);
      canvas.drawLine(
        Offset(cos * (r - len), sin * (r - len)),
        Offset(cos * r,         sin * r),
        isMaj ? tickM : tickN,
      );
    }

    // cardinal labels
    final tp = TextPainter(textDirection: TextDirection.ltr);
    const cardinals = <String, double>{'N': 0, 'E': 90, 'S': 180, 'W': 270};
    for (final e in cardinals.entries) {
      final angle = e.value * math.pi / 180;
      final cos = math.cos(angle - math.pi / 2);
      final sin = math.sin(angle - math.pi / 2);
      final lr = r - 22.0;
      tp.text = TextSpan(
        text: e.key,
        style: TextStyle(
          color: e.key == 'N' ? Colors.redAccent : Colors.white,
          fontSize: 13,
          fontWeight: FontWeight.bold,
        ),
      );
      tp.layout();
      tp.paint(canvas,
          Offset(cos * lr - tp.width / 2, sin * lr - tp.height / 2));
    }

    // inter-cardinal labels
    const sub = <String, double>{'NE': 45, 'SE': 135, 'SW': 225, 'NW': 315};
    for (final e in sub.entries) {
      final angle = e.value * math.pi / 180;
      final cos = math.cos(angle - math.pi / 2);
      final sin = math.sin(angle - math.pi / 2);
      final lr = r - 20.0;
      tp.text = TextSpan(
        text: e.key,
        style: const TextStyle(color: Colors.white38, fontSize: 9),
      );
      tp.layout();
      tp.paint(canvas,
          Offset(cos * lr - tp.width / 2, sin * lr - tp.height / 2));
    }

    canvas.restore();

    // ── fixed north-pointer arrow ──
    final arrowLen = r * 0.55;
    canvas.drawLine(Offset(cx, cy), Offset(cx, cy - arrowLen),
        Paint()
          ..color = Colors.redAccent
          ..strokeWidth = 3
          ..strokeCap = StrokeCap.round);
    canvas.drawLine(Offset(cx, cy), Offset(cx, cy + arrowLen * 0.45),
        Paint()
          ..color = Colors.white54
          ..strokeWidth = 3
          ..strokeCap = StrokeCap.round);
    canvas.drawPath(
      Path()
        ..moveTo(cx, cy - arrowLen)
        ..lineTo(cx - 6, cy - arrowLen + 14)
        ..lineTo(cx + 6, cy - arrowLen + 14)
        ..close(),
      Paint()..color = Colors.redAccent,
    );

    // centre dot
    canvas.drawCircle(Offset(cx, cy), 5, Paint()..color = Colors.white);
    canvas.drawCircle(Offset(cx, cy), 5,
        Paint()
          ..color = Colors.black54
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1);

    // ── roll arc (bank angle indicator) ──
    final rollRad = roll * math.pi / 180;
    const arcHalf = 20 * math.pi / 180;
    canvas.drawArc(
      Rect.fromCircle(center: Offset(cx, cy), radius: r + 4),
      -math.pi / 2 + rollRad - arcHalf,
      arcHalf * 2,
      false,
      Paint()
        ..color = Colors.cyanAccent.withOpacity(0.8)
        ..strokeWidth = 3
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round,
    );
  }

  @override
  bool shouldRepaint(_CompassPainter old) =>
      old.yaw != yaw || old.roll != roll;
}
