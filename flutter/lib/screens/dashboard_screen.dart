import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/telemetry_service.dart';
import '../services/rpi_power_service.dart';
import '../widgets/info_card.dart';
import '../widgets/altitude_chart.dart';
import '../widgets/map_view.dart';
import '../widgets/attitude_indicator.dart';
import '../widgets/control_panel.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final svc = context.watch<TelemetryService>();
    final rpi = context.watch<RpiPowerService>();
    final t = svc.latest;

    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161B22),
        title: const Text('StratoSTEAM', style: TextStyle(color: Colors.white)),
        actions: [
          // RPi status chip
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 14),
            child: _RpiChip(running: rpi.rpiRunning),
          ),
          const SizedBox(width: 8),
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
      body: SingleChildScrollView(
              padding: const EdgeInsets.all(12),
              child: Column(
                children: [
                  // GPS status bar (-- gdy brak danych)
                  _StatusBar(t: t),
                  const SizedBox(height: 12),

                  // mapa + sztuczny horyzont obok siebie
                  LayoutBuilder(builder: (ctx, bc) {
                    final roll  = t?.roll  ?? 0.0;
                    final pitch = t?.pitch ?? 0.0;
                    final wide  = bc.maxWidth > 700;
                    final map = SizedBox(height: 300, child: MapView(history: svc.history));
                    final att = SizedBox(
                      height: 300,
                      child: AttitudeIndicator(roll: roll, pitch: pitch),
                    );
                    if (wide) {
                      return Row(children: [
                        Expanded(child: map),
                        const SizedBox(width: 12),
                        SizedBox(width: 300, child: att),
                      ]);
                    }
                    return Column(children: [att, const SizedBox(height: 12), map]);
                  }),
                  const SizedBox(height: 12),

                  // karty czujników (-- gdy brak danych)
                  Wrap(
                    spacing: 12,
                    runSpacing: 12,
                    children: [
                      InfoCard(
                        label: 'Altitude GPS',
                        value: t != null ? '${t.alt?.toStringAsFixed(0) ?? '--'} m' : '-- m',
                        icon: Icons.arrow_upward,
                        color: Colors.cyanAccent,
                      ),
                      InfoCard(
                        label: 'Altitude baro',
                        value: t != null ? '${t.msAlt.toStringAsFixed(0)} m' : '-- m',
                        icon: Icons.compress,
                        color: Colors.lightBlueAccent,
                      ),
                      InfoCard(
                        label: 'Temperatura',
                        value: t != null ? '${t.bmeTemp.toStringAsFixed(1)} °C' : '-- °C',
                        icon: Icons.thermostat,
                        color: Colors.orangeAccent,
                      ),
                      InfoCard(
                        label: 'Ciśnienie',
                        value: t != null ? '${t.msPres.toStringAsFixed(1)} hPa' : '-- hPa',
                        icon: Icons.speed,
                        color: Colors.purpleAccent,
                      ),
                      InfoCard(
                        label: 'Wilgotność',
                        value: t != null ? '${t.bmeHum.toStringAsFixed(1)} %' : '-- %',
                        icon: Icons.water_drop,
                        color: Colors.blueAccent,
                      ),
                      InfoCard(
                        label: 'Bateria',
                        value: t != null ? '${t.voltage.toStringAsFixed(2)} V' : '-- V',
                        icon: Icons.battery_full,
                        color: (t?.voltage ?? 4.0) > 3.6 ? Colors.greenAccent : Colors.redAccent,
                      ),
                      InfoCard(
                        label: 'Prąd',
                        value: t != null ? '${t.currentMa.toStringAsFixed(0)} mA' : '-- mA',
                        icon: Icons.bolt,
                        color: Colors.yellowAccent,
                      ),
                      InfoCard(
                        label: 'LoRa RSSI',
                        value: t != null ? '${t.rssi} dBm' : '-- dBm',
                        icon: Icons.signal_cellular_alt,
                        color: (t?.rssi ?? -50) > -100 ? Colors.greenAccent : Colors.redAccent,
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  SizedBox(height: 200, child: AltitudeChart(history: svc.history)),
                  const SizedBox(height: 12),
                  const ControlPanel(),
                ],
              ),
            ),
    );
  }
}


class _RpiChip extends StatelessWidget {
  final bool running;
  const _RpiChip({required this.running});

  @override
  Widget build(BuildContext context) => Row(children: [
        Icon(Icons.circle,
            color: running ? Colors.greenAccent : Colors.orangeAccent,
            size: 8),
        const SizedBox(width: 5),
        Text(
          running ? 'RPi ON' : 'RPi OFF',
          style: TextStyle(
            color: running ? Colors.greenAccent : Colors.orangeAccent,
            fontSize: 11,
            fontWeight: FontWeight.bold,
          ),
        ),
      ]);
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
          _Stat('SEQ', t != null ? '${t.seq}' : '--'),
          _Stat('SAT', t != null ? '${t.satellites}' : '--'),
          _Stat('FIX', t != null ? (t.gpsFix ? 'YES' : 'NO') : '--',
              color: t?.gpsFix == true ? Colors.greenAccent : Colors.redAccent),
          _Stat('SPD', t != null ? '${t.speedKmh?.toStringAsFixed(1) ?? '--'} km/h' : '-- km/h'),
          _Stat('HDG', t != null ? '${t.yaw.toStringAsFixed(0)}°' : '--°'),
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
