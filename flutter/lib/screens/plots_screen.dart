import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/telemetry.dart';
import '../services/telemetry_service.dart';

class PlotsScreen extends StatelessWidget {
  const PlotsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final history = context.watch<TelemetryService>().history;

    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161B22),
        title: const Text('Wykresy', style: TextStyle(color: Colors.white)),
        actions: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            child: Text('${history.length} pkt',
                style: const TextStyle(color: Colors.white38, fontSize: 12)),
          ),
        ],
      ),
      body: history.isEmpty
          ? const Center(
              child: Text('Brak danych telemetrii',
                  style: TextStyle(color: Colors.white38)))
          : ListView(
              padding: const EdgeInsets.all(12),
              children: [
                _ChartCard(
                  title: 'Wysokość',
                  unit: 'm',
                  color1: Colors.cyanAccent,
                  color2: Colors.lightBlueAccent,
                  label1: 'GPS',
                  label2: 'Baro (MS5611)',
                  data1: history.map((t) => t.alt ?? 0).toList(),
                  data2: history.map((t) => t.msAlt).toList(),
                ),
                _ChartCard(
                  title: 'Temperatura',
                  unit: '°C',
                  color1: Colors.orangeAccent,
                  color2: Colors.deepOrangeAccent,
                  label1: 'BME280',
                  label2: 'MS5611',
                  data1: history.map((t) => t.bmeTemp).toList(),
                  data2: history.map((t) => t.msTemp).toList(),
                ),
                _ChartCard(
                  title: 'Ciśnienie',
                  unit: 'hPa',
                  color1: Colors.purpleAccent,
                  color2: Colors.deepPurpleAccent,
                  label1: 'BME280',
                  label2: 'MS5611',
                  data1: history.map((t) => t.bmePres).toList(),
                  data2: history.map((t) => t.msPres).toList(),
                ),
                _ChartCard(
                  title: 'Wilgotność',
                  unit: '%',
                  color1: Colors.blueAccent,
                  data1: history.map((t) => t.bmeHum).toList(),
                ),
                _ChartCard(
                  title: 'Orientacja — Roll / Pitch',
                  unit: '°',
                  color1: Colors.greenAccent,
                  color2: Colors.tealAccent,
                  label1: 'Roll',
                  label2: 'Pitch',
                  data1: history.map((t) => t.roll).toList(),
                  data2: history.map((t) => t.pitch).toList(),
                ),
                _ChartCard(
                  title: 'Kurs (Yaw)',
                  unit: '°',
                  color1: Colors.tealAccent,
                  data1: history.map((t) => t.yaw).toList(),
                ),
                _ChartCard(
                  title: 'Napięcie baterii',
                  unit: 'V',
                  color1: Colors.greenAccent,
                  data1: history.map((t) => t.voltage).toList(),
                  minY: 3.0,
                  maxY: 4.2,
                  dangerLine: 3.5,
                ),
                _ChartCard(
                  title: 'Prąd poboru',
                  unit: 'mA',
                  color1: Colors.yellowAccent,
                  data1: history.map((t) => t.currentMa).toList(),
                ),
                _ChartCard(
                  title: 'Moc',
                  unit: 'mW',
                  color1: Colors.amberAccent,
                  data1: history.map((t) => t.powerMw).toList(),
                ),
                _ChartCard(
                  title: 'LoRa RSSI',
                  unit: 'dBm',
                  color1: Colors.redAccent,
                  data1: history.map((t) => t.rssi.toDouble()).toList(),
                  dangerLine: -100,
                ),
                _ChartCard(
                  title: 'LoRa SNR',
                  unit: 'dB',
                  color1: Colors.pinkAccent,
                  data1: history.map((t) => t.snr).toList(),
                ),
                _ChartCard(
                  title: 'Satelity GPS',
                  unit: '',
                  color1: Colors.cyanAccent,
                  data1: history.map((t) => t.satellites.toDouble()).toList(),
                  minY: 0,
                  maxY: 16,
                ),
                _ChartCard(
                  title: 'Prędkość',
                  unit: 'km/h',
                  color1: Colors.lightGreenAccent,
                  data1: history.map((t) => t.speedKmh ?? 0).toList(),
                ),
              ],
            ),
    );
  }
}


class _ChartCard extends StatelessWidget {
  final String title;
  final String unit;
  final Color color1;
  final Color? color2;
  final String? label1;
  final String? label2;
  final List<double> data1;
  final List<double>? data2;
  final double? minY;
  final double? maxY;
  final double? dangerLine;

  const _ChartCard({
    required this.title,
    required this.unit,
    required this.color1,
    this.color2,
    this.label1,
    this.label2,
    required this.data1,
    this.data2,
    this.minY,
    this.maxY,
    this.dangerLine,
  });

  List<FlSpot> _spots(List<double> data) => data
      .asMap()
      .entries
      .map((e) => FlSpot(e.key.toDouble(), e.value))
      .toList();

  @override
  Widget build(BuildContext context) {
    if (data1.isEmpty) return const SizedBox.shrink();

    final spots1 = _spots(data1);
    final spots2 = data2 != null ? _spots(data2!) : null;

    final allVals = [...data1, ...?data2];
    final vMin = minY ?? (allVals.reduce((a, b) => a < b ? a : b) - 1);
    final vMax = maxY ?? (allVals.reduce((a, b) => a > b ? a : b) + 1);

    final bars = <LineChartBarData>[
      LineChartBarData(
        spots: spots1,
        isCurved: true,
        color: color1,
        barWidth: 2,
        dotData: const FlDotData(show: false),
        belowBarData: BarAreaData(show: true, color: color1.withOpacity(0.08)),
      ),
      if (spots2 != null)
        LineChartBarData(
          spots: spots2,
          isCurved: true,
          color: color2!,
          barWidth: 2,
          dotData: const FlDotData(show: false),
          belowBarData: BarAreaData(show: true, color: color2!.withOpacity(0.05)),
          dashArray: [4, 4],
        ),
    ];

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color1.withOpacity(0.2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // header
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(title,
                  style: TextStyle(
                      color: color1,
                      fontWeight: FontWeight.bold,
                      fontSize: 13)),
              Row(children: [
                if (label1 != null) _Legend(label1!, color1),
                if (label2 != null && color2 != null) ...[
                  const SizedBox(width: 10),
                  _Legend(label2!, color2!, dashed: true),
                ],
                if (unit.isNotEmpty) ...[
                  const SizedBox(width: 8),
                  Text(unit,
                      style: const TextStyle(
                          color: Colors.white38, fontSize: 11)),
                ],
              ]),
            ],
          ),
          const SizedBox(height: 2),
          // current value
          Text(
            '${data1.last.toStringAsFixed(unit == 'dBm' || unit == 'dB' ? 1 : 2)}$unit'
            '${spots2 != null && data2!.isNotEmpty ? '  /  ${data2!.last.toStringAsFixed(2)}$unit' : ''}',
            style: const TextStyle(color: Colors.white54, fontSize: 12),
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 140,
            child: LineChart(
              LineChartData(
                minY: vMin,
                maxY: vMax,
                gridData: FlGridData(
                  show: true,
                  getDrawingHorizontalLine: (_) =>
                      const FlLine(color: Color(0xFF21262D), strokeWidth: 1),
                  getDrawingVerticalLine: (_) =>
                      const FlLine(color: Color(0xFF21262D), strokeWidth: 1),
                ),
                titlesData: FlTitlesData(
                  leftTitles: AxisTitles(
                    sideTitles: SideTitles(
                      showTitles: true,
                      reservedSize: 46,
                      getTitlesWidget: (v, _) => Text(
                        v.toStringAsFixed(v.abs() >= 100 ? 0 : 1),
                        style: const TextStyle(
                            color: Colors.white24, fontSize: 9),
                      ),
                    ),
                  ),
                  bottomTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  rightTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                  topTitles: const AxisTitles(
                      sideTitles: SideTitles(showTitles: false)),
                ),
                borderData: FlBorderData(show: false),
                lineBarsData: bars,
                extraLinesData: dangerLine != null
                    ? ExtraLinesData(horizontalLines: [
                        HorizontalLine(
                          y: dangerLine!,
                          color: Colors.redAccent.withOpacity(0.5),
                          strokeWidth: 1,
                          dashArray: [6, 4],
                          label: HorizontalLineLabel(
                            show: true,
                            labelResolver: (_) =>
                                'limit ${dangerLine!.toStringAsFixed(1)}',
                            style: const TextStyle(
                                color: Colors.redAccent, fontSize: 9),
                          ),
                        ),
                      ])
                    : null,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Legend extends StatelessWidget {
  final String label;
  final Color color;
  final bool dashed;
  const _Legend(this.label, this.color, {this.dashed = false});

  @override
  Widget build(BuildContext context) => Row(children: [
        Container(
          width: 16,
          height: 2,
          color: dashed ? Colors.transparent : color,
          child: dashed
              ? Row(children: [
                  Container(width: 6, height: 2, color: color),
                  const SizedBox(width: 4),
                  Container(width: 6, height: 2, color: color),
                ])
              : null,
        ),
        const SizedBox(width: 4),
        Text(label,
            style: TextStyle(color: color.withOpacity(0.8), fontSize: 10)),
      ]);
}
