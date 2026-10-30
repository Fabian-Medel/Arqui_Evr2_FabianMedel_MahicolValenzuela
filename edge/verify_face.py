"""Prueba local interactiva. No controla puertas ni incluye prueba de vida."""
from pathlib import Path
from getpass import getpass
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import time
import cv2
import numpy as np
from edge_db import connect, DB_PATH

ROOT = Path(__file__).resolve().parent
ZONE = 'ENTRADA-PRINCIPAL'
# Valores iniciales de demostracion: requieren calibracion con pruebas propias.
THRESHOLD = 0.50
MIN_MARGIN = 0.08
# Politica conservadora del prototipo, no una garantia de autonomia de 72 horas.
POLICY_MAX_AGE = timedelta(minutes=15)

def decide(db, recognizer, image, faces):
    if faces is None or len(faces) == 0:
        return None, False, 'No se detecto un rostro', None
    if len(faces) != 1:
        return None, False, 'Debe haber exactamente un rostro', None
    feature = recognizer.feature(recognizer.alignCrop(image, faces[0])).flatten()
    norm = np.linalg.norm(feature)
    if not np.isfinite(feature).all() or norm < 1e-8:
        return None, False, 'Captura invalida', None
    feature = feature / norm
    matches = []
    for student_id, model, blob in db.execute('SELECT student_id,model,embedding FROM face_templates'):
        if model != 'sface_2021dec':
            continue
        template = np.frombuffer(blob, dtype='<f4')
        if template.shape != feature.shape or not np.isfinite(template).all():
            continue
        length = np.linalg.norm(template)
        if length < 1e-8:
            continue
        matches.append((float(np.dot(feature, template / length)), student_id))
    matches.sort(reverse=True)
    if not matches:
        return None, False, 'No hay plantillas compatibles', None
    score, student_id = matches[0]
    if score < THRESHOLD:
        return None, False, 'Rostro no reconocido', score
    if len(matches) > 1 and score - matches[1][0] < MIN_MARGIN:
        return None, False, 'Coincidencia ambigua', score
    row = db.execute("SELECT value FROM sync_state WHERE name='last_policy_sync'").fetchone()
    try:
        timestamp = datetime.fromisoformat(row[0]) if row else None
        age = datetime.now(timezone.utc) - timestamp if timestamp else None
    except (ValueError, TypeError):
        age = None
    if age is None or age < timedelta(0) or age > POLICY_MAX_AGE:
        return student_id, False, 'Permisos vencidos: sincroniza de nuevo', score
    permission = db.execute('SELECT enabled FROM permissions WHERE student_id=? AND zone=?', (student_id, ZONE)).fetchone()
    allowed = bool(permission and permission[0] == 1)
    return student_id, allowed, 'Permiso local habilitado' if allowed else 'Sin permiso para esta zona', score

def main():
    if not DB_PATH.is_file():
        raise RuntimeError('No existe la base cifrada')
    db = connect(getpass('Clave de la base cifrada: '))
    camera = None
    try:
        db.execute('SELECT 1 FROM face_templates LIMIT 1').fetchone()
        detector = cv2.FaceDetectorYN.create(str(ROOT/'models'/'yunet.onnx'), '', (320,320), .9, .3, 5000)
        recognizer = cv2.FaceRecognizerSF.create(str(ROOT/'models'/'sface.onnx'), '')
        camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not camera.isOpened():
            raise RuntimeError('No se pudo abrir la camara')
        title = 'SAAD Edge - Verificacion local'
        print('V: verificar y registrar un intento. Q: salir.')
        print('Zona:', ZONE)
        print('Prueba de demostracion sin deteccion de suplantacion.')
        result = 'V: verificar | Q: salir'
        color = (255,255,255)
        shown_until = 0
        last_attempt = -10.0
        while True:
            ok, frame = camera.read()
            if not ok:
                raise RuntimeError('La camara no entrega imagen')
            h,w = frame.shape[:2]
            side = min(h,w)
            top,left = (h-side)//2,(w-side)//2
            image = cv2.resize(frame[top:top+side,left:left+side], (320,320))
            _,faces = detector.detect(image)
            preview = image.copy()
            if faces is not None:
                for face in faces:
                    x,y,fw,fh = face[:4].astype(int)
                    cv2.rectangle(preview,(x,y),(x+fw,y+fh),(255,180,0),1)
            if time.monotonic() > shown_until:
                result, color = 'V: verificar | Q: salir', (255,255,255)
            preview = cv2.resize(preview,(640,640))
            cv2.rectangle(preview,(0,580),(640,640),(25,25,25),-1)
            cv2.putText(preview,result,(15,615),cv2.FONT_HERSHEY_SIMPLEX,.65,color,2)
            cv2.imshow(title,preview)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or cv2.getWindowProperty(title,cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == ord('v') and time.monotonic()-last_attempt >= 3:
                last_attempt = time.monotonic()
                student,allowed,reason,score = decide(db,recognizer,image,faces)
                event_id = str(uuid4())
                # Persistir antes de mostrar una autorizacion.
                with db:
                    db.execute('INSERT INTO pending_events(id,student_id,zone,allowed,occurred_at) VALUES (?,?,?,?,?)',
                               (event_id,student,ZONE,int(allowed),datetime.now(timezone.utc).isoformat()))
                result = 'ACCESO AUTORIZADO' if allowed else 'ACCESO DENEGADO'
                color = (70,230,90) if allowed else (70,70,255)
                shown_until = time.monotonic()+5
                print(result, '|', student or 'Desconocido', '|', reason)
                if score is not None:
                    print(f'Similitud: {score:.3f} (no es un porcentaje de certeza)')
                print('Evento guardado:', event_id)
    finally:
        if camera is not None:
            camera.release()
        cv2.destroyAllWindows()
        db.close()

if __name__ == '__main__':
    main()
