import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/command_service.dart';

// Preset LED colors with Polish labels
const _presets = [
  {'label': 'OFF',       'r': 0,   'g': 0,   'b': 0},
  {'label': 'Czerwony',  'r': 255, 'g': 0,   'b': 0},
  {'label': 'Zielony',   'r': 0,   'g': 255, 'b': 0},
  {'label': 'Niebieski', 'r': 0,   'g': 0,   'b': 255},
  {'label': 'Żółty',     'r': 255, 'g': 200, 'b': 0},
  {'label': 'Biały',     'r': 255, 'g': 255, 'b': 255},
  {'label': 'Fiolet',    'r': 180, 'g': 0,   'b': 255},
  {'label': 'Cyjan',     'r': 0,   'g': 255, 'b': 255},
];

class ControlPanel extends StatelessWidget {
  const ControlPanel({super.key});

  @override
  Widget build(BuildContext context) {
    final cmd = context.watch<CommandService>();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.cyanAccent.withOpacity(0.2)),
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

          // ── Buzzer ──────────────────────────────────────────
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
                    ? Colors.cyanAccent.withOpacity(0.15)
                    : Colors.white.withOpacity(0.05),
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

          // ── LED kolor ────────────────────────────────────────
          Row(children: [
            const Icon(Icons.lightbulb_outline, color: Colors.white54, size: 18),
            const SizedBox(width: 10),
            const Text('LED RGB',
                style: TextStyle(color: Colors.white70, fontSize: 14)),
            const Spacer(),
            // preview circle
            Container(
              width: 24,
              height: 24,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Color.fromARGB(255, cmd.ledR, cmd.ledG, cmd.ledB),
                border: Border.all(color: Colors.white24),
              ),
            ),
          ]),
          const SizedBox(height: 10),

          // Color presets
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: _presets.map((p) {
              final r = p['r'] as int;
              final g = p['g'] as int;
              final b = p['b'] as int;
              final selected = cmd.ledR == r && cmd.ledG == g && cmd.ledB == b;
              return GestureDetector(
                onTap: () => cmd.setColor(r, g, b),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: selected
                        ? Color.fromARGB(255, r, g, b).withOpacity(0.25)
                        : const Color(0xFF21262D),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(
                      color: selected
                          ? Color.fromARGB(255, r, g, b)
                          : Colors.white12,
                      width: selected ? 1.5 : 1,
                    ),
                  ),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    Container(
                      width: 10,
                      height: 10,
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        color: r == 0 && g == 0 && b == 0
                            ? Colors.white12
                            : Color.fromARGB(255, r, g, b),
                      ),
                    ),
                    const SizedBox(width: 5),
                    Text(p['label'] as String,
                        style: const TextStyle(
                            color: Colors.white70, fontSize: 11)),
                  ]),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 16),

          // ── RGB suwaki ───────────────────────────────────────
          _RgbSlider('R', cmd.ledR, Colors.red,
              (v) => cmd.setColor(v, cmd.ledG, cmd.ledB)),
          _RgbSlider('G', cmd.ledG, Colors.green,
              (v) => cmd.setColor(cmd.ledR, v, cmd.ledB)),
          _RgbSlider('B', cmd.ledB, Colors.blue,
              (v) => cmd.setColor(cmd.ledR, cmd.ledG, v)),
          const SizedBox(height: 16),

          // ── Wyślij ───────────────────────────────────────────
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
              label: const Text('Wyślij komendę do balonu',
                  style: TextStyle(fontWeight: FontWeight.bold)),
              onPressed: cmd.loading ? null : cmd.send,
            ),
          ),
          const SizedBox(height: 6),
          const Text(
            'Komenda zostanie wysłana przy następnym odebranym pakiecie telemetrii.',
            style: TextStyle(color: Colors.white24, fontSize: 10),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
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
            activeTrackColor: color.withOpacity(0.8),
            inactiveTrackColor: color.withOpacity(0.15),
            thumbColor: color,
            overlayColor: color.withOpacity(0.1),
            trackHeight: 3,
            thumbShape:
                const RoundSliderThumbShape(enabledThumbRadius: 7),
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
