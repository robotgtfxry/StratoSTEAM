import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../services/pin_service.dart';
import '../services/settings_service.dart';

/// Returns true if the user is (or becomes) authenticated.
Future<bool> requirePin(BuildContext context) async {
  final pin = context.read<PinService>();
  if (pin.authenticated) return true;
  if (!context.mounted) return false;
  final ok = await showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (_) => const _PinDialog(),
  );
  return ok == true;
}

/// Two-step PIN change dialog (requires existing auth first).
Future<void> showChangePinDialog(BuildContext context) async {
  if (!await requirePin(context)) return;
  if (!context.mounted) return;
  final newPin = await showDialog<String>(
    context: context,
    barrierDismissible: false,
    builder: (_) => const _NewPinDialog(),
  );
  if (newPin != null && context.mounted) {
    await context.read<SettingsService>().setPin(newPin);
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('PIN został zmieniony'),
          backgroundColor: const Color(0xFF21262D),
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        ),
      );
    }
  }
}

// ── Verify existing PIN ────────────────────────────────────────────────────────

class _PinDialog extends StatefulWidget {
  const _PinDialog();
  @override
  State<_PinDialog> createState() => _PinDialogState();
}

class _PinDialogState extends State<_PinDialog>
    with SingleTickerProviderStateMixin {
  String _entered = '';
  bool _error = false;
  late AnimationController _shakeCtrl;
  late Animation<double> _shakeAnim;
  final _kbFocus = FocusNode();

  @override
  void initState() {
    super.initState();
    _shakeCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 450),
    );
    _shakeAnim = TweenSequence<double>([
      TweenSequenceItem(tween: Tween(begin: 0.0, end: -10.0), weight: 1),
      TweenSequenceItem(tween: Tween(begin: -10.0, end: 10.0), weight: 2),
      TweenSequenceItem(tween: Tween(begin: 10.0, end: -10.0), weight: 2),
      TweenSequenceItem(tween: Tween(begin: -10.0, end: 0.0), weight: 1),
    ]).animate(CurvedAnimation(parent: _shakeCtrl, curve: Curves.easeInOut));
    WidgetsBinding.instance.addPostFrameCallback((_) => _kbFocus.requestFocus());
  }

  @override
  void dispose() {
    _shakeCtrl.dispose();
    _kbFocus.dispose();
    super.dispose();
  }

  KeyEventResult _handleKey(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent) return KeyEventResult.ignored;
    final key = event.logicalKey;
    if (key == LogicalKeyboardKey.backspace || key == LogicalKeyboardKey.delete) {
      _onKey('⌫');
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.escape) {
      Navigator.pop(context, false);
      return KeyEventResult.handled;
    }
    final label = event.character;
    if (label != null && RegExp(r'^[0-9]$').hasMatch(label)) {
      _onKey(label);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  void _onKey(String key) {
    if (key == '⌫') {
      if (_entered.isNotEmpty) {
        setState(() {
          _entered = _entered.substring(0, _entered.length - 1);
          _error = false;
        });
      }
    } else if (_entered.length < 4) {
      setState(() {
        _entered += key;
        _error = false;
      });
      if (_entered.length == 4) _tryVerify();
    }
  }

  void _tryVerify() {
    final ok = context.read<PinService>().verify(_entered);
    if (ok) {
      Navigator.pop(context, true);
    } else {
      setState(() {
        _error = true;
        _entered = '';
      });
      _shakeCtrl.forward(from: 0);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Focus(
      focusNode: _kbFocus,
      onKeyEvent: _handleKey,
      child: _PinShell(
        title: 'Autoryzacja',
        subtitle: _error ? 'Nieprawidłowy PIN' : 'Wprowadź PIN',
        subtitleColor: _error ? Colors.redAccent : Colors.white38,
        entered: _entered,
        shakeAnim: _shakeAnim,
        isError: _error,
        onKey: _onKey,
        onCancel: () => Navigator.pop(context, false),
      ),
    );
  }
}

// ── Set new PIN (two-phase: enter + confirm) ───────────────────────────────────

class _NewPinDialog extends StatefulWidget {
  const _NewPinDialog();
  @override
  State<_NewPinDialog> createState() => _NewPinDialogState();
}

class _NewPinDialogState extends State<_NewPinDialog>
    with SingleTickerProviderStateMixin {
  String _entered = '';
  String? _firstPin;
  bool _error = false;
  late AnimationController _shakeCtrl;
  late Animation<double> _shakeAnim;
  final _kbFocus = FocusNode();

  @override
  void initState() {
    super.initState();
    _shakeCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 450),
    );
    _shakeAnim = TweenSequence<double>([
      TweenSequenceItem(tween: Tween(begin: 0.0, end: -10.0), weight: 1),
      TweenSequenceItem(tween: Tween(begin: -10.0, end: 10.0), weight: 2),
      TweenSequenceItem(tween: Tween(begin: 10.0, end: -10.0), weight: 2),
      TweenSequenceItem(tween: Tween(begin: -10.0, end: 0.0), weight: 1),
    ]).animate(CurvedAnimation(parent: _shakeCtrl, curve: Curves.easeInOut));
    WidgetsBinding.instance.addPostFrameCallback((_) => _kbFocus.requestFocus());
  }

  @override
  void dispose() {
    _shakeCtrl.dispose();
    _kbFocus.dispose();
    super.dispose();
  }

  KeyEventResult _handleKey(FocusNode node, KeyEvent event) {
    if (event is! KeyDownEvent) return KeyEventResult.ignored;
    final key = event.logicalKey;
    if (key == LogicalKeyboardKey.backspace || key == LogicalKeyboardKey.delete) {
      _onKey('⌫');
      return KeyEventResult.handled;
    }
    if (key == LogicalKeyboardKey.escape) {
      Navigator.pop(context, null);
      return KeyEventResult.handled;
    }
    final label = event.character;
    if (label != null && RegExp(r'^[0-9]$').hasMatch(label)) {
      _onKey(label);
      return KeyEventResult.handled;
    }
    return KeyEventResult.ignored;
  }

  void _onKey(String key) {
    if (key == '⌫') {
      if (_entered.isNotEmpty) {
        setState(() {
          _entered = _entered.substring(0, _entered.length - 1);
          _error = false;
        });
      }
    } else if (_entered.length < 4) {
      setState(() {
        _entered += key;
        _error = false;
      });
      if (_entered.length == 4) _next();
    }
  }

  void _next() {
    if (_firstPin == null) {
      setState(() {
        _firstPin = _entered;
        _entered = '';
      });
    } else {
      if (_entered == _firstPin) {
        Navigator.pop(context, _entered);
      } else {
        setState(() {
          _firstPin = null;
          _entered = '';
          _error = true;
        });
        _shakeCtrl.forward(from: 0);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final phase = _firstPin == null ? 1 : 2;
    return Focus(
      focusNode: _kbFocus,
      onKeyEvent: _handleKey,
      child: _PinShell(
        title: 'Zmień PIN',
        subtitle: _error
            ? 'Kody się nie zgadzają — spróbuj ponownie'
            : 'Wprowadź nowy PIN ($phase/2)',
        subtitleColor: _error ? Colors.redAccent : Colors.white38,
        entered: _entered,
        shakeAnim: _shakeAnim,
        isError: _error,
        onKey: _onKey,
        onCancel: () => Navigator.pop(context, null),
      ),
    );
  }
}

// ── Shared dialog shell ────────────────────────────────────────────────────────

class _PinShell extends StatelessWidget {
  final String title;
  final String subtitle;
  final Color subtitleColor;
  final String entered;
  final Animation<double> shakeAnim;
  final bool isError;
  final void Function(String) onKey;
  final VoidCallback onCancel;

  const _PinShell({
    required this.title,
    required this.subtitle,
    required this.subtitleColor,
    required this.entered,
    required this.shakeAnim,
    required this.isError,
    required this.onKey,
    required this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: const Color(0xFF161B22),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(18),
        side: BorderSide(color: Colors.cyanAccent.withValues(alpha: 0.3)),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 28, 20, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.lock_outline, color: Colors.cyanAccent, size: 30),
            const SizedBox(height: 10),
            Text(
              title,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 6),
            AnimatedSwitcher(
              duration: const Duration(milliseconds: 200),
              child: Text(
                subtitle,
                key: ValueKey(subtitle),
                style: TextStyle(color: subtitleColor, fontSize: 12),
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: 26),
            // PIN dots with shake animation
            AnimatedBuilder(
              animation: shakeAnim,
              builder: (_, child) => Transform.translate(
                offset: Offset(shakeAnim.value, 0),
                child: child,
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(4, (i) {
                  final filled = i < entered.length;
                  return AnimatedContainer(
                    duration: const Duration(milliseconds: 150),
                    margin: const EdgeInsets.symmetric(horizontal: 10),
                    width: 14,
                    height: 14,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      color: filled
                          ? (isError ? Colors.redAccent : Colors.cyanAccent)
                          : Colors.transparent,
                      border: Border.all(
                        color: filled
                            ? (isError ? Colors.redAccent : Colors.cyanAccent)
                            : Colors.white24,
                        width: 1.5,
                      ),
                    ),
                  );
                }),
              ),
            ),
            const SizedBox(height: 28),
            _buildNumpad(),
            const SizedBox(height: 4),
            TextButton(
              onPressed: onCancel,
              style: TextButton.styleFrom(foregroundColor: Colors.white38),
              child: const Text('Anuluj', style: TextStyle(fontSize: 12)),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNumpad() {
    const rows = [
      ['1', '2', '3'],
      ['4', '5', '6'],
      ['7', '8', '9'],
      ['', '0', '⌫'],
    ];
    return Column(
      children: rows.map((row) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: row
              .map((k) => _NumKey(
                    label: k,
                    onTap: k.isEmpty ? null : () => onKey(k),
                  ))
              .toList(),
        ),
      )).toList(),
    );
  }
}

class _NumKey extends StatelessWidget {
  final String label;
  final VoidCallback? onTap;

  const _NumKey({required this.label, this.onTap});

  @override
  Widget build(BuildContext context) {
    final isBack = label == '⌫';
    final isEmpty = label.isEmpty;
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 10),
        width: 62,
        height: 62,
        decoration: isEmpty
            ? null
            : BoxDecoration(
                shape: BoxShape.circle,
                color: const Color(0xFF21262D),
                border: Border.all(color: Colors.white12),
              ),
        child: Center(
          child: isEmpty
              ? null
              : isBack
                  ? const Icon(Icons.backspace_outlined,
                      color: Colors.white54, size: 20)
                  : Text(
                      label,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 22,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
        ),
      ),
    );
  }
}
