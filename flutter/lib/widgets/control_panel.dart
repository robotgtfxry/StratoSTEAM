import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/command_service.dart';
import '../services/rpi_power_service.dart';
import '../services/camera_service.dart';

// ── Paleta kolorów LED ────────────────────────────────────────────────────────
const _palette = [
  // rząd 1 — podstawowe
  {'r': 0,   'g': 0,   'b': 0,   'name': 'OFF'},
  {'r': 255, 'g': 0,   'b': 0,   'name': 'Czerwony'},
  {'r': 0,   'g': 255, 'b': 0,   'name': 'Zielony'},
  {'r': 0,   'g': 0,   'b': 255, 'name': 'Niebieski'},
  {'r': 255, 'g': 255, 'b': 0,   'name': 'Żółty'},
  {'r': 0,   'g': 255, 'b': 255, 'name': 'Cyjan'},
  {'r': 255, 'g': 0,   'b': 255, 'name': 'Magenta'},
  {'r': 255, 'g': 255, 'b': 255, 'name': 'Biały'},
  // rząd 2 — pastelowe
  {'r': 255, 'g': 128, 'b': 0,   'name': 'Pomarańcz'},
  {'r': 180, 'g': 0,   'b': 255, 'name': 'Fiolet'},
  {'r': 0,   'g': 255, 'b': 128, 'name': 'Miętowy'},
  {'r': 255, 'g': 192, 'b': 203, 'name': 'Różowy'},
  {'r': 64,  'g': 224, 'b': 208, 'name': 'Turkus'},
  {'r': 255, 'g': 69,  'b': 0,   'name': 'Vermeil'},
  {'r': 50,  'g': 205, 'b': 50,  'name': 'Limonka'},
  {'r': 135, 'g': 206, 'b': 235, 'name': 'Błękit'},
  // rząd 3 — ciemne
  {'r': 128, 'g': 0,   'b': 0,   'name': 'Bordo'},
  {'r': 0,   'g': 128, 'b': 0,   'name': 'Ciemna zieleń'},
  {'r': 0,   'g': 0,   'b': 128, 'name': 'Granat'},
  {'r': 128, 'g': 128, 'b': 0,   'name': 'Oliwka'},
  {'r': 64,  'g': 0,   'b': 128, 'name': 'Purpura'},
  {'r': 128, 'g': 64,  'b': 0,   'name': 'Brąz'},
  {'r': 192, 'g': 192, 'b': 192, 'name': 'Srebro'},
  {'r': 255, 'g': 140, 'b': 0,   'name': 'Ciemny amber'},
];


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
    _tab = TabController(length: 2, vsync: this);
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
    final cam = context.watch<CameraService>();

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
          // ── Nagłówek ────────────────────────────────────────
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

          // ── RPi status + control ─────────────────────────────
          _RpiPowerRow(rpi: rpi),
          const SizedBox(height: 14),
          const Divider(color: Colors.white12, height: 1),
          const SizedBox(height: 14),

          // ── Kamera ──────────────────────────────────────────
          _CameraSection(cam: cam),
          const SizedBox(height: 14),
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

          // ── LED RGB ─────────────────────────────────────────
          Row(children: [
            const Icon(Icons.lightbulb_outline, color: Colors.white54, size: 18),
            const SizedBox(width: 8),
            const Text('LED RGB',
                style: TextStyle(color: Colors.white70, fontSize: 14)),
            const Spacer(),
            // podgląd koloru
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

          // tabs: Paleta | Suwaki
          TabBar(
            controller: _tab,
            indicatorColor: Colors.cyanAccent,
            labelColor: Colors.cyanAccent,
            unselectedLabelColor: Colors.white38,
            indicatorSize: TabBarIndicatorSize.label,
            tabs: const [
              Tab(text: 'Paleta'),
              Tab(text: 'Suwaki RGB'),
            ],
          ),
          const SizedBox(height: 12),

          SizedBox(
            height: _tab.index == 0 ? 130 : 100,
            child: TabBarView(
              controller: _tab,
              children: [
                // ── PALETA ──────────────────────────────────
                _buildPalette(cmd),
                // ── SUWAKI ──────────────────────────────────
                _buildSliders(cmd),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // ── Jasność ─────────────────────────────────────────
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
                  thumbShape:
                      const RoundSliderThumbShape(enabledThumbRadius: 7),
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
              label: const Text('Wyślij do balonu',
                  style: TextStyle(fontWeight: FontWeight.bold)),
              onPressed: cmd.loading ? null : cmd.send,
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
          color: color.withOpacity(0.12),
          borderRadius: BorderRadius.circular(6),
          border: Border.all(color: color.withOpacity(0.4)),
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
      // Przycisk włącz / wyłącz
      SizedBox(
        height: 34,
        child: ElevatedButton.icon(
          style: ElevatedButton.styleFrom(
            backgroundColor: running
                ? Colors.redAccent.withOpacity(0.15)
                : Colors.greenAccent.withOpacity(0.15),
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
          onPressed: rpi.loading ? null : () => rpi.setPower(!running),
        ),
      ),
    ]);
  }
}


// ── Sekcja kamery ─────────────────────────────────────────────────────────────

class _CameraSection extends StatelessWidget {
  final CameraService cam;
  const _CameraSection({required this.cam});

  @override
  Widget build(BuildContext context) {
    final hasPhoto = cam.latestPhoto != null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Nagłówek + przycisk nagrywania
        Row(children: [
          const Icon(Icons.videocam_outlined, color: Colors.white54, size: 18),
          const SizedBox(width: 8),
          const Text('Kamera', style: TextStyle(color: Colors.white70, fontSize: 14)),
          const SizedBox(width: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: cam.recording
                  ? Colors.redAccent.withOpacity(0.15)
                  : Colors.white.withOpacity(0.05),
              borderRadius: BorderRadius.circular(4),
              border: Border.all(
                  color: cam.recording
                      ? Colors.redAccent.withOpacity(0.5)
                      : Colors.white12),
            ),
            child: Text(
              cam.recording ? '● REC' : 'STOP',
              style: TextStyle(
                color: cam.recording ? Colors.redAccent : Colors.white38,
                fontSize: 10,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
          const Spacer(),
          // Toggle nagrywania
          SizedBox(
            height: 32,
            child: ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                backgroundColor: cam.recording
                    ? Colors.redAccent.withOpacity(0.15)
                    : Colors.greenAccent.withOpacity(0.15),
                foregroundColor:
                    cam.recording ? Colors.redAccent : Colors.greenAccent,
                side: BorderSide(
                    color: cam.recording ? Colors.redAccent : Colors.greenAccent,
                    width: 1),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8)),
                elevation: 0,
                padding: const EdgeInsets.symmetric(horizontal: 10),
              ),
              icon: cam.recLoading
                  ? const SizedBox(
                      width: 12,
                      height: 12,
                      child: CircularProgressIndicator(
                          strokeWidth: 1.5, color: Colors.white54),
                    )
                  : Icon(
                      cam.recording ? Icons.stop_circle_outlined : Icons.fiber_manual_record,
                      size: 14),
              label: Text(cam.recording ? 'Stop' : 'Nagraj',
                  style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
              onPressed: cam.recLoading ? null : () => cam.setRecording(!cam.recording),
            ),
          ),
        ]),
        const SizedBox(height: 10),

        // Przycisk zdjęcia
        SizedBox(
          width: double.infinity,
          height: 40,
          child: ElevatedButton.icon(
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.blueAccent.withOpacity(0.15),
              foregroundColor: Colors.blueAccent,
              side: BorderSide(color: Colors.blueAccent.withOpacity(0.5), width: 1),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              elevation: 0,
            ),
            icon: cam.photoLoading
                ? const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(
                        strokeWidth: 2, color: Colors.blueAccent),
                  )
                : const Icon(Icons.camera_alt_outlined, size: 16),
            label: const Text('Zrób zdjęcie',
                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
            onPressed: cam.photoLoading ? null : cam.requestPhoto,
          ),
        ),

        if (cam.lastPhotoOk != null) ...[
          const SizedBox(height: 4),
          Row(children: [
            Icon(
              cam.lastPhotoOk! ? Icons.check_circle_outline : Icons.error_outline,
              color: cam.lastPhotoOk! ? Colors.greenAccent : Colors.redAccent,
              size: 13,
            ),
            const SizedBox(width: 4),
            Text(
              cam.lastPhotoOk!
                  ? 'Żądanie wysłane — zdjęcie nadejdzie za ~1 min'
                  : 'Błąd wysyłania',
              style: TextStyle(
                color: cam.lastPhotoOk! ? Colors.white38 : Colors.redAccent,
                fontSize: 10,
              ),
            ),
          ]),
        ],

        // Podgląd ostatniego zdjęcia
        if (hasPhoto) ...[
          const SizedBox(height: 10),
          Row(children: [
            const Icon(Icons.image_outlined, color: Colors.white24, size: 13),
            const SizedBox(width: 4),
            Text(
              'Ostatnie zdjęcie: ${_fmtTs(cam.latestPhotoTs)}',
              style: const TextStyle(color: Colors.white38, fontSize: 10),
            ),
          ]),
          const SizedBox(height: 6),
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: Image.memory(
              cam.latestPhoto!,
              fit: BoxFit.contain,
              width: double.infinity,
              // ograniczamy wysokość żeby panel nie był za duży
              height: 160,
              gaplessPlayback: true,
            ),
          ),
        ],
      ],
    );
  }

  String _fmtTs(DateTime? ts) {
    if (ts == null) return '—';
    return '${ts.hour.toString().padLeft(2, '0')}:'
        '${ts.minute.toString().padLeft(2, '0')}:'
        '${ts.second.toString().padLeft(2, '0')}';
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
