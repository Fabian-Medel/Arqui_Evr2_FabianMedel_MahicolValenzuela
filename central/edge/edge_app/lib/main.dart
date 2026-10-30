import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'node_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // El video llega como imágenes sueltas: no tiene sentido conservarlas en memoria.
  PaintingBinding.instance.imageCache.maximumSize = 8;
  SystemChrome.setSystemUIOverlayStyle(SystemUiOverlayStyle.light);
  runApp(const NodeApp());
}

class NodeApp extends StatelessWidget {
  const NodeApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'SAAD-Campus · Nodo',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: Palette.background,
      colorScheme: ColorScheme.fromSeed(
        seedColor: Palette.blue,
        brightness: Brightness.dark,
      ),
      fontFamily: 'Segoe UI',
    ),
    home: const NodeRoot(),
  );
}
