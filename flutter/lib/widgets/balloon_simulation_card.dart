import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/telemetry_service.dart';

// ── Public card (reads service, stateless) ───────────────────────────────────

class BalloonSimulationCard extends StatelessWidget {
  const BalloonSimulationCard({super.key});

  static const double _pRef = 1013.25; // hPa sea-level reference

  // r ∝ (P₀/P)^(1/3)  — Boyle's law, isothermal approximation
  static double _radiusNorm(double pHpa) =>
      pHpa > 0 ? math.pow(_pRef / pHpa, 1.0 / 3.0).toDouble() : 1.0;

  // sg2 (rear-left) + sg3 (rear-right) are the parachute lines.
  // 0 = folded, 1 = fully open. Threshold: 200 g → 1200 g combined tension.
  static double _chuteOpen(double sg2, double sg3) {
    final sum = sg2 + sg3;
    if (sum < 200) return 0.0;
    if (sum > 1200) return 1.0;
    return (sum - 200) / 1000.0;
  }

  @override
  Widget build(BuildContext context) {
    final svc = context.watch<TelemetryService>();
    final t = svc.latest;
    final pressure = t?.msPres ?? _pRef;
    return _BalloonView(
      radiusNorm: _radiusNorm(pressure),
      chuteOpenFactor: t == null ? 0.0 : _chuteOpen(t.strainG2, t.strainG3),
      pressure: pressure,
      sg2: t?.strainG2 ?? 0.0,
      sg3: t?.strainG3 ?? 0.0,
      hasData: t != null,
    );
  }
}

// ── Balloon state ─────────────────────────────────────────────────────────────

enum _BState { ground, ascending, highAlt, burstRisk }

_BState _stateOf(double p) {
  if (p > 900) return _BState.ground;
  if (p > 200) return _BState.ascending;
  if (p > 50) return _BState.highAlt;
  return _BState.burstRisk;
}

// ── Animated view (StatefulWidget) ───────────────────────────────────────────

class _BalloonView extends StatefulWidget {
  final double radiusNorm;
  final double chuteOpenFactor;
  final double pressure;
  final double sg2;
  final double sg3;
  final bool hasData;

  const _BalloonView({
    required this.radiusNorm,
    required this.chuteOpenFactor,
    required this.pressure,
    required this.sg2,
    required this.sg3,
    required this.hasData,
  });

  @override
  State<_BalloonView> createState() => _BalloonViewState();
}

class _BalloonViewState extends State<_BalloonView>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double> _rAnim;
  late Animation<double> _cAnim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 600));
    _rAnim = AlwaysStoppedAnimation(widget.radiusNorm);
    _cAnim = AlwaysStoppedAnimation(widget.chuteOpenFactor);
  }

  @override
  void didUpdateWidget(_BalloonView old) {
    super.didUpdateWidget(old);
    if (old.radiusNorm != widget.radiusNorm ||
        old.chuteOpenFactor != widget.chuteOpenFactor) {
      _rAnim = Tween<double>(begin: _rAnim.value, end: widget.radiusNorm)
          .animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeOut));
      _cAnim =
          Tween<double>(begin: _cAnim.value, end: widget.chuteOpenFactor)
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
    final state = _stateOf(widget.pressure);
    final deployed = widget.chuteOpenFactor > 0.1;

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white12),
      ),
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text(
                'SYMULACJA BALONU',
                style: TextStyle(
                    color: Colors.white38, fontSize: 11, letterSpacing: 1.2),
              ),
              Flexible(
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _Chip(
                      label: switch (state) {
                        _BState.ground    => 'ZIEMIA',
                        _BState.ascending => 'WZNOSZENIE',
                        _BState.highAlt   => 'WYSOKO',
                        _BState.burstRisk => 'RYZYKO PĘKNIĘCIA',
                      },
                      color: switch (state) {
                        _BState.ground    => Colors.cyanAccent,
                        _BState.ascending => Colors.lightBlueAccent,
                        _BState.highAlt   => Colors.yellowAccent,
                        _BState.burstRisk => Colors.redAccent,
                      },
                    ),
                    const SizedBox(width: 6),
                    _Chip(
                      label: deployed ? 'SPADOCHRON OTWARTY' : 'SPADOCHRON ZŁOŻONY',
                      color: deployed ? Colors.greenAccent : Colors.white38,
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          // Body
          LayoutBuilder(builder: (ctx, bc) {
            final wide = bc.maxWidth > 520;
            const vizH = 340.0;
            final viz = AnimatedBuilder(
              animation: _ctrl,
              builder: (_, __) => CustomPaint(
                size: Size(wide ? 200 : double.infinity, vizH),
                painter: _BalloonPainter(
                  radiusNorm: _rAnim.value.clamp(0.8, 3.5),
                  chuteOpen: _cAnim.value.clamp(0.0, 1.0),
                  state: state,
                ),
              ),
            );
            final stats = _StatsPanel(
              pressure: widget.pressure,
              radiusNorm: widget.radiusNorm,
              sg2: widget.sg2,
              sg3: widget.sg3,
              deployed: deployed,
              hasData: widget.hasData,
            );
            if (wide) {
              return Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  SizedBox(width: 200, height: vizH, child: viz),
                  const SizedBox(width: 16),
                  Expanded(child: stats),
                ],
              );
            }
            return Column(children: [
              SizedBox(height: vizH, child: viz),
              const SizedBox(height: 12),
              stats,
            ]);
          }),
        ],
      ),
    );
  }
}

// ── Stats panel ───────────────────────────────────────────────────────────────

class _StatsPanel extends StatelessWidget {
  final double pressure;
  final double radiusNorm;
  final double sg2;
  final double sg3;
  final bool deployed;
  final bool hasData;

  const _StatsPanel({
    required this.pressure,
    required this.radiusNorm,
    required this.sg2,
    required this.sg3,
    required this.deployed,
    required this.hasData,
  });

  Widget _row(String label, String value, Color color) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label,
                style: const TextStyle(color: Colors.white54, fontSize: 13)),
            Text(value,
                style: TextStyle(
                    color: color,
                    fontSize: 13,
                    fontWeight: FontWeight.bold)),
          ],
        ),
      );

  @override
  Widget build(BuildContext context) {
    final na = !hasData;
    final volRatio = radiusNorm * radiusNorm * radiusNorm;

    final Color rColor = na
        ? Colors.white38
        : radiusNorm < 1.5
            ? Colors.cyanAccent
            : radiusNorm < 2.5
                ? Colors.yellowAccent
                : Colors.redAccent;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const _SectionLabel('Atmosfera'),
        _row('Ciśnienie',
            na ? '--' : '${pressure.toStringAsFixed(1)} hPa',
            Colors.purpleAccent),
        _row('Odniesienie', '1013.25 hPa', Colors.white38),
        const Divider(color: Colors.white12, height: 16),
        const _SectionLabel('Balon (prawo Boyle\'a)'),
        _row('Promień ×', na ? '--' : '×${radiusNorm.toStringAsFixed(2)}', rColor),
        _row('Objętość ×', na ? '--' : '×${volRatio.toStringAsFixed(1)}', rColor),
        const Divider(color: Colors.white12, height: 16),
        const _SectionLabel('Liny spadochronowe (sg2 / sg3)'),
        _row('Naprężenie L (sg2)',
            na ? '--' : '${sg2.toStringAsFixed(0)} g', Colors.orangeAccent),
        _row('Naprężenie P (sg3)',
            na ? '--' : '${sg3.toStringAsFixed(0)} g', Colors.orangeAccent),
        _row('Suma',
            na ? '--' : '${(sg2 + sg3).toStringAsFixed(0)} g',
            deployed ? Colors.greenAccent : Colors.white54),
        const Divider(color: Colors.white12, height: 16),
        _row(
          'Status spadochronu',
          na ? '--' : (deployed ? 'OTWARTY' : 'ZŁOŻONY'),
          deployed ? Colors.greenAccent : Colors.white70,
        ),
      ],
    );
  }
}

class _SectionLabel extends StatelessWidget {
  final String text;
  const _SectionLabel(this.text);

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 4),
        child: Text(text,
            style: const TextStyle(
                color: Colors.white24, fontSize: 10, letterSpacing: 0.8)),
      );
}

class _Chip extends StatelessWidget {
  final String label;
  final Color color;
  const _Chip({required this.label, required this.color});

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: color.withValues(alpha: 0.4)),
        ),
        child: Text(label,
            style: TextStyle(
                color: color, fontSize: 10, fontWeight: FontWeight.bold)),
      );
}

// ── CustomPainter ─────────────────────────────────────────────────────────────

class _BalloonPainter extends CustomPainter {
  final double radiusNorm; // clamped 0.8–3.5
  final double chuteOpen;  // 0–1
  final _BState state;

  const _BalloonPainter({
    required this.radiusNorm,
    required this.chuteOpen,
    required this.state,
  });

  Color get _fill => switch (state) {
        _BState.ground    => const Color(0xFF90CAF9),
        _BState.ascending => const Color(0xFFB3E5FC),
        _BState.highAlt   => const Color(0xFFFFF9C4),
        _BState.burstRisk => const Color(0xFFFFCDD2),
      };

  Color get _glow => switch (state) {
        _BState.ground    => Colors.lightBlue,
        _BState.ascending => Colors.lightBlueAccent,
        _BState.highAlt   => Colors.yellowAccent,
        _BState.burstRisk => Colors.redAccent,
      };

  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final h  = size.height; // 340

    // ── Balloon geometry ─────────────────────────────────────────────────
    // Visual scale compresses the 1–3.5× physics range into 1–2.2× screen range
    // so the balloon never overflows the canvas.
    final baseR  = h * 0.13; // ~44 px at h=340
    final vScale = 1.0 + (radiusNorm - 1.0) * 0.48;
    final br     = baseR * vScale;

    // Center drifts slightly upward as balloon grows so it never clips top.
    final balloonCy = (br * 1.1 + 8.0).clamp(88.0, 128.0);

    final bRect = Rect.fromCenter(
      center: Offset(cx, balloonCy),
      width:  br * 2,
      height: br * 2.18, // slight vertical stretch → pear shape
    );

    // Burst-risk glow
    if (state == _BState.burstRisk) {
      canvas.drawOval(
        bRect.inflate(8),
        Paint()
          ..color = Colors.redAccent.withValues(alpha: 0.2)
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 14),
      );
    }

    // Balloon fill (radial gradient: white highlight on upper-left)
    canvas.drawOval(
      bRect,
      Paint()
        ..shader = RadialGradient(
          center: const Alignment(-0.3, -0.4),
          radius: 0.75,
          colors: [
            Colors.white.withValues(alpha: 0.72),
            _fill.withValues(alpha: 0.88),
            _fill.withValues(alpha: 0.52),
          ],
        ).createShader(bRect),
    );
    canvas.drawOval(
      bRect,
      Paint()
        ..color = _glow.withValues(alpha: 0.45)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1.5,
    );

    // Radius & volume label inside balloon
    final volStr = (radiusNorm * radiusNorm * radiusNorm).toStringAsFixed(1);
    final tp = TextPainter(
      text: TextSpan(
        text: '×${radiusNorm.toStringAsFixed(2)}\nV×$volStr',
        style: TextStyle(
          color: Colors.black.withValues(alpha: 0.45),
          fontSize: 9.5,
          height: 1.5,
        ),
      ),
      textAlign: TextAlign.center,
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, Offset(cx - tp.width / 2, balloonCy - tp.height / 2));

    // ── Nozzle ───────────────────────────────────────────────────────────
    final nozzleTopY = balloonCy + br * 1.09;
    final nozzleBotY = nozzleTopY + 10.0;
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromCenter(
            center: Offset(cx, nozzleTopY + 5), width: 10, height: 10),
        const Radius.circular(2),
      ),
      Paint()..color = _fill.withValues(alpha: 0.7),
    );

    // ── Suspension string ────────────────────────────────────────────────
    const payloadTop = 248.0;
    canvas.drawLine(
      Offset(cx, nozzleBotY),
      Offset(cx, payloadTop),
      Paint()
        ..color = Colors.white38
        ..strokeWidth = 1.2,
    );

    // ── Payload box ──────────────────────────────────────────────────────
    const payloadW = 38.0;
    const payloadH = 22.0;
    final pBox = RRect.fromRectAndRadius(
      Rect.fromLTWH(cx - payloadW / 2, payloadTop, payloadW, payloadH),
      const Radius.circular(3),
    );
    canvas.drawRRect(pBox, Paint()..color = const Color(0xFF263238));
    canvas.drawRRect(
      pBox,
      Paint()
        ..color = Colors.white24
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1,
    );

    // ── Parachute ────────────────────────────────────────────────────────
    const chuteAttachY = payloadTop + payloadH; // 270
    final maxChuteR = (cx * 0.88).clamp(0.0, 68.0);
    final chuteR    = 10.0 + (maxChuteR - 10.0) * chuteOpen;
    final lineLen   = 16.0 + chuteOpen * 16.0;
    final domeCy    = chuteAttachY + lineLen;

    // Lines from payload corners to canopy edge (visible when deploying)
    if (chuteOpen > 0.02) {
      final alpha = (0.3 + 0.7 * chuteOpen).clamp(0.0, 1.0);
      final linePaint = Paint()
        ..color = Colors.white54.withValues(alpha: alpha)
        ..strokeWidth = 0.9;
      canvas.drawLine(Offset(cx - payloadW * 0.4, chuteAttachY),
          Offset(cx - chuteR * 0.72, domeCy), linePaint);
      canvas.drawLine(Offset(cx + payloadW * 0.4, chuteAttachY),
          Offset(cx + chuteR * 0.72, domeCy), linePaint);
      canvas.drawLine(
          Offset(cx, chuteAttachY), Offset(cx, domeCy), linePaint);
    }

    if (chuteOpen < 0.08) {
      // Folded: small orange cone
      final fp = Path()
        ..moveTo(cx, chuteAttachY)
        ..lineTo(cx - 9, chuteAttachY + 24)
        ..lineTo(cx + 9, chuteAttachY + 24)
        ..close();
      canvas.drawPath(fp, Paint()..color = Colors.orange.withValues(alpha: 0.45));
      canvas.drawPath(
        fp,
        Paint()
          ..color = Colors.orangeAccent.withValues(alpha: 0.65)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1,
      );
    } else {
      // Deployed: dome arc
      final domeRect = Rect.fromCenter(
        center: Offset(cx, domeCy),
        width:  chuteR * 2,
        height: chuteR,
      );
      final dome = Path()
        ..moveTo(cx - chuteR, domeCy)
        ..arcTo(domeRect, math.pi, math.pi, false)
        ..close();

      canvas.drawPath(
        dome,
        Paint()
          ..shader = LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Colors.orange.withValues(alpha: (0.88 * chuteOpen).clamp(0.0, 1.0)),
              Colors.deepOrange
                  .withValues(alpha: (0.60 * chuteOpen).clamp(0.0, 1.0)),
            ],
          ).createShader(domeRect),
      );
      canvas.drawPath(
        dome,
        Paint()
          ..color = Colors.orangeAccent
              .withValues(alpha: (0.65 * chuteOpen).clamp(0.0, 1.0))
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.2,
      );

      // Canopy ribs
      final ribPaint = Paint()
        ..color =
            Colors.orange.withValues(alpha: (0.35 * chuteOpen).clamp(0.0, 1.0))
        ..strokeWidth = 0.7;
      for (var i = 1; i <= 5; i++) {
        final angle = math.pi + i * math.pi / 6.0;
        canvas.drawLine(
          Offset(cx, domeCy),
          Offset(
            cx + chuteR * math.cos(angle),
            domeCy + (chuteR / 2) * math.sin(angle).abs(),
          ),
          ribPaint,
        );
      }
    }
  }

  @override
  bool shouldRepaint(_BalloonPainter old) =>
      old.radiusNorm != radiusNorm ||
      old.chuteOpen != chuteOpen ||
      old.state != state;
}
