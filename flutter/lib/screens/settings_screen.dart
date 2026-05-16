import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/settings_service.dart';
import '../services/telemetry_service.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  late TextEditingController _serverCtrl;
  late TextEditingController _apiKeyCtrl;
  late TextEditingController _callsignCtrl;
  late TextEditingController _minVoltCtrl;
  late TextEditingController _loraFreqCtrl;
  late int _minSats;
  late int _loraSf;
  bool _apiKeyVisible = false;
  bool _saved = false;

  @override
  void initState() {
    super.initState();
    final s = context.read<SettingsService>();
    _serverCtrl   = TextEditingController(text: s.serverUrl);
    _apiKeyCtrl   = TextEditingController(text: s.apiKey);
    _callsignCtrl = TextEditingController(text: s.callsign);
    _minVoltCtrl  = TextEditingController(text: s.minVoltage.toStringAsFixed(1));
    _loraFreqCtrl = TextEditingController(text: s.loraFreq.toStringAsFixed(1));
    _minSats = s.minSats;
    _loraSf  = s.loraSf;
  }

  @override
  void dispose() {
    _serverCtrl.dispose();
    _apiKeyCtrl.dispose();
    _callsignCtrl.dispose();
    _minVoltCtrl.dispose();
    _loraFreqCtrl.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    await context.read<SettingsService>().save(
      serverUrl:  _serverCtrl.text.trim(),
      apiKey:     _apiKeyCtrl.text.trim(),
      callsign:   _callsignCtrl.text.trim().toUpperCase(),
      minVoltage: double.tryParse(_minVoltCtrl.text) ?? 3.5,
      minSats:    _minSats,
      loraFreq:   double.tryParse(_loraFreqCtrl.text) ?? 433.0,
      loraSf:     _loraSf,
    );
    // reconnect telemetry with new server URL
    context.read<TelemetryService>().reconnect();
    setState(() => _saved = true);
    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) setState(() => _saved = false);
    });
  }

  Future<void> _reset() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: const Color(0xFF161B22),
        title: const Text('Reset ustawień', style: TextStyle(color: Colors.white)),
        content: const Text('Przywrócić domyślne wartości?', style: TextStyle(color: Colors.white70)),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Anuluj')),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Reset', style: TextStyle(color: Colors.redAccent)),
          ),
        ],
      ),
    );
    if (ok == true) {
      await context.read<SettingsService>().reset();
      final s = context.read<SettingsService>();
      setState(() {
        _serverCtrl.text   = s.serverUrl;
        _apiKeyCtrl.text   = s.apiKey;
        _callsignCtrl.text = s.callsign;
        _minVoltCtrl.text  = s.minVoltage.toStringAsFixed(1);
        _loraFreqCtrl.text = s.loraFreq.toStringAsFixed(1);
        _minSats = s.minSats;
        _loraSf  = s.loraSf;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final svc = context.watch<TelemetryService>();

    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161B22),
        title: const Text('Ustawienia', style: TextStyle(color: Colors.white)),
        actions: [
          if (_saved)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 16),
              child: Icon(Icons.check_circle, color: Colors.greenAccent),
            ),
          IconButton(
            icon: const Icon(Icons.restart_alt, color: Colors.white54),
            tooltip: 'Reset do domyślnych',
            onPressed: _reset,
          ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [

          // ── Połączenie ──────────────────────────────────────────
          _Section(
            title: 'Połączenie z serwerem',
            icon: Icons.cloud,
            color: Colors.cyanAccent,
            children: [
              _StatusTile(connected: svc.connected),
              const SizedBox(height: 12),
              _Field(
                label: 'URL serwera',
                hint: 'http://twoj-serwer.pl:8000',
                controller: _serverCtrl,
                icon: Icons.link,
              ),
              const SizedBox(height: 12),
              _Field(
                label: 'API Key',
                hint: 'sekretny-klucz',
                controller: _apiKeyCtrl,
                icon: Icons.key,
                obscure: !_apiKeyVisible,
                suffix: IconButton(
                  icon: Icon(
                    _apiKeyVisible ? Icons.visibility_off : Icons.visibility,
                    color: Colors.white38,
                    size: 18,
                  ),
                  onPressed: () => setState(() => _apiKeyVisible = !_apiKeyVisible),
                ),
              ),
            ],
          ),
          const SizedBox(height: 16),

          // ── RPi Ground ──────────────────────────────────────────
          _Section(
            title: 'RPi Ground',
            icon: Icons.router,
            color: Colors.greenAccent,
            children: [
              _InfoTile(
                label: 'WebSocket URL (auto)',
                value: context.watch<SettingsService>().wsUrl,
              ),
              const SizedBox(height: 12),
              _InfoTile(
                label: 'Endpoint telemetrii',
                value: '${context.watch<SettingsService>().serverUrl}/api/telemetry',
              ),
            ],
          ),
          const SizedBox(height: 16),

          // ── LoRa ────────────────────────────────────────────────
          _Section(
            title: 'LoRa SX1278',
            icon: Icons.signal_cellular_alt,
            color: Colors.purpleAccent,
            children: [
              _Field(
                label: 'Częstotliwość (MHz)',
                hint: '433.0',
                controller: _loraFreqCtrl,
                icon: Icons.radio,
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Spreading Factor (SF)',
                      style: TextStyle(color: Colors.white70, fontSize: 14)),
                  Row(
                    children: [
                      IconButton(
                        icon: const Icon(Icons.remove, color: Colors.white54),
                        onPressed: _loraSf > 6 ? () => setState(() => _loraSf--) : null,
                      ),
                      Text('SF$_loraSf',
                          style: const TextStyle(color: Colors.purpleAccent,
                              fontWeight: FontWeight.bold, fontSize: 16)),
                      IconButton(
                        icon: const Icon(Icons.add, color: Colors.white54),
                        onPressed: _loraSf < 12 ? () => setState(() => _loraSf++) : null,
                      ),
                    ],
                  ),
                ],
              ),
              _HintText('Wyższy SF = większy zasięg, wolniejsza transmisja'),
            ],
          ),
          const SizedBox(height: 16),

          // ── Nośna 144 MHz ───────────────────────────────────────
          _Section(
            title: 'Nośna 144.800 MHz',
            icon: Icons.broadcast_on_personal,
            color: Colors.orangeAccent,
            children: [
              _Field(
                label: 'Znak wywoławczy',
                hint: 'SP0STR-11',
                controller: _callsignCtrl,
                icon: Icons.badge,
              ),
              _HintText('Używany do logowania eksperymentu jonosferycznego'),
            ],
          ),
          const SizedBox(height: 16),

          // ── Alerty ──────────────────────────────────────────────
          _Section(
            title: 'Alerty',
            icon: Icons.notifications_active,
            color: Colors.redAccent,
            children: [
              _Field(
                label: 'Min. napięcie baterii (V)',
                hint: '3.5',
                controller: _minVoltCtrl,
                icon: Icons.battery_alert,
                keyboardType: TextInputType.number,
              ),
              const SizedBox(height: 16),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Min. satelity GPS',
                      style: TextStyle(color: Colors.white70, fontSize: 14)),
                  Row(
                    children: [
                      IconButton(
                        icon: const Icon(Icons.remove, color: Colors.white54),
                        onPressed: _minSats > 1 ? () => setState(() => _minSats--) : null,
                      ),
                      Text('$_minSats',
                          style: const TextStyle(color: Colors.redAccent,
                              fontWeight: FontWeight.bold, fontSize: 16)),
                      IconButton(
                        icon: const Icon(Icons.add, color: Colors.white54),
                        onPressed: _minSats < 12 ? () => setState(() => _minSats++) : null,
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
          const SizedBox(height: 24),

          // ── Zapisz ──────────────────────────────────────────────
          SizedBox(
            width: double.infinity,
            height: 50,
            child: ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.cyanAccent,
                foregroundColor: Colors.black,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              ),
              icon: const Icon(Icons.save),
              label: const Text('Zapisz i połącz ponownie',
                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
              onPressed: _save,
            ),
          ),
          const SizedBox(height: 32),
        ],
      ),
    );
  }
}


// ── Reusable widgets ──────────────────────────────────────────────────────────

class _Section extends StatelessWidget {
  final String title;
  final IconData icon;
  final Color color;
  final List<Widget> children;

  const _Section({
    required this.title,
    required this.icon,
    required this.color,
    required this.children,
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
                    color: color, fontWeight: FontWeight.bold, fontSize: 14)),
          ]),
          const SizedBox(height: 14),
          const Divider(color: Colors.white12, height: 1),
          const SizedBox(height: 14),
          ...children,
        ],
      ),
    );
  }
}

class _Field extends StatelessWidget {
  final String label;
  final String hint;
  final TextEditingController controller;
  final IconData icon;
  final bool obscure;
  final Widget? suffix;
  final TextInputType? keyboardType;

  const _Field({
    required this.label,
    required this.hint,
    required this.controller,
    required this.icon,
    this.obscure = false,
    this.suffix,
    this.keyboardType,
  });

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      obscureText: obscure,
      keyboardType: keyboardType,
      style: const TextStyle(color: Colors.white, fontSize: 14),
      decoration: InputDecoration(
        labelText: label,
        hintText: hint,
        labelStyle: const TextStyle(color: Colors.white54),
        hintStyle: const TextStyle(color: Colors.white24),
        prefixIcon: Icon(icon, color: Colors.white38, size: 18),
        suffixIcon: suffix,
        filled: true,
        fillColor: const Color(0xFF0D1117),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Colors.white12),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Colors.white12),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
          borderSide: const BorderSide(color: Colors.cyanAccent),
        ),
      ),
    );
  }
}

class _InfoTile extends StatelessWidget {
  final String label;
  final String value;
  const _InfoTile({required this.label, required this.value});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.white38, fontSize: 11)),
        const SizedBox(height: 4),
        Text(value,
            style: const TextStyle(
                color: Colors.white70, fontSize: 13, fontFamily: 'monospace')),
      ],
    );
  }
}

class _StatusTile extends StatelessWidget {
  final bool connected;
  const _StatusTile({required this.connected});

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Icon(
        connected ? Icons.wifi : Icons.wifi_off,
        color: connected ? Colors.greenAccent : Colors.redAccent,
        size: 18,
      ),
      const SizedBox(width: 8),
      Text(
        connected ? 'Połączono z serwerem' : 'Brak połączenia',
        style: TextStyle(
          color: connected ? Colors.greenAccent : Colors.redAccent,
          fontSize: 13,
          fontWeight: FontWeight.w500,
        ),
      ),
    ]);
  }
}

class _HintText extends StatelessWidget {
  final String text;
  const _HintText(this.text);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 6),
      child: Text(text, style: const TextStyle(color: Colors.white24, fontSize: 11)),
    );
  }
}
