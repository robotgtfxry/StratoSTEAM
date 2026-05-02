import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'services/telemetry_service.dart';
import 'screens/dashboard_screen.dart';

void main() {
  runApp(
    ChangeNotifierProvider(
      create: (_) => TelemetryService(),
      child: const StratoSteamApp(),
    ),
  );
}

class StratoSteamApp extends StatelessWidget {
  const StratoSteamApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'StratoSTEAM',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark().copyWith(
        scaffoldBackgroundColor: const Color(0xFF0D1117),
        colorScheme: const ColorScheme.dark(primary: Colors.cyanAccent),
      ),
      home: const DashboardScreen(),
    );
  }
}
