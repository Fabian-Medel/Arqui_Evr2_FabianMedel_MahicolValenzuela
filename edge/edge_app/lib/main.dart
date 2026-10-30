import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

// Pantalla del nodo. La camara, el reconocimiento y la base cifrada viven en edge_service.py.
const service = 'http://127.0.0.1:8001';

void main() => runApp(
  MaterialApp(
    title: 'SAAD-Campus · Nodo',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: const Color(0xFF0F1626),
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xFF2764E7),
        brightness: Brightness.dark,
      ),
      fontFamily: 'Segoe UI',
    ),
    home: const NodeScreen(),
  ),
);

class NodeScreen extends StatefulWidget {
  const NodeScreen({super.key});
  @override
  State<NodeScreen> createState() => _NodeScreenState();
}

class _NodeScreenState extends State<NodeScreen> {
  static const green = Color(0xFF1FA67A);
  static const red = Color(0xFFD95454);
  static const amber = Color(0xFFE0A63A);
  static const panel = Color(0xFF172036);
  static const muted = Color(0xFF8A96AD);

  Map<String, dynamic>? status;
  Uint8List? frame;
  bool reachable = true, busy = false, disposed = false;
  String unlockError = '';
  final password = TextEditingController();
  Timer? poll;

  @override
  void initState() {
    super.initState();
    poll = Timer.periodic(
      const Duration(milliseconds: 500),
      (_) => refreshStatus(),
    );
    refreshStatus();
    frameLoop();
  }

  @override
  void dispose() {
    disposed = true;
    poll?.cancel();
    password.dispose();
    super.dispose();
  }

  Future<void> refreshStatus() async {
    try {
      final response = await http
          .get(Uri.parse('$service/status'))
          .timeout(const Duration(seconds: 2));
      if (!mounted) return;
      setState(() {
        status = jsonDecode(utf8.decode(response.bodyBytes));
        reachable = true;
      });
    } catch (_) {
      if (mounted) setState(() => reachable = false);
    }
  }

  // Pide el siguiente cuadro solo cuando llego el anterior, para no acumular solicitudes.
  Future<void> frameLoop() async {
    while (!disposed) {
      try {
        if (reachable && status?['locked'] == false) {
          final response = await http
              .get(Uri.parse('$service/frame.jpg'))
              .timeout(const Duration(seconds: 2));
          if (response.statusCode == 200 && mounted) {
            setState(() => frame = response.bodyBytes);
          }
        }
      } catch (_) {}
      await Future<void>.delayed(const Duration(milliseconds: 80));
    }
  }

  Future<void> post(String path, [Map<String, dynamic>? body]) async {
    final response = await http
        .post(
          Uri.parse('$service$path'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body ?? {}),
        )
        .timeout(const Duration(seconds: 10));
    if (response.statusCode >= 400) {
      String message = 'Error ${response.statusCode}';
      try {
        message = jsonDecode(utf8.decode(response.bodyBytes))['detail'];
      } catch (_) {}
      throw Exception(message);
    }
  }

  Future<void> unlock() async {
    setState(() {
      busy = true;
      unlockError = '';
    });
    try {
      await post('/unlock', {'password': password.text});
      password.clear();
      await refreshStatus();
    } catch (e) {
      if (mounted) {
        setState(() => unlockError = '$e'.replaceFirst('Exception: ', ''));
      }
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Widget centered(Widget child) => Scaffold(
    body: Center(
      child: Container(
        width: 440,
        padding: const EdgeInsets.all(32),
        decoration: BoxDecoration(
          color: panel,
          borderRadius: BorderRadius.circular(20),
        ),
        child: child,
      ),
    ),
  );

  Widget brand() => const Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Icon(Icons.shield_outlined, color: Color(0xFF5C8DF5)),
      SizedBox(width: 10),
      Text(
        'SAAD-Campus · Nodo',
        style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
      ),
    ],
  );

  Widget offlineScreen() => centered(
    Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        brand(),
        const SizedBox(height: 24),
        const Text(
          'El servicio del nodo no está en marcha',
          style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 10),
        const Text(
          'Inícialo en PowerShell desde la carpeta saad-campus-edge:',
          style: TextStyle(color: muted),
        ),
        const SizedBox(height: 10),
        const SelectableText(
          r'.\.venv\Scripts\python.exe .\edge_service.py',
          style: TextStyle(fontFamily: 'Consolas'),
        ),
        const SizedBox(height: 16),
        const Text(
          'Esta pantalla se conectará sola.',
          style: TextStyle(color: muted, fontSize: 12),
        ),
      ],
    ),
  );

  Widget unlockScreen() => centered(
    Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        brand(),
        const SizedBox(height: 24),
        const Text(
          'Desbloquear nodo',
          style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
        ),
        const SizedBox(height: 6),
        const Text(
          'Clave de la base cifrada de este equipo.',
          style: TextStyle(color: muted),
        ),
        const SizedBox(height: 18),
        TextField(
          controller: password,
          obscureText: true,
          autofocus: true,
          onSubmitted: (_) => busy ? null : unlock(),
          decoration: const InputDecoration(
            labelText: 'Clave',
            border: OutlineInputBorder(),
          ),
        ),
        if (unlockError.isNotEmpty) ...[
          const SizedBox(height: 10),
          Text(unlockError, style: const TextStyle(color: red)),
        ],
        const SizedBox(height: 18),
        SizedBox(
          width: double.infinity,
          child: FilledButton(
            onPressed: busy ? null : unlock,
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Text(busy ? 'Abriendo…' : 'Desbloquear'),
            ),
          ),
        ),
      ],
    ),
  );

  Widget banner(Map result) {
    final allowed = result['allowed'] == true;
    final enrollment = result['enrollment'] == true;
    final title = enrollment
        ? (allowed ? 'ROSTRO ENROLADO' : 'ENROLAMIENTO FALLIDO')
        : (allowed ? 'ACCESO AUTORIZADO' : 'ACCESO DENEGADO');
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 18),
      color: (allowed ? green : red).withValues(alpha: .92),
      child: Row(
        children: [
          Icon(
            allowed ? Icons.check_circle : Icons.cancel,
            size: 44,
            color: Colors.white,
          ),
          const SizedBox(width: 18),
          Expanded(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 26,
                    fontWeight: FontWeight.w800,
                    color: Colors.white,
                  ),
                ),
                Text(
                  '${result['name']} · ${result['reason'] ?? ''}',
                  style: const TextStyle(fontSize: 15, color: Colors.white),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget video(Map s) {
    final result = s['result'] as Map?;
    final hint = '${s['hint'] ?? ''}';
    return AspectRatio(
      aspectRatio: 1,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(20),
        child: Stack(
          fit: StackFit.expand,
          children: [
            Container(color: Colors.black),
            if (frame != null)
              Image.memory(frame!, gaplessPlayback: true, fit: BoxFit.cover)
            else
              const Center(child: CircularProgressIndicator()),
            if (hint.isNotEmpty && result == null)
              Align(
                alignment: Alignment.topCenter,
                child: Container(
                  margin: const EdgeInsets.all(18),
                  padding: const EdgeInsets.symmetric(
                    horizontal: 18,
                    vertical: 10,
                  ),
                  decoration: BoxDecoration(
                    color: Colors.black54,
                    borderRadius: BorderRadius.circular(30),
                  ),
                  child: Text(hint, style: const TextStyle(fontSize: 18)),
                ),
              ),
            if (result != null)
              Align(alignment: Alignment.bottomCenter, child: banner(result)),
          ],
        ),
      ),
    );
  }

  Widget card(List<Widget> children) => Container(
    width: double.infinity,
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      color: panel,
      borderRadius: BorderRadius.circular(16),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: children,
    ),
  );

  Widget line(String label, String value, {Color? color}) => Padding(
    padding: const EdgeInsets.only(top: 10),
    child: Row(
      children: [
        Expanded(
          child: Text(label, style: const TextStyle(color: muted)),
        ),
        Text(
          value,
          style: TextStyle(fontWeight: FontWeight.w600, color: color),
        ),
      ],
    ),
  );

  String time(String? iso) {
    final date = iso == null ? null : DateTime.tryParse(iso)?.toLocal();
    if (date == null) return 'Nunca';
    String pad(int n) => n.toString().padLeft(2, '0');
    return '${pad(date.hour)}:${pad(date.minute)}:${pad(date.second)}';
  }

  Widget sidePanel(Map s) {
    final job = s['enrolling'] as Map?;
    final online = s['central_online'] == true;
    return Column(
      children: [
        card([
          brand(),
          const SizedBox(height: 6),
          Text('Zona: ${s['zone']}', style: const TextStyle(color: muted)),
          line(
            'Central',
            online ? 'Conectada' : 'Sin conexión',
            color: online ? green : amber,
          ),
          line('Última sincronización', time(s['last_sync'])),
          line('Rostros enrolados', '${s['templates']}'),
          line('Eventos por enviar', '${s['pending_events']}'),
        ]),
        const SizedBox(height: 16),
        if (job != null)
          card([
            const Text(
              'ENROLANDO',
              style: TextStyle(
                color: amber,
                fontWeight: FontWeight.w700,
                letterSpacing: 1.2,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '${job['name']}',
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w700),
            ),
            Text(
              '${job['student_id']}',
              style: const TextStyle(color: muted),
            ),
            const SizedBox(height: 16),
            LinearProgressIndicator(
              value: (job['progress'] as num) / (job['total'] as num),
              minHeight: 8,
              borderRadius: BorderRadius.circular(8),
            ),
            const SizedBox(height: 8),
            Text(
              'Captura ${job['progress']} de ${job['total']} · quedan ${job['seconds_left']} s',
              style: const TextStyle(color: muted),
            ),
            const SizedBox(height: 16),
            OutlinedButton.icon(
              onPressed: () => post('/enrollment/cancel').catchError((_) {}),
              icon: const Icon(Icons.close),
              label: const Text('Cancelar enrolamiento'),
            ),
          ])
        else
          card(const [
            Text(
              'Listo para verificar',
              style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600),
            ),
            SizedBox(height: 6),
            Text(
              'Acércate a la cámara para validar tu acceso. Los enrolamientos '
              'pedidos desde el panel central aparecen aquí automáticamente.',
              style: TextStyle(color: muted),
            ),
          ]),
        if (s['error'] != null) ...[
          const SizedBox(height: 16),
          card([
            Text('${s['error']}', style: const TextStyle(color: red)),
            const SizedBox(height: 6),
            const Text(
              'Cierra y vuelve a iniciar edge_service.py.',
              style: TextStyle(color: muted),
            ),
          ]),
        ],
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final s = status;
    if (!reachable || s == null) return offlineScreen();
    if (s['locked'] == true) return unlockScreen();
    return Scaffold(
      body: LayoutBuilder(
        builder: (context, size) {
          final wide = size.maxWidth >= 900;
          final children = [
            if (wide)
              Expanded(child: Center(child: video(s)))
            else
              video(s),
            SizedBox(width: wide ? 24 : 0, height: wide ? 0 : 24),
            SizedBox(width: wide ? 360 : double.infinity, child: sidePanel(s)),
          ];
          return SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: wide
                ? SizedBox(
                    height: size.maxHeight - 48,
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: children,
                    ),
                  )
                : Column(children: children),
          );
        },
      ),
    );
  }
}
