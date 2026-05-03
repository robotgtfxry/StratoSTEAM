import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'services/settings_service.dart';
import 'services/telemetry_service.dart';
import 'services/hf_service.dart';
import 'services/command_service.dart';
import 'services/rpi_power_service.dart';
import 'services/terminal_service.dart';
import 'screens/dashboard_screen.dart';
import 'screens/map_screen.dart';
import 'screens/transmitter_screen.dart';
import 'screens/plots_screen.dart';
import 'screens/settings_screen.dart';
import 'screens/terminal_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final settings = SettingsService();
  await settings.load();
  runApp(
    MultiProvider(
      providers: [
        ChangeNotifierProvider.value(value: settings),
        ChangeNotifierProxyProvider<SettingsService, TelemetryService>(
          create: (ctx) => TelemetryService(ctx.read<SettingsService>()),
          update: (_, s, prev) => prev ?? TelemetryService(s),
        ),
        ChangeNotifierProxyProvider<SettingsService, HfService>(
          create: (ctx) => HfService(ctx.read<SettingsService>()),
          update: (_, s, prev) => prev ?? HfService(s),
        ),
        ChangeNotifierProxyProvider<SettingsService, CommandService>(
          create: (ctx) => CommandService(ctx.read<SettingsService>()),
          update: (_, s, prev) => prev ?? CommandService(s),
        ),
        ChangeNotifierProxyProvider<SettingsService, RpiPowerService>(
          create: (ctx) => RpiPowerService(ctx.read<SettingsService>()),
          update: (_, s, prev) => prev ?? RpiPowerService(s),
        ),
        ChangeNotifierProxyProvider<SettingsService, TerminalService>(
          create: (ctx) => TerminalService(ctx.read<SettingsService>()),
          update: (_, s, prev) => prev ?? TerminalService(s),
        ),
      ],
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
      home: const _Shell(),
    );
  }
}

class _Shell extends StatefulWidget {
  const _Shell();

  @override
  State<_Shell> createState() => _ShellState();
}

class _ShellState extends State<_Shell> {
  int _idx = 0;

  static const _screens = [
    DashboardScreen(),
    MapScreen(),
    PlotsScreen(),
    TransmitterScreen(),
    TerminalScreen(),
    SettingsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    final telemetry = context.watch<TelemetryService>();
    final hf = context.watch<HfService>();

    return Scaffold(
      body: IndexedStack(index: _idx, children: _screens),
      bottomNavigationBar: NavigationBar(
        backgroundColor: const Color(0xFF161B22),
        indicatorColor: Colors.cyanAccent.withOpacity(0.15),
        selectedIndex: _idx,
        onDestinationSelected: (i) => setState(() => _idx = i),
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard, color: Colors.cyanAccent),
            label: 'Dashboard',
          ),
          NavigationDestination(
            icon: Badge(
              isLabelVisible: telemetry.latest?.gpsFix == true,
              backgroundColor: Colors.greenAccent,
              child: const Icon(Icons.map_outlined),
            ),
            selectedIcon: const Icon(Icons.map, color: Colors.cyanAccent),
            label: 'Mapa',
          ),
          const NavigationDestination(
            icon: Icon(Icons.show_chart_outlined),
            selectedIcon: Icon(Icons.show_chart, color: Colors.cyanAccent),
            label: 'Wykresy',
          ),
          NavigationDestination(
            icon: Badge(
              isLabelVisible: hf.hwActive,
              backgroundColor: Colors.redAccent,
              child: const Icon(Icons.broadcast_on_personal_outlined),
            ),
            selectedIcon: const Icon(Icons.broadcast_on_personal,
                color: Colors.cyanAccent),
            label: 'Nadajnik',
          ),
          const NavigationDestination(
            icon: Icon(Icons.terminal_outlined),
            selectedIcon: Icon(Icons.terminal, color: Colors.cyanAccent),
            label: 'Terminal',
          ),
          const NavigationDestination(
            icon: Icon(Icons.settings_outlined),
            selectedIcon: Icon(Icons.settings, color: Colors.cyanAccent),
            label: 'Ustawienia',
          ),
        ],
      ),
    );
  }
}
