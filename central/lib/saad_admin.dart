import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

void main() => runApp(
  MaterialApp(
    title: 'SAAD-Campus',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: const Color(0xFFF5F6F8),
      colorScheme: ColorScheme.fromSeed(
        seedColor: const Color(0xFF2764E7),
        primary: const Color(0xFF2764E7),
      ),
      fontFamily: 'Segoe UI',
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFFF7F8FA),
        contentPadding: const EdgeInsets.all(18),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFFE1E5EC)),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFFE1E5EC)),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 20),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
      ),
      dividerColor: const Color(0xFFE9ECF2),
    ),
    home: const AdminPanel(),
  ),
);

class ApiError implements Exception {
  ApiError(this.message);
  final String message;
  @override
  String toString() => message;
}

class AdminPanel extends StatefulWidget {
  const AdminPanel({super.key});
  @override
  State<AdminPanel> createState() => _AdminPanelState();
}

class _AdminPanelState extends State<AdminPanel> {
  static const api = String.fromEnvironment(
    'API_URL',
    defaultValue: 'http://localhost:8000',
  );
  final username = TextEditingController(text: 'admin');
  final password = TextEditingController();
  String? token;
  String status = 'Sin conexión', error = '';
  bool busy = false;
  int selected = 0;
  bool reveal = false;
  String query = '';
  final search = TextEditingController();
  Map<String, dynamic> data = {};
  final Set<String> savingAccess = {};
  WebSocketChannel? socket;
  Timer? reconnect;

  Future<dynamic> request(
    String path,
    Map<String, dynamic> body, {
    String method = 'POST',
  }) async {
    final headers = {
      'Content-Type': 'application/json',
      if (token != null) 'Authorization': 'Bearer $token',
    };
    final uri = Uri.parse('$api$path');
    final response =
        await (method == 'PUT'
                ? http.put(uri, headers: headers, body: jsonEncode(body))
                : method == 'DELETE'
                ? http.delete(uri, headers: headers)
                : http.post(uri, headers: headers, body: jsonEncode(body)))
            .timeout(const Duration(seconds: 15));
    if (response.statusCode >= 400) {
      String message = 'Error ${response.statusCode}';
      try {
        final detail = jsonDecode(utf8.decode(response.bodyBytes))['detail'];
        message = detail is String ? detail : 'Revisa los datos ingresados.';
      } catch (_) {}
      throw ApiError(message);
    }
    return jsonDecode(utf8.decode(response.bodyBytes));
  }

  Future<void> login() async {
    setState(() {
      busy = true;
      error = '';
    });
    try {
      final result = await request('/login', {
        'username': username.text,
        'password': password.text,
      });
      if (!mounted) return;
      if (result['role'] != 'admin') {
        setState(() => error = 'Este panel es solo para administradores.');
        return;
      }
      setState(() => token = result['access_token']);
      password.clear();
      connect();
    } catch (e) {
      if (mounted) setState(() => error = '$e');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  void connect() {
    if (token == null || !mounted) return;
    setState(() => status = 'Conectando');
    final uri = Uri.parse(api);
    final channel = WebSocketChannel.connect(
      uri.replace(scheme: uri.scheme == 'https' ? 'wss' : 'ws', path: '/ws'),
    );
    socket = channel;
    channel.sink.add(token!);
    channel.stream.listen(
      (message) {
        if (!mounted || socket != channel) return;
        setState(() {
          data = jsonDecode(message as String);
          status = 'En vivo · actualización cada segundo';
        });
      },
      onError: (Object e) {
        if (mounted && socket == channel) {
          setState(() => status = 'Conexión interrumpida');
        }
      },
      onDone: () {
        if (!mounted || socket != channel) return;
        if (channel.closeCode == 1008) {
          logout();
          return;
        }
        setState(() => status = 'Desconectado · reintentando');
        reconnect = Timer(const Duration(seconds: 3), connect);
      },
    );
  }

  void logout() {
    reconnect?.cancel();
    final old = socket;
    socket = null;
    old?.sink.close();
    setState(() {
      token = null;
      data = {};
      status = 'Sesión cerrada';
    });
  }

  // Registrar un nodo devuelve su clave una sola vez. Repetirlo sobre un nodo existente la reemplaza.
  Future<void> nodeDialog() async {
    final id = TextEditingController();
    String localError = '';
    bool saving = false;
    String? key;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, update) {
          final known = ((data['nodes'] as List?) ?? []).any(
            (n) => n['id'] == id.text.trim(),
          );
          return AlertDialog(
            title: Text(key == null ? 'Registrar nodo' : 'Clave del nodo'),
            content: SizedBox(
              width: 420,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: key == null
                      ? [
                          TextField(
                            controller: id,
                            onChanged: (_) => update(() {}),
                            decoration: const InputDecoration(
                              labelText: 'Identificador del nodo',
                            ),
                          ),
                          if (known)
                            const Padding(
                              padding: EdgeInsets.only(top: 12),
                              child: Text(
                                'Este nodo ya existe. Se generará una clave nueva y dejará de conectarse hasta guardarla en su connection.json.',
                                style: TextStyle(color: Color(0xFFB7791F)),
                              ),
                            ),
                          if (localError.isNotEmpty)
                            Padding(
                              padding: const EdgeInsets.only(top: 12),
                              child: SelectableText(
                                localError,
                                style: const TextStyle(color: Colors.red),
                              ),
                            ),
                        ]
                      : [
                          const Text(
                            'Guárdala en el connection.json del nodo. No se volverá a mostrar.',
                          ),
                          const SizedBox(height: 12),
                          SelectableText(key!),
                        ],
                ),
              ),
            ),
            actions: [
              TextButton(
                onPressed: saving ? null : () => Navigator.pop(dialogContext),
                child: Text(key == null ? 'Cancelar' : 'Cerrar'),
              ),
              if (key == null)
                FilledButton(
                  onPressed: saving
                      ? null
                      : () async {
                          if (id.text.trim().isEmpty) {
                            update(() => localError = 'Escribe el identificador.');
                            return;
                          }
                          update(() {
                            saving = true;
                            localError = '';
                          });
                          try {
                            final result = await request(
                              '/nodes/${Uri.encodeComponent(id.text.trim())}',
                              {},
                            );
                            update(() {
                              key = '${result['api_key']}';
                              saving = false;
                            });
                          } catch (e) {
                            if (dialogContext.mounted) {
                              update(() {
                                localError = '$e';
                                saving = false;
                              });
                            }
                          }
                        },
                  child: Text(known ? 'Renovar clave' : 'Registrar'),
                ),
            ],
          );
        },
      ),
    );
    // Dialog transitions may still reference their text controllers; dispose with the widget tree.
  }

  // Alta o reenrolamiento: la captura del rostro ocurre en el nodo elegido, nunca en la central.
  Future<void> studentDialog({Map? student, bool edit = false}) async {
    final id = TextEditingController(text: '${student?['id'] ?? ''}');
    final name = TextEditingController(text: '${student?['name'] ?? ''}');
    final nodes = [
      for (final n in (data['nodes'] as List?) ?? []) '${n['id']}',
    ];
    String? node = nodes.length == 1 && !edit ? nodes.first : null;
    final current = student == null
        ? <String, bool>{}
        : accessOf('${student['id']}');
    // Un estudiante nuevo parte con acceso a la zona principal; se puede desmarcar.
    final access = {
      for (final z in zones)
        z: student == null ? z == defaultZone : current[z] == true,
    };
    final newZone = TextEditingController();
    String localError = '';
    bool saving = false;
    String? notice;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          title: Text(
            student == null
                ? 'Nuevo estudiante'
                : edit
                ? 'Editar estudiante'
                : 'Enrolar rostro',
          ),
          content: SizedBox(
            width: 420,
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  TextField(
                    controller: id,
                    readOnly: student != null,
                    decoration: const InputDecoration(
                      labelText: 'Identificador (matrícula o documento)',
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: name,
                    decoration: const InputDecoration(
                      labelText: 'Nombre completo',
                    ),
                  ),
                  if (student == null || edit) ...[
                    const SizedBox(height: 20),
                    const Text(
                      'Acceso permitido a',
                      style: TextStyle(color: ink, fontWeight: FontWeight.w600),
                    ),
                    for (final zone in access.keys)
                      CheckboxListTile(
                        dense: true,
                        contentPadding: EdgeInsets.zero,
                        controlAffinity: ListTileControlAffinity.leading,
                        title: Text(zone),
                        value: access[zone],
                        onChanged: (v) => update(() => access[zone] = v!),
                      ),
                    TextField(
                      controller: newZone,
                      decoration: const InputDecoration(
                        labelText: 'Agregar otra zona (opcional)',
                        hintText: 'Ej.: BIBLIOTECA y presiona Enter',
                        isDense: true,
                      ),
                      onSubmitted: (v) => update(() {
                        final zone = v.trim().toUpperCase();
                        if (zone.isNotEmpty) access[zone] = true;
                        newZone.clear();
                      }),
                    ),
                  ],
                  const SizedBox(height: 20),
                  const Text(
                    'Enrolar rostro en',
                    style: TextStyle(color: ink, fontWeight: FontWeight.w600),
                  ),
                  const SizedBox(height: 6),
                  if (nodes.isEmpty)
                    const Text(
                      'Registra primero un nodo de acceso para poder enrolar rostros.',
                      style: TextStyle(color: muted),
                    )
                  else
                    DropdownButton<String?>(
                      isExpanded: true,
                      value: node,
                      items: [
                        DropdownMenuItem(
                          value: null,
                          child: Text(edit ? 'No volver a enrolar' : 'Más tarde'),
                        ),
                        for (final n in nodes)
                          DropdownMenuItem(value: n, child: Text('Cámara de $n')),
                      ],
                      onChanged: (v) => update(() => node = v),
                    ),
                  if (node != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 8),
                      child: Text(
                        'Al guardar, el estudiante debe ubicarse frente a la cámara de $node. '
                        'La foto no sale del nodo.',
                        style: const TextStyle(color: muted, fontSize: 12),
                      ),
                    ),
                  if (localError.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: SelectableText(
                        localError,
                        style: const TextStyle(color: Colors.red),
                      ),
                    ),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: saving ? null : () => Navigator.pop(dialogContext),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: saving
                  ? null
                  : () async {
                      final studentId = id.text.trim();
                      final studentName = name.text.trim();
                      if (studentId.isEmpty || studentName.isEmpty) {
                        update(() => localError = 'Completa identificador y nombre.');
                        return;
                      }
                      update(() {
                        saving = true;
                        localError = '';
                      });
                      try {
                        await request('/students', {
                          'id': studentId,
                          'name': studentName,
                        }, method: 'PUT');
                        for (final entry in access.entries) {
                          if (entry.value != (current[entry.key] ?? false)) {
                            await savePermission(
                              studentId,
                              entry.key,
                              entry.value,
                            );
                          }
                        }
                        if (node != null) {
                          await request(
                            '/students/${Uri.encodeComponent(studentId)}/enrollment',
                            {'node_id': node},
                          );
                        }
                        notice = node == null
                            ? (student == null
                                  ? '$studentName quedó registrado.'
                                  : 'Cambios guardados.')
                            : 'Listo: $studentName debe ubicarse frente a la cámara de $node.';
                        if (dialogContext.mounted) Navigator.pop(dialogContext);
                      } catch (e) {
                        if (dialogContext.mounted) {
                          update(() {
                            localError = '$e';
                            saving = false;
                          });
                        }
                      }
                    },
              child: Text(node == null ? 'Guardar' : 'Guardar y enrolar'),
            ),
          ],
        ),
      ),
    );
    if (notice != null && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(notice!)));
    }
  }

  List<String> get zones => {
    defaultZone,
    for (final p in (data['permissions'] as List?) ?? []) '${p['zone']}',
  }.toList()..sort();

  Map<String, bool> accessOf(String studentId) => {
    for (final p in (data['permissions'] as List?) ?? [])
      if (p['student_id'] == studentId) '${p['zone']}': p['enabled'] == true,
  };

  // Con la versión vista en pantalla, la central rechaza pisar un cambio ajeno (409).
  int permissionVersion(String studentId, String zone) {
    for (final p in (data['permissions'] as List?) ?? []) {
      if (p['student_id'] == studentId && p['zone'] == zone) {
        return (p['version'] as num).toInt();
      }
    }
    return 0;
  }

  Future<void> savePermission(String studentId, String zone, bool enabled) =>
      request('/permissions', {
        'student_id': studentId,
        'zone': zone,
        'enabled': enabled,
        'expected_version': permissionVersion(studentId, zone),
      }, method: 'PUT');

  Future<void> setAccess(String studentId, String zone, bool enabled) async {
    setState(() => savingAccess.add('$studentId:$zone'));
    try {
      await savePermission(studentId, zone, enabled);
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('$e')));
      }
    } finally {
      // El monitor en vivo trae el estado nuevo en menos de un segundo.
      await Future<void>.delayed(const Duration(milliseconds: 1200));
      if (mounted) setState(() => savingAccess.remove('$studentId:$zone'));
    }
  }

  Widget accessCell(Map row) {
    final id = '${row['id']}';
    final access = accessOf(id);
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (final zone in zones)
          Padding(
            padding: const EdgeInsets.only(right: 6),
            child: Tooltip(
              message: access[zone] == true
                  ? 'Clic para revocar el acceso'
                  : 'Clic para permitir el acceso',
              child: FilterChip(
                label: Text(
                  '$zone · ${access[zone] == true ? 'Permitido' : 'Sin acceso'}',
                  style: TextStyle(
                    fontSize: 11,
                    color: access[zone] == true
                        ? const Color(0xFF158268)
                        : muted,
                  ),
                ),
                selected: access[zone] == true,
                showCheckmark: true,
                checkmarkColor: const Color(0xFF158268),
                selectedColor: const Color(0xFF158268).withValues(alpha: .1),
                visualDensity: VisualDensity.compact,
                onSelected: savingAccess.contains('$id:$zone')
                    ? null
                    : (v) => setAccess(id, zone, v),
              ),
            ),
          ),
      ],
    );
  }

  Future<void> deleteStudent(Map student) async {
    String localError = '';
    bool deleting = false;
    String? notice;
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          title: Text('¿Eliminar a ${student['name']}?'),
          content: SizedBox(
            width: 420,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Se borrarán sus permisos y su rostro enrolado en todos los nodos. '
                  'El historial de accesos se conserva.\n\n'
                  'Identificador: ${student['id']}',
                ),
                if (localError.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: SelectableText(
                      localError,
                      style: const TextStyle(color: Colors.red),
                    ),
                  ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: deleting ? null : () => Navigator.pop(dialogContext),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: const Color(0xFFBF5656),
              ),
              onPressed: deleting
                  ? null
                  : () async {
                      update(() {
                        deleting = true;
                        localError = '';
                      });
                      try {
                        await request(
                          '/students/${Uri.encodeComponent('${student['id']}')}',
                          {},
                          method: 'DELETE',
                        );
                        notice =
                            '${student['name']} fue eliminado. Los nodos borrarán su rostro al sincronizar.';
                        if (dialogContext.mounted) Navigator.pop(dialogContext);
                      } catch (e) {
                        if (dialogContext.mounted) {
                          update(() {
                            localError = '$e';
                            deleting = false;
                          });
                        }
                      }
                    },
              child: const Text('Eliminar'),
            ),
          ],
        ),
      ),
    );
    if (notice != null && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(notice!)));
    }
  }

  Widget enrollmentCell(Map row) {
    final enrollments = (row['enrollments'] as List?) ?? [];
    final failed = enrollments.any((e) => e['status'] == 'failed');
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (enrollments.isEmpty) pill('Sin rostro', muted),
        for (final e in enrollments)
          Padding(
            padding: const EdgeInsets.only(right: 6),
            child: Tooltip(
              message: '${e['detail'] ?? ''}',
              child: pill(
                '${{'pending': 'Esperando cámara', 'enrolled': 'Enrolado', 'failed': 'Falló'}[e['status']]} · ${e['node_id']}',
                {
                  'pending': const Color(0xFFB7791F),
                  'enrolled': const Color(0xFF158268),
                  'failed': const Color(0xFFBF5656),
                }[e['status']]!,
              ),
            ),
          ),
        TextButton(
          onPressed: () => studentDialog(student: row),
          child: Text(
            enrollments.isEmpty
                ? 'Enrolar'
                : failed
                ? 'Reintentar'
                : 'Reenrolar',
          ),
        ),
      ],
    );
  }

  static const ink = Color(0xFF17233B);
  static const muted = Color(0xFF718096);
  static const blue = Color(0xFF2764E7);
  static const labels = [
    'Vista general',
    'Estudiantes',
    'Nodos de acceso',
    'Auditoría',
  ];
  static const icons = [
    Icons.grid_view_rounded,
    Icons.people_outline_rounded,
    Icons.hub_outlined,
    Icons.history_rounded,
  ];
  static const keys = ['events', 'students', 'nodes', 'audit'];
  // Zona que validan los nodos actuales; aparece aunque nadie tenga permiso todavía.
  static const defaultZone = 'ENTRADA-PRINCIPAL';
  static const columns = [
    {
      'occurred_at': 'Fecha y hora',
      'student_name': 'Nombre completo',
      'zone': 'Zona',
      'allowed': 'Resultado',
      'reason': 'Motivo',
      'physical_status': 'Apertura',
      'seq': 'Nodo · evento',
    },
    {
      'id': 'Identificador',
      'name': 'Nombre completo',
      'access': 'Acceso (clic para cambiar)',
      'enrollments': 'Rostro',
      'actions': '',
    },
    {
      'id': 'Identificador',
      'online': 'Conexión',
      'applied_policy_version': 'Política aplicada',
      'last_seen': 'Última actividad',
    },
    {
      'created_at': 'Fecha y hora',
      'actor': 'Usuario / nodo',
      'action': 'Acción',
      'target': 'Registro',
    },
  ];

  Widget pill(String text, Color color) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 11, vertical: 7),
    decoration: BoxDecoration(
      color: color.withValues(alpha: .09),
      borderRadius: BorderRadius.circular(30),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(Icons.circle, size: 6, color: color),
        const SizedBox(width: 7),
        Text(
          text,
          style: TextStyle(
            color: color,
            fontSize: 12,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    ),
  );

  Widget brand({bool dark = false}) => Row(
    children: [
      Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: blue,
          borderRadius: BorderRadius.circular(12),
        ),
        child: const Icon(Icons.shield_outlined, color: Colors.white, size: 25),
      ),
      const SizedBox(width: 12),
      Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'SAAD',
            style: TextStyle(
              color: dark ? Colors.white : ink,
              fontSize: 23,
              fontWeight: FontWeight.w800,
              letterSpacing: 2,
            ),
          ),
          Text(
            'C A M P U S',
            style: TextStyle(
              color: dark ? Colors.white54 : muted,
              fontSize: 10,
            ),
          ),
        ],
      ),
    ],
  );

  Widget loginPage() => LayoutBuilder(
    builder: (context, constraints) {
      final wide = constraints.maxWidth >= 900;
      final loginForm = Center(
        child: SingleChildScrollView(
          padding: EdgeInsets.all(wide ? 56 : 28),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 390),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (!wide) ...[brand(), const SizedBox(height: 48)],
                const Text(
                  'PORTAL DE ADMINISTRACIÓN',
                  style: TextStyle(
                    color: blue,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.7,
                  ),
                ),
                const SizedBox(height: 18),
                const Text(
                  'Bienvenido de nuevo',
                  style: TextStyle(
                    fontSize: 32,
                    fontWeight: FontWeight.w700,
                    color: ink,
                    letterSpacing: -1,
                  ),
                ),
                const SizedBox(height: 12),
                const Text(
                  'Ingresa a tu cuenta para gestionar los accesos de tu campus.',
                  style: TextStyle(color: muted, height: 1.7, fontSize: 15),
                ),
                const SizedBox(height: 36),
                TextField(
                  controller: username,
                  decoration: const InputDecoration(
                    labelText: 'Usuario',
                    prefixIcon: Icon(Icons.person_outline),
                  ),
                ),
                const SizedBox(height: 18),
                TextField(
                  controller: password,
                  obscureText: !reveal,
                  onSubmitted: (_) {
                    if (!busy) login();
                  },
                  decoration: InputDecoration(
                    labelText: 'Contraseña',
                    prefixIcon: const Icon(Icons.lock_outline),
                    suffixIcon: IconButton(
                      tooltip: reveal
                          ? 'Ocultar contraseña'
                          : 'Mostrar contraseña',
                      onPressed: () => setState(() => reveal = !reveal),
                      icon: Icon(
                        reveal
                            ? Icons.visibility_off_outlined
                            : Icons.visibility_outlined,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 26),
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: busy ? null : login,
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Text(busy ? 'Ingresando…' : 'Ingresar al panel'),
                        const SizedBox(width: 16),
                        if (busy)
                          const SizedBox(
                            width: 16,
                            height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        else
                          const Icon(Icons.arrow_forward_rounded, size: 18),
                      ],
                    ),
                  ),
                ),
                if (error.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 16),
                    child: Text(
                      error,
                      style: const TextStyle(color: Colors.red),
                    ),
                  ),
                const SizedBox(height: 32),
                const Row(
                  children: [
                    Icon(
                      Icons.admin_panel_settings_outlined,
                      size: 16,
                      color: muted,
                    ),
                    SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Acceso exclusivo para personal autorizado',
                        style: TextStyle(color: muted, fontSize: 12),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      );
      return Scaffold(
        body: Row(
          children: [
            if (wide)
              Expanded(
                child: Container(
                  decoration: const BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                      colors: [Color(0xFF101E38), Color(0xFF173C72)],
                    ),
                  ),
                  child: LayoutBuilder(
                    builder: (context, box) => SingleChildScrollView(
                      child: ConstrainedBox(
                        constraints: BoxConstraints(minHeight: box.maxHeight),
                        child: Padding(
                          padding: const EdgeInsets.all(52),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              brand(dark: true),
                              Padding(
                                padding: const EdgeInsets.symmetric(
                                  vertical: 48,
                                ),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Container(
                                      width: 108,
                                      height: 108,
                                      decoration: BoxDecoration(
                                        border: Border.all(
                                          color: const Color(0xFF527BB0),
                                        ),
                                        borderRadius: BorderRadius.circular(28),
                                        color: Colors.white.withValues(
                                          alpha: .04,
                                        ),
                                      ),
                                      child: const Icon(
                                        Icons.fingerprint_rounded,
                                        size: 70,
                                        color: Color(0xFF9CBFFF),
                                      ),
                                    ),
                                    const SizedBox(height: 36),
                                    const Text(
                                      'Un campus conectado.\nCada acceso, bajo control.',
                                      style: TextStyle(
                                        color: Colors.white,
                                        fontSize: 37,
                                        height: 1.2,
                                        fontWeight: FontWeight.w700,
                                        letterSpacing: -1.2,
                                      ),
                                    ),
                                    const SizedBox(height: 20),
                                    const Text(
                                      'Supervisa la actividad, administra permisos y mantén una visión clara de tu comunidad.',
                                      style: TextStyle(
                                        color: Color(0xFFB0C2DD),
                                        fontSize: 16,
                                        height: 1.8,
                                      ),
                                    ),
                                    const SizedBox(height: 32),
                                    Wrap(
                                      spacing: 12,
                                      runSpacing: 12,
                                      children: [
                                        pill(
                                          'Monitoreo en vivo',
                                          const Color(0xFFB9D6FF),
                                        ),
                                        pill(
                                          'Gestión centralizada',
                                          const Color(0xFFB9D6FF),
                                        ),
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                              const Text(
                                'SAAD-CAMPUS  /  CONTROL DE ACCESO INTELIGENTE',
                                style: TextStyle(
                                  color: Color(0xFF8CA5C8),
                                  fontSize: 10,
                                  letterSpacing: 1.5,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            Expanded(child: loginForm),
          ],
        ),
      );
    },
  );

  Widget navigation() => Container(
    width: 230,
    color: const Color(0xFF111E35),
    child: SafeArea(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 28),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.only(left: 10),
              child: brand(dark: true),
            ),
            const SizedBox(height: 48),
            const Padding(
              padding: EdgeInsets.only(left: 14, bottom: 16),
              child: Text(
                'ESPACIO DE TRABAJO',
                style: TextStyle(
                  color: Color(0xFF7E91B0),
                  fontSize: 10,
                  letterSpacing: 1.5,
                ),
              ),
            ),
            for (var i = 0; i < labels.length; i++)
              Padding(
                padding: const EdgeInsets.only(bottom: 7),
                child: Material(
                  color: selected == i
                      ? const Color(0xFF253D63)
                      : Colors.transparent,
                  borderRadius: BorderRadius.circular(10),
                  child: ListTile(
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10),
                    ),
                    leading: Icon(
                      icons[i],
                      size: 20,
                      color: selected == i
                          ? const Color(0xFF8EB5FF)
                          : const Color(0xFF899BB7),
                    ),
                    title: Text(
                      labels[i],
                      style: TextStyle(
                        fontSize: 13,
                        color: selected == i
                            ? Colors.white
                            : const Color(0xFFAFBDD2),
                        fontWeight: selected == i
                            ? FontWeight.w600
                            : FontWeight.w400,
                      ),
                    ),
                    onTap: () => setState(() {
                      selected = i;
                      query = '';
                      search.clear();
                    }),
                  ),
                ),
              ),
            const Spacer(),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: .04),
                borderRadius: BorderRadius.circular(14),
              ),
              child: const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    Icons.account_balance_outlined,
                    color: Color(0xFF91A9CF),
                    size: 23,
                  ),
                  SizedBox(height: 12),
                  Text(
                    'Administración central',
                    style: TextStyle(color: Colors.white, fontSize: 12),
                  ),
                  SizedBox(height: 6),
                  Text(
                    'La actividad de tu campus,\nen un solo lugar.',
                    style: TextStyle(
                      color: Color(0xFF8C9FBF),
                      fontSize: 11,
                      height: 1.7,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 20),
            TextButton.icon(
              onPressed: logout,
              icon: const Icon(Icons.logout_rounded, size: 18),
              label: const Text('Cerrar sesión'),
              style: TextButton.styleFrom(
                foregroundColor: const Color(0xFFAFBDD2),
              ),
            ),
          ],
        ),
      ),
    ),
  );

  Widget metric(
    String label,
    String value,
    String caption,
    IconData icon,
    Color color,
  ) => Container(
    padding: const EdgeInsets.all(21),
    decoration: BoxDecoration(
      color: Colors.white,
      border: Border.all(color: const Color(0xFFE6EAF0)),
      borderRadius: BorderRadius.circular(16),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                label,
                style: const TextStyle(
                  color: muted,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: color.withValues(alpha: .08),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(icon, size: 18, color: color),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Text(
          value,
          style: const TextStyle(
            fontSize: 32,
            fontWeight: FontWeight.w700,
            color: ink,
            letterSpacing: -1,
          ),
        ),
        const SizedBox(height: 6),
        Text(caption, style: const TextStyle(color: muted, fontSize: 11)),
      ],
    ),
  );

  static const auditLabels = {
    'login_ok': 'Inicio de sesión',
    'login_failed': 'Intento de sesión fallido',
    'grant': 'Permiso concedido',
    'revoke': 'Permiso revocado',
    'save_student': 'Estudiante guardado',
    'delete_student': 'Estudiante eliminado',
    'request_enrollment': 'Enrolamiento solicitado',
    'enrollment_enrolled': 'Rostro enrolado',
    'enrollment_failed': 'Enrolamiento fallido',
    'rotate_node_key': 'Clave de nodo emitida',
    'create_user': 'Usuario creado',
    'edge_event': 'Evento recibido del nodo',
  };

  Widget physicalCell(Map row) {
    final status = row['physical_status'];
    if (status == null) {
      return Text(
        row['allowed'] == true ? 'Pendiente' : 'No aplica',
        style: const TextStyle(color: muted),
      );
    }
    final (label, color) = switch (status) {
      'ack' => ('Confirmada (ACK)', const Color(0xFF158268)),
      'simulado' => ('Simulada', blue),
      _ => ('No declarada', const Color(0xFFB7791F)),
    };
    return Tooltip(
      message: '${row['physical_detail'] ?? ''}',
      child: pill(label, color),
    );
  }

  Widget policyCell(dynamic version) {
    if (version == null) return const Text('—');
    final current = version == data['policy_version'];
    return pill(
      'v$version · ${current ? 'al día' : 'desactualizada'}',
      current ? const Color(0xFF158268) : const Color(0xFFB7791F),
    );
  }

  String displayValue(String key, dynamic value) {
    if (key == 'action') return auditLabels[value] ?? '$value';
    if (value == null) return '—';
    if ([
      'occurred_at',
      'received_at',
      'created_at',
      'last_seen',
    ].contains(key)) {
      final date = DateTime.tryParse('$value')?.toLocal();
      if (date != null) {
        String pad(int n) => n.toString().padLeft(2, '0');
        return '${pad(date.day)}/${pad(date.month)}/${date.year}  ${pad(date.hour)}:${pad(date.minute)}:${pad(date.second)}';
      }
    }
    return '$value';
  }

  Widget table() {
    final all = (data[keys[selected]] as List?) ?? [];
    final rows = all
        .where(
          (row) => (row as Map).values.any(
            (v) => '$v'.toLowerCase().contains(query.toLowerCase()),
          ),
        )
        .toList();
    if (rows.isEmpty) {
      return Padding(
        padding: const EdgeInsets.all(54),
        child: Center(
          child: Column(
            children: [
              Container(
                padding: const EdgeInsets.all(18),
                decoration: const BoxDecoration(
                  color: Color(0xFFF0F4FC),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  query.isEmpty ? icons[selected] : Icons.search_off,
                  size: 30,
                  color: blue,
                ),
              ),
              const SizedBox(height: 18),
              Text(
                query.isEmpty
                    ? 'Todo listo para comenzar'
                    : 'Sin coincidencias',
                style: const TextStyle(
                  color: ink,
                  fontWeight: FontWeight.w600,
                  fontSize: 17,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                query.isEmpty
                    ? 'Los registros aparecerán aquí cuando haya actividad.'
                    : 'Prueba con otro nombre o identificador.',
                textAlign: TextAlign.center,
                style: const TextStyle(color: muted),
              ),
            ],
          ),
        ),
      );
    }
    return LayoutBuilder(
      builder: (context, c) => SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: ConstrainedBox(
          constraints: BoxConstraints(minWidth: c.maxWidth),
          child: DataTable(
            headingRowColor: const WidgetStatePropertyAll(Color(0xFFF8FAFC)),
            headingRowHeight: 48,
            dataRowMinHeight: 64,
            dataRowMaxHeight: 64,
            horizontalMargin: 24,
            columnSpacing: 30,
            dividerThickness: .5,
            headingTextStyle: const TextStyle(
              color: muted,
              fontSize: 11,
              fontWeight: FontWeight.w600,
            ),
            dataTextStyle: const TextStyle(color: ink, fontSize: 12),
            columns: columns[selected].values
                .map((label) => DataColumn(label: Text(label)))
                .toList(),
            rows: rows
                .map(
                  (row) => DataRow(
                    cells: columns[selected].keys.map((key) {
                      final value = row[key];
                      if (key == 'enrollments') {
                        return DataCell(enrollmentCell(row));
                      }
                      if (key == 'access') {
                        return DataCell(accessCell(row));
                      }
                      if (key == 'physical_status') {
                        return DataCell(physicalCell(row));
                      }
                      if (key == 'applied_policy_version') {
                        return DataCell(policyCell(value));
                      }
                      if (key == 'seq') {
                        return DataCell(
                          Text(
                            value == null
                                ? '${row['node_id']}'
                                : '${row['node_id']} · #$value',
                          ),
                        );
                      }
                      if (key == 'actions') {
                        return DataCell(
                          Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              IconButton(
                                tooltip: 'Editar estudiante',
                                icon: const Icon(Icons.edit_outlined, size: 18),
                                onPressed: () =>
                                    studentDialog(student: row, edit: true),
                              ),
                              IconButton(
                                tooltip: 'Eliminar estudiante',
                                icon: const Icon(
                                  Icons.delete_outline,
                                  size: 18,
                                  color: Color(0xFFBF5656),
                                ),
                                onPressed: () => deleteStudent(row),
                              ),
                            ],
                          ),
                        );
                      }
                      if (value is bool) {
                        return DataCell(
                          pill(
                            key == 'allowed'
                                ? (value ? 'Autorizado' : 'Denegado')
                                : key == 'online'
                                ? (value ? 'En línea' : 'Desconectado')
                                : (value ? 'Habilitado' : 'Revocado'),
                            value
                                ? const Color(0xFF158268)
                                : const Color(0xFFBF5656),
                          ),
                        );
                      }
                      return DataCell(SelectableText(displayValue(key, value)));
                    }).toList(),
                  ),
                )
                .toList(),
          ),
        ),
      ),
    );
  }

  List<Widget> actions() => [
    if (selected <= 1)
      FilledButton.icon(
        onPressed: studentDialog,
        icon: const Icon(Icons.add, size: 18),
        label: const Text('Estudiante'),
      ),
    if (selected == 2)
      FilledButton.icon(
        onPressed: nodeDialog,
        icon: const Icon(Icons.hub_outlined, size: 17),
        label: const Text('Registrar nodo'),
      ),
  ];

  @override
  void dispose() {
    reconnect?.cancel();
    socket?.sink.close();
    username.dispose();
    password.dispose();
    search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (token == null) return loginPage();
    final events = (data['events'] as List?) ?? [];
    final nodes = (data['nodes'] as List?) ?? [];
    final allowed = events.where((e) => e['allowed'] == true).length;
    final online = nodes.where((e) => e['online'] == true).length;
    final live = status.startsWith('En vivo');
    return LayoutBuilder(
      builder: (context, size) {
        final wide = size.maxWidth >= 1000;
        return Scaffold(
          body: Row(
            children: [
              if (wide) navigation(),
              Expanded(
                child: Column(
                  children: [
                    Container(
                      padding: EdgeInsets.symmetric(
                        horizontal: wide ? 34 : 20,
                        vertical: 18,
                      ),
                      decoration: const BoxDecoration(
                        color: Colors.white,
                        border: Border(
                          bottom: BorderSide(color: Color(0xFFE6EAF0)),
                        ),
                      ),
                      child: Row(
                        children: [
                          if (wide)
                            const Text(
                              'Campus  /  Administración',
                              style: TextStyle(color: muted, fontSize: 12),
                            )
                          else
                            brand(),
                          const Spacer(),
                          if (size.maxWidth > 700 &&
                              data['policy_version'] != null) ...[
                            pill('Política v${data['policy_version']}', blue),
                            const SizedBox(width: 10),
                          ],
                          if (size.maxWidth > 560)
                            pill(
                              live ? 'En vivo' : 'Sin conexión',
                              live ? const Color(0xFF158268) : muted,
                            ),
                          const SizedBox(width: 20),
                          const CircleAvatar(
                            radius: 18,
                            backgroundColor: Color(0xFFECF1FC),
                            child: Icon(
                              Icons.person_outline,
                              size: 20,
                              color: blue,
                            ),
                          ),
                          if (size.maxWidth > 650) ...[
                            const SizedBox(width: 10),
                            const Text(
                              'Administrador',
                              style: TextStyle(
                                color: ink,
                                fontSize: 12,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ],
                          if (!wide)
                            IconButton(
                              tooltip: 'Cerrar sesión',
                              onPressed: logout,
                              icon: const Icon(Icons.logout, size: 19),
                            ),
                        ],
                      ),
                    ),
                    if (!wide)
                      SingleChildScrollView(
                        scrollDirection: Axis.horizontal,
                        child: Row(
                          children: List.generate(
                            labels.length,
                            (i) => Padding(
                              padding: const EdgeInsets.all(6),
                              child: ChoiceChip(
                                label: Text(labels[i]),
                                selected: selected == i,
                                onSelected: (_) => setState(() {
                                  selected = i;
                                  query = '';
                                  search.clear();
                                }),
                              ),
                            ),
                          ),
                        ),
                      ),
                    Expanded(
                      child: SingleChildScrollView(
                        padding: EdgeInsets.all(wide ? 34 : 20),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              selected == 0
                                  ? 'Tu campus, en tiempo real'
                                  : labels[selected],
                              style: const TextStyle(
                                color: ink,
                                fontSize: 29,
                                fontWeight: FontWeight.w700,
                                letterSpacing: -.8,
                              ),
                            ),
                            const SizedBox(height: 8),
                            Text(
                              selected == 0
                                  ? 'Una mirada a los accesos y a la actividad de tu comunidad.'
                                  : [
                                      '',
                                      'Gestiona los miembros de tu comunidad, su acceso y su rostro.',
                                      'Supervisa la conectividad de tus puntos de acceso.',
                                      'Consulta el historial de acciones y cambios.',
                                    ][selected],
                              style: const TextStyle(
                                color: muted,
                                fontSize: 13,
                              ),
                            ),
                            const SizedBox(height: 28),
                            if (selected == 0) ...[
                              LayoutBuilder(
                                builder: (context, c) {
                                  final count = c.maxWidth >= 850
                                      ? 4
                                      : c.maxWidth >= 450
                                      ? 2
                                      : 1;
                                  final width =
                                      (c.maxWidth - (count - 1) * 16) / count;
                                  return Wrap(
                                    spacing: 16,
                                    runSpacing: 16,
                                    children: [
                                      SizedBox(
                                        width: width,
                                        child: metric(
                                          'Accesos recientes',
                                          '${events.length}',
                                          'Últimos 100 eventos recibidos',
                                          Icons.login_rounded,
                                          blue,
                                        ),
                                      ),
                                      SizedBox(
                                        width: width,
                                        child: metric(
                                          'Autorizados',
                                          '$allowed',
                                          'En los eventos mostrados',
                                          Icons.check_circle_outline,
                                          const Color(0xFF158268),
                                        ),
                                      ),
                                      SizedBox(
                                        width: width,
                                        child: metric(
                                          'Denegados',
                                          '${events.length - allowed}',
                                          'En los eventos mostrados',
                                          Icons.block_outlined,
                                          const Color(0xFFBF5656),
                                        ),
                                      ),
                                      SizedBox(
                                        width: width,
                                        child: metric(
                                          'Nodos en línea',
                                          '$online / ${nodes.length}',
                                          'Contacto en los últimos 30 s',
                                          Icons.sensors,
                                          const Color(0xFF8056BD),
                                        ),
                                      ),
                                    ],
                                  );
                                },
                              ),
                              const SizedBox(height: 28),
                            ],
                            if (actions().isNotEmpty) ...[
                              Wrap(
                                spacing: 10,
                                runSpacing: 10,
                                children: actions(),
                              ),
                              const SizedBox(height: 24),
                            ],
                            Container(
                              clipBehavior: Clip.antiAlias,
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(16),
                                border: Border.all(
                                  color: const Color(0xFFE6EAF0),
                                ),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Padding(
                                    padding: const EdgeInsets.all(22),
                                    child: Wrap(
                                      alignment: WrapAlignment.spaceBetween,
                                      crossAxisAlignment:
                                          WrapCrossAlignment.center,
                                      spacing: 24,
                                      runSpacing: 18,
                                      children: [
                                        Column(
                                          crossAxisAlignment:
                                              CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                              selected == 0
                                                  ? 'Últimos accesos'
                                                  : labels[selected],
                                              style: const TextStyle(
                                                color: ink,
                                                fontSize: 17,
                                                fontWeight: FontWeight.w700,
                                              ),
                                            ),
                                            const SizedBox(height: 6),
                                            Text(
                                              selected == 0
                                                  ? 'Resultados enviados por los nodos de acceso'
                                                  : 'Información actualizada automáticamente',
                                              style: const TextStyle(
                                                color: muted,
                                                fontSize: 12,
                                              ),
                                            ),
                                          ],
                                        ),
                                        SizedBox(
                                          width: 250,
                                          child: TextField(
                                            controller: search,
                                            onChanged: (v) =>
                                                setState(() => query = v),
                                            decoration: const InputDecoration(
                                              hintText:
                                                  'Buscar en los registros…',
                                              prefixIcon: Icon(
                                                Icons.search,
                                                size: 20,
                                              ),
                                              isDense: true,
                                              contentPadding: EdgeInsets.all(
                                                12,
                                              ),
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  table(),
                                  Padding(
                                    padding: const EdgeInsets.all(18),
                                    child: Text(
                                      'Hora local del navegador · ${selected == 0 || selected == 3 ? 'Últimos 100 registros' : 'Registros sincronizados'}',
                                      style: const TextStyle(
                                        color: muted,
                                        fontSize: 11,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            const SizedBox(height: 22),
                            Row(
                              children: [
                                Icon(
                                  live ? Icons.sync : Icons.sync_problem,
                                  size: 15,
                                  color: muted,
                                ),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    status,
                                    style: const TextStyle(
                                      color: muted,
                                      fontSize: 11,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
