"""Enrolamiento de rostros en el edge. La imagen y la plantilla nunca salen de este equipo.

Consulta a la central las ordenes pendientes (GET /edge/enrollments), captura el rostro con la
camara local, guarda la plantilla SFace en SQLCipher y responde el resultado sin datos biometricos.
Requiere edge-01-connection/ (certificados y connection.json) y models/yunet.onnx + models/sface.onnx.
"""
from pathlib import Path
from getpass import getpass
from datetime import datetime, timezone
import json, ssl, sys, time, urllib.error, urllib.parse, urllib.request
import cv2
import numpy as np
from edge_db import connect, DB_PATH

ROOT = Path(__file__).resolve().parent
BUNDLE = ROOT / 'edge-01-connection'
MODEL = 'sface_2021dec'
POLL_SECONDS = 10
SAMPLES = 5
TIMEOUT_SECONDS = 90
# Mismo umbral que verify_face.py: por encima, el rostro ya pertenece a otro estudiante.
DUPLICATE_THRESHOLD = 0.50
MIN_CONSISTENCY = 0.60
MIN_FACE = 70  # ancho minimo del rostro en pixeles sobre la imagen de 320x320

class EnrollmentFailed(Exception):
    pass

def central():
    config = json.loads((BUNDLE / 'connection.json').read_text())
    ctx = ssl.create_default_context(cafile=str(BUNDLE / 'ca.crt'))
    ctx.load_cert_chain(str(BUNDLE / 'client.crt'), str(BUNDLE / 'client.key'))
    # Ignore ambient HTTP proxy settings for the private LAN connection.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx))
    def request(path, body=None):
        headers = {'X-Node-Id': config['node_id'], 'X-Node-Key': config['api_key'], 'Content-Type': 'application/json'}
        req = urllib.request.Request(config['url'] + path, headers=headers, data=None if body is None else json.dumps(body).encode())
        with opener.open(req, timeout=15) as response: return json.load(response)
    return request

def ensure_schema(db):
    # Una version anterior (enroll_face.py) creo face_templates con otras columnas.
    columns = {row[1]: row for row in db.execute('PRAGMA table_info(face_templates)')}
    required = {'student_id', 'model', 'embedding', 'enrolled_at'}
    blocking = [name for name, row in columns.items() if name not in required and row[3] and row[4] is None]
    with db:
        if columns and (not required <= set(columns) or blocking):
            if db.execute('SELECT count(*) FROM face_templates').fetchone()[0] == 0:
                db.execute('DROP TABLE face_templates')
            else:
                old = 'face_templates_old_' + datetime.now().strftime('%Y%m%d%H%M%S')
                db.execute(f'ALTER TABLE face_templates RENAME TO {old}')
                print(f'Tabla de rostros anterior conservada como {old}; hay que volver a enrolar.')
        db.execute('''CREATE TABLE IF NOT EXISTS face_templates (
            student_id TEXT PRIMARY KEY, model TEXT NOT NULL, embedding BLOB NOT NULL, enrolled_at TEXT NOT NULL)''')

def duplicate_of(db, student_id, template):
    for other, model, blob in db.execute('SELECT student_id,model,embedding FROM face_templates WHERE student_id<>?', (student_id,)):
        existing = np.frombuffer(blob, dtype='<f4')
        if model == MODEL and existing.shape == template.shape and float(np.dot(existing, template)) >= DUPLICATE_THRESHOLD:
            return other
    return None

def capture(student, detector, recognizer, camera):
    """Toma SAMPLES capturas de un unico rostro y devuelve la plantilla promedio normalizada."""
    title = 'SAAD Edge - Enrolamiento'
    samples, last_sample, deadline = [], 0.0, time.monotonic() + TIMEOUT_SECONDS
    try:
        while True:
            if time.monotonic() > deadline: raise EnrollmentFailed('No se logro capturar el rostro a tiempo')
            ok, frame = camera.read()
            if not ok: raise EnrollmentFailed('La camara no entrega imagen')
            h, w = frame.shape[:2]
            side = min(h, w)
            top, left = (h - side) // 2, (w - side) // 2
            image = cv2.resize(frame[top:top + side, left:left + side], (320, 320))
            _, faces = detector.detect(image)
            count = 0 if faces is None else len(faces)
            if count == 1 and faces[0][2] >= MIN_FACE and time.monotonic() - last_sample >= .4:
                feature = recognizer.feature(recognizer.alignCrop(image, faces[0])).flatten()
                norm = np.linalg.norm(feature)
                if np.isfinite(feature).all() and norm > 1e-8:
                    samples.append(feature / norm)
                    last_sample = time.monotonic()
            message = ('Acercate un poco a la camara' if count == 1 and faces[0][2] < MIN_FACE else
                       'Mira a la camara' if count == 0 else
                       'Debe haber una sola persona' if count > 1 else
                       f'Capturando {len(samples)}/{SAMPLES}...')
            preview = image.copy()
            for face in faces if faces is not None else []:
                x, y, fw, fh = face[:4].astype(int)
                cv2.rectangle(preview, (x, y), (x + fw, y + fh), (255, 180, 0), 1)
            preview = cv2.resize(preview, (640, 640))
            cv2.rectangle(preview, (0, 0), (640, 50), (25, 25, 25), -1)
            cv2.putText(preview, f'Enrolando: {student["name"]}', (15, 33), cv2.FONT_HERSHEY_SIMPLEX, .75, (255, 255, 255), 2)
            cv2.rectangle(preview, (0, 580), (640, 640), (25, 25, 25), -1)
            cv2.putText(preview, message + '   ESC: cancelar', (15, 615), cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 2)
            cv2.imshow(title, preview)
            if (cv2.waitKey(1) & 0xFF) == 27: raise EnrollmentFailed('Cancelado por el operador')
            if len(samples) >= SAMPLES:
                template = np.mean(samples, axis=0)
                template /= np.linalg.norm(template)
                if min(float(np.dot(s, template)) for s in samples) < MIN_CONSISTENCY:
                    samples = []  # capturas inconsistentes (movimiento, otra persona): repetir
                    continue
                return template.astype('<f4')
    finally:
        cv2.destroyWindow(title)

def enroll(db, request, student, capture_face):
    student_id = student['student_id']
    try:
        template = capture_face(student)
        other = duplicate_of(db, student_id, template)
        if other: raise EnrollmentFailed(f'El rostro ya esta enrolado como {other}')
        with db:
            db.execute('INSERT OR REPLACE INTO face_templates(student_id,model,embedding,enrolled_at) VALUES (?,?,?,?)',
                       (student_id, MODEL, template.tobytes(), datetime.now(timezone.utc).isoformat()))
        result = {'status': 'enrolled'}
    except EnrollmentFailed as error:
        result = {'status': 'failed', 'detail': str(error)[:200]}
    request('/edge/enrollments/' + urllib.parse.quote(student_id, safe=''), result)
    print(student['name'], '->', 'ENROLADO' if result['status'] == 'enrolled' else 'FALLO: ' + result['detail'])

def run(db, request, capture_face, once=False):
    ensure_schema(db)
    waiting = False
    while True:
        try:
            pending = request('/edge/enrollments')['enrollments']
            if pending: waiting = False
            elif not waiting:
                print('Esperando ordenes de enrolamiento desde el panel... (Ctrl+C para salir)')
                waiting = True
            for student in pending: enroll(db, request, student, capture_face)
        except (urllib.error.URLError, TimeoutError) as error:
            print('Central no disponible, reintentando:', getattr(error, 'reason', error))
        if once: return
        time.sleep(POLL_SECONDS)

def main():
    if not DB_PATH.is_file(): raise RuntimeError('No existe la base cifrada. Ejecuta edge_db.py primero.')
    request = central()
    request('/edge/enrollments')  # falla aqui si mTLS o la clave del nodo no son validos
    print('Conexion con la central: OK')
    db = connect(getpass('Clave de la base cifrada: '))
    camera = None
    try:
        detector = cv2.FaceDetectorYN.create(str(ROOT / 'models' / 'yunet.onnx'), '', (320, 320), .9, .3, 5000)
        recognizer = cv2.FaceRecognizerSF.create(str(ROOT / 'models' / 'sface.onnx'), '')
        camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not camera.isOpened(): raise RuntimeError('No se pudo abrir la camara')
        run(db, request, lambda student: capture(student, detector, recognizer, camera))
    except KeyboardInterrupt:
        print('Enrolamiento detenido.')
    finally:
        if camera is not None: camera.release()
        cv2.destroyAllWindows()
        db.close()

if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('Enrolamiento no iniciado:', type(error).__name__, str(error))
        sys.exit(1)
