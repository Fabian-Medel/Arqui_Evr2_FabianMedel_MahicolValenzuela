import 'dart:async';
import 'package:flutter/material.dart';
import 'node_view_model.dart';

class Palette {
  static const background = Color(0xFF0B1220);
  static const panel = Color(0xFF141D31);
  static const line = Color(0xFF243049);
  static const blue = Color(0xFF4F8BF9);
  static const green = Color(0xFF1FB07A);
  static const red = Color(0xFFE05252);
  static const amber = Color(0xFFE9A83B);
  static const muted = Color(0xFF8E9BB3);
  static const text = Color(0xFFEDF1F8);

  static Color of(Tone tone) => switch (tone) {
    Tone.success => green,
    Tone.danger => red,
    Tone.info => blue,
    Tone.warning => amber,
  };
}

/// Elige la pantalla según el estado del nodo.
class NodeRoot extends StatefulWidget {
  const NodeRoot({super.key});
  @override
  State<NodeRoot> createState() => _NodeRootState();
}

class _NodeRootState extends State<NodeRoot> {
  final viewModel = NodeViewModel();

  @override
  void initState() {
    super.initState();
    viewModel.start();
  }

  @override
  void dispose() {
    viewModel.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: viewModel,
    builder: (context, _) {
      if (!viewModel.ready) return const OfflineScreen();
      if (viewModel.locked) return UnlockScreen(viewModel: viewModel);
      return KioskScreen(viewModel: viewModel);
    },
  );
}

class Brand extends StatelessWidget {
  const Brand({super.key});

  @override
  Widget build(BuildContext context) => Row(
    mainAxisSize: MainAxisSize.min,
    children: [
      Container(
        padding: const EdgeInsets.all(7),
        decoration: BoxDecoration(
          color: Palette.blue,
          borderRadius: BorderRadius.circular(10),
        ),
        child: const Icon(Icons.shield_outlined, color: Colors.white, size: 20),
      ),
      const SizedBox(width: 11),
      const Text(
        'SAAD-Campus',
        style: TextStyle(
          fontSize: 19,
          fontWeight: FontWeight.w700,
          color: Palette.text,
          letterSpacing: -.2,
        ),
      ),
    ],
  );
}

class CenteredCard extends StatelessWidget {
  const CenteredCard({super.key, required this.child});
  final Widget child;

  @override
  Widget build(BuildContext context) => Scaffold(
    body: Center(
      child: Container(
        width: 460,
        padding: const EdgeInsets.all(36),
        decoration: BoxDecoration(
          color: Palette.panel,
          borderRadius: BorderRadius.circular(22),
          border: Border.all(color: Palette.line),
        ),
        child: child,
      ),
    ),
  );
}

class OfflineScreen extends StatelessWidget {
  const OfflineScreen({super.key});

  @override
  Widget build(BuildContext context) => const CenteredCard(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Brand(),
        SizedBox(height: 26),
        Text(
          'El servicio del nodo no está en marcha',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
        ),
        SizedBox(height: 10),
        Text(
          'Inícialo en PowerShell desde la carpeta saad-campus-edge:',
          style: TextStyle(color: Palette.muted),
        ),
        SizedBox(height: 12),
        SelectableText(
          r'.\.venv\Scripts\python.exe .\edge_service.py',
          style: TextStyle(fontFamily: 'Consolas', color: Palette.text),
        ),
        SizedBox(height: 18),
        Text(
          'Esta pantalla se conectará sola.',
          style: TextStyle(color: Palette.muted, fontSize: 12),
        ),
      ],
    ),
  );
}

class UnlockScreen extends StatefulWidget {
  const UnlockScreen({super.key, required this.viewModel});
  final NodeViewModel viewModel;
  @override
  State<UnlockScreen> createState() => _UnlockScreenState();
}

class _UnlockScreenState extends State<UnlockScreen> {
  final password = TextEditingController();

  @override
  void dispose() {
    password.dispose();
    super.dispose();
  }

  void submit() {
    if (!widget.viewModel.busy) widget.viewModel.unlock(password.text);
  }

  @override
  Widget build(BuildContext context) {
    final vm = widget.viewModel;
    return CenteredCard(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Brand(),
          const SizedBox(height: 26),
          const Text(
            'Desbloquear nodo',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 6),
          const Text(
            'Clave de la base cifrada de este equipo.',
            style: TextStyle(color: Palette.muted),
          ),
          const SizedBox(height: 20),
          TextField(
            controller: password,
            obscureText: true,
            autofocus: true,
            onSubmitted: (_) => submit(),
            decoration: const InputDecoration(
              labelText: 'Clave',
              border: OutlineInputBorder(),
            ),
          ),
          if (vm.unlockError.isNotEmpty) ...[
            const SizedBox(height: 12),
            Text(vm.unlockError, style: const TextStyle(color: Palette.red)),
          ],
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            child: FilledButton(
              onPressed: vm.busy ? null : submit,
              child: Padding(
                padding: const EdgeInsets.all(13),
                child: Text(vm.busy ? 'Abriendo…' : 'Desbloquear'),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class KioskScreen extends StatelessWidget {
  const KioskScreen({super.key, required this.viewModel});
  final NodeViewModel viewModel;

  @override
  Widget build(BuildContext context) {
    final vm = viewModel;
    return Scaffold(
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TopBar(viewModel: vm),
          if (!vm.centralOnline) IslandStrip(viewModel: vm),
          Expanded(
            child: LayoutBuilder(
              builder: (context, size) {
                if (size.maxWidth >= 980) {
                  return Padding(
                    padding: const EdgeInsets.all(22),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Expanded(child: Center(child: VideoPanel(viewModel: vm))),
                        const SizedBox(width: 22),
                        SizedBox(
                          width: 372,
                          child: SingleChildScrollView(
                            child: SidePanel(viewModel: vm),
                          ),
                        ),
                      ],
                    ),
                  );
                }
                return SingleChildScrollView(
                  padding: const EdgeInsets.all(18),
                  child: Column(
                    children: [
                      VideoPanel(viewModel: vm),
                      const SizedBox(height: 18),
                      SidePanel(viewModel: vm),
                    ],
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class TopBar extends StatelessWidget {
  const TopBar({super.key, required this.viewModel});
  final NodeViewModel viewModel;

  @override
  Widget build(BuildContext context) {
    final vm = viewModel;
    final online = vm.centralOnline;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
      decoration: const BoxDecoration(
        color: Palette.panel,
        border: Border(bottom: BorderSide(color: Palette.line)),
      ),
      child: Row(
        children: [
          const Brand(),
          const SizedBox(width: 22),
          Flexible(
            child: Text(
              'Nodo ${vm.nodeId}  ·  ${vm.zone}',
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(color: Palette.muted, fontSize: 14),
            ),
          ),
          const Spacer(),
          StatusPill(
            label: vm.jornadaLabel,
            color: vm.recintoOpen ? Palette.blue : Palette.amber,
          ),
          const SizedBox(width: 10),
          StatusPill(
            label: online ? 'Central conectada' : 'Modo Isla',
            color: online ? Palette.green : Palette.amber,
          ),
          const SizedBox(width: 18),
          const LiveClock(),
        ],
      ),
    );
  }
}

class LiveClock extends StatefulWidget {
  const LiveClock({super.key});
  @override
  State<LiveClock> createState() => _LiveClockState();
}

class _LiveClockState extends State<LiveClock> {
  late final Timer timer;

  @override
  void initState() {
    super.initState();
    timer = Timer.periodic(
      const Duration(seconds: 1),
      (_) => setState(() {}),
    );
  }

  @override
  void dispose() {
    timer.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Text(
    NodeViewModel.clock(DateTime.now().toIso8601String()),
    style: const TextStyle(
      fontSize: 20,
      fontWeight: FontWeight.w600,
      color: Palette.text,
      fontFeatures: [FontFeature.tabularFigures()],
    ),
  );
}

class StatusPill extends StatelessWidget {
  const StatusPill({super.key, required this.label, required this.color});
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 7),
    decoration: BoxDecoration(
      color: color.withValues(alpha: .14),
      borderRadius: BorderRadius.circular(30),
    ),
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(color: color, shape: BoxShape.circle),
        ),
        const SizedBox(width: 8),
        Text(
          label,
          style: TextStyle(
            color: color,
            fontWeight: FontWeight.w600,
            fontSize: 13,
          ),
        ),
      ],
    ),
  );
}

/// Aviso permanente mientras el nodo opera sin la central.
class IslandStrip extends StatelessWidget {
  const IslandStrip({super.key, required this.viewModel});
  final NodeViewModel viewModel;

  @override
  Widget build(BuildContext context) {
    final vm = viewModel;
    final String text;
    if (!vm.firstSyncDone) {
      text = 'Sin política descargada: el nodo deniega hasta sincronizar con la central.';
    } else if (vm.policyExpired) {
      text = 'Política vencida: más de 72 h sin sincronizar. El nodo deniega todos los accesos.';
    } else {
      text =
          'Sin conexión con la central. Las decisiones siguen siendo locales con la política ${vm.policyLabel}, '
          'vigente ${vm.validityLabel} más. Eventos por enviar: ${vm.pendingEvents}.';
    }
    return Container(
      color: Palette.amber.withValues(alpha: .13),
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10),
      child: Row(
        children: [
          const Icon(Icons.cloud_off_rounded, size: 18, color: Palette.amber),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(color: Palette.amber, fontSize: 13.5),
            ),
          ),
        ],
      ),
    );
  }
}

class VideoPanel extends StatelessWidget {
  const VideoPanel({super.key, required this.viewModel});
  final NodeViewModel viewModel;

  @override
  Widget build(BuildContext context) {
    final vm = viewModel;
    final result = vm.result;
    final Color frameColor = result != null
        ? Palette.of(result.tone)
        : vm.enrolling != null
        ? Palette.amber
        : Palette.line;
    return AspectRatio(
      aspectRatio: 1,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 220),
        padding: const EdgeInsets.all(4),
        decoration: BoxDecoration(
          color: frameColor,
          borderRadius: BorderRadius.circular(24),
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(20),
          child: Stack(
            fit: StackFit.expand,
            children: [
              Container(color: Colors.black),
              ValueListenableBuilder(
                valueListenable: vm.frame,
                builder: (context, frame, _) => frame == null
                    ? CameraPlaceholder(error: vm.cameraError)
                    : Image.memory(
                        frame,
                        gaplessPlayback: true,
                        fit: BoxFit.cover,
                      ),
              ),
              if (vm.enrolling != null)
                Align(
                  alignment: Alignment.topLeft,
                  child: Container(
                    margin: const EdgeInsets.all(14),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 6,
                    ),
                    decoration: BoxDecoration(
                      color: Palette.amber,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: const Text(
                      'ENROLANDO',
                      style: TextStyle(
                        color: Color(0xFF2B1D04),
                        fontWeight: FontWeight.w800,
                        fontSize: 12,
                        letterSpacing: 1,
                      ),
                    ),
                  ),
                ),
              if (vm.hint.isNotEmpty && result == null)
                Align(
                  alignment: Alignment.bottomCenter,
                  child: Container(
                    margin: const EdgeInsets.all(22),
                    padding: const EdgeInsets.symmetric(
                      horizontal: 22,
                      vertical: 11,
                    ),
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: .62),
                      borderRadius: BorderRadius.circular(30),
                    ),
                    child: Text(
                      vm.hint,
                      style: const TextStyle(
                        fontSize: 20,
                        color: Colors.white,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ),
              Align(
                alignment: Alignment.bottomCenter,
                child: AnimatedSwitcher(
                  duration: const Duration(milliseconds: 220),
                  transitionBuilder: (child, animation) => SlideTransition(
                    position: Tween(
                      begin: const Offset(0, .25),
                      end: Offset.zero,
                    ).animate(animation),
                    child: FadeTransition(opacity: animation, child: child),
                  ),
                  child: result == null
                      ? const SizedBox.shrink()
                      : ResultBanner(key: ValueKey(result.title), result: result),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class CameraPlaceholder extends StatelessWidget {
  const CameraPlaceholder({super.key, this.error});
  final String? error;

  @override
  Widget build(BuildContext context) => Center(
    child: Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (error == null)
          const CircularProgressIndicator()
        else
          const Icon(Icons.videocam_off_rounded, size: 40, color: Palette.muted),
        const SizedBox(height: 14),
        Text(
          error ?? 'Iniciando cámara…',
          style: const TextStyle(color: Palette.muted),
        ),
      ],
    ),
  );
}

class ResultBanner extends StatelessWidget {
  const ResultBanner({super.key, required this.result});
  final ResultView result;

  IconData get icon => switch (result.tone) {
    Tone.success => Icons.check_circle_rounded,
    Tone.danger => Icons.cancel_rounded,
    Tone.info => Icons.info_rounded,
    Tone.warning => Icons.refresh_rounded,
  };

  @override
  Widget build(BuildContext context) {
    final lines = [result.name, result.detail, result.physical];
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(26, 20, 26, 20),
      color: Palette.of(result.tone).withValues(alpha: .94),
      child: Row(
        children: [
          Icon(icon, size: 52, color: Colors.white),
          const SizedBox(width: 18),
          Expanded(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  result.title,
                  style: const TextStyle(
                    fontSize: 27,
                    fontWeight: FontWeight.w800,
                    color: Colors.white,
                    height: 1.15,
                  ),
                ),
                for (final (index, line) in lines.indexed)
                  if (line != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 3),
                      child: Text(
                        line,
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: index == 0 ? 18 : 15,
                          fontWeight: index == 0
                              ? FontWeight.w600
                              : FontWeight.w400,
                        ),
                      ),
                    ),
              ],
            ),
          ),
          if (result.latencyMs != null)
            Padding(
              padding: const EdgeInsets.only(left: 12),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    '${result.latencyMs} ms',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 19,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const Text(
                    'decisión local',
                    style: TextStyle(color: Colors.white, fontSize: 11),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class SidePanel extends StatelessWidget {
  const SidePanel({super.key, required this.viewModel});
  final NodeViewModel viewModel;

  @override
  Widget build(BuildContext context) {
    final vm = viewModel;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (vm.enrolling != null) ...[
          EnrollmentCard(viewModel: vm),
          const SizedBox(height: 16),
        ],
        Section(
          title: 'Estado del nodo',
          children: [
            InfoRow('Política', '${vm.policyLabel} · ${vm.lastSyncLabel}'),
            InfoRow(
              'Vigencia sin central',
              vm.validityLabel,
              color: vm.policyExpired ? Palette.red : null,
            ),
            InfoRow('Rostros enrolados', '${vm.templates}'),
            InfoRow(
              'Eventos por enviar',
              '${vm.pendingEvents}',
              color: vm.pendingEvents > 0 ? Palette.amber : null,
            ),
            InfoRow(
              'Verificador facial',
              vm.verifierLabel,
              color: vm.verifierReady ? null : Palette.red,
            ),
            InfoRow('Torniquete', vm.actuatorLabel),
            InfoRow('Tiempo de decisión', vm.latencyLabel),
          ],
        ),
        const SizedBox(height: 16),
        if (vm.syncError != null || vm.verifierDetail != null) ...[
          Section(
            title: 'Atención',
            children: [
              for (final message in [vm.syncError, vm.verifierDetail])
                if (message != null)
                  Text(message, style: const TextStyle(color: Palette.red)),
            ],
          ),
          const SizedBox(height: 16),
        ],
        if (vm.enrolling == null)
          Section(
            title: 'Últimos accesos',
            children: [
              if (vm.recent.isEmpty)
                const Text(
                  'Acércate a la cámara para validar tu acceso.',
                  style: TextStyle(color: Palette.muted),
                ),
              for (final access in vm.recent) RecentRow(access),
            ],
          ),
      ],
    );
  }
}

class Section extends StatelessWidget {
  const Section({super.key, required this.title, required this.children});
  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(20),
    decoration: BoxDecoration(
      color: Palette.panel,
      borderRadius: BorderRadius.circular(18),
      border: Border.all(color: Palette.line),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: const TextStyle(
            color: Palette.text,
            fontSize: 15,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 8),
        ...children,
      ],
    ),
  );
}

class InfoRow extends StatelessWidget {
  const InfoRow(this.label, this.value, {super.key, this.color});
  final String label;
  final String value;
  final Color? color;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 9),
    child: Row(
      children: [
        Expanded(
          child: Text(label, style: const TextStyle(color: Palette.muted)),
        ),
        Text(
          value,
          style: TextStyle(
            fontWeight: FontWeight.w600,
            color: color ?? Palette.text,
          ),
        ),
      ],
    ),
  );
}

class RecentRow extends StatelessWidget {
  const RecentRow(this.access, {super.key});
  final RecentAccess access;

  @override
  Widget build(BuildContext context) {
    final color = access.allowed ? Palette.green : Palette.red;
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Row(
        children: [
          Icon(
            access.allowed ? Icons.check_circle : Icons.cancel,
            size: 18,
            color: color,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  access.name,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    color: Palette.text,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                Text(
                  access.reason,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Palette.muted, fontSize: 12),
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Text(
            access.time,
            style: const TextStyle(color: Palette.muted, fontSize: 12.5),
          ),
        ],
      ),
    );
  }
}

class EnrollmentCard extends StatelessWidget {
  const EnrollmentCard({super.key, required this.viewModel});
  final NodeViewModel viewModel;

  @override
  Widget build(BuildContext context) {
    final job = viewModel.enrolling!;
    final progress = (job['progress'] as num).toInt();
    final total = (job['total'] as num).toInt();
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Palette.amber.withValues(alpha: .1),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Palette.amber),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'ENROLAMIENTO EN CURSO',
            style: TextStyle(
              color: Palette.amber,
              fontWeight: FontWeight.w700,
              fontSize: 12.5,
              letterSpacing: 1.1,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            '${job['name']}',
            style: const TextStyle(
              fontSize: 22,
              fontWeight: FontWeight.w700,
              color: Palette.text,
            ),
          ),
          Text(
            '${job['student_id']}',
            style: const TextStyle(color: Palette.muted),
          ),
          const SizedBox(height: 14),
          LinearProgressIndicator(
            value: progress / total,
            minHeight: 9,
            color: Palette.amber,
            backgroundColor: Palette.line,
            borderRadius: BorderRadius.circular(8),
          ),
          const SizedBox(height: 8),
          Text(
            'Captura $progress de $total · quedan ${job['seconds_left']} s',
            style: const TextStyle(color: Palette.muted),
          ),
          const SizedBox(height: 14),
          OutlinedButton.icon(
            onPressed: viewModel.cancelEnrollment,
            icon: const Icon(Icons.close, size: 18),
            label: const Text('Cancelar enrolamiento'),
          ),
        ],
      ),
    );
  }
}
