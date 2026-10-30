SAAD-Campus: kiosco web local para edge-01

ACTUALIZACION: NOMBRES COMPLETOS
La central sincroniza el nombre registrado en Estudiantes. El kiosco lo conserva
en student_directory dentro de SQLCipher para mostrarlo incluso sin conexion.
No modifica el identificador de los permisos, plantillas faciales ni eventos.
Si aun no hay nombre sincronizado, indica Nombre pendiente de sincronizacion.

INSTALACION EN EL NOTEBOOK DE GOKUX
1. Detener con Ctrl+C edge_api.py y cualquier prueba de camara.
2. Extraer el ZIP dentro de:
   C:\Users\gokux\Projects\saad-campus-edge
   Debe quedar la carpeta saad-edge-kiosk dentro de esa raiz.
   Ejecutar: powershell -NoProfile -ExecutionPolicy Bypass -File .\saad-edge-kiosk\install.ps1
   El instalador comprueba requisitos y guarda copia de archivos que actualiza.
   No se incluyen ni reemplazan edge_db.py, verify_face.py, data, models o edge-01-connection.
3. En PowerShell:
   Set-Location 'C:\Users\gokux\Projects\saad-campus-edge'
   .\.venv\Scripts\python.exe .\edge_web.py
4. Introducir la clave existente de SQLCipher. No se guarda en archivos.
5. Abrir http://127.0.0.1:8001 en el navegador DEL EDGE.

FUNCIONAMIENTO
- Presionar Verificar mi acceso. La captura y comparacion ocurren en el edge.
- Se registra el UUID del intento en SQLCipher antes de mostrar autorizacion.
- Sincronizacion al iniciar y 10 segundos despues de cada ciclo completado.
- En cada ciclo se reemplaza atomicamente la instantanea de permisos.
- Se envian hasta 50 eventos pendientes por ciclo, conservando sus UUID.
- Solo una confirmacion ok de la central permite marcarlos enviados.
- Si la red falla, se reintenta y los eventos permanecen pendientes.
- Permisos validos como maximo 15 minutos desde ultima sincronizacion.
- Una revocacion no recibida aun puede seguir autorizando dentro de esa ventana.
- Sin certificado valido o con IP de central cambiada, la sincronizacion falla.
- La imagen de camara se muestra solo en localhost; no se envia a la central.
- No ejecutar sync_once.py simultaneamente con el kiosco: ya incluye sincronizacion.
- Mantener abierta la terminal; cerrar con Ctrl+C libera la camara.
- No ejecutar varios procesos o workers ni exponer este servicio a la red.

PRUEBAS EN LOS DOS EQUIPOS
1. Rostro registrado y permiso habilitado: autorizado; aparece en central.
2. Revocar permiso en central, esperar sincronizacion y verificar: denegado.
3. Rehabilitarlo y esperar sincronizacion antes de la siguiente prueba.
4. Rostro no registrado, camara vacia o varios rostros: denegado.
5. Desconectar red DEL EDGE, verificar dentro de 15 minutos: decision local.
6. Reconectar: disminuyen eventos pendientes y aparecen en central sin duplicados.
7. Mas de 15 minutos sin actualizar permisos: denegado incluso con rostro conocido.

ALCANCE
Prototipo academico. Sin prueba de vida, sin control de puerta fisica.
Los umbrales de similitud necesitan calibracion. No garantiza 72 h offline.
La pantalla /health comprueba acceso a la base y carga del motor facial;
no certifica precision biometrica ni disponibilidad de la central.
La fecha y hora se muestran en la zona del navegador.
Se usa la misma base y el mismo registro facial ya probados.
Para volver a la API anterior, detener este programa y ejecutar edge_api.py.
