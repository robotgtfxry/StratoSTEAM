import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import '../services/terminal_service.dart';

class TerminalScreen extends StatefulWidget {
  const TerminalScreen({super.key});

  @override
  State<TerminalScreen> createState() => _TerminalScreenState();
}

class _TerminalScreenState extends State<TerminalScreen> {
  final _ctrl    = TextEditingController();
  final _scroll  = ScrollController();
  final _focus   = FocusNode();
  final List<String> _history = [];
  int _histIdx = -1;

  @override
  void dispose() {
    _ctrl.dispose();
    _scroll.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _submit(TerminalService svc) {
    final text = _ctrl.text.trim();
    if (text.isEmpty) return;
    _history.insert(0, text);
    _histIdx = -1;
    _ctrl.clear();
    svc.run(text);
    _scrollToBottom();
    _focus.requestFocus();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 120),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Color _msgColor(MsgType t) => switch (t) {
        MsgType.input  => Colors.cyanAccent,
        MsgType.ok     => Colors.greenAccent,
        MsgType.error  => Colors.redAccent,
        MsgType.info   => Colors.white54,
        MsgType.system => Colors.amberAccent,
      };

  @override
  Widget build(BuildContext context) {
    final svc = context.watch<TerminalService>();

    // Auto-scroll na nową wiadomość
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients &&
          _scroll.position.maxScrollExtent > 0 &&
          _scroll.position.pixels > _scroll.position.maxScrollExtent - 200) {
        _scroll.jumpTo(_scroll.position.maxScrollExtent);
      }
    });

    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161B22),
        title: Row(children: [
          const Icon(Icons.terminal, color: Colors.cyanAccent, size: 18),
          const SizedBox(width: 8),
          const Text('Terminal LoRa',
              style: TextStyle(color: Colors.white, fontSize: 16)),
          const Spacer(),
          // przycisk clear
          IconButton(
            icon: const Icon(Icons.delete_outline, color: Colors.white38, size: 20),
            tooltip: 'Wyczyść',
            onPressed: () => svc.run('clear'),
          ),
        ]),
      ),
      body: Column(
        children: [
          // ── Log ──────────────────────────────────────────────────────────────
          Expanded(
            child: ListView.builder(
              controller: _scroll,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              itemCount: svc.log.length,
              itemBuilder: (_, i) {
                final msg = svc.log[i];
                return Padding(
                  padding: const EdgeInsets.symmetric(vertical: 1),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // timestamp
                      Text(
                        '${msg.time.hour.toString().padLeft(2, '0')}:'
                        '${msg.time.minute.toString().padLeft(2, '0')}:'
                        '${msg.time.second.toString().padLeft(2, '0')} ',
                        style: const TextStyle(
                            color: Colors.white24,
                            fontSize: 11,
                            fontFamily: 'monospace'),
                      ),
                      // treść
                      Expanded(
                        child: Text(
                          msg.text,
                          style: TextStyle(
                            color: _msgColor(msg.type),
                            fontSize: 13,
                            fontFamily: 'monospace',
                            fontWeight: msg.type == MsgType.input
                                ? FontWeight.bold
                                : FontWeight.normal,
                          ),
                        ),
                      ),
                    ],
                  ),
                );
              },
            ),
          ),

          // ── Divider ───────────────────────────────────────────────────────────
          const Divider(color: Colors.white12, height: 1),

          // ── Input ─────────────────────────────────────────────────────────────
          Container(
            color: const Color(0xFF161B22),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(children: [
              const Text('> ',
                  style: TextStyle(
                      color: Colors.cyanAccent,
                      fontFamily: 'monospace',
                      fontSize: 15,
                      fontWeight: FontWeight.bold)),
              Expanded(
                child: KeyboardListener(
                  focusNode: FocusNode(),
                  onKeyEvent: (e) {
                    if (e is KeyDownEvent) {
                      if (e.logicalKey == LogicalKeyboardKey.arrowUp) {
                        if (_history.isNotEmpty &&
                            _histIdx < _history.length - 1) {
                          _histIdx++;
                          _ctrl.text = _history[_histIdx];
                          _ctrl.selection = TextSelection.fromPosition(
                              TextPosition(offset: _ctrl.text.length));
                        }
                      } else if (e.logicalKey == LogicalKeyboardKey.arrowDown) {
                        if (_histIdx > 0) {
                          _histIdx--;
                          _ctrl.text = _history[_histIdx];
                          _ctrl.selection = TextSelection.fromPosition(
                              TextPosition(offset: _ctrl.text.length));
                        } else if (_histIdx == 0) {
                          _histIdx = -1;
                          _ctrl.clear();
                        }
                      }
                    }
                  },
                  child: TextField(
                    controller: _ctrl,
                    focusNode: _focus,
                    autofocus: true,
                    style: const TextStyle(
                        color: Colors.white,
                        fontFamily: 'monospace',
                        fontSize: 14),
                    decoration: const InputDecoration(
                      isDense: true,
                      border: InputBorder.none,
                      hintText: 'buzzer on  /  led #ff0000  /  rpi off  /  help',
                      hintStyle: TextStyle(
                          color: Colors.white24,
                          fontFamily: 'monospace',
                          fontSize: 12),
                    ),
                    onSubmitted: (_) => _submit(svc),
                    textInputAction: TextInputAction.send,
                  ),
                ),
              ),
              IconButton(
                icon: const Icon(Icons.send, color: Colors.cyanAccent, size: 20),
                onPressed: () => _submit(svc),
              ),
            ]),
          ),

          // bezpieczny margines na system navigation bar
          SizedBox(height: MediaQuery.of(context).padding.bottom),
        ],
      ),
    );
  }
}
