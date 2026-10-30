# SAAD-Campus · Nodo perimetral (edge-01)

Las decisiones de acceso se toman aquí, sin depender de la WAN. Si la central no responde, el nodo sigue en Modo Isla con
la política descargada hasta 72 horas; después deniega. Las imágenes y plantillas faciales no salen del equipo.

| Artefacto | Archivo | Responsabilidad |
| --- | --- | --- |
| Access API | `edge_service.py` (127.0.0.1:8001) | Orquesta cámara, verificación, decisión y actuador; atiende al kiosco |
| Repository | `store.py` | Único módulo con SQL sobre SQLCipher; `validate()`, `record_event()`, `pending()`, `acknowledge()` |
| Strategy facial | `verification.py` | `FaceVerificationStrategy`: `SFaceStrategy` real y `UnavailableStrategy` de fallo seguro |
| Sync Worker | `sync_worker.py` | Mismo ciclo que la API sync: política primero, outbox con ACK, HTTPS con certificado de cliente |
| Adaptador USB serial | `actuator/app.py` (127.0.0.1:8002) | `OPEN:<event_id>` y `ACK` por USB a 9600 baudios; `--simular` sin hardware |
| Controlador físico | `arduino/Torniquete_SAAD/Torniquete_SAAD.ino` | Arduino + SG90, actuador esclavo |
| Kiosco | `edge_app/` (Flutter Windows, MVVM) | `node_view_model.dart` (estado) y `node_screen.dart` (vista) |
| Jornadas | `schedule.py` | Jornada abierta y próxima apertura, en hora local del nodo |
| Configuración | `config.py` | Zona, 72 h, jornadas, tiempos |
| Base cifrada | `edge_db.py`, `data\edge.db` | Creada en el edge-01; no se reemplaza |

## Instalar en edge-01

Descomprimir el paquete en `C:\Users\gokux\Projects\saad-campus-edge\`, junto a `edge_db.py`. Debe contener también
`edge-01-connection\` (certificados y `connection.json` con `"url": "https://192.168.1.23:8443"`) y
`models\yunet.onnx` + `models\sface.onnx`. El kiosco se entrega compilado en `app\`.

## Uso

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar_nodo.ps1
```

Abre el adaptador en modo simulado, la API de acceso y el kiosco, reiniciándolos si ya estaban abiertos. Con el Arduino
conectado se agrega `-Arduino` y hace falta `.\.venv\Scripts\python.exe -m pip install pyserial`.

- `demo_tools.py estado`: versión de política, rostros y eventos sin confirmar.
- `demo_tools.py vencer`: simula 73 h sin sincronizar (caso F; usar en Modo Isla, al reconectar se corrige solo).
- `demo_tools.py hora 13:05`: simula esa hora para las jornadas, y el kiosco lo indica. `demo_tools.py hora real` la desactiva.
- `reset_edge.py`: vacía rostros, permisos y eventos, conservando la base cifrada y su clave. Detener antes el servicio.

## Comportamiento

- Una decisión por acercamiento: exige 5 cuadros estables y considera que la persona se fue tras 20 cuadros sin rostro.
- Si no reconoce el rostro permite 3 intentos sin salir del cuadro y pide intentar de nuevo o solicitar el enrolamiento.
- Jornadas de 08:00 a 12:00 y de 13:00 a 18:00 (`JORNADAS` en `config.py`), según el reloj del equipo. Cada estudiante ingresa una vez por jornada: si vuelve, se informa como ya concedido y no se crea evento. Al cerrar queda liberado y en la jornada siguiente puede ingresar otra vez. Si le revocan y devuelven el permiso, su ingreso anterior deja de contar.
- Fuera de jornada el recinto está cerrado: se deniega y se registra el intento. El enrolamiento sigue disponible.
- El evento se persiste antes de mostrar el resultado o actuar. El estado físico se registra aparte: sin ACK no se declara apertura.
- Umbrales de detección (0.9) y reconocimiento (0.50): valores de demostración que requieren calibración propia.
  No hay detección de suplantación: una foto frente a la cámara puede ser aceptada.

## Compilar el kiosco

Requiere Visual Studio con C++ (el edge-01 no lo tiene; se compila en el equipo central):

```powershell
Set-Location edge\edge_app
flutter build windows
```

El resultado queda en `build\windows\x64\runner\Release`.

El sketch `Torniquete_SAAD.ino` no se ha compilado ni probado en una placa. El adaptador se verificó con un puerto serie simulado.
