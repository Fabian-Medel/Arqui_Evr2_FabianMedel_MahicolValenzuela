# Guion del video · SAAD-Campus

Cubre el flujo del informe, "administrar permiso → distribuir política → validar ingreso → registrar y sincronizar",
y los casos de la sección 4.3. Duración estimada: 8 a 10 minutos.

**Pantallas a grabar:** panel central (PC central) y kiosco (PC edge-01). Conviene tener ambas visibles o alternarlas.

## Antes de grabar

**PC central**, en una PowerShell dentro de `saad_campus`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\central\iniciar_central.ps1
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\central\limpiar_para_demo.ps1 -Todo
```

**PC edge-01**, en `C:\Users\gokux\Projects\saad-campus-edge`:

```powershell
.\.venv\Scripts\python.exe .\reset_edge.py
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\iniciar_nodo.ps1
```

Escribe la clave de la base cifrada en el kiosco. Luego, en otra PowerShell del edge-01, simula las 09:00 para grabar a cualquier
hora y poder mostrar el cambio de jornada sin esperar hasta las 13:00:

```powershell
.\.venv\Scripts\python.exe .\demo_tools.py hora 09:00
```

Comprueba que el kiosco diga **Jornada Mañana · hasta 12:00 · hora simulada 09:00** y **Central conectada** (ambos PC deben estar en la misma red), y que en el panel,
en *Nodos de acceso*, edge-01 aparezca **En línea** y **al día**. Ten dos personas a mano: una se enrola y la otra hace de desconocido.

**Al terminar de grabar**, vuelve a la hora real:

```powershell
.\.venv\Scripts\python.exe .\demo_tools.py hora real
```

## Escenas

### 1. Arquitectura (30 s)
- **Muestra:** el diagrama del informe y, en la PC central, `docker compose ps`.
- **Di:** cada contenedor es un artefacto del diagrama: `api` es la API central, `sync` la API sync, `edge_tls` la puerta mTLS y `db` PostgreSQL. El nodo decide localmente; la central es la autoridad sobre estudiantes y permisos.

### 2. Administrador y enrolamiento (1 min)
- **Haz:** inicia sesión en el panel como `admin`. En *Estudiantes* pulsa **+ Estudiante**, escribe identificador y nombre, deja marcada `ENTRADA-PRINCIPAL`, elige **Cámara de edge-01** y pulsa **Guardar y enrolar**.
- **Se ve:** en menos de 5 segundos el kiosco muestra **Enrolamiento en curso** con el nombre. Mira a la cámara: 5 capturas, **ROSTRO ENROLADO**. El panel cambia a **Enrolado · edge-01**.
- **Di:** la imagen nunca sale del nodo. La plantilla queda en SQLCipher y a la central solo llega el estado.

### 3. Caso A · Acceso autorizado (45 s)
- **Haz:** sal del cuadro y vuelve a acercarte.
- **Se ve:** **ACCESO AUTORIZADO**, el nombre, los milisegundos de la decisión local y "Apertura simulada: maqueta sin hardware". En la *Vista general* del panel aparece el evento con su motivo, apertura y número de evento.
- **Di:** la decisión se toma sin la WAN; la meta del informe es bajo 500 ms. Sin Arduino conectado el sistema marca la apertura como simulada: un ACK real solo llegaría del controlador.

### 4. Acceso repetido en la misma jornada (15 s)
- **Haz:** sal del cuadro y vuelve a acercarte.
- **Se ve:** en azul, **ACCESO YA CONCEDIDO** con la hora del ingreso y **Jornada Mañana**. No se crea otro evento.

### 5. Jornadas: cierre y nuevo ingreso en la tarde (1 min)
- **Di:** el recinto tiene dos jornadas, de 08:00 a 12:00 y de 13:00 a 18:00. Al cerrar, quienes ingresaron quedan liberados. Para no esperar usamos una hora simulada, que el kiosco indica en pantalla.
- **Haz:** en el edge-01 simula el cierre y acércate cuando la barra superior diga **Recinto cerrado · abre 13:00**:

  ```powershell
  .\.venv\Scripts\python.exe .\demo_tools.py hora 12:30
  ```

- **Se ve:** **RECINTO CERRADO · Próxima apertura: 13:00**. El intento queda registrado como denegado.
- **Haz:** simula el inicio de la tarde y acércate cuando la barra diga **Jornada Tarde · hasta 18:00**:

  ```powershell
  .\.venv\Scripts\python.exe .\demo_tools.py hora 13:05
  ```

- **Se ve:** **ACCESO AUTORIZADO**: el mismo estudiante vuelve a ingresar y no aparece "ya concedido". En el panel quedan dos ingresos autorizados el mismo día.

### 6. Caso B · Denegado y rostro no reconocido (45 s)
- **Haz:** la otra persona, sin enrolar, se acerca a la cámara.
- **Se ve:** **ROSTRO NO RECONOCIDO · Intente nuevamente o solicite su enrolamiento**. Lo reintenta solo hasta 3 veces. El panel registra los intentos como denegados.

### 7. Caso D · Revocación (45 s)
- **Haz:** en *Estudiantes*, haz clic en el acceso de la primera persona para dejarlo en **Sin acceso**. Mira que la **Política** suba de versión en el panel y en el kiosco, en unos 5 segundos. Luego acércate.
- **Se ve:** **ACCESO DENEGADO · Sin permiso para esta zona**.
- **Di:** la política se descarga antes de subir eventos, para que una revocación prevalezca. Después vuelve a dejarlo en **Permitido**.

### 8. Caso C · Modo Isla (1 min 30 s)
- **Haz:** en la PC central, dentro de `central`, detén la API sync:

  ```powershell
  docker compose -f compose.yaml -f compose.edge.yaml stop sync
  ```

- **Se ve:** en unos 5 segundos el kiosco cambia a **Modo Isla**, con una franja que indica la política y la vigencia restante. En el panel, tras 30 segundos, edge-01 pasa a **Desconectado**.
- **Haz:** acércate a la cámara. Como su permiso cambió en la escena anterior, cuenta como un ingreso nuevo.
- **Se ve:** **ACCESO AUTORIZADO** sin central, y **Eventos por enviar: 1**.
- **Haz:** vuelve a levantar la API sync:

  ```powershell
  docker compose -f compose.yaml -f compose.edge.yaml start sync
  ```

- **Se ve:** vuelve **Central conectada**, **Eventos por enviar** baja a 0 y el evento aparece en el panel con su hora original.
- **Di:** es el outbox: el evento se guarda antes de actuar y solo se marca confirmado con el ACK. Reenviar no lo duplica. El riesgo residual: durante el corte, una revocación no llega al nodo hasta reconectar.

### 9. Caso F · Política vencida (45 s)
- **Haz:** detén otra vez `sync` y, en el edge-01, en una PowerShell aparte:

  ```powershell
  .\.venv\Scripts\python.exe .\demo_tools.py vencer
  ```

  Espera a que **Vigencia sin central** diga **Vencida** y acércate.
- **Se ve:** **ACCESO DENEGADO · Política vencida: más de 72 h sin sincronizar**.
- **Di:** es una simulación de 73 horas, no un ensayo real de 72 horas. El nodo prefiere denegar antes que decidir con datos viejos.
- **Haz:** levanta `sync` otra vez y muestra que la vigencia vuelve a 72 h.

### 10. Caso E · Roles en la API (30 s)
- **Haz:** en la PC central, crea un auditor y prueba modificar un permiso:

  ```powershell
  $admin = Invoke-RestMethod -Method Post http://localhost:8000/login -ContentType 'application/json' -Body (@{username='admin'; password=(Read-Host 'Clave admin')} | ConvertTo-Json)
  ```

  ```powershell
  $h = @{Authorization = "Bearer $($admin.access_token)"}
  ```

  ```powershell
  Invoke-RestMethod -Method Post http://localhost:8000/users -Headers $h -ContentType 'application/json' -Body (@{username='auditor'; password='clave-de-auditor-1'; role='auditor'} | ConvertTo-Json)
  ```

  ```powershell
  $aud = Invoke-RestMethod -Method Post http://localhost:8000/login -ContentType 'application/json' -Body (@{username='auditor'; password='clave-de-auditor-1'} | ConvertTo-Json)
  ```

  ```powershell
  Invoke-RestMethod -Method Put http://localhost:8000/permissions -Headers @{Authorization = "Bearer $($aud.access_token)"} -ContentType 'application/json' -Body (@{student_id='x'; zone='y'; enabled=$true} | ConvertTo-Json)
  ```

- **Se ve:** error **403 Requiere administrador**. La lectura sí está permitida. El panel de esta entrega es solo para administradores.

### 11. Auditoría y cierre (30 s)
- **Haz:** abre *Auditoría* y *Nodos de acceso*.
- **Di:** cada acción queda registrada y el panel muestra qué versión de política aplicó cada nodo. Límites de esta entrega: el Arduino no está conectado, no hay factor NFC ni archivo WORM, y el reconocimiento no detecta suplantación con fotos.

## Si algo falla durante la grabación

| Síntoma | Qué hacer |
| --- | --- |
| El kiosco dice que el servicio no está en marcha | Vuelve a ejecutar `iniciar_nodo.ps1` |
| Dice **Recinto cerrado** a todos | Estás fuera de jornada: ejecuta `demo_tools.py hora 09:00` |
| Pide acercarse aunque estés cerca | Más luz en el rostro y mira de frente; el rostro debe ocupar al menos un cuarto del ancho del video |
| No te reconoce | Reenrola desde el panel con la misma luz y distancia que usarás al verificar |
| Modo Isla sin motivo | Revisa `docker compose -f compose.yaml -f compose.edge.yaml ps` y que ambos PC sigan en la misma red. Si cambiaron de red, actualiza la dirección del nodo (ver *Cambiar de red* en `central/README.md`) |

## Qué actualizar en el informe

Lo construido difiere de la V2 en estos puntos; conviene alinearlos para que informe y video digan lo mismo:

| Tema | Informe | Implementación actual |
| --- | --- | --- |
| Interfaces | Vue 3 | Flutter: panel web y kiosco de Windows; el kiosco separa ViewModel y vista (MVVM) |
| Sistema del nodo | Linux / Raspberry Pi | Notebook con Windows (edge-01) |
| Factor facial | `DemoFaceProof`, sin autenticar rostros | Reconocimiento real con YuNet + SFace; `UnavailableStrategy` como fallo seguro |
| Factor NFC | Validador NFC-#### | No incluido: solo rostro |
| Archivo WORM | MinIO Object Lock | No incluido: pendiente |
| Actuador | Arduino + SG90 | Adaptador y sketch escritos; sin hardware conectado, modo simulado |
| Contraseñas y tokens | PBKDF2 y HMAC | Argon2 y JWT |
| Datos centrales | PostgreSQL 16 con SQLAlchemy | PostgreSQL 17 con psycopg y `repository.py` |
| TLS | Mínimo TLS 1.3 pendiente | Resuelto: el proxy solo acepta TLS 1.3 |
| Servicios del nodo | Face, NFC, Access y Worker separados | Un proceso modular más el adaptador (alternativa de monolito modular de ADR-01) |
| Kiosco → orquestador | HTTPS | HTTP en loopback (127.0.0.1) |
| Rutas | `/api/login`, `/api/permissions`, `/policies` | `/login`, `/permissions`, `/edge/policies`, `/edge/batch` |
| Jornadas | No se mencionan | Dos jornadas diarias, 08:00–12:00 y 13:00–18:00: un ingreso por jornada y recinto cerrado fuera de ellas |
| Roles | Administrador, estudiante y auditor en la interfaz | La API aplica los tres roles; el panel es solo para admin |
| Autonomía y latencia | Metas sin medir | La caducidad de 72 h se probó simulando el tiempo. La latencia p95 estuvo bajo 200 ms en pruebas con imágenes en el PC central; hay que medirla en el edge-01 (el kiosco la muestra) |
