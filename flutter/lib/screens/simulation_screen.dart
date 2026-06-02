import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/telemetry_service.dart';

// ── Public screen ─────────────────────────────────────────────────────────────

class SimulationScreen extends StatelessWidget {
  const SimulationScreen({super.key});

  static const double _pRef = 1013.25;

  static double _radiusNorm(double p) =>
      p > 0 ? math.pow(_pRef / p, 1.0 / 3.0).toDouble() : 1.0;

  static double _chuteOpen(double sg2, double sg3) {
    final sum = sg2 + sg3;
    if (sum < 200) return 0.0;
    if (sum > 1200) return 1.0;
    return (sum - 200) / 1000.0;
  }

  @override
  Widget build(BuildContext context) {
    final svc = context.watch<TelemetryService>();
    final t   = svc.latest;
    final pressure  = t?.msPres ?? _pRef;
    final rNorm     = _radiusNorm(pressure);
    final chuteOpen = t == null ? 0.0 : _chuteOpen(t.strainG2, t.strainG3);
    final deployed  = chuteOpen > 0.1;

    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161B22),
        title: const Text('Symulacja 3D', style: TextStyle(color: Colors.white)),
        actions: [
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 10, horizontal: 12),
            child: _ParachuteChip(deployed: deployed),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(
              child: _3DCard(
                radiusNorm:  rNorm,
                chuteOpen:   chuteOpen,
                pressure:    pressure,
                hasData:     t != null,
              ),
            ),
            const SizedBox(height: 6),
            _ParachutePanel(
              deployed:  deployed,
              chuteOpen: chuteOpen,
              sg2:       t?.strainG2 ?? 0,
              sg3:       t?.strainG3 ?? 0,
              hasData:   t != null,
            ),
            const SizedBox(height: 6),
            _BalloonStats(
              pressure:   pressure,
              radiusNorm: rNorm,
              hasData:    t != null,
            ),
          ],
        ),
      ),
    );
  }
}

// ── Parachute chip (also used externally) ────────────────────────────────────

class ParachuteStatusChip extends StatelessWidget {
  final bool deployed;
  const ParachuteStatusChip({super.key, required this.deployed});
  @override
  Widget build(BuildContext context) => _ParachuteChip(deployed: deployed);
}

class _ParachuteChip extends StatelessWidget {
  final bool deployed;
  const _ParachuteChip({required this.deployed});
  @override
  Widget build(BuildContext context) {
    final color = deployed ? Colors.greenAccent : Colors.white38;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.45)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Icon(deployed ? Icons.paragliding : Icons.compress, color: color, size: 14),
        const SizedBox(width: 5),
        Text(
          deployed ? 'SPADOCHRON OTWARTY' : 'SPADOCHRON ZŁOŻONY',
          style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.bold),
        ),
      ]),
    );
  }
}

// ── Balloon state ─────────────────────────────────────────────────────────────

enum _BState { ground, ascending, highAlt, burstRisk }

_BState _stateOf(double p) {
  if (p > 900) return _BState.ground;
  if (p > 200) return _BState.ascending;
  if (p > 50)  return _BState.highAlt;
  return _BState.burstRisk;
}

// ── 3D scene card with drag-to-rotate ─────────────────────────────────────────

class _3DCard extends StatefulWidget {
  final double radiusNorm, chuteOpen, pressure;
  final bool hasData;
  const _3DCard({
    required this.radiusNorm,
    required this.chuteOpen,
    required this.pressure,
    required this.hasData,
  });
  @override
  State<_3DCard> createState() => _3DCardState();
}

class _3DCardState extends State<_3DCard> {
  double _az = -2.45; // azimuth (~-140°, matplotlib default)
  double _el = 0.42;  // elevation ~24°

  void _onPan(Offset delta) {
    setState(() {
      _az -= delta.dx * 0.008;
      _el = (_el - delta.dy * 0.005).clamp(0.08, math.pi / 2 - 0.05);
    });
  }

  @override
  Widget build(BuildContext context) {
    final state = _stateOf(widget.pressure);
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF0D1117),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white12),
      ),
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Text('BALON — UKŁAD WSPÓŁRZĘDNYCH 3D',
                  style: TextStyle(
                      color: Colors.white38, fontSize: 11, letterSpacing: 1.0)),
              _BStateChip(state),
            ],
          ),
          const SizedBox(height: 4),
          const Text('⟵ przeciągnij aby obracać',
              style: TextStyle(color: Colors.white24, fontSize: 10)),
          const SizedBox(height: 6),
          Expanded(
            child: GestureDetector(
              onPanUpdate: (d) => _onPan(d.delta),
              child: CustomPaint(
                painter: _3DPainter(
                  az:         _az,
                  el:         _el,
                  radiusNorm: widget.radiusNorm.clamp(0.8, 3.5),
                  chuteOpen:  widget.chuteOpen,
                  state:      state,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _BStateChip extends StatelessWidget {
  final _BState state;
  const _BStateChip(this.state);
  @override
  Widget build(BuildContext context) {
    final (label, color) = switch (state) {
      _BState.ground    => ('ZIEMIA',            Colors.cyanAccent),
      _BState.ascending => ('WZNOSZENIE',         Colors.lightBlueAccent),
      _BState.highAlt   => ('WYSOKO',             Colors.yellowAccent),
      _BState.burstRisk => ('RYZYKO PĘKNIĘCIA',  Colors.redAccent),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Text(label,
          style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.bold)),
    );
  }
}

// ── 3D Painter ────────────────────────────────────────────────────────────────
//
// Scene (all dimensions in metres, real scale):
//   Box:        [-W, W] × [-W, W] × [0, H]   where W=1.5m, H=5.0m
//   Balloon:    sphere centre (0, 0, Bz)       baseline φ300mm (r=0.150m)
//   Hub:        kula φ300mm (r=0.150m) at (0, 0, Pz)
//   String:     from bottom of balloon to top of payload
//
// Projection: orthographic axonometric
//   screen_x = (−x·sin(az) + y·cos(az)) · scale
//   screen_y = ( x·cos(az)·sin(el) + y·sin(az)·sin(el) − z·cos(el)) · scale
//              (Y flipped so Z goes up on screen)

class _3DPainter extends CustomPainter {
  final double az;         // azimuth (radians)
  final double el;         // elevation (radians)
  final double radiusNorm; // 1.0 = sea-level φ300mm sphere
  final double chuteOpen;
  final _BState state;

  const _3DPainter({
    required this.az,
    required this.el,
    required this.radiusNorm,
    required this.chuteOpen,
    required this.state,
  });

  // ── Scene constants ────────────────────────────────────────────────────────
  static const double _W  = 1.5;   // box half-width [m]
  static const double _H  = 5.0;   // box height [m]
  static const double _Bz = 3.6;   // balloon centre Z [m]
  static const double _Pz = 1.1;   // payload centre Z [m]
  static const double _baseR = 0.150; // baseline sphere radius [m] (φ300mm/2)

  // ── Projection ─────────────────────────────────────────────────────────────
  Offset _proj(double x, double y, double z, Offset origin, double scale) {
    final sinAz = math.sin(az), cosAz = math.cos(az);
    final sinEl = math.sin(el), cosEl = math.cos(el);
    final sx = (-x * sinAz + y * cosAz) * scale;
    final sy = ( x * cosAz * sinEl + y * sinAz * sinEl - z * cosEl) * scale;
    return Offset(origin.dx + sx, origin.dy + sy);
  }

  // Depth for painter's algorithm (larger = further away from camera)
  double _depth(double x, double y, double z) {
    final cosAz = math.cos(az), sinAz = math.sin(az);
    final cosEl = math.cos(el), sinEl = math.sin(el);
    return -(x * cosAz * cosEl + y * sinAz * cosEl + z * sinEl);
  }

  // Camera direction (from scene towards camera)
  (double, double, double) get _camDir {
    final cosAz = math.cos(az), sinAz = math.sin(az);
    final cosEl = math.cos(el), sinEl = math.sin(el);
    return (cosAz * cosEl, sinAz * cosEl, sinEl);
  }

  // ── Draw helpers ───────────────────────────────────────────────────────────
  void _line(Canvas c, Paint p, double x1, double y1, double z1,
             double x2, double y2, double z2, Offset o, double s) {
    c.drawLine(_proj(x1, y1, z1, o, s), _proj(x2, y2, z2, o, s), p);
  }

  // ── Box + filled wall planes (matplotlib-style) ───────────────────────────
  void _drawBox(Canvas canvas, Offset o, double s) {
    const w = _W, h = _H;
    final (cx, cy, cz) = _camDir;

    // Inside-of-box view: face is visible when its outward normal points AWAY
    // from the camera, i.e. outward_normal · camDir < 0
    bool faceVis(double nx, double ny, double nz) =>
        nx * cx + ny * cy + nz * cz < 0;

    // Fill a quad face with a flat colour
    void fillFace(List<(double, double, double)> pts, Color color) {
      final path = Path();
      for (int i = 0; i < pts.length; i++) {
        final p = _proj(pts[i].$1, pts[i].$2, pts[i].$3, o, s);
        if (i == 0) path.moveTo(p.dx, p.dy);
        else        path.lineTo(p.dx, p.dy);
      }
      path.close();
      canvas.drawPath(path, Paint()
        ..color = color
        ..style = PaintingStyle.fill);
    }

    // Collect visible faces, sort farthest-first (painter's algorithm), then draw
    final tasks = <(double, void Function())>[];

    void addFace(double nx, double ny, double nz,
                 List<(double, double, double)> corners, Color fill) {
      if (!faceVis(nx, ny, nz)) return;
      double sx = 0, sy = 0, sz = 0;
      for (final c in corners) { sx += c.$1; sy += c.$2; sz += c.$3; }
      final n = corners.length.toDouble();
      final depth = _depth(sx / n, sy / n, sz / n);
      tasks.add((depth, () => fillFace(corners, fill)));
    }

    const wallFill  = Color(0x440A1929);
    const floorFill = Color(0x550D2137);

    addFace(0, 0,-1, [(-w,-w,0.0),(w,-w,0.0),(w,w,0.0),(-w,w,0.0)], floorFill);
    addFace(0, 0, 1, [(-w,-w,h),(w,-w,h),(w,w,h),(-w,w,h)], wallFill);
    addFace(-1, 0,0, [(-w,-w,0.0),(-w,w,0.0),(-w,w,h),(-w,-w,h)], wallFill);
    addFace( 1, 0,0, [(w,-w,0.0),(w,w,0.0),(w,w,h),(w,-w,h)], wallFill);
    addFace(0,-1, 0, [(-w,-w,0.0),(w,-w,0.0),(w,-w,h),(-w,-w,h)], wallFill);
    addFace(0, 1, 0, [(-w,w,0.0),(w,w,0.0),(w,w,h),(-w,w,h)], wallFill);

    // Draw farthest first
    tasks.sort((a, b) => b.$1.compareTo(a.$1));
    for (final t in tasks) t.$2();

    // ── Box edges ──
    final edgeFront = Paint()..color = Colors.white54..strokeWidth = 1.5;
    final edgeBack  = Paint()..color = Colors.white12..strokeWidth = 0.6;

    Paint ep(double n1x, double n1y, double n1z,
             double n2x, double n2y, double n2z) =>
        (faceVis(n1x,n1y,n1z) || faceVis(n2x,n2y,n2z)) ? edgeFront : edgeBack;

    // Bottom edges (z=0)
    _line(canvas, ep(0,-1,0, 0,0,-1), -w,-w,0,  w,-w,0,  o,s);
    _line(canvas, ep(0, 1,0, 0,0,-1),  w, w,0, -w, w,0,  o,s);
    _line(canvas, ep(-1,0,0, 0,0,-1), -w,-w,0, -w, w,0,  o,s);
    _line(canvas, ep( 1,0,0, 0,0,-1),  w,-w,0,  w, w,0,  o,s);
    // Top edges (z=H)
    _line(canvas, ep(0,-1,0, 0,0, 1), -w,-w,h,  w,-w,h,  o,s);
    _line(canvas, ep(0, 1,0, 0,0, 1),  w, w,h, -w, w,h,  o,s);
    _line(canvas, ep(-1,0,0, 0,0, 1), -w,-w,h, -w, w,h,  o,s);
    _line(canvas, ep( 1,0,0, 0,0, 1),  w,-w,h,  w, w,h,  o,s);
    // Vertical edges
    _line(canvas, ep(-1,0,0, 0,-1,0), -w,-w,0, -w,-w,h,  o,s);
    _line(canvas, ep( 1,0,0, 0,-1,0),  w,-w,0,  w,-w,h,  o,s);
    _line(canvas, ep( 1,0,0, 0, 1,0),  w, w,0,  w, w,h,  o,s);
    _line(canvas, ep(-1,0,0, 0, 1,0), -w, w,0, -w, w,h,  o,s);
  }

  // ── Axis arrows + labels ───────────────────────────────────────────────────
  void _drawAxes(Canvas canvas, Offset o, double s) {
    const w = _W, h = _H;
    final (cx, cy, cz) = _camDir;

    // Find the 3 bottom corners that face toward camera most
    // Pick the corner on the floor-ring that is closest to the viewer
    // for placing axis labels

    // X-axis: draw a bold arrow along x from (-W,-W,0) to (+W,-W,0) or similar
    final axPaint = Paint()..strokeWidth = 2.0..style = PaintingStyle.stroke;

    // We'll draw axes along box bottom edges closest to camera
    // X axis
    axPaint.color = const Color(0xFFFF6B6B).withValues(alpha: 0.85);
    _line(canvas, axPaint, -w,-w,0,  w,-w,0,  o,s);
    // Y axis
    axPaint.color = const Color(0xFF6BCB77).withValues(alpha: 0.85);
    _line(canvas, axPaint, -w,-w,0, -w, w,0,  o,s);
    // Z axis
    axPaint.color = const Color(0xFF4D96FF).withValues(alpha: 0.85);
    _line(canvas, axPaint, -w,-w,0, -w,-w,h,  o,s);

    // Labels
    void label(String text, double x, double y, double z, Color color) {
      final tp = TextPainter(
        text: TextSpan(
          text: text,
          style: TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.bold),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      final pos = _proj(x, y, z, o, s);
      tp.paint(canvas, pos - Offset(tp.width / 2, tp.height / 2));
    }

    label('X', w + 0.18, -w, 0, const Color(0xFFFF6B6B));
    label('Y', -w, w + 0.18, 0, const Color(0xFF6BCB77));
    label('Z', -w - 0.08, -w, h + 0.22, const Color(0xFF4D96FF));

    // Tick marks + dimension labels on Z axis
    final tickPaint = Paint()
      ..color = const Color(0xFF4D96FF).withValues(alpha: 0.5)
      ..strokeWidth = 0.8;
    for (int z = 0; z <= _H.toInt(); z++) {
      _line(canvas, tickPaint, -w, -w, z.toDouble(), -w - 0.08, -w, z.toDouble(), o, s);
      final tp = TextPainter(
        text: TextSpan(
          text: '${z}m',
          style: const TextStyle(color: Color(0xFF4D96FF), fontSize: 9),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      final pos = _proj(-w - 0.22, -w, z.toDouble(), o, s);
      tp.paint(canvas, pos - Offset(tp.width, tp.height / 2));
    }
  }

  // ── Sphere (balloon) ───────────────────────────────────────────────────────
  void _drawSphere(Canvas canvas, Offset o, double s,
                   double cx, double cy, double cz, double r, Color color,
                   double balloonRotAngle) {
    final (camX, camY, camZ) = _camDir;
    const nSeg = 48;

    // Visibility: is surface point (nx,ny,nz) facing camera?
    double vis(double nx, double ny, double nz) =>
        nx * camX + ny * camY + nz * camZ;

    // Draw an arc from t0 to t1 in steps, using parametric fn
    void drawArc(List<(double, double, double)> pts, double alpha) {
      if (pts.length < 2) return;
      final paint = Paint()
        ..color = color.withValues(alpha: alpha)
        ..strokeWidth = 0.9
        ..style = PaintingStyle.stroke;
      final path = Path();
      bool first = true;
      for (final (x, y, z) in pts) {
        final p = _proj(x, y, z, o, s);
        if (first) { path.moveTo(p.dx, p.dy); first = false; }
        else path.lineTo(p.dx, p.dy);
      }
      canvas.drawPath(path, paint);
    }

    // ── Latitude circles ──
    const latAngles = [-60.0, -30.0, 0.0, 30.0, 60.0];
    for (final latDeg in latAngles) {
      final lat = latDeg * math.pi / 180;
      final zLat = cz + r * math.sin(lat);
      final rLat = r * math.cos(lat);

      // Split into front and back segments
      final front = <(double,double,double)>[];
      final back  = <(double,double,double)>[];
      for (int i = 0; i <= nSeg; i++) {
        final t = i * 2 * math.pi / nSeg;
        final x = cx + rLat * math.cos(t);
        final y = cy + rLat * math.sin(t);
        final z = zLat;
        // Normal at this point
        final nx = math.cos(lat) * math.cos(t);
        final ny = math.cos(lat) * math.sin(t);
        final nz = math.sin(lat);
        if (vis(nx, ny, nz) >= 0) front.add((x, y, z));
        else                       back.add((x, y, z));
      }
      // Draw segments by scanning continuously
      void drawContinuous(List<(double,double,double)> pts, double alpha) {
        if (pts.isEmpty) return;
        // pts may not be continuous — draw short sub-segments for each scan
        drawArc(pts, alpha);
      }

      // Better: draw all points with varying alpha per segment
      for (int i = 0; i < nSeg; i++) {
        final t1 = i * 2 * math.pi / nSeg;
        final t2 = (i + 1) * 2 * math.pi / nSeg;
        final x1 = cx + rLat * math.cos(t1); final y1 = cy + rLat * math.sin(t1);
        final x2 = cx + rLat * math.cos(t2); final y2 = cy + rLat * math.sin(t2);
        final nxM = math.cos(lat) * math.cos((t1+t2)/2);
        final nyM = math.cos(lat) * math.sin((t1+t2)/2);
        final nzM = math.sin(lat);
        final v = vis(nxM, nyM, nzM);
        final alpha = v > 0 ? (0.15 + 0.7 * v).clamp(0.1, 0.85) : 0.10;
        canvas.drawLine(
          _proj(x1, y1, zLat, o, s),
          _proj(x2, y2, zLat, o, s),
          Paint()
            ..color = color.withValues(alpha: alpha)
            ..strokeWidth = 0.85,
        );
      }
    }

    // ── Longitude arcs (rotating) ──
    const nMerid = 8;
    for (int m = 0; m < nMerid; m++) {
      final lonBase = balloonRotAngle + m * math.pi / nMerid;
      final pts = <(double, double, double)>[];
      for (int i = 0; i <= nSeg ~/ 2; i++) {
        final lat = -math.pi / 2 + i * math.pi / (nSeg ~/ 2);
        final x = cx + r * math.cos(lat) * math.cos(lonBase);
        final y = cy + r * math.cos(lat) * math.sin(lonBase);
        final z = cz + r * math.sin(lat);
        pts.add((x, y, z));
      }
      // Draw each segment with visibility-based alpha
      for (int i = 0; i < pts.length - 1; i++) {
        final (x1, y1, z1) = pts[i];
        final (x2, y2, z2) = pts[i + 1];
        final tM = i / (pts.length - 2);
        final latM = -math.pi / 2 + (tM + 0.5 / (pts.length - 2)) * math.pi;
        final nxM = math.cos(latM) * math.cos(lonBase);
        final nyM = math.cos(latM) * math.sin(lonBase);
        final nzM = math.sin(latM);
        final v = vis(nxM, nyM, nzM);
        final alpha = v > 0 ? (0.12 + 0.65 * v).clamp(0.08, 0.77) : 0.08;
        canvas.drawLine(
          _proj(x1, y1, z1, o, s),
          _proj(x2, y2, z2, o, s),
          Paint()
            ..color = color.withValues(alpha: alpha)
            ..strokeWidth = 0.85,
        );
      }
    }

    // ── Sphere outline circle ──
    // Find the silhouette: the great circle perpendicular to the camera direction
    // For orthographic projection, silhouette is a circle of radius r projected
    // The outline is an ellipse — simplest to draw the projected outline
    final outlinePts = <Offset>[];
    for (int i = 0; i <= 64; i++) {
      final t = i * 2 * math.pi / 64;
      // Silhouette of a sphere is the equator of the view-aligned coordinate system
      // In world space, the silhouette circle has:
      //   normal = cam_dir, radius = r, centre = (cx, cy, cz)
      // Two vectors perpendicular to cam_dir:
      final (ex, ey, ez) = _perpendicular(camX, camY, camZ);
      final (fx, fy, fz) = _cross(camX, camY, camZ, ex, ey, ez);
      final x = cx + r * (math.cos(t) * ex + math.sin(t) * fx);
      final y = cy + r * (math.cos(t) * ey + math.sin(t) * fy);
      final z = cz + r * (math.cos(t) * ez + math.sin(t) * fz);
      outlinePts.add(_proj(x, y, z, o, s));
    }
    final outPath = Path()..moveTo(outlinePts[0].dx, outlinePts[0].dy);
    for (final p in outlinePts.skip(1)) outPath.lineTo(p.dx, p.dy);
    outPath.close();
    canvas.drawPath(outPath, Paint()
      ..color = color.withValues(alpha: 0.9)
      ..strokeWidth = 1.8
      ..style = PaintingStyle.stroke);

    // ── Sphere fill (subtle) ──
    canvas.drawPath(outPath, Paint()
      ..color = color.withValues(alpha: 0.06));
  }

  // Find a vector perpendicular to (nx, ny, nz)
  (double, double, double) _perpendicular(double nx, double ny, double nz) {
    if (nz.abs() < 0.9) return _normalise(-ny, nx, 0);
    return _normalise(0, -nz, ny);
  }

  (double, double, double) _normalise(double x, double y, double z) {
    final l = math.sqrt(x*x + y*y + z*z);
    return (x/l, y/l, z/l);
  }

  (double, double, double) _cross(double ax, double ay, double az,
                                  double bx, double by, double bz) {
    return _normalise(
      ay*bz - az*by,
      az*bx - ax*bz,
      ax*by - ay*bx,
    );
  }

  // ── Hub — kula φ300mm ──────────────────────────────────────────────────────
  static const double _hubR = 0.150; // φ300mm / 2

  void _drawHub(Canvas canvas, Offset o, double s) {
    _drawSphere(canvas, o, s, 0.0, 0.0, _Pz, _hubR, Colors.cyanAccent, 0.0);

    final tp = TextPainter(
      text: const TextSpan(
        text: 'HUB  φ300mm',
        style: TextStyle(color: Colors.cyanAccent, fontSize: 9),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    final pos = _proj(0, 0, _Pz + _hubR + 0.12, o, s);
    tp.paint(canvas, pos - Offset(tp.width / 2, tp.height / 2));
  }

  // ── Suspension string ──────────────────────────────────────────────────────
  void _drawString(Canvas canvas, Offset o, double s, double r) {
    final strPaint = Paint()
      ..color = Colors.white38
      ..strokeWidth = 1.0;
    // From balloon bottom → top of hub sphere
    _line(canvas, strPaint,
      0, 0, _Bz - r,
      0, 0, _Pz + _hubR,
      o, s);
  }

  // ── Parachute ──────────────────────────────────────────────────────────────
  void _drawChute(Canvas canvas, Offset o, double s) {
    if (chuteOpen < 0.05) return;
    final chuteR = 0.05 + chuteOpen * 0.60; // m
    final domeCy_world = _Pz - 0.1 - chuteOpen * 0.3;

    // Dome: draw as latitude arcs of a downward hemisphere
    const nArc = 20;
    final color = Colors.orange.withValues(alpha: (0.75 * chuteOpen).clamp(0, 1));
    // Bottom rim circle
    for (int i = 0; i < nArc; i++) {
      final t1 = i * 2 * math.pi / nArc;
      final t2 = (i + 1) * 2 * math.pi / nArc;
      canvas.drawLine(
        _proj(chuteR * math.cos(t1), chuteR * math.sin(t1), domeCy_world, o, s),
        _proj(chuteR * math.cos(t2), chuteR * math.sin(t2), domeCy_world, o, s),
        Paint()..color = color..strokeWidth = 1.2,
      );
    }
    // Ribs from top of dome down
    for (int i = 0; i < 8; i++) {
      final t = i * 2 * math.pi / 8;
      _line(canvas, Paint()..color = color..strokeWidth = 1.0,
        0, 0, domeCy_world + chuteR * 0.4,
        chuteR * math.cos(t), chuteR * math.sin(t), domeCy_world,
        o, s);
    }
    // Strings from dome rim to payload
    for (int i = 0; i < 4; i++) {
      final t = i * math.pi / 2;
      _line(canvas, Paint()..color = Colors.orange.withValues(alpha: 0.3)..strokeWidth = 0.7,
        chuteR * math.cos(t), chuteR * math.sin(t), domeCy_world,
        0, 0, _Pz - 0.05,
        o, s);
    }
  }

  // ── Balloon size label ─────────────────────────────────────────────────────
  void _drawBalloonLabel(Canvas canvas, Offset o, double s, double r, Color color) {
    final labelPos = _proj(0, 0, _Bz + r + 0.12, o, s);
    final diamM = (r * 2 * 1000).round(); // mm
    final tp = TextPainter(
      text: TextSpan(
        children: [
          TextSpan(
            text: 'φ${diamM}mm',
            style: TextStyle(
              color: color.withValues(alpha: 0.9),
              fontSize: 11,
              fontWeight: FontWeight.bold,
            ),
          ),
          TextSpan(
            text: '  ×${radiusNorm.toStringAsFixed(2)}',
            style: TextStyle(color: color.withValues(alpha: 0.6), fontSize: 10),
          ),
        ],
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, labelPos - Offset(tp.width / 2, tp.height / 2));
  }

  // ── Balloon base colour ────────────────────────────────────────────────────
  Color get _balloonColor => switch (state) {
    _BState.ground    => const Color(0xFF90CAF9),
    _BState.ascending => const Color(0xFF4FC3F7),
    _BState.highAlt   => const Color(0xFFFFEE58),
    _BState.burstRisk => const Color(0xFFEF9A9A),
  };

  // ── Main paint ─────────────────────────────────────────────────────────────
  @override
  void paint(Canvas canvas, Size size) {
    final balloonSpin = az * 1.5;

    // Auto-fit: project all 8 box corners at unit scale to find 2-D bounding
    // box, then choose the largest scale that fits within the canvas with an
    // 88 % margin, and centre the scene exactly.
    final corners8 = [
      (-_W,-_W,0.0), (_W,-_W,0.0), (_W,_W,0.0), (-_W,_W,0.0),
      (-_W,-_W,_H),  (_W,-_W,_H),  (_W,_W,_H),  (-_W,_W,_H),
    ];
    double bMinX = double.infinity,  bMaxX = double.negativeInfinity;
    double bMinY = double.infinity,  bMaxY = double.negativeInfinity;
    for (final (bx, by, bz) in corners8) {
      final p = _proj(bx, by, bz, Offset.zero, 1.0);
      if (p.dx < bMinX) bMinX = p.dx;
      if (p.dx > bMaxX) bMaxX = p.dx;
      if (p.dy < bMinY) bMinY = p.dy;
      if (p.dy > bMaxY) bMaxY = p.dy;
    }
    const fitMargin = 0.88;
    final scaleX = size.width  * fitMargin / (bMaxX - bMinX);
    final scaleY = size.height * fitMargin / (bMaxY - bMinY);
    final scale  = math.min(scaleX, scaleY);
    final origin = Offset(
      size.width  / 2 - (bMaxX + bMinX) / 2 * scale,
      size.height / 2 - (bMaxY + bMinY) / 2 * scale,
    );

    // Background
    canvas.drawRect(
      Rect.fromLTWH(0, 0, size.width, size.height),
      Paint()..color = const Color(0xFF0A0E16),
    );

    // 1. Box + grid
    _drawBox(canvas, origin, scale);

    // 2. Axes
    _drawAxes(canvas, origin, scale);

    // 3. Balloon sphere
    final r = _baseR * radiusNorm;
    final bColor = _balloonColor;
    _drawSphere(canvas, origin, scale, 0, 0, _Bz, r, bColor, balloonSpin);

    // 4. Hub sphere φ300mm
    _drawHub(canvas, origin, scale);

    // 5. String
    _drawString(canvas, origin, scale, r);

    // 6. Parachute
    _drawChute(canvas, origin, scale);

    // 7. Balloon diameter label
    _drawBalloonLabel(canvas, origin, scale, r, bColor);

    // 8. "drag to rotate" hint label (small, bottom-right)
    final hintTp = TextPainter(
      text: const TextSpan(
        text: 'az / el',
        style: TextStyle(color: Color(0x33FFFFFF), fontSize: 9),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    hintTp.paint(canvas, Offset(size.width - hintTp.width - 8, size.height - 14));
  }

  @override
  bool shouldRepaint(_3DPainter old) =>
      old.az != az || old.el != el ||
      old.radiusNorm != radiusNorm || old.chuteOpen != chuteOpen ||
      old.state != state;
}

// ── Parachute panel ───────────────────────────────────────────────────────────

class _ParachutePanel extends StatelessWidget {
  final bool deployed;
  final double chuteOpen, sg2, sg3;
  final bool hasData;

  const _ParachutePanel({
    required this.deployed,
    required this.chuteOpen,
    required this.sg2,
    required this.sg3,
    required this.hasData,
  });

  @override
  Widget build(BuildContext context) {
    final color = deployed ? Colors.greenAccent : Colors.white38;
    final label = deployed ? 'OTWARTY' : 'ZŁOŻONY';
    final icon  = deployed ? Icons.paragliding : Icons.compress;
    final pct   = (chuteOpen * 100).toStringAsFixed(0);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.45), width: 1.5),
      ),
      child: Column(
        children: [
          Row(mainAxisAlignment: MainAxisAlignment.center, children: [
            Icon(icon, color: color, size: 28),
            const SizedBox(width: 10),
            Text('SPADOCHRON: $label',
                style: TextStyle(
                    color: color, fontSize: 20,
                    fontWeight: FontWeight.bold, letterSpacing: 1.0)),
          ]),
          const SizedBox(height: 10),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: chuteOpen,
              backgroundColor: Colors.white12,
              color: color,
              minHeight: 6,
            ),
          ),
          const SizedBox(height: 8),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text('sg2 (L): ${hasData ? "${sg2.toStringAsFixed(0)} g" : "--"}',
                style: const TextStyle(color: Colors.white54, fontSize: 13)),
            Text('$pct % otwarty',
                style: TextStyle(color: color, fontSize: 13, fontWeight: FontWeight.bold)),
            Text('sg3 (P): ${hasData ? "${sg3.toStringAsFixed(0)} g" : "--"}',
                style: const TextStyle(color: Colors.white54, fontSize: 13)),
          ]),
        ],
      ),
    );
  }
}

// ── Balloon stats ─────────────────────────────────────────────────────────────

class _BalloonStats extends StatelessWidget {
  final double pressure, radiusNorm;
  final bool hasData;

  const _BalloonStats({
    required this.pressure,
    required this.radiusNorm,
    required this.hasData,
  });

  Widget _row(String label, String value, Color color) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 4),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: const TextStyle(color: Colors.white54, fontSize: 13)),
        Text(value, style: TextStyle(
            color: color, fontSize: 13, fontWeight: FontWeight.bold)),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) {
    final na  = !hasData;
    final vol = radiusNorm * radiusNorm * radiusNorm;
    final r   = 0.150 * radiusNorm;
    final Color rColor = na
        ? Colors.white38
        : radiusNorm < 1.5
            ? Colors.cyanAccent
            : radiusNorm < 2.5
                ? Colors.yellowAccent
                : Colors.redAccent;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.white12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('PARAMETRY BALONU',
              style: TextStyle(
                  color: Colors.white38, fontSize: 11, letterSpacing: 1.2)),
          const Divider(color: Colors.white12, height: 16),
          _row('Ciśnienie atmosferyczne',
              na ? '--' : '${pressure.toStringAsFixed(1)} hPa',
              Colors.purpleAccent),
          _row('Ciśnienie odniesienia', '1013.25 hPa', Colors.white38),
          _row('Średnica balonu',
              na ? '--' : '${(r * 2 * 1000).toStringAsFixed(0)} mm  (×${radiusNorm.toStringAsFixed(3)})',
              rColor),
          _row('Objętość × (względna)',
              na ? '--' : '×${vol.toStringAsFixed(2)}', rColor),
          _row('Kształt',
              na
                  ? '--'
                  : radiusNorm < 1.5
                      ? 'Gruszkowy (częściowo napełniony)'
                      : radiusNorm < 2.5
                          ? 'Pośredni'
                          : 'Kulisty (silnie napełniony)',
              Colors.white54),
        ],
      ),
    );
  }
}
