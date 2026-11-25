import 'dart:async';
import 'dart:ui' show FontFeature;
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/mission_service.dart';

/// Faza misji ze stacji: START, zegar T+, wysokość, ostatnie zdarzenia.
class MissionCard extends StatefulWidget {
  const MissionCard({super.key});

  @override
  State<MissionCard> createState() => _MissionCardState();
}

class _MissionCardState extends State<MissionCard> {
  Timer? _tick;

  @override
  void initState() {
    super.initState();
    _tick = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _tick?.cancel();
    super.dispose();
  }

  static (String, Color, IconData) _look(String? phase) => switch (phase) {
        'PRZYGOTOWANIE' => (
            'PRZYGOTOWANIE',
            Colors.white54,
            Icons.checklist
          ),
        'START' => (
            'START — czekam na wznoszenie',
            Colors.orangeAccent,
            Icons.rocket_launch
          ),
        'WZNOSZENIE' => (
            'LOT: WZNOSZENIE',
            Colors.greenAccent,
            Icons.trending_up
          ),
        'OPADANIE' => (
            'LOT: OPADANIE',
            Colors.lightBlueAccent,
            Icons.trending_down
          ),
        'LĄDOWANIE' => ('WYLĄDOWAŁ', Colors.orangeAccent, Icons.flag),
        null => ('Brak danych o misji', Colors.white38, Icons.help_outline),
        _ => (phase, Colors.white70, Icons.info_outline),
      };

  static String _clock(double s) {
    final t = s.abs().floor();
    String two(int v) => v.toString().padLeft(2, '0');
    return 'T${s < 0 ? '-' : '+'}${two(t ~/ 3600)}:${two(t % 3600 ~/ 60)}:${two(t % 60)}';
  }

  static String _ago(double s) => s < 90
      ? '${s.round()} s temu'
      : s < 5400
          ? '${(s / 60).round()} min temu'
          : '${(s / 3600).toStringAsFixed(1)} h temu';

  @override
  Widget build(BuildContext context) {
    final m = context.watch<MissionService>().info;
    final (text, color, icon) = _look(m?.phase);
    final tPlus = m?.tPlus;
    final pkt = m?.packetAge;
    final bits = <String>[
      if (m?.alt != null)
        '${m!.alt!.toStringAsFixed(0)} m${m.src != null ? ' (${m.src})' : ''}',
      if (m?.vs != null)
        '${m!.vs! >= 0 ? '+' : ''}${m.vs!.toStringAsFixed(1)} m/s',
      if (m != null && m.maxAlt != null && !m.prep)
        'szczyt ${m.maxAlt!.toStringAsFixed(0)} m',
    ];
    final events = m == null ? const <(double, String)>[] : m.events;

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(icon, color: color, size: 22),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                text,
                style: TextStyle(
                    color: color, fontSize: 16, fontWeight: FontWeight.bold),
              ),
            ),
            if (tPlus != null)
              Text(
                _clock(tPlus),
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 17,
                  fontWeight: FontWeight.bold,
                  fontFeatures: [FontFeature.tabularFigures()],
                ),
              ),
          ]),
          if (bits.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(bits.join('   •   '),
                style: const TextStyle(color: Colors.white70, fontSize: 13)),
          ],
          if (m != null) ...[
            const SizedBox(height: 6),
            Text(
              m.auto
                  ? 'Automatyczne zdjęcia: włączone'
                  : 'Automatyczne zdjęcia: wyłączone',
              style: TextStyle(
                  color: m.auto ? Colors.greenAccent : Colors.white38,
                  fontSize: 12),
            ),
            if (!m.stationOnline)
              Text('Stacja bez kontaktu z serwerem: ${_ago(m.stationAge)}',
                  style:
                      const TextStyle(color: Colors.redAccent, fontSize: 12))
            else if (pkt == null)
              const Text('Stacja nie odebrała jeszcze pakietu z balonu',
                  style: TextStyle(color: Colors.orangeAccent, fontSize: 12))
            else
              Text('Ostatni pakiet z balonu: ${_ago(pkt)}',
                  style: TextStyle(
                      color: pkt < 20 ? Colors.white38 : Colors.orangeAccent,
                      fontSize: 12)),
          ],
          if (events.isNotEmpty) ...[
            const SizedBox(height: 8),
            for (final (t, what)
                in events.sublist(events.length > 3 ? events.length - 3 : 0))
              Text('${_clock(t)}  $what',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white38, fontSize: 11)),
          ],
        ],
      ),
    );
  }
}
