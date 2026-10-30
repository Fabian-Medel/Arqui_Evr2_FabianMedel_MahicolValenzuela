# SAAD-Campus · Nodo central

| Artefacto | Archivo | Responsabilidad |
| --- | --- | --- |
| API central | `app.py` (`api`, 127.0.0.1:8000) | Login, administración de estudiantes y permisos versionados, enrolamientos, nodos, monitor en vivo |
| API sync | `sync_app.py` (`sync`, sin puertos publicados) | Política para los nodos, lotes de eventos con ACK, resultados de enrolamiento |
| Proxy mTLS | `edge-tls/nginx.conf` (`edge_tls`, puerto 8443) | TLS 1.3 con certificado de cliente; el `X-Node-Id` sale del CN del certificado |
| Repository | `repository.py` | Único módulo con SQL |
| Credenciales | `security.py` | Argon2, JWT de 30 minutos, claves de nodo |
| Datos | PostgreSQL 17 (`db`, sin puertos publicados) | Usuarios, estudiantes, permisos, política, eventos, actuaciones, auditoría |
| Panel | `../lib/saad_admin.dart` (Flutter web, localhost:3000) | Administración; solo para el rol admin |

## Iniciar

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\central\iniciar_central.ps1
```

Levanta los contenedores, sirve el panel y abre http://localhost:3000. La primera vez, `central\setup.ps1`
genera `.env`. Editar `ADMIN_PASSWORD` después de crear la base no cambia la contraseña del usuario ya registrado.

- Recompilar el panel: `powershell -NoProfile -ExecutionPolicy Bypass -File .\central\start-panel.ps1 -Rebuild`
- Limpiar datos antes de una demostración: `central\limpiar_para_demo.ps1` (con `-Todo` también borra estudiantes)
- Detener sin borrar datos: `docker compose -f compose.yaml -f compose.edge.yaml stop`
- No ejecutar `down -v` si se quieren conservar los datos.

## Cambiar de red

El proxy atiende en cualquier red, pero el nodo guarda la dirección de la central en `edge-01-connection\connection.json`.
Al cambiar de red hay que actualizarla en el edge-01 y reiniciar el nodo. El certificado de la central solo es válido para:

| Red | IP de la central | Dirección en `connection.json` |
| --- | --- | --- |
| Wi-Fi | 192.168.1.23 | `https://192.168.1.23:8443` |
| Hotspot del iPhone | 172.20.10.6 | `https://172.20.10.6:8443` |

Si la central recibe otra IP, hay que fijarla o emitir un certificado nuevo. En una red privada, además, la regla de firewall
`SAAD-Edge01-mTLS` debe permitir la IP del edge-01; en una red pública basta la regla de Docker Desktop.

## Pruebas

```powershell
docker compose exec -T api python smoke_test.py
```

Prueba contra las APIs en ejecución: login, roles, permisos versionados, cursor de política, lotes idempotentes,
conflictos 409/413, actuación, enrolamiento, eliminación y monitor en vivo. Crea registros `TEST-` y los elimina al terminar.

## Contrato con los nodos (API sync)

Toda llamada lleva `X-Node-Key` y, si ya tiene política, `X-Policy-Version`. Un ciclo del nodo sigue este orden:

1. `GET /edge/policies?known_version=N`: primero la política, para que una revocación prevalezca. Devuelve `policy_version`
   y `node_last_seq`. Si `N` sigue vigente responde `replace_snapshot: false`; si no, la instantánea completa
   (`permissions`, `students`), que el nodo aplica de forma atómica. Sin `known_version` siempre entrega la instantánea.
2. `POST /edge/batch` con `events` y `actuations` (máximo 500 registros y 512 KiB, si no 413). Todo o nada: devuelve
   `accepted_ids` y `accepted_actuations`, y solo esos se marcan confirmados en el nodo. Reenviar un lote es idempotente.
   Reutilizar un UUID con otros datos o repetir una secuencia responde 409 con `code` (`id_conflict`, `seq_conflict`).
   - Evento: `id`, `student_id` (o null), `zone`, `allowed`, `occurred_at` (ISO 8601 con zona), `seq`, `policy_version`, `reason`.
   - Actuación: `event_id`, `status` (`ack`, `simulado`, `sin_actuador`, `sin_respuesta`), `detail`, `occurred_at`.
3. `POST /edge/enrollments/{student_id}` con `{"status": "enrolled"}` o `{"status": "failed", "detail": "..."}`.
4. `GET /edge/enrollments`: órdenes pendientes de ese nodo.

La central no reconoce rostros ni autoriza cada ingreso, y no recibe fotografías ni plantillas biométricas.
Un nodo sin solicitudes autenticadas durante 30 segundos se muestra desconectado.

## Roles

El panel es solo para `admin`. La API ya distingue `admin`, `auditor` y `estudiante` (lectura sin modificar; el estudiante
solo ve lo propio) para cuando se habilite en la interfaz.

## Pendientes

Archivo WORM (MinIO Object Lock), factor NFC, OIDC/MFA, cambio y bloqueo de cuentas, limitación de intentos de login,
políticas con vigencia, paginación del historial, respaldo, firma de contenido y migraciones versionadas (hoy el esquema
se actualiza al arrancar). Las dependencias Python usan rangos: fijar un lock antes de un despliegue definitivo.
