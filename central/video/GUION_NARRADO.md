# Video de 4 minutos · SAAD-Campus

Formato: MP4 de 1920×1080. Duración objetivo: entre 4:05 y 4:30, porque la pauta exige mínimo 4 minutos.

## Lo que necesito de ustedes

### 1. Dos grabaciones de pantalla, sin voz

Una en cada PC, en una sola toma larga. Yo corto y ordeno todo después.

1. Dejen ambos PC listos con la sección *Antes de grabar* de `GUION_VIDEO.md`.
2. Maximicen el kiosco y el navegador del panel. Cierren WhatsApp y otras notificaciones.
3. En cada PC abran la grabación de pantalla con **Windows + Shift + R**, elijan la pantalla completa y pulsen *Iniciar*.
4. Hagan las escenas 2 a 10 de `GUION_VIDEO.md`, sin hablar y sin apuro.
5. Después de cada resultado en el kiosco, quédense **3 segundos quietos**.
6. Detengan la grabación y guárdenla como `central.mp4` y `nodo.mp4`.

### 2. Las voces

Lean el texto de abajo con el celular, en un lugar silencioso, a ritmo normal. Puede ser un audio largo por persona o un audio por escena.
Si se equivocan, repitan la frase: yo corto lo que sobre. Guárdenlos como `voz_mahicol` y `voz_fabian`.

### 3. Dónde dejar todo

`C:\Users\maiqo\Videos\SAAD-video\material`

La grabación del edge-01 hay que pasarla a este PC con un USB.

## Texto para leer

### 1. Apertura · Mahicol

Hola, somos Mahicol Valenzuela y Fabián Medel. Les presentamos SAAD-Campus, un sistema de control de acceso para cuatro campus universitarios y más de treinta mil usuarios. El desafío es responder en menos de medio segundo y seguir operando hasta setenta y dos horas sin conexión con la central.

### 2. Arquitectura · Fabián

Para lograrlo usamos una arquitectura Edge-to-Central. La central administra estudiantes, permisos y auditoría, con FastAPI y PostgreSQL. El nodo perimetral decide cada acceso de forma local: reconoce el rostro y consulta su base cifrada con SQLCipher, sin depender de la red. Ambos se sincronizan por HTTPS con certificado de cliente y TLS 1.3. La imagen del rostro nunca sale del nodo: a la central solo llegan decisiones y estados.

### 3. Enrolamiento · Mahicol

Partimos en el panel de administración. Creamos un estudiante, le damos acceso a la entrada principal y pedimos enrolar su rostro en el nodo. En pocos segundos, el kiosco recibe la orden y toma cinco capturas. La plantilla queda cifrada en el nodo y el panel cambia a Enrolado.

### 4. Acceso autorizado · Mahicol

Ahora el estudiante se acerca a la cámara. El nodo lo reconoce, valida su permiso con la política local y registra el evento antes de mostrar el resultado. Acceso autorizado, y aquí se ve cuánto tardó la decisión. El evento ya aparece en la central, con su motivo y su secuencia. Como aún no conectamos el Arduino, el sistema lo informa y marca la apertura como simulada.

### 5. Jornadas · Fabián

El recinto funciona en dos jornadas: de ocho a doce y de trece a dieciocho. Si el estudiante vuelve en la misma jornada, el sistema avisa que el acceso ya fue concedido y no crea otro ingreso. A las doce el recinto cierra y todos quedan liberados. Para no esperar, usamos una hora simulada que se indica en pantalla. Fuera de jornada, el acceso se deniega. Y a las trece, el mismo estudiante puede ingresar de nuevo.

### 6. Rostro no reconocido · Mahicol

Si se acerca alguien sin enrolar, el nodo deniega y le pide intentar nuevamente o solicitar su enrolamiento. Cada intento queda registrado.

### 7. Revocación · Fabián

Ahora el administrador revoca un permiso con un clic. La versión de la política sube y, en segundos, el nodo la descarga. Cuando el estudiante vuelve, el acceso se deniega. Cada ciclo descarga la política antes de subir eventos, para que una revocación siempre prevalezca.

### 8. Modo Isla · Mahicol

Probemos un corte de red: detenemos la API de sincronización. El kiosco entra en Modo Isla, pero sigue decidiendo con la política descargada. El acceso se autoriza y el evento queda pendiente en la cola local. Al volver la conexión, se envía en lote y la central confirma cada evento, sin duplicarlos. Es el patrón outbox: primero se guarda y después se sincroniza.

### 9. Política vencida · Fabián

La autonomía tiene un límite. Simulamos setenta y tres horas sin sincronizar y el nodo deniega: prefiere no decidir con datos viejos. Al reconectar, la vigencia vuelve a setenta y dos horas.

### 10. Roles y código · Fabián

Los roles se validan en la API: si un auditor intenta modificar un permiso, responde cuatro cero tres. En el código aplicamos Repository, porque las consultas del nodo viven en store punto py y no en la lógica de acceso, y Strategy, porque la verificación facial es intercambiable: si el verificador falla, nadie es reconocido y se deniega. Además, los permisos tienen versión: si dos cambios chocan, la central responde cuatro cero nueve.

### 11. Cierre · Mahicol

Así completamos el flujo: administrar el permiso, distribuir la política, validar el ingreso y sincronizar el evento. Quedan pendientes el factor NFC, el archivo WORM, conectar el Arduino real y detectar suplantación con fotos. Muchas gracias.
