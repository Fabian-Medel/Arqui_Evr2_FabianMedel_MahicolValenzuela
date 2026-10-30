"""API de acceso del nodo (artefacto "Access API · decision local"): orquesta camara, verificador facial,
base cifrada, actuador y sincronizacion. La app Flutter del kiosco la usa por http://127.0.0.1:8001; no escucha en la red.

Las imagenes y plantillas no salen de este equipo: a la central solo van decisiones, estados y resultados.
La decision no depende de la WAN: si la central no responde, el nodo sigue operando en Modo Isla con la politica
descargada, hasta POLICY_MAX_AGE_HOURS. Cualquier fallo del verificador o de la politica termina en denegacion.
"""
import json
import queue
import threading
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timezone

import cv2
import uvicorn
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel

import config
import schedule
import store
from edge_db import connect, DB_PATH
from sync_worker import CentralClient, SyncWorker
from verification import select_strategy

NOT_RECOGNIZED = {'no_match': 'Rostro no reconocido', 'no_templates': 'Rostro no reconocido',
                  'ambiguous': 'Coincidencia ambigua', 'invalid_capture': 'Captura inválida',
                  'unavailable': 'Verificador facial no disponible'}
RETRYABLE = {'no_match', 'no_templates', 'ambiguous', 'invalid_capture'}
PHYSICAL_TEXT = {'ack': 'Apertura confirmada por Arduino (ACK)', 'simulado': 'Apertura simulada: maqueta sin hardware',
                 'sin_actuador': 'Actuador no disponible: no se declara apertura',
                 'sin_respuesta': 'Arduino sin respuesta: no se declara apertura'}
COLORS = {'idle': (245, 141, 92), 'enrolling': (58, 166, 224), 'allowed': (122, 166, 31), 'denied': (84, 84, 217)}

class NodeState:
    def __init__(self):
        self.lock = threading.Lock()
        self.password = None
        self.node_id = 'nodo'
        self.verifier = None
        self.frame = None
        self.camera_error = None
        self.sync_error = None
        self.hint = ''
        self.central_online = False
        self.policy = {'version': None, 'last_sync': None}
        self.demo_time = None
        self.counts = {'templates': 0, 'pending_events': 0}
        self.recent = []
        self.result = None
        self.enrolling = None
        self.cancel = False
        self.actuator = {'mode': 'apagado', 'detail': None}
        self.latencies = deque(maxlen=200)

state = NodeState()
actuations = queue.Queue()

def show_result(seconds=config.RESULT_SECONDS, **result):
    state.result = {'physical': None, **result, 'until': time.monotonic() + seconds}

def refresh(db):
    state.counts = store.counts(db)
    state.recent = store.recent(db)

# --- Decision de acceso ---------------------------------------------------------------------------

def decide(db, image, face):
    """Verifica, valida con la politica local y persiste antes de mostrar o actuar. Devuelve el codigo de la decision."""
    started = time.perf_counter()
    match = state.verifier.identify(image, face, store.templates(db))
    if match.student_id is None:
        reason = NOT_RECOGNIZED[match.code]
        store.record_event(db, None, config.ZONE, False, reason)
        latency = (time.perf_counter() - started) * 1000
        state.latencies.append(latency)
        show_result(code='not_recognized' if match.code in ('no_match', 'no_templates') else match.code, student_id=None,
                    name='Desconocido', allowed=False, reason=reason, latency_ms=round(latency),
                    seconds=3 if match.code in RETRYABLE else config.RESULT_SECONDS)
        refresh(db)
        return match.code
    student = match.student_id
    name = store.student_name(db, student)
    simulated = store.demo_time(db)
    jornada = schedule.current(simulated)
    allowed, code, reason = store.validate(db, student, config.ZONE, jornada)
    granted_at = store.last_grant(db, student, config.ZONE, jornada) if allowed else None
    if granted_at:
        show_result(code='repeat', student_id=student, name=name, allowed=True, reason='Acceso ya concedido',
                    granted_at=granted_at, jornada=jornada.name)
        return 'repeat'
    event = store.record_event(db, student, config.ZONE, allowed, reason, jornada)
    latency = (time.perf_counter() - started) * 1000
    state.latencies.append(latency)
    show_result(code=code, student_id=student, name=name, allowed=allowed, reason=reason, event_id=event['id'],
                seq=event['seq'], policy_version=event['policy_version'], latency_ms=round(latency),
                next_opening=schedule.next_opening(simulated))
    if allowed: actuations.put(event['id'])
    refresh(db)
    return code

def finish_enrollment(db, status, detail=None):
    with state.lock:
        job, state.enrolling, state.cancel = state.enrolling, None, False
    store.report_enrollment(db, job['student_id'], status, detail)
    show_result(code='enrolled' if status == 'enrolled' else 'enroll_failed', student_id=job['student_id'], name=job['name'],
                allowed=status == 'enrolled', reason='Rostro enrolado' if status == 'enrolled' else detail)
    refresh(db)

def enroll_step(db, image, faces, close):
    job = state.enrolling
    if state.cancel: return finish_enrollment(db, 'failed', 'Cancelado por el operador')
    if time.monotonic() > job['deadline']: return finish_enrollment(db, 'failed', 'No se logró capturar el rostro a tiempo')
    if close and time.monotonic() - job['last_sample'] >= config.ENROLL_SAMPLE_GAP:
        feature = state.verifier.embed(image, faces[0])
        if feature is not None:
            job['samples'].append(feature)
            job['last_sample'] = time.monotonic()
    if len(job['samples']) >= config.ENROLL_SAMPLES:
        template = state.verifier.build_template(job['samples'])
        if template is None:
            job['samples'] = []  # capturas inconsistentes (movimiento, otra persona): repetir
            return
        other = state.verifier.duplicate_of(job['student_id'], template, store.templates(db))
        if other: return finish_enrollment(db, 'failed', f'El rostro ya está enrolado como {store.student_name(db, other)}')
        store.save_template(db, job['student_id'], template)
        finish_enrollment(db, 'enrolled')

# --- Camara ---------------------------------------------------------------------------------------

def open_camera():
    camera = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_DSHOW)
    if not camera.isOpened(): raise RuntimeError('No se pudo abrir la cámara')
    camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*'MJPG'))
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_SIZE[0])
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_SIZE[1])
    if camera.read()[0]: return camera
    # La camara no acepto el formato pedido: se usa el que trae por defecto.
    camera.release()
    camera = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_DSHOW)
    if not camera.isOpened(): raise RuntimeError('No se pudo abrir la cámara')
    return camera

def corners(image, box, color):
    x, y, w, h = (int(value) for value in box)
    length = max(16, w // 5)
    for px, py, dx, dy in ((x, y, 1, 1), (x + w, y, -1, 1), (x, y + h, 1, -1), (x + w, y + h, -1, -1)):
        cv2.line(image, (px, py), (px + dx * length, py), color, 3, cv2.LINE_AA)
        cv2.line(image, (px, py), (px, py + dy * length), color, 3, cv2.LINE_AA)

def publish_frame(image, faces):
    size = config.PREVIEW_SIZE
    preview = cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA)
    result = state.result
    color = COLORS['enrolling'] if state.enrolling else COLORS['idle'] if not result else COLORS['allowed' if result['allowed'] else 'denied']
    for face in faces:
        corners(preview, (face[:4] * size / image.shape[0]).astype(int), color)
    ok, jpeg = cv2.imencode('.jpg', cv2.flip(preview, 1), [cv2.IMWRITE_JPEG_QUALITY, 82])
    if ok: state.frame = jpeg.tobytes()

def hint_for(count, close, waiting):
    if count > 1: return 'Debe haber una sola persona'
    if count == 0 and not state.enrolling and not schedule.current(state.demo_time): return 'Recinto cerrado'
    if count == 0: return 'Mira a la cámara' if state.enrolling else 'Acércate a la cámara'
    if not close: return 'Acércate un poco'
    if state.enrolling: return 'Mantente quieto'
    return '' if waiting else 'Verificando…'

def watch_camera(db, camera):
    # Una decision por acercamiento. Solo si no se reconoce el rostro se puede reintentar sin salir del cuadro.
    stable, gone, left, retries = 0, 0, True, config.FACE_RETRIES
    while True:
        ok, frame = camera.read()
        if not ok: raise RuntimeError('La cámara no entrega imagen')
        state.camera_error = None
        h, w = frame.shape[:2]
        side = min(h, w)
        top, offset = (h - side) // 2, (w - side) // 2
        image = frame[top:top + side, offset:offset + side]
        faces = state.verifier.detect(image)
        count = len(faces)
        close = count == 1 and faces[0][2] >= side * config.MIN_FACE_RATIO
        stable = stable + 1 if close else 0
        gone = gone + 1 if count == 0 else 0
        if gone >= config.GONE_FRAMES: left, retries = True, config.FACE_RETRIES
        if state.result and time.monotonic() > state.result['until']: state.result = None
        if state.enrolling:
            try: enroll_step(db, image, faces, close)
            except Exception as error: finish_enrollment(db, 'failed', f'Error interno: {error}')
        elif stable >= config.STABLE_FRAMES and not state.result and (left or retries > 0):
            try: code = decide(db, image, faces[0])
            except Exception as error:
                code = 'error'
                show_result(code='error', student_id=None, name='Error', allowed=False, reason=f'Error interno: {error}')
            left, stable = False, 0
            retries = retries - 1 if code in RETRYABLE else 0
        waiting = bool(state.result) or (not left and retries == 0)
        state.hint = hint_for(count, close, waiting)
        publish_frame(image, faces)

def camera_loop():
    db = connect(state.password)
    while True:
        camera = None
        try:
            camera = open_camera()
            watch_camera(db, camera)
        except Exception as error:
            state.frame = None
            state.camera_error = f'Cámara detenida: {error}'
        finally:
            if camera is not None: camera.release()
        time.sleep(3)

# --- Sincronizacion ------------------------------------------------------------------------------

def start_enrollment(db, pending):
    reported = {row[0] for row in store.enrollment_reports(db)}
    with state.lock:
        if state.enrolling: return
        for job in pending:
            if job['student_id'] not in reported:
                state.enrolling = {'student_id': job['student_id'], 'name': job['name'], 'samples': [], 'last_sample': 0.0,
                                   'deadline': time.monotonic() + config.ENROLL_TIMEOUT_SECONDS}
                state.cancel = False
                return

def sync_loop():
    db = connect(state.password)
    worker = None
    try:
        client = CentralClient()
        state.node_id = client.node_id
        worker = SyncWorker(db, client)
    except Exception as error:
        state.sync_error = f'Sin datos de conexión con la central: {error}'
    while True:
        if worker:
            try:
                pending = worker.cycle()
                state.central_online, state.sync_error = True, None
                start_enrollment(db, pending)
            except urllib.error.HTTPError as error:
                state.central_online = False
                state.sync_error = None if error.code >= 500 else f'La central rechazó la sincronización ({error.code})'
            except (urllib.error.URLError, TimeoutError, OSError):
                state.central_online, state.sync_error = False, None
            except Exception as error:
                state.central_online, state.sync_error = False, f'Sincronización detenida: {error}'
        state.policy = store.policy_info(db)
        state.demo_time = store.demo_time(db)
        refresh(db)
        time.sleep(config.SYNC_SECONDS)

# --- Actuador (adaptador USB serial) --------------------------------------------------------------

def actuator_call(path, event_id=None):
    data = None if event_id is None else json.dumps({'event_id': event_id}).encode()
    request = urllib.request.Request(config.ACTUATOR_URL + path, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=4) as response: return json.load(response)

def open_gate(event_id):
    """Solicita la apertura. Solo un ACK (o el modo simulado explicito) se informa como apertura."""
    try:
        return actuator_call('/open', event_id)['status']
    except urllib.error.HTTPError as error:
        return 'sin_respuesta' if error.code == 504 else 'sin_actuador'
    except (urllib.error.URLError, TimeoutError, OSError):
        return 'sin_actuador'

def actuator_health():
    try: return actuator_call('/health')
    except (urllib.error.URLError, TimeoutError, OSError): return {'mode': 'apagado', 'detail': None}

def actuator_loop():
    db = connect(state.password)
    state.actuator = actuator_health()
    while True:
        try: event_id = actuations.get(timeout=5)
        except queue.Empty:
            state.actuator = actuator_health()
            continue
        status = 'sin_actuador' if state.actuator['mode'] == 'apagado' else open_gate(event_id)
        store.record_actuation(db, event_id, status, PHYSICAL_TEXT[status])
        with state.lock:
            result = state.result
            if result and result.get('event_id') == event_id:
                result['physical'] = {'status': status, 'detail': PHYSICAL_TEXT[status]}
                result['until'] = max(result['until'], time.monotonic() + 3)
        refresh(db)

# --- API para el kiosco --------------------------------------------------------------------------

app = FastAPI(title='SAAD-Campus · API de acceso del nodo')

class Unlock(BaseModel):
    password: str

@app.post('/unlock')
def unlock(body: Unlock):
    if state.password: raise HTTPException(409, 'El nodo ya está desbloqueado')
    if not DB_PATH.is_file(): raise HTTPException(400, 'No existe la base cifrada. Ejecuta edge_db.py primero.')
    try:
        db = connect(body.password)
        try:
            store.migrate(db)
            state.policy = store.policy_info(db)
            state.demo_time = store.demo_time(db)
            refresh(db)
        finally: db.close()
    except Exception:
        raise HTTPException(401, 'Clave incorrecta')
    state.verifier = select_strategy()
    state.password = body.password
    for loop in (camera_loop, sync_loop, actuator_loop): threading.Thread(target=loop, daemon=True).start()
    return {'ok': True}

def seconds_left(policy):
    if not policy.get('last_sync'): return None
    age = (datetime.now(timezone.utc) - datetime.fromisoformat(policy['last_sync'])).total_seconds()
    return max(0, round(config.POLICY_MAX_AGE_HOURS * 3600 - age))

def jornada_status():
    jornada = schedule.current(state.demo_time)
    return {'open': jornada is not None, 'name': jornada.name if jornada else None, 'closes': jornada.closes if jornada else None,
            'next_opening': schedule.next_opening(state.demo_time), 'simulated': state.demo_time}

def latency_summary():
    values = sorted(state.latencies)
    if not values: return None
    return {'count': len(values), 'p50': round(values[len(values) // 2]), 'p95': round(values[min(len(values) - 1, int(len(values) * .95))]),
            'max': round(values[-1])}

@app.get('/status')
def status():
    job, result, verifier = state.enrolling, state.result, state.verifier
    return {'locked': state.password is None, 'node_id': state.node_id, 'zone': config.ZONE, 'hint': state.hint,
            'central_online': state.central_online, 'sync_error': state.sync_error, 'camera_error': state.camera_error,
            'policy_version': state.policy.get('version'), 'last_sync': state.policy.get('last_sync'),
            'policy_seconds_left': seconds_left(state.policy), 'policy_max_hours': config.POLICY_MAX_AGE_HOURS,
            'jornada': jornada_status(), **state.counts, 'recent': state.recent, 'actuator': state.actuator, 'latency': latency_summary(),
            'verifier': None if not verifier else {'name': verifier.name, 'ready': verifier.ready, 'detail': verifier.detail},
            'enrolling': None if not job else {'student_id': job['student_id'], 'name': job['name'],
                                               'progress': len(job['samples']), 'total': config.ENROLL_SAMPLES,
                                               'seconds_left': max(0, int(job['deadline'] - time.monotonic()))},
            'result': None if not result else {k: v for k, v in result.items() if k != 'until'}}

@app.get('/frame.jpg')
def frame():
    if state.frame is None: return Response(status_code=204)
    return Response(state.frame, media_type='image/jpeg', headers={'Cache-Control': 'no-store'})

@app.post('/enrollment/cancel')
def cancel_enrollment():
    if not state.enrolling: raise HTTPException(409, 'No hay un enrolamiento en curso')
    state.cancel = True
    return {'ok': True}

if __name__ == '__main__':
    uvicorn.run(app, host='127.0.0.1', port=config.SERVICE_PORT, log_level='warning')
