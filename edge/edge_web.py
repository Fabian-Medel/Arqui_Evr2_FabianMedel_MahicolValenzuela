"""SAAD edge kiosk. Run locally with one process; never publish on the LAN."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from getpass import getpass
import json
from pathlib import Path
import secrets
import ssl
import threading
import time
import urllib.request
from uuid import uuid4

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
import uvicorn
from edge_db import connect, DB_PATH
from verify_face import decide, ZONE

ROOT = Path(__file__).resolve().parent
SYNC_INTERVAL = 10

def utcnow():
    return datetime.now(timezone.utc).isoformat()

def replace_policies(db, snapshot):
    if snapshot.get('replace_snapshot') is not True or not isinstance(snapshot.get('permissions'), list):
        raise ValueError('Invalid policy snapshot')
    students = snapshot.get('students')
    if students is not None:
        if not isinstance(students, list) or any(not isinstance(s, dict) or not isinstance(s.get('id'), str) or not s['id'] or not isinstance(s.get('name'), str) or not s['name'].strip() for s in students):
            raise ValueError('Invalid student directory')
    values = []
    for p in snapshot['permissions']:
        if not isinstance(p, dict) or not isinstance(p.get('student_id'), str) or not p['student_id'] or not isinstance(p.get('zone'), str) or not p['zone'] or type(p.get('enabled')) is not bool:
            raise ValueError('Invalid policy entry')
        values.append((p['student_id'], p['zone'], int(p['enabled'])))
    with db:
        if students is not None:
            db.execute('DELETE FROM student_directory')
            db.executemany('INSERT INTO student_directory(id,name) VALUES (?,?)', [(s['id'],s['name'].strip()) for s in students])
        db.execute('DELETE FROM permissions')
        db.executemany('INSERT INTO permissions(student_id,zone,enabled) VALUES (?,?,?)', values)
        db.execute('INSERT OR REPLACE INTO sync_state(name,value) VALUES (?,?)', ('last_policy_sync', utcnow()))

def upload_pending(db, request, stop):
    rows = db.execute('SELECT id,student_id,zone,allowed,occurred_at FROM pending_events WHERE synced_at IS NULL ORDER BY occurred_at LIMIT 50').fetchall()
    for row in rows:
        if stop.is_set():
            return
        event = dict(zip(['id', 'student_id', 'zone', 'allowed', 'occurred_at'], row))
        event['allowed'] = bool(event['allowed'])
        receipt = request('/edge/events', event)
        if receipt.get('ok') is not True:
            raise ValueError('Central did not acknowledge event')
        with db:
            db.execute('UPDATE pending_events SET synced_at=? WHERE id=?', (utcnow(), event['id']))

class Runtime:
    def __init__(self, password):
        self.password = password
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.verifying = threading.Lock()
        self.frame = None
        self.jpeg = None
        self.frame_at = 0.0
        self.last_attempt = -10.0
        self.csrf = secrets.token_urlsafe(32)
        self.info = {'node_id': 'edge-01', 'zone': ZONE, 'camera_ready': False,
                     'sync_ok': False, 'sync_message': 'Conectando con la central',
                     'last_sync': None, 'last_policy_sync': None, 'pending': 0,
                     'recognition_ready': False, 'recent': []}

    def database(self):
        db = connect(self.password)
        db.execute('PRAGMA busy_timeout = 5000')
        return db

    def refresh(self, db):
        pending = db.execute('SELECT count(*) FROM pending_events WHERE synced_at IS NULL').fetchone()[0]
        rows = db.execute('SELECT e.student_id,e.allowed,e.occurred_at,s.name FROM pending_events e LEFT JOIN student_directory s ON s.id=e.student_id ORDER BY e.occurred_at DESC LIMIT 5').fetchall()
        policy = db.execute("SELECT value FROM sync_state WHERE name='last_policy_sync'").fetchone()
        with self.lock:
            self.info.update(pending=pending, recent=[dict(zip(['student_id','allowed','occurred_at','student_name'], row)) for row in rows], last_policy_sync=policy[0] if policy else None)

    def start(self):
        if not DB_PATH.is_file():
            raise RuntimeError('No existe la base cifrada')
        db = self.database()
        try:
            db.execute('CREATE TABLE IF NOT EXISTS student_directory (id TEXT PRIMARY KEY, name TEXT NOT NULL)')
            db.commit()
            db.execute('SELECT student_id,model,embedding FROM face_templates LIMIT 1').fetchone()
            self.refresh(db)
        finally:
            db.close()
        self.detector = cv2.FaceDetectorYN.create(str(ROOT/'models'/'yunet.onnx'), '', (320,320), .9, .3, 5000)
        self.recognizer = cv2.FaceRecognizerSF.create(str(ROOT/'models'/'sface.onnx'), '')
        self.detector.detect(np.zeros((320,320,3), dtype=np.uint8))
        self.recognizer.feature(np.zeros((112,112,3), dtype=np.uint8))
        self.info['recognition_ready'] = True
        self.threads = [threading.Thread(target=self.capture, daemon=True), threading.Thread(target=self.sync_loop, daemon=True)]
        for thread in self.threads:
            thread.start()

    def close(self):
        self.stop.set()
        for thread in self.threads:
            thread.join(timeout=12)
        self.password = None

    def capture(self):
        while not self.stop.is_set():
            camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            try:
                if not camera.isOpened():
                    raise RuntimeError('Camara no disponible')
                while not self.stop.is_set():
                    ok, frame = camera.read()
                    if not ok:
                        raise RuntimeError('Camara sin imagen')
                    h, w = frame.shape[:2]
                    side = min(h,w)
                    image = cv2.resize(frame[(h-side)//2:(h+side)//2, (w-side)//2:(w+side)//2], (320,320))
                    ok, jpeg = cv2.imencode('.jpg', image, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if not ok:
                        continue
                    with self.lock:
                        self.frame, self.jpeg, self.frame_at = image, jpeg.tobytes(), time.monotonic()
                        self.info['camera_ready'] = True
                    self.stop.wait(.05)
            except Exception:
                with self.lock:
                    self.frame = self.jpeg = None
                    self.info['camera_ready'] = False
            finally:
                camera.release()
            self.stop.wait(3)

    def sync_loop(self):
        while not self.stop.is_set():
            db = None
            try:
                folder = ROOT/'edge-01-connection'
                config = json.loads((folder/'connection.json').read_text())
                if not config['url'].startswith('https://') or config['node_id'] != 'edge-01':
                    raise ValueError('Invalid central configuration')
                ctx = ssl.create_default_context(cafile=str(folder/'ca.crt'))
                ctx.load_cert_chain(str(folder/'client.crt'), str(folder/'client.key'))
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx))
                def request(path, body=None):
                    headers = {'X-Node-Id': config['node_id'], 'X-Node-Key': config['api_key'], 'Content-Type': 'application/json'}
                    req = urllib.request.Request(config['url']+path, headers=headers, data=None if body is None else json.dumps(body).encode())
                    with opener.open(req, timeout=8) as response:
                        return json.load(response)
                snapshot = request('/edge/policies')
                db = self.database()
                replace_policies(db, snapshot)
                upload_pending(db, request, self.stop)
                with self.lock:
                    self.info.update(sync_ok=True, sync_message='Central conectada', last_sync=utcnow())
            except Exception as error:
                # Do not log credentials or request headers.
                print('Sincronizacion pendiente:', type(error).__name__, flush=True)
                with self.lock:
                    self.info.update(sync_ok=False, sync_message='No se pudo completar la sincronizacion. Reintentando.')
            finally:
                try:
                    if db is None:
                        db = self.database()
                    self.refresh(db)
                except Exception:
                    pass
                finally:
                    if db is not None:
                        db.close()
            self.stop.wait(SYNC_INTERVAL)

    def verify(self):
        if not self.verifying.acquire(blocking=False):
            raise HTTPException(429, 'Ya hay una verificacion en curso')
        db = None
        try:
            if time.monotonic()-self.last_attempt < 3:
                raise HTTPException(429, 'Espera tres segundos entre intentos')
            with self.lock:
                if self.frame is None or time.monotonic()-self.frame_at > 2:
                    raise HTTPException(503, 'Camara no disponible. No se autorizo el acceso.')
                image = self.frame.copy()
            self.last_attempt = time.monotonic()
            _, faces = self.detector.detect(image)
            db = self.database()
            # Keep policy reads consistent with the permission snapshot.
            db.execute('BEGIN IMMEDIATE')
            try:
                student, allowed, reason, _ = decide(db, self.recognizer, image, faces)
                named = db.execute('SELECT name FROM student_directory WHERE id=?',(student,)).fetchone() if student else None
                event_id = str(uuid4())
                db.execute('INSERT INTO pending_events(id,student_id,zone,allowed,occurred_at) VALUES (?,?,?,?,?)',
                           (event_id, student, ZONE, int(allowed), utcnow()))
                db.commit()
            except Exception:
                db.rollback()
                raise
            self.refresh(db)
            return {'allowed': allowed, 'student_id': student, 'student_name': named[0] if named else None, 'reason': reason, 'event_id': event_id}
        except HTTPException:
            raise
        except Exception as error:
            print('Verificacion fallida:', type(error).__name__, flush=True)
            raise HTTPException(503, 'No se pudo completar o guardar la verificacion. No se autorizo el acceso.')
        finally:
            if db is not None:
                db.close()
            self.verifying.release()

def create_app(runtime):
    @asynccontextmanager
    async def lifespan(app):
        await asyncio.to_thread(runtime.start)
        try:
            yield
        finally:
            await asyncio.to_thread(runtime.close)

    app = FastAPI(title='SAAD-Campus Edge', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def local_only(request: Request, call_next):
        host = request.headers.get('host', '')
        if host not in ('127.0.0.1:8001', 'localhost:8001') or request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': 'Solo acceso local'}, status_code=403)
        if request.method == 'POST':
            if request.headers.get('origin') not in ('http://127.0.0.1:8001', 'http://localhost:8001') or not secrets.compare_digest(request.headers.get('x-kiosk-token',''), runtime.csrf):
                return JSONResponse({'detail': 'Solicitud no autorizada'}, status_code=403)
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response

    @app.get('/')
    def home():
        return FileResponse(ROOT/'kiosk'/'index.html')

    @app.get('/kiosk/{filename}')
    def asset(filename: str):
        if filename not in ('style.css', 'app.js'):
            raise HTTPException(404)
        return FileResponse(ROOT/'kiosk'/filename)

    @app.get('/status')
    def status():
        with runtime.lock:
            info = dict(runtime.info)
            info['camera_ready'] = runtime.frame is not None and time.monotonic()-runtime.frame_at <= 2
        return {**info, 'token': runtime.csrf}

    @app.get('/health')
    def health():
        try:
            db = runtime.database()
            try:
                db.execute('SELECT 1 FROM permissions LIMIT 1').fetchone()
            finally:
                db.close()
        except Exception:
            raise HTTPException(503, 'Base cifrada no disponible')
        with runtime.lock:
            return {'status':'ok','node_id':'edge-01','database_ready':True,'recognition_ready':runtime.info['recognition_ready']}

    @app.get('/camera.jpg')
    def camera():
        with runtime.lock:
            if runtime.jpeg is None or time.monotonic()-runtime.frame_at > 2:
                raise HTTPException(503, 'Camara no disponible')
            jpeg = runtime.jpeg
        return Response(jpeg, media_type='image/jpeg')

    @app.post('/verify')
    def verify():
        return runtime.verify()
    return app

if __name__ == '__main__':
    print('SAAD Edge - Kiosco local. Cierra otros programas que usen la camara.')
    runtime = Runtime(getpass('Clave de la base cifrada: '))
    uvicorn.run(create_app(runtime), host='127.0.0.1', port=8001, access_log=False)
