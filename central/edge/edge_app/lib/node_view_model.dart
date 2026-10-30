import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

/// Tono visual de un resultado; la vista decide los colores.
enum Tone { success, danger, info, warning }

/// Texto listo para mostrar de una decisión del nodo.
class ResultView {
  const ResultView({
    required this.title,
    required this.tone,
    this.name,
    this.detail,
    this.physical,
    this.latencyMs,
  });
  final String title;
  final Tone tone;
  final String? name;
  final String? detail;
  final String? physical;
  final int? latencyMs;
}

/// Una fila del historial local del kiosco.
class RecentAccess {
  const RecentAccess(this.time, this.name, this.allowed, this.reason);
  final String time;
  final String name;
  final bool allowed;
  final String reason;
}

/// ViewModel del kiosco: consulta la API de acceso local y expone el estado
/// ya interpretado. La vista no conoce URLs ni el formato de las respuestas.
class NodeViewModel extends ChangeNotifier {
  static const service = 'http://127.0.0.1:8001';

  final frame = ValueNotifier<Uint8List?>(null);
  final http.Client _statusClient = http.Client();
  final http.Client _frameClient = http.Client();
  Map<String, dynamic>? _status;
  bool reachable = true;
  bool busy = false;
  String unlockError = '';
  Timer? _poll;
  bool _disposed = false;

  void start() {
    _poll = Timer.periodic(
      const Duration(milliseconds: 400),
      (_) => refresh(),
    );
    refresh();
    _frameLoop();
  }

  @override
  void dispose() {
    _disposed = true;
    _poll?.cancel();
    _statusClient.close();
    _frameClient.close();
    frame.dispose();
    super.dispose();
  }

  Future<void> refresh() async {
    try {
      final response = await _statusClient
          .get(Uri.parse('$service/status'))
          .timeout(const Duration(seconds: 2));
      if (_disposed) return;
      _status = jsonDecode(utf8.decode(response.bodyBytes));
      reachable = true;
    } catch (_) {
      if (_disposed) return;
      reachable = false;
    }
    notifyListeners();
  }

  // Pide el siguiente cuadro solo cuando llegó el anterior, para no acumular solicitudes.
  Future<void> _frameLoop() async {
    while (!_disposed) {
      try {
        if (reachable && !locked) {
          final response = await _frameClient
              .get(Uri.parse('$service/frame.jpg'))
              .timeout(const Duration(seconds: 2));
          if (_disposed) return;
          if (response.statusCode == 200) {
            frame.value = response.bodyBytes;
          } else {
            frame.value = null;
          }
        }
      } catch (_) {}
      await Future<void>.delayed(const Duration(milliseconds: 40));
    }
  }

  Future<void> _post(String path, [Map<String, dynamic>? body]) async {
    final response = await _statusClient
        .post(
          Uri.parse('$service$path'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body ?? {}),
        )
        .timeout(const Duration(seconds: 15));
    if (response.statusCode >= 400) {
      String message = 'Error ${response.statusCode}';
      try {
        message = jsonDecode(utf8.decode(response.bodyBytes))['detail'];
      } catch (_) {}
      throw StateError(message);
    }
  }

  Future<void> unlock(String password) async {
    busy = true;
    unlockError = '';
    notifyListeners();
    try {
      await _post('/unlock', {'password': password});
      await refresh();
    } on StateError catch (e) {
      unlockError = e.message;
    } catch (_) {
      unlockError = 'No se pudo contactar el servicio del nodo.';
    }
    busy = false;
    notifyListeners();
  }

  Future<void> cancelEnrollment() async {
    try {
      await _post('/enrollment/cancel');
    } catch (_) {}
  }

  // --- Estado interpretado para la vista --------------------------------------

  bool get ready => reachable && _status != null;
  bool get locked => _status?['locked'] != false;
  bool get centralOnline => _status?['central_online'] == true;
  bool get firstSyncDone => _status?['last_sync'] != null;
  String get nodeId => '${_status?['node_id'] ?? 'nodo'}';
  String get zone => '${_status?['zone'] ?? ''}';
  String get hint => '${_status?['hint'] ?? ''}';
  int get templates => (_status?['templates'] as num?)?.toInt() ?? 0;
  int get pendingEvents => (_status?['pending_events'] as num?)?.toInt() ?? 0;
  String? get cameraError => _status?['camera_error'] as String?;
  String? get syncError => _status?['sync_error'] as String?;

  String get policyLabel {
    final version = _status?['policy_version'];
    return version == null ? 'Sin política' : 'v$version';
  }

  String get lastSyncLabel {
    final date = DateTime.tryParse('${_status?['last_sync']}');
    if (date == null) return 'nunca';
    final seconds = DateTime.now().difference(date).inSeconds;
    if (seconds < 5) return 'ahora';
    if (seconds < 60) return 'hace $seconds s';
    if (seconds < 3600) return 'hace ${seconds ~/ 60} min';
    if (seconds < 172800) return 'hace ${seconds ~/ 3600} h';
    return 'hace ${seconds ~/ 86400} días';
  }

  bool get policyExpired => _status?['policy_seconds_left'] == 0;

  bool get recintoOpen => (_status?['jornada'] as Map?)?['open'] == true;

  String get jornadaLabel {
    final jornada = _status?['jornada'] as Map?;
    if (jornada == null) return '';
    final label = recintoOpen
        ? 'Jornada ${jornada['name']} · hasta ${jornada['closes']}'
        : 'Recinto cerrado · abre ${jornada['next_opening']}';
    final simulated = jornada['simulated'];
    return simulated == null ? label : '$label · hora simulada $simulated';
  }

  /// Tiempo que el nodo puede seguir decidiendo sin la central.
  String get validityLabel {
    final left = (_status?['policy_seconds_left'] as num?)?.toInt();
    if (left == null) return 'Sin política';
    if (left == 0) return 'Vencida';
    return '${left ~/ 3600} h ${(left % 3600) ~/ 60} min';
  }

  String get verifierLabel {
    final verifier = _status?['verifier'] as Map?;
    if (verifier == null) return 'Iniciando';
    return verifier['ready'] == true
        ? '${verifier['name']}'
        : 'No disponible';
  }

  bool get verifierReady => (_status?['verifier'] as Map?)?['ready'] == true;
  String? get verifierDetail {
    final detail = (_status?['verifier'] as Map?)?['detail'];
    return detail == null || '$detail'.isEmpty ? null : '$detail';
  }

  String get actuatorLabel {
    final actuator = _status?['actuator'] as Map?;
    return switch (actuator?['mode']) {
      'arduino' => 'Arduino en ${actuator?['detail']}',
      'simulado' => 'Simulado (sin hardware)',
      'sin_hardware' => 'Arduino no conectado',
      _ => 'No disponible',
    };
  }

  bool get actuatorReady => (_status?['actuator'] as Map?)?['mode'] == 'arduino';

  String get latencyLabel {
    final latency = _status?['latency'] as Map?;
    return latency == null ? 'Sin datos' : '${latency['p95']} ms (p95)';
  }

  /// Datos del enrolamiento en curso, o null.
  Map? get enrolling => _status?['enrolling'] as Map?;

  List<RecentAccess> get recent => [
    for (final e in (_status?['recent'] as List?) ?? const [])
      RecentAccess(
        clock(e['occurred_at'] as String?),
        '${e['name']}',
        e['allowed'] == true,
        '${e['reason'] ?? ''}',
      ),
  ];

  static String clock(String? iso, {bool seconds = true}) {
    final date = iso == null ? null : DateTime.tryParse(iso)?.toLocal();
    if (date == null) return '--:--';
    String pad(int n) => n.toString().padLeft(2, '0');
    final time = '${pad(date.hour)}:${pad(date.minute)}';
    return seconds ? '$time:${pad(date.second)}' : time;
  }

  ResultView? get result {
    final r = _status?['result'] as Map?;
    if (r == null) return null;
    final name = r['name'] == null ? null : '${r['name']}';
    final reason = r['reason'] == null ? null : '${r['reason']}';
    final latency = (r['latency_ms'] as num?)?.toInt();
    final physical = (r['physical'] as Map?)?['detail'] as String?;
    switch (r['code']) {
      case 'granted':
        return ResultView(
          title: 'ACCESO AUTORIZADO',
          tone: Tone.success,
          name: name,
          physical: physical ?? 'Solicitando apertura…',
          latencyMs: latency,
        );
      case 'repeat':
        return ResultView(
          title: 'ACCESO YA CONCEDIDO',
          tone: Tone.info,
          name: name,
          detail:
              'Ingresó a las ${clock(r['granted_at'] as String?, seconds: false)} · Jornada ${r['jornada']}',
        );
      case 'closed':
        return ResultView(
          title: 'RECINTO CERRADO',
          tone: Tone.danger,
          name: name,
          detail: 'Próxima apertura: ${r['next_opening']}',
          latencyMs: latency,
        );
      case 'not_recognized':
        return ResultView(
          title: 'ROSTRO NO RECONOCIDO',
          tone: Tone.danger,
          detail: 'Intente nuevamente o solicite su enrolamiento',
          latencyMs: latency,
        );
      case 'ambiguous':
      case 'invalid_capture':
        return ResultView(
          title: 'INTENTE NUEVAMENTE',
          tone: Tone.warning,
          detail: 'No se pudo confirmar la identidad. Mire de frente a la cámara.',
          latencyMs: latency,
        );
      case 'unavailable':
        return const ResultView(
          title: 'VERIFICADOR NO DISPONIBLE',
          tone: Tone.danger,
          detail: 'Acceso denegado por seguridad',
        );
      case 'enrolled':
        return ResultView(
          title: 'ROSTRO ENROLADO',
          tone: Tone.success,
          name: name,
          detail: 'La plantilla quedó cifrada en este nodo',
        );
      case 'enroll_failed':
        return ResultView(
          title: 'ENROLAMIENTO FALLIDO',
          tone: Tone.danger,
          name: name,
          detail: reason,
        );
      case 'error':
        return ResultView(
          title: 'ACCESO DENEGADO',
          tone: Tone.danger,
          detail: reason,
        );
      default:
        return ResultView(
          title: 'ACCESO DENEGADO',
          tone: Tone.danger,
          name: name,
          detail: reason,
          latencyMs: latency,
        );
    }
  }
}
