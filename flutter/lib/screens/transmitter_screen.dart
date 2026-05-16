import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:fl_chart/fl_chart.dart';
import '../services/hf_service.dart';

class TransmitterScreen extends StatefulWidget {
  const TransmitterScreen({super.key});

  @override
  State<TransmitterScreen> createState() => _TransmitterScreenState();
}

class _TransmitterScreenState extends State<TransmitterScreen> {
  int _selectedBandIndex = 0;
  late TextEditingController _freqCtrl;

  @override
  void initState() {
    super.initState();
    _freqCtrl = TextEditingController(
      text: (HfService.bands[0]['freq'] as int).toString(),
    );
  }

  @override
  void dispose() {
    _freqCtrl.dispose();
    super.dispose();
  }

  int get _freqHz =>
      int.tryParse(_freqCtrl.text) ??
      (HfService.bands[_selectedBandIndex]['freq'] as int);

  @override
  Widget build(BuildContext context) {
    final hf = context.watch<HfService>();

    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161B22),
        title: const Text('Nadajnik HF', style: TextStyle(color: Colors.white)),
        actions: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            child: _HwBadge(active: hf.hwActive),
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [

          // ── Status sprzętu ────────────────────────────────────
          _StatusCard(hf: hf),
          const SizedBox(height: 16),

          // ── Wybór pasma ───────────────────────────────────────
          _SectionBox(
            title: 'Pasmo / częstotliwość',
            icon: Icons.radio,
            color: Colors.orangeAccent,
            child: Column(
              children: [
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: HfService.bands.asMap().entries.map((e) {
                    final selected = _selectedBandIndex == e.key;
                    return ChoiceChip(
                      label: Text(e.value['label'] as String,
                          style: TextStyle(
                            color: selected ? Colors.black : Colors.white70,
                            fontSize: 12,
                          )),
                      selected: selected,
                      selectedColor: Colors.orangeAccent,
                      backgroundColor: const Color(0xFF21262D),
                      onSelected: (_) {
                        setState(() {
                          _selectedBandIndex = e.key;
                          _freqCtrl.text =
                              (e.value['freq'] as int).toString();
                        });
                      },
                    );
                  }).toList(),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: _freqCtrl,
                  keyboardType: TextInputType.number,
                  style: const TextStyle(color: Colors.white),
                  decoration: InputDecoration(
                    labelText: 'Częstotliwość (Hz)',
                    labelStyle: const TextStyle(color: Colors.white54),
                    helperText: _freqHz > 0
                        ? '${(_freqHz / 1e6).toStringAsFixed(4)} MHz'
                        : null,
                    helperStyle:
                        const TextStyle(color: Colors.orangeAccent),
                    prefixIcon: const Icon(Icons.tune,
                        color: Colors.white38, size: 18),
                    filled: true,
                    fillColor: const Color(0xFF0D1117),
                    border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide:
                            const BorderSide(color: Colors.white12)),
                    enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide:
                            const BorderSide(color: Colors.white12)),
                    focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                        borderSide:
                            const BorderSide(color: Colors.orangeAccent)),
                  ),
                  onChanged: (_) => setState(() {}),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // ── Sterowanie ────────────────────────────────────────
          _SectionBox(
            title: 'Sterowanie',
            icon: Icons.power_settings_new,
            color: Colors.cyanAccent,
            child: Column(
              children: [
                // big TX toggle
                _TxToggle(
                  active: hf.hwActive,
                  loading: hf.loading,
                  onStart: () =>
                      hf.sendCommand('start', _freqHz),
                  onStop: () =>
                      hf.sendCommand('stop', _freqHz),
                ),
                if (hf.hwActive) ...[
                  const SizedBox(height: 16),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Colors.orangeAccent,
                        side: const BorderSide(color: Colors.orangeAccent),
                        padding: const EdgeInsets.symmetric(vertical: 14),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10)),
                      ),
                      icon: const Icon(Icons.swap_horiz),
                      label: Text(
                          'Zmień na ${(_freqHz / 1e6).toStringAsFixed(4)} MHz'),
                      onPressed: hf.loading
                          ? null
                          : () => hf.sendCommand('set_freq', _freqHz),
                    ),
                  ),
                ],
              ],
            ),
          ),
          const SizedBox(height: 16),

          // ── Info / ostrzeżenie ────────────────────────────────
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.amber.withOpacity(0.08),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: Colors.amber.withOpacity(0.3)),
            ),
            child: const Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.warning_amber_rounded,
                    color: Colors.amber, size: 20),
                SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Upewnij się że antena jest podłączona przed włączeniem nadajnika. '
                    'RD06HHF1 bez obciążenia może ulec uszkodzeniu.',
                    style: TextStyle(color: Colors.amber, fontSize: 12),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // ── Wykres dBFS vs wysokość ───────────────────────────
          _MeasurementsChart(measurements: hf.measurements),
        ],
      ),
    );
  }
}


// ── Widgety pomocnicze ────────────────────────────────────────────────────────

class _MeasurementsChart extends StatelessWidget {
  final List<HfMeasurement> measurements;
  const _MeasurementsChart({required this.measurements});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: Colors.purpleAccent.withOpacity(0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            const Icon(Icons.show_chart, color: Colors.purpleAccent, size: 18),
            const SizedBox(width: 8),
            const Text('Pomiary SDR — dBFS vs wysokość',
                style: TextStyle(
                    color: Colors.purpleAccent,
                    fontWeight: FontWeight.bold,
                    fontSize: 14)),
            const Spacer(),
            Text('${measurements.length} pkt',
                style: const TextStyle(color: Colors.white38, fontSize: 11)),
          ]),
          const SizedBox(height: 14),
          const Divider(color: Colors.white12, height: 1),
          const SizedBox(height: 14),

          if (measurements.isEmpty)
            const Center(
              child: Padding(
                padding: EdgeInsets.symmetric(vertical: 32),
                child: Text('Brak pomiarów',
                    style: TextStyle(color: Colors.white38, fontSize: 13)),
              ),
            )
          else ...[
            // Last measurement summary
            _LastMeasurement(m: measurements.last),
            const SizedBox(height: 16),
            SizedBox(
              height: 220,
              child: _Chart(measurements: measurements),
            ),
          ],
        ],
      ),
    );
  }
}


class _LastMeasurement extends StatelessWidget {
  final HfMeasurement m;
  const _LastMeasurement({required this.m});

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      _Stat(label: 'dBFS', value: m.dbfs.toStringAsFixed(1),
          color: Colors.purpleAccent),
      const SizedBox(width: 24),
      _Stat(label: 'Wysokość', value: '${m.alt.toStringAsFixed(0)} m',
          color: Colors.cyanAccent),
    ]);
  }
}


class _Stat extends StatelessWidget {
  final String label;
  final String value;
  final Color color;
  const _Stat({required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: const TextStyle(color: Colors.white38, fontSize: 11)),
          Text(value,
              style: TextStyle(
                  color: color, fontSize: 22, fontWeight: FontWeight.bold)),
        ],
      );
}


class _Chart extends StatelessWidget {
  final List<HfMeasurement> measurements;
  const _Chart({required this.measurements});

  @override
  Widget build(BuildContext context) {
    final spots = measurements
        .map((m) => FlSpot(m.alt, m.dbfs))
        .toList()
      ..sort((a, b) => a.x.compareTo(b.x));

    final minAlt  = spots.map((s) => s.x).reduce((a, b) => a < b ? a : b);
    final maxAlt  = spots.map((s) => s.x).reduce((a, b) => a > b ? a : b);
    final minDbfs = spots.map((s) => s.y).reduce((a, b) => a < b ? a : b);
    final maxDbfs = spots.map((s) => s.y).reduce((a, b) => a > b ? a : b);
    final altRange  = (maxAlt  - minAlt).clamp(1.0, double.infinity);
    final dbfsRange = (maxDbfs - minDbfs).clamp(1.0, double.infinity);

    return LineChart(
      LineChartData(
        backgroundColor: const Color(0xFF0D1117),
        gridData: FlGridData(
          show: true,
          getDrawingHorizontalLine: (_) =>
              const FlLine(color: Colors.white12, strokeWidth: 0.5),
          getDrawingVerticalLine: (_) =>
              const FlLine(color: Colors.white12, strokeWidth: 0.5),
        ),
        borderData: FlBorderData(
          show: true,
          border: Border.all(color: Colors.white12),
        ),
        titlesData: FlTitlesData(
          leftTitles: AxisTitles(
            axisNameWidget: const Text('dBFS',
                style: TextStyle(color: Colors.white38, fontSize: 10)),
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 42,
              getTitlesWidget: (v, _) => Text(
                v.toStringAsFixed(0),
                style: const TextStyle(color: Colors.white38, fontSize: 9),
              ),
            ),
          ),
          bottomTitles: AxisTitles(
            axisNameWidget: const Text('Wysokość (m)',
                style: TextStyle(color: Colors.white38, fontSize: 10)),
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 28,
              getTitlesWidget: (v, _) => Text(
                '${v.toInt()}',
                style: const TextStyle(color: Colors.white38, fontSize: 9),
              ),
            ),
          ),
          rightTitles: const AxisTitles(
              sideTitles: SideTitles(showTitles: false)),
          topTitles: const AxisTitles(
              sideTitles: SideTitles(showTitles: false)),
        ),
        minX: minAlt  - altRange  * 0.05,
        maxX: maxAlt  + altRange  * 0.05,
        minY: minDbfs - dbfsRange * 0.1,
        maxY: maxDbfs + dbfsRange * 0.1,
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: false,
            color: Colors.purpleAccent,
            barWidth: 2,
            dotData: FlDotData(
              show: true,
              getDotPainter: (_, __, ___, ____) => FlDotCirclePainter(
                radius: 3,
                color: Colors.purpleAccent,
                strokeWidth: 0,
              ),
            ),
            belowBarData: BarAreaData(
              show: true,
              color: Colors.purpleAccent.withOpacity(0.07),
            ),
          ),
        ],
        lineTouchData: LineTouchData(
          touchTooltipData: LineTouchTooltipData(
            getTooltipColor: (_) => const Color(0xFF21262D),
            getTooltipItems: (spots) => spots.map((s) => LineTooltipItem(
              '${s.y.toStringAsFixed(1)} dBFS\n${s.x.toStringAsFixed(0)} m',
              const TextStyle(color: Colors.purpleAccent, fontSize: 11),
            )).toList(),
          ),
        ),
      ),
    );
  }
}


class _HwBadge extends StatelessWidget {
  final bool active;
  const _HwBadge({required this.active});

  @override
  Widget build(BuildContext context) => Row(children: [
        Icon(Icons.circle,
            color: active ? Colors.redAccent : Colors.white24, size: 10),
        const SizedBox(width: 6),
        Text(
          active ? 'NADAJE' : 'CICHO',
          style: TextStyle(
            color: active ? Colors.redAccent : Colors.white38,
            fontWeight: FontWeight.bold,
            fontSize: 12,
          ),
        ),
      ]);
}


class _StatusCard extends StatelessWidget {
  final HfService hf;
  const _StatusCard({required this.hf});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: hf.hwActive
              ? Colors.redAccent.withOpacity(0.5)
              : Colors.white12,
          width: hf.hwActive ? 2 : 1,
        ),
      ),
      child: Row(
        children: [
          // big indicator circle
          Container(
            width: 60,
            height: 60,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: hf.hwActive
                  ? Colors.redAccent.withOpacity(0.15)
                  : Colors.white.withOpacity(0.05),
              border: Border.all(
                color: hf.hwActive ? Colors.redAccent : Colors.white24,
                width: 2,
              ),
            ),
            child: Icon(
              Icons.broadcast_on_personal,
              color: hf.hwActive ? Colors.redAccent : Colors.white24,
              size: 28,
            ),
          ),
          const SizedBox(width: 20),
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                hf.hwActive ? 'NADAWANIE' : 'WYŁĄCZONY',
                style: TextStyle(
                  color: hf.hwActive ? Colors.redAccent : Colors.white38,
                  fontWeight: FontWeight.bold,
                  fontSize: 18,
                ),
              ),
              const SizedBox(height: 4),
              if (hf.hwActive && hf.hwFreqHz > 0)
                Text(
                  '${(hf.hwFreqHz / 1e6).toStringAsFixed(4)} MHz',
                  style: const TextStyle(
                      color: Colors.white70, fontSize: 15),
                )
              else
                const Text('---',
                    style: TextStyle(color: Colors.white24, fontSize: 15)),
              const SizedBox(height: 2),
              Text(
                'RPi Ground: ${hf.hwActive ? "TX ON" : "TX OFF"}',
                style: const TextStyle(
                    color: Colors.white38, fontSize: 11),
              ),
            ],
          ),
        ],
      ),
    );
  }
}


class _TxToggle extends StatelessWidget {
  final bool active;
  final bool loading;
  final VoidCallback onStart;
  final VoidCallback onStop;

  const _TxToggle({
    required this.active,
    required this.loading,
    required this.onStart,
    required this.onStop,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      height: 56,
      child: ElevatedButton.icon(
        style: ElevatedButton.styleFrom(
          backgroundColor:
              active ? Colors.redAccent : Colors.greenAccent,
          foregroundColor: active ? Colors.white : Colors.black,
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12)),
          elevation: active ? 4 : 0,
        ),
        icon: loading
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                    strokeWidth: 2, color: Colors.white),
              )
            : Icon(active ? Icons.stop_circle : Icons.play_circle),
        label: Text(
          active ? 'WYŁĄCZ NADAJNIK' : 'WŁĄCZ NADAJNIK',
          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
        ),
        onPressed: loading ? null : (active ? onStop : onStart),
      ),
    );
  }
}


class _SectionBox extends StatelessWidget {
  final String title;
  final IconData icon;
  final Color color;
  final Widget child;

  const _SectionBox({
    required this.title,
    required this.icon,
    required this.color,
    required this.child,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withOpacity(0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Icon(icon, color: color, size: 18),
            const SizedBox(width: 8),
            Text(title,
                style: TextStyle(
                    color: color,
                    fontWeight: FontWeight.bold,
                    fontSize: 14)),
          ]),
          const SizedBox(height: 14),
          const Divider(color: Colors.white12, height: 1),
          const SizedBox(height: 14),
          child,
        ],
      ),
    );
  }
}
