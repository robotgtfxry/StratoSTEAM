import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/command_service.dart';
import '../services/rpi_power_service.dart';
import 'pin_dialog.dart';

// ── Preset palette ────────────────────────────────────────────────────────────
const _palette = [
  // row 1 – basic
  {'r': 0,   'g': 0,   'b': 0,   'name': 'OFF'},
  {'r': 255, 'g': 0,   'b': 0,   'name': 'Czerwony'},
  {'r': 0,   'g': 255, 'b': 0,   'name': 'Zielony'},
  {'r': 0,   'g': 0,   'b': 255, 'name': 'Niebieski'},
  {'r': 255, 'g': 255, 'b': 0,   'name': 'Żółty'},
  {'r': 0,   'g': 255, 'b': 255, 'name': 'Cyjan'},
  {'r': 255, 'g': 0,   'b': 255, 'name': 'Magenta'},
  {'r': 255, 'g': 255, 'b': 255, 'name': 'Biały'},
  // row 2 – pastels
  {'r': 255, 'g': 128, 'b': 0,   'name': 'Pomarańcz'},
  {'r': 180, 'g': 0,   'b': 255, 'name': 'Fiolet'},
  {'r': 0,   'g': 255, 'b': 128, 'name': 'Miętowy'},
  {'r': 255, 'g': 192, 'b': 203, 'name': 'Różowy'},
  {'r': 64,  'g': 224, 'b': 208, 'name': 'Turkus'},
  {'r': 255, 'g': 69,  'b': 0,   'name': 'Vermeil'},
  {'r': 50,  'g': 205, 'b': 50,  'name': 'Limonka'},
  {'r': 135, 'g': 206, 'b': 235, 'name': 'Błękit'},
  // row 3 – dark
  {'r': 128, 'g': 0,   'b': 0,   'name': 'Bordo'},
  {'r': 0,   'g': 128, 'b': 0,   'name': 'Ciemna zieleń'},
  {'r': 0,   'g': 0,   'b': 128, 'name': 'Granat'},
  {'r': 128, 'g': 128, 'b': 0,   'name': 'Oliwka'},
  {'r': 64,  'g': 0,   'b': 128, 'name': 'Purpura'},
  {'r': 128, 'g': 64,  'b': 0,   'name': 'Brąz'},
  {'r': 192, 'g': 192, 'b': 192, 'name': 'Srebro'},
  {'r': 255, 'g': 140, 'b': 0,   'name': 'Ciemny amber'},
];

// ── HSV ↔ RGB helpers ─────────────────────────────────────────────────────────
(double h, double s, double v) rgbToHsv(int r, int g, int b) {
  final rf = r / 255.0;
  final gf = g / 255.0;
  final bf = b / 255.0;
  final max = [rf, gf, bf].reduce(math.max);
  final min = [rf, gf, bf].reduce(math.min);
  final delta = max - min;
  double h = 0, s = 0;
  final v = max;
  if (max != 0) s = delta / max;
  if (delta != 0) {
    if (max == rf) {
      h = ((gf - bf) / delta) % 6;
    } else if (max == gf) {
      h = (bf - rf) / delta + 2;
    } else {
      h = (rf - gf) / delta + 4;
    }
    h *= 60;
    if (h < 0) h += 360;
  }
  return (h, s, v);
}

(int r, int g, int b) hsvToRgb(double h, double s, double v) {
  if (s == 0) {
    final c = (v * 255).round();
    return (c, c, c);
  }
  final sector = (h / 60).floor();
  final f = h / 60 - sector;
  final p = v * (1 - s);
  final q = v * (1 - s * f);
  final t = v * (1 - s * (1 - f));
  double r, g, b;
  switch (sector % 6) {
    case 0: r = v; g = t; b = p;
    case 1: r = q; g = v; b = p;
    case 2: r = p; g = v; b = t;
    case 3: r = p; g = q; b = v;
    case 4: r = t; g = p; b = v;
    default: r = v; g = p; b = q;
  }
  return ((r * 255).round(), (g * 255).round(), (b * 255).round());
}

// ── Main widget ───────────────────────────────────────────────────────────────
class ControlPanel extends StatefulWidget {
  const ControlPanel({super.key});
  @override
  State<ControlPanel> createState() => _ControlPanelState();
}

class _ControlPanelState extends State<ControlPanel>
    with SingleTickerProviderStateMixin {
  late TabController _tab;
  int? _selectedPreset;

  @override
  void initState() {
    super.initState();
    _tab = TabController(length: 3, vsync: this);
    _tab.addListener(() => setState(() {}));
  }

  @override
  void dispose() {
    _tab.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final cmd = context.watch<CommandService>();
    final rpi = context.watch<RpiPowerService>();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.cyanAccent.withValues(alpha: 0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header
          Row(children: [
            const Icon(Icons.settings_remote, color: Colors.cyanAccent, size: 18),
            const SizedBox(width: 8),
            const Text('Sterowanie balonem',
                style: TextStyle(
                    color: Colors.cyanAccent,
                    fontWeight: FontWeight.bold,
                    fontSize: 14)),
            const Spacer(),
            if (cmd.lastSendOk != null)
              Icon(
                cmd.lastSendOk! ? Icons.check_circle : Icons.error,
                color: cmd.lastSendOk! ? Colors.greenAccent : Colors.redAccent,
                size: 16,
              ),
          ]),
          const SizedBox(height: 12),
          const Divider(color: Colors.white12, height: 1),
          const SizedBox(height: 14),

          // RPi status + control
          _RpiPowerRow(rpi: rpi),
          const SizedBox(height: 14),
          const Divider(color: Colors.white12, height: 1),
          const SizedBox(height: 14),

          // Buzzer
          Row(children: [
            const Icon(Icons.volume_up, color: Colors.white54, size: 18),
            const SizedBox(width: 10),
            const Text('Buzzer',
                style: TextStyle(color: Colors.white70, fontSize: 14)),
            const Spacer(),
            Switch(
              value: cmd.buzzer,
              activeColor: Colors.cyanAccent,
              onChanged: (v) => cmd.setBuzzer(v),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
              decoration: BoxDecoration(
                color: cmd.buzzer
                    ? Colors.cyanAccent.withValues(alpha: 0.15)
                    : Colors.white.withValues(alpha: 0.05),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                cmd.buzzer ? 'ON' : 'OFF',
                style: TextStyle(
                  color: cmd.buzzer ? Colors.cyanAccent : Colors.white38,
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                ),
              ),
            ),
          ]),
          const SizedBox(height: 16),

          // LED RGB header + preview
          Row(children: [
            const Icon(Icons.lightbulb_outline, color: Colors.white54, size: 18),
            const SizedBox(width: 8),
            const Text('LED RGB',
                style: TextStyle(color: Colors.white70, fontSize: 14)),
            const Spacer(),
            Container(
              width: 28,
              height: 28,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Color.fromARGB(255, cmd.ledR, cmd.ledG, cmd.ledB),
                border: Border.all(color: Colors.white24, width: 1.5),
                boxShadow: cmd.ledR + cmd.ledG + cmd.ledB > 0
                    ? [BoxShadow(
                        color: Color.fromARGB(100, cmd.ledR, cmd.ledG, cmd.ledB),
                        blurRadius: 8,
                        spreadRadius: 2,
                      )]
                    : null,
              ),
            ),
            const SizedBox(width: 8),
            Text(
              '#${cmd.ledR.toRadixString(16).padLeft(2, '0')}'
              '${cmd.ledG.toRadixString(16).padLeft(2, '0')}'
              '${cmd.ledB.toRadixString(16).padLeft(2, '0')}'.toUpperCase(),
              style: const TextStyle(
                  color: Colors.white38, fontSize: 11, fontFamily: 'monospace'),
            ),
          ]),
          const SizedBox(height: 12),

          // Tabs
          TabBar(
            controller: _tab,
            indicatorColor: Colors.cyanAccent,
            labelColor: Colors.cyanAccent,
            unselectedLabelColor: Colors.white38,
            indicatorSize: TabBarIndicatorSize.label,
            tabs: const [
              Tab(text: 'Paleta'),
              Tab(text: 'Suwaki'),
              Tab(text: 'Koło HSV'),
            ],
          ),
          const SizedBox(height: 12),

          SizedBox(
            height: _tab.index == 2 ? 220 : (_tab.index == 0 ? 130 : 100),
            child: TabBarView(
              controller: _tab,
              children: [
                _buildPalette(cmd),
                _buildSliders(cmd),
                _HsvPicker(
                  r: cmd.ledR, g: cmd.ledG, b: cmd.ledB,
                  onColor: (r, g, b) {
                    setState(() => _selectedPreset = null);
                    cmd.setColor(r, g, b);
                  },
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // Brightness slider
          Row(children: [
            const Icon(Icons.brightness_6, color: Colors.white38, size: 16),
            const SizedBox(width: 8),
            const Text('Jasność',
                style: TextStyle(color: Colors.white54, fontSize: 12)),
            Expanded(
              child: SliderTheme(
                data: SliderTheme.of(context).copyWith(
                  activeTrackColor: Colors.white70,
                  inactiveTrackColor: Colors.white12,
                  thumbColor: Colors.white,
                  overlayColor: Colors.white12,
                  trackHeight: 3,
                  thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 7),
                ),
                child: Slider(
                  value: cmd.brightness,
                  min: 0,
                  max: 1,
                  onChanged: (v) => cmd.setBrightness(v),
                ),
              ),
            ),
            Text('${(cmd.brightness * 100).round()}%',
                style: const TextStyle(color: Colors.white38, fontSize: 11)),
          ]),
          const SizedBox(height: 16),

          // Send button
          SizedBox(
            width: double.infinity,
            height: 44,
            child: ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.cyanAccent,
                foregroundColor: Colors.black,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8)),
              ),
              icon: cmd.loading
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.black),
                    )
                  : const Icon(Icons.send, size: 16),
              label: const Text('Wyślij do balonu',
                  style: TextStyle(fontWeight: FontWeight.bold)),
              onPressed: cmd.loading
                  ? null
                  : () async {
                      if (!await requirePin(context)) return;
                      cmd.send();
                    },
            ),
          ),
          const SizedBox(height: 6),
          const Text(
            'Komenda zostanie wysłana przy najbliższym pakiecie telemetrii.',
            style: TextStyle(color: Colors.white24, fontSize: 10),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _buildPalette(CommandService cmd) {
    return GridView.builder(
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 8,
        crossAxisSpacing: 6,
        mainAxisSpacing: 6,
      ),
      itemCount: _palette.length,
      itemBuilder: (ctx, i) {
        final p = _palette[i];
        final r = p['r'] as int;
        final g = p['g'] as int;
        final b = p['b'] as int;
        final selected = _selectedPreset == i;
        return Tooltip(
          message: p['name'] as String,
          child: GestureDetector(
            onTap: () {
              setState(() => _selectedPreset = i);
              final bright = cmd.brightness;
              cmd.setColor(
                (r * bright).round(),
                (g * bright).round(),
                (b * bright).round(),
              );
            },
            child: Container(
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: r + g + b == 0
                    ? const Color(0xFF21262D)
                    : Color.fromARGB(255, r, g, b),
                border: Border.all(
                  color: selected ? Colors.white : Colors.white12,
                  width: selected ? 2.5 : 1,
                ),
                boxShadow: selected && r + g + b > 0
                    ? [BoxShadow(
                        color: Color.fromARGB(120, r, g, b),
                        blurRadius: 6,
                      )]
                    : null,
              ),
              child: r + g + b == 0
                  ? const Icon(Icons.close, color: Colors.white38, size: 12)
                  : null,
            ),
          ),
        );
      },
    );
  }

  Widget _buildSliders(CommandService cmd) {
    return Column(
      children: [
        _RgbSlider('R', cmd.ledR, Colors.red,
            (v) { setState(() => _selectedPreset = null); cmd.setColor(v, cmd.ledG, cmd.ledB); }),
        _RgbSlider('G', cmd.ledG, Colors.green,
            (v) { setState(() => _selectedPreset = null); cmd.setColor(cmd.ledR, v, cmd.ledB); }),
        _RgbSlider('B', cmd.ledB, Colors.blue,
            (v) { setState(() => _selectedPreset = null); cmd.setColor(cmd.ledR, cmd.ledG, v); }),
      ],
    );
  }
}

// ── HSV Color Wheel Picker ────────────────────────────────────────────────────

class _HsvPicker extends StatefulWidget {
  final int r, g, b;
  final void Function(int r, int g, int b) onColor;

  const _HsvPicker({required this.r, required this.g, required this.b, required this.onColor});

  @override
  State<_HsvPicker> createState() => _HsvPickerState();
}

class _HsvPickerState extends State<_HsvPicker> {
  late double _h, _s, _v;

  @override
  void initState() {
    super.initState();
    final hsv = rgbToHsv(widget.r, widget.g, widget.b);
    _h = hsv.$1; _s = hsv.$2; _v = hsv.$3;
  }

  @override
  void didUpdateWidget(_HsvPicker old) {
    super.didUpdateWidget(old);
    if (old.r != widget.r || old.g != widget.g || old.b != widget.b) {
      final newHsv = rgbToHsv(widget.r, widget.g, widget.b);
      // Only sync if the change came from outside (not our own drag)
      final cur = hsvToRgb(_h, _s, _v);
      if (cur.$1 != widget.r || cur.$2 != widget.g || cur.$3 != widget.b) {
        setState(() { _h = newHsv.$1; _s = newHsv.$2; _v = newHsv.$3; });
      }
    }
  }

  void _onWheelDrag(Offset localPos, Size wheelSize) {
    final cx = wheelSize.width / 2;
    final cy = wheelSize.height / 2;
    final radius = (math.min(wheelSize.width, wheelSize.height) / 2) - 4;
    final dx = localPos.dx - cx;
    final dy = localPos.dy - cy;
    final dist = math.sqrt(dx * dx + dy * dy);
    final s = (dist / radius).clamp(0.0, 1.0);
    double h = math.atan2(dy, dx) * 180 / math.pi;
    if (h < 0) h += 360;
    setState(() { _h = h; _s = s; });
    final (r, g, b) = hsvToRgb(_h, _s, _v);
    widget.onColor(r, g, b);
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: Row(
            children: [
              // Color wheel
              Expanded(
                flex: 3,
                child: LayoutBuilder(builder: (ctx, constraints) {
                  final size = Size(constraints.maxWidth, constraints.maxHeight);
                  return GestureDetector(
                    onPanUpdate: (d) => _onWheelDrag(d.localPosition, size),
                    onTapDown:   (d) => _onWheelDrag(d.localPosition, size),
                    child: CustomPaint(
                      size: size,
                      painter: _WheelPainter(h: _h, s: _s, v: _v),
                    ),
                  );
                }),
              ),
              const SizedBox(width: 12),
              // Value/brightness slider (vertical)
              SizedBox(
                width: 28,
                child: RotatedBox(
                  quarterTurns: 3,
                  child: SliderTheme(
                    data: SliderTheme.of(context).copyWith(
                      trackHeight: 16,
                      thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 10),
                      overlayShape: const RoundSliderOverlayShape(overlayRadius: 14),
                      activeTrackColor: HSVColor.fromAHSV(1, _h, _s, 1).toColor(),
                      inactiveTrackColor: const Color(0xFF21262D),
                      thumbColor: Colors.white,
                      overlayColor: Colors.white24,
                    ),
                    child: Slider(
                      value: _v,
                      min: 0,
                      max: 1,
                      onChanged: (v) {
                        setState(() => _v = v);
                        final (r, g, b) = hsvToRgb(_h, _s, _v);
                        widget.onColor(r, g, b);
                      },
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 6),
        // HSV values display
        Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            _HsvLabel('H', '${_h.round()}°', Colors.redAccent),
            const SizedBox(width: 16),
            _HsvLabel('S', '${(_s * 100).round()}%', Colors.greenAccent),
            const SizedBox(width: 16),
            _HsvLabel('V', '${(_v * 100).round()}%', Colors.blueAccent),
          ],
        ),
      ],
    );
  }
}

class _HsvLabel extends StatelessWidget {
  final String label, value;
  final Color color;
  const _HsvLabel(this.label, this.value, this.color);

  @override
  Widget build(BuildContext context) {
    return RichText(
      text: TextSpan(children: [
        TextSpan(text: '$label:', style: TextStyle(color: color, fontSize: 10, fontWeight: FontWeight.bold)),
        TextSpan(text: ' $value', style: const TextStyle(color: Colors.white54, fontSize: 10)),
      ]),
    );
  }
}

class _WheelPainter extends CustomPainter {
  final double h, s, v;
  const _WheelPainter({required this.h, required this.s, required this.v});

  @override
  void paint(Canvas canvas, Size size) {
    final cx = size.width / 2;
    final cy = size.height / 2;
    final radius = math.min(cx, cy) - 4;
    final center = Offset(cx, cy);
    final rect = Rect.fromCircle(center: center, radius: radius);

    // 1. Hue sweep
    canvas.drawCircle(
      center, radius,
      Paint()..shader = SweepGradient(
        colors: const [
          Color(0xFFFF0000),
          Color(0xFFFFFF00),
          Color(0xFF00FF00),
          Color(0xFF00FFFF),
          Color(0xFF0000FF),
          Color(0xFFFF00FF),
          Color(0xFFFF0000),
        ],
      ).createShader(rect),
    );

    // 2. Saturation overlay (white centre → transparent edge)
    canvas.drawCircle(
      center, radius,
      Paint()..shader = RadialGradient(
        colors: [Colors.white, Colors.transparent],
      ).createShader(rect),
    );

    // 3. Value/brightness overlay (transparent → black)
    canvas.drawCircle(
      center, radius,
      Paint()..color = Colors.black.withValues(alpha: 1.0 - v),
    );

    // 4. Border
    canvas.drawCircle(
      center, radius,
      Paint()
        ..color = Colors.white12
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1,
    );

    // 5. Indicator dot
    final angle = h * math.pi / 180;
    final dotDist = s * radius;
    final dotX = cx + dotDist * math.cos(angle);
    final dotY = cy + dotDist * math.sin(angle);
    final dotColor = HSVColor.fromAHSV(1, h, s, v).toColor();

    canvas.drawCircle(Offset(dotX, dotY), 11,
        Paint()..color = Colors.black.withValues(alpha: 0.5));
    canvas.drawCircle(Offset(dotX, dotY), 10,
        Paint()..color = Colors.white);
    canvas.drawCircle(Offset(dotX, dotY), 8,
        Paint()..color = dotColor);
  }

  @override
  bool shouldRepaint(_WheelPainter old) =>
      old.h != h || old.s != s || old.v != v;
}


// ── RPi Power row ─────────────────────────────────────────────────────────────
class _RpiPowerRow extends StatelessWidget {
  final RpiPowerService rpi;
  const _RpiPowerRow({required this.rpi});

  @override
  Widget build(BuildContext context) {
    final running = rpi.rpiRunning;
    final color   = running ? Colors.greenAccent : Colors.orangeAccent;
    final label   = running ? 'DZIAŁA' : 'WYŁĄCZONA';
    final icon    = running ? Icons.memory : Icons.power_off;

    return Row(children: [
      Icon(icon, color: color, size: 18),
      const SizedBox(width: 8),
      const Text('Raspberry Pi',
          style: TextStyle(color: Colors.white70, fontSize: 14)),
      const SizedBox(width: 8),
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: color.withValues(alpha: 0.4)),
        ),
        child: Text(label,
            style: TextStyle(
                color: color, fontSize: 11, fontWeight: FontWeight.bold)),
      ),
      if (rpi.pending) ...[
        const SizedBox(width: 6),
        const SizedBox(
          width: 10, height: 10,
          child: CircularProgressIndicator(strokeWidth: 1.5, color: Colors.white38),
        ),
      ],
      const Spacer(),
      SizedBox(
        height: 34,
        child: ElevatedButton.icon(
          style: ElevatedButton.styleFrom(
            backgroundColor: running
                ? Colors.redAccent.withValues(alpha: 0.15)
                : Colors.greenAccent.withValues(alpha: 0.15),
            foregroundColor: running ? Colors.redAccent : Colors.greenAccent,
            side: BorderSide(
                color: running ? Colors.redAccent : Colors.greenAccent,
                width: 1),
            shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(8)),
            elevation: 0,
            padding: const EdgeInsets.symmetric(horizontal: 12),
          ),
          icon: rpi.loading
              ? const SizedBox(
                  width: 14, height: 14,
                  child: CircularProgressIndicator(
                      strokeWidth: 2, color: Colors.white54),
                )
              : Icon(running ? Icons.power_off : Icons.power, size: 16),
          label: Text(
            running ? 'Wyłącz' : 'Włącz',
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
          ),
          onPressed: rpi.loading
              ? null
              : () async {
                  if (!await requirePin(context)) return;
                  rpi.setPower(!running);
                },
        ),
      ),
    ]);
  }
}


class _RgbSlider extends StatelessWidget {
  final String label;
  final int value;
  final Color color;
  final ValueChanged<int> onChanged;

  const _RgbSlider(this.label, this.value, this.color, this.onChanged);

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      SizedBox(
        width: 14,
        child: Text(label,
            style: TextStyle(
                color: color, fontWeight: FontWeight.bold, fontSize: 12)),
      ),
      Expanded(
        child: SliderTheme(
          data: SliderTheme.of(context).copyWith(
            activeTrackColor: color.withValues(alpha: 0.8),
            inactiveTrackColor: color.withValues(alpha: 0.15),
            thumbColor: color,
            overlayColor: color.withValues(alpha: 0.1),
            trackHeight: 3,
            thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 7),
          ),
          child: Slider(
            value: value.toDouble(),
            min: 0,
            max: 255,
            onChanged: (v) => onChanged(v.round()),
          ),
        ),
      ),
      SizedBox(
        width: 30,
        child: Text('$value',
            style: const TextStyle(color: Colors.white38, fontSize: 11),
            textAlign: TextAlign.right),
      ),
    ]);
  }
}
