import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

void main() => runApp(MaterialApp(
  title: 'SAAD-Campus',
  theme: ThemeData(colorSchemeSeed: Colors.teal, useMaterial3: true),
  home: const AdminPanel(),
));

class AdminPanel extends StatefulWidget {
  const AdminPanel({super.key});
  @override
  State<AdminPanel> createState() => _AdminPanelState();
}

class _AdminPanelState extends State<AdminPanel> {
  static const api = String.fromEnvironment('API_URL', defaultValue: 'http://localhost:8000');
  final username = TextEditingController(text: 'admin');
  final password = TextEditingController();
  String? token;
  String role = '', status = 'Sin conexión', error = '';
  bool busy = false;
  Map<String, dynamic> data = {};
  WebSocketChannel? socket;
  Timer? reconnect;

  Future<dynamic> request(String path, Map<String, dynamic> body, {String method = 'POST'}) async {
    final headers = {'Content-Type': 'application/json', if (token != null) 'Authorization': 'Bearer $token'};
    final uri = Uri.parse('$api$path');
    final response = await (method == 'PUT' ? http.put(uri, headers: headers, body: jsonEncode(body)) : http.post(uri, headers: headers, body: jsonEncode(body))).timeout(const Duration(seconds: 15));
    if (response.statusCode >= 400) throw Exception('${response.statusCode}: ${response.body}');
    return jsonDecode(response.body);
  }

  Future<void> login() async {
    setState(() { busy = true; error = ''; });
    try {
      final result = await request('/login', {'username': username.text, 'password': password.text});
      if (!mounted) return;
      setState(() { token = result['access_token']; role = result['role']; });
      password.clear();
      connect();
    } catch (e) { if (mounted) setState(() => error = '$e'); }
    finally { if (mounted) setState(() => busy = false); }
  }

  void connect() {
    if (token == null || !mounted) return;
    setState(() => status = 'Conectando');
    final uri = Uri.parse(api);
    final channel = WebSocketChannel.connect(uri.replace(scheme: uri.scheme == 'https' ? 'wss' : 'ws', path: '/ws'));
    socket = channel;
    channel.sink.add(token!);
    channel.stream.listen((message) {
      if (!mounted || socket != channel) return;
      setState(() { data = jsonDecode(message as String); status = 'En vivo · actualización cada segundo'; });
    }, onError: (Object e) {
      if (mounted && socket == channel) setState(() => status = 'Conexión interrumpida');
    }, onDone: () {
      if (!mounted || socket != channel) return;
      if (channel.closeCode == 1008) { logout(); return; }
      setState(() => status = 'Desconectado · reintentando');
      reconnect = Timer(const Duration(seconds: 3), connect);
    });
  }

  void logout() {
    reconnect?.cancel();
    final old = socket;
    socket = null;
    old?.sink.close();
    setState(() { token = null; data = {}; status = 'Sesión cerrada'; });
  }

  Future<void> form(String title, Map<String, String> fields, String path, {String method = 'POST', bool permission = false, bool user = false}) async {
    final controllers = {for (final key in fields.keys) key: TextEditingController()};
    bool enabled = true;
    String selectedRole = 'auditor';
    String localError = '';
    bool saving = false;
    await showDialog<void>(context: context, builder: (dialogContext) => StatefulBuilder(builder: (context, update) => AlertDialog(
      title: Text(title),
      content: SizedBox(width: 420, child: SingleChildScrollView(child: Column(mainAxisSize: MainAxisSize.min, children: [
        for (final entry in fields.entries) Padding(padding: const EdgeInsets.only(bottom: 12), child: TextField(controller: controllers[entry.key], obscureText: entry.key == 'password', decoration: InputDecoration(labelText: entry.value))),
        if (permission) SwitchListTile(title: const Text('Permiso habilitado'), value: enabled, onChanged: (v) => update(() => enabled = v)),
        if (user) DropdownButton<String>(value: selectedRole, items: ['auditor', 'admin'].map((r) => DropdownMenuItem(value: r, child: Text(r))).toList(), onChanged: (r) => update(() => selectedRole = r!)),
        if (localError.isNotEmpty) SelectableText(localError, style: const TextStyle(color: Colors.red)),
      ]))),
      actions: [TextButton(onPressed: saving ? null : () => Navigator.pop(dialogContext), child: const Text('Cancelar')),
        FilledButton(onPressed: saving ? null : () async {
          update(() { saving = true; localError = ''; });
          try {
            final body = <String, dynamic>{for (final entry in controllers.entries) entry.key: entry.value.text, if (permission) 'enabled': enabled, if (user) 'role': selectedRole};
            final result = await request(path == '/nodes' ? '/nodes/${Uri.encodeComponent(controllers['id']!.text)}' : path, path == '/nodes' ? {} : body, method: method);
            if (!dialogContext.mounted) return;
            Navigator.pop(dialogContext);
            if (path == '/nodes' && mounted) {
              await showDialog<void>(context: this.context, builder: (c) => AlertDialog(title: const Text('Clave del nodo · guardar en el edge'), content: SelectableText(jsonEncode(result)), actions: [TextButton(onPressed: () => Navigator.pop(c), child: const Text('Cerrar'))]));
            }
          } catch (e) { if (dialogContext.mounted) update(() { localError = '$e'; saving = false; }); }
        }, child: const Text('Guardar')),
      ],
    )));
    // Dialog transitions may still reference their text controllers; dispose with the widget tree.
  }

  Widget table(String key, Map<String, String> columns) {
    final rows = (data[key] as List?) ?? [];
    if (rows.isEmpty) return const Center(child: Text('Sin registros'));
    return SingleChildScrollView(child: SingleChildScrollView(scrollDirection: Axis.horizontal, child: DataTable(
      columns: columns.values.map((label) => DataColumn(label: Text(label))).toList(),
      rows: rows.map((row) => DataRow(cells: columns.keys.map((key) {
        final value = row[key];
        final text = value is bool ? (value ? 'Sí' : 'No') : '${value ?? "—"}';
        return DataCell(SelectableText(text));
      }).toList())).toList(),
    )));
  }

  @override
  void dispose() { reconnect?.cancel(); socket?.sink.close(); username.dispose(); password.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    if (token == null) {
      return Scaffold(body: Center(child: SizedBox(width: 380, child: Card(child: Padding(padding: const EdgeInsets.all(28), child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text('SAAD-Campus', style: Theme.of(context).textTheme.headlineMedium),
        const Text('Administración central'), const SizedBox(height: 24),
        TextField(controller: username, decoration: const InputDecoration(labelText: 'Usuario')),
        TextField(controller: password, obscureText: true, onSubmitted: (_) { if (!busy) login(); }, decoration: const InputDecoration(labelText: 'Contraseña')),
        const SizedBox(height: 20), FilledButton(onPressed: busy ? null : login, child: Text(busy ? 'Ingresando…' : 'Ingresar')),
        if (error.isNotEmpty) SelectableText(error, style: const TextStyle(color: Colors.red)),
      ]))))));
    }
    return DefaultTabController(length: 5, child: Scaffold(
      appBar: AppBar(title: const Text('SAAD-Campus · Central'), actions: [Text(role), TextButton(onPressed: logout, child: const Text('Salir'))], bottom: const TabBar(isScrollable: true, tabs: [Tab(text: 'Accesos'),Tab(text: 'Estudiantes'),Tab(text: 'Permisos'),Tab(text: 'Nodos'),Tab(text: 'Auditoría')])),
      body: Column(children: [
        ListTile(leading: Icon(status.startsWith('En vivo') ? Icons.wifi : Icons.wifi_off), title: Text(status), subtitle: const Text('El nodo edge reconoce el rostro y decide el acceso localmente. Horas en UTC.')),
        if (role == 'admin') Padding(padding: const EdgeInsets.all(12), child: Wrap(spacing: 10, runSpacing: 10, children: [
          FilledButton.tonal(onPressed: () => form('Registrar estudiante', {'id':'Identificador','name':'Nombre'}, '/students', method: 'PUT'), child: const Text('Estudiante')),
          FilledButton.tonal(onPressed: () => form('Otorgar o revocar permiso', {'student_id':'Identificador del estudiante','zone':'Zona'}, '/permissions', method: 'PUT', permission: true), child: const Text('Permiso')),
          FilledButton.tonal(onPressed: () => form('Registrar nodo / renovar clave', {'id':'Identificador del nodo'}, '/nodes'), child: const Text('Nodo')),
          FilledButton.tonal(onPressed: () => form('Crear usuario', {'username':'Usuario','password':'Contraseña (mínimo 12 caracteres)'}, '/users', user: true), child: const Text('Usuario')),
        ])),
        Expanded(child: TabBarView(children: [
          table('events', {'occurred_at':'Fecha del acceso','student_id':'Estudiante','zone':'Zona','allowed':'Autorizado','node_id':'Nodo'}),
          table('students', {'id':'Identificador','name':'Nombre'}),
          table('permissions', {'student_id':'Estudiante','zone':'Zona','enabled':'Habilitado'}),
          table('nodes', {'id':'Nodo','online':'Conectado','last_seen':'Último contacto'}),
          table('audit', {'created_at':'Fecha','actor':'Actor','action':'Acción','target':'Objeto'}),
        ])),
      ]),
    ));
  }
}
