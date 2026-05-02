import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/telemetry_service.dart';
import '../widgets/info_card.dart';
import '../widgets/altitude_chart.dart';
import '../widgets/map_view.dart';
import '../widgets/attitude_indicator.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final svc = context.watch<TelemetryService>();
    final t = svc.latest;

    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161B22),
        title: const Text('StratoSTEAM', style: TextStyle(color: Colors.white)),
        actions: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: Icon(
              Icons.circle,
              color: svc.connected ? Colors.greenAccent : Colors.red,
              size: 14,
            ),
          ),
        ],
      ),
      body: t == null
          ? const Center(
              child: Text('Waiting for telemetry…', style: TextStyle(color: Colors.white54)),
            )
          : SingleChildScrollView(
              padding: const EdgeInsets.all(12),
              child: Column(
                children: [
                  // top row — GPS status bar
                  _StatusBar(t: t),
                  const SizedBox(height: 12),
                  // map + attitude side by side (on wide screens)
                  LayoutBuilder(builder: (ctx, bc) {
                    final wide = bc.maxWidth > 700;
                    final map = SizedBox(height: 280, child: MapView(history: svc.history));
                    final att = SizedBox(height: 280, child: AttitudeIndicator(roll: t.roll, pitch: t.pitch));
                    if (wide) {
                      return Row(children: [
                        Expanded(child: map),
                        const SizedBox(width: 12),
                        SizedBox(width: 280, child: att),
                      ]);
                    }
                    return Column(children: [map, const SizedBox(height: 12), att]);
                  }),
                  const SizedBox(height: 12),
                  // sensor cards
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      InfoCard(
                        label: 'Altitude (GPS)',
                        value: '${t.alt?.toStringAsFixed(0) ?? '--'} m',
                        icon: Icons.arrow_upward,
                        color: Colors.cyanAccent,
                      ),
                      InfoCard(
                        label: 'Altitude (baro)',
                        value: '${t.msAlt.toStringAsFixed(0)} m',
                        icon: Icons.compress,
                        color: Colors.lightBlueAccent,
                      ),
                      InfoCard(
                        label: 'Temperature',
                        value: '${t.bmeTemp.toStringAsFixed(1)} °C',
                        icon: Icons.thermostat,
                        color: Colors.orangeAccent,
                      ),
                      InfoCard(
                        label: 'Pressure',
                        value: '${t.msPres.toStringAsFixed(1)} hPa',
                        icon: Icons.speed,
                        color: Colors.purpleAccent,
                      ),
                      InfoCard(
                        label: 'Humidity',
                        value: '${t.bmeHum.toStringAsFixed(1)} %',
                        icon: Icons.water_drop,
                        color: Colors.blueAccent,
                      ),
                      InfoCard(
                        label: 'Battery',
                        value: '${t.voltage.toStringAsFixed(2)} V',
                        icon: Icons.battery_full,
                        color: t.voltage > 3.6 ? Colors.greenAccent : Colors.redAccent,
                      ),
                      InfoCard(
                        label: 'Current',
                        value: '${t.currentMa.toStringAsFixed(0)} mA',
                        icon: Icons.bolt,
                        color: Colors.yellowAccent,
                      ),
                      InfoCard(
                        label: 'LoRa RSSI',
                        value: '${t.rssi} dBm',
                        icon: Icons.signal_cellular_alt,
                        color: t.rssi > -100 ? Colors.greenAccent : Colors.redAccent,
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  SizedBox(height: 200, child: AltitudeChart(history: svc.history)),
                ],
              ),
            ),
    );
  }
}


class _StatusBar extends StatelessWidget {
  final dynamic t;
  const _StatusBar({required this.t});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF161B22),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceAround,
        children: [
          _Stat('SEQ', '${t.seq}'),
          _Stat('SAT', '${t.satellites}'),
          _Stat('FIX', t.gpsFix ? 'YES' : 'NO', color: t.gpsFix ? Colors.greenAccent : Colors.redAccent),
          _Stat('SPD', '${t.speedKmh?.toStringAsFixed(1) ?? '--'} km/h'),
          _Stat('HDG', '${t.yaw.toStringAsFixed(0)}°'),
        ],
      ),
    );
  }
}

class _Stat extends StatelessWidget {
  final String label, value;
  final Color color;
  const _Stat(this.label, this.value, {this.color = Colors.white});

  @override
  Widget build(BuildContext context) => Column(
        children: [
          Text(label, style: const TextStyle(color: Colors.white38, fontSize: 11)),
          Text(value, style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 15)),
        ],
      );
}
