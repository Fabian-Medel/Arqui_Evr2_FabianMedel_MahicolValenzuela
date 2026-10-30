"""Parametros del nodo perimetral. Las decisiones de acceso se toman aqui, sin depender de la WAN."""
from datetime import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUNDLE = ROOT / 'edge-01-connection'    # certificado de cliente, CA y connection.json
MODELS = ROOT / 'models'
ACTUATOR_URL = 'http://127.0.0.1:8002'
SERVICE_PORT = 8001

ZONE = 'ENTRADA-PRINCIPAL'
POLICY_MAX_AGE_HOURS = 72   # RNF-02: autonomia maxima sin sincronizar; despues se deniega
# Nombre, apertura y cierre (hora local). Un estudiante ingresa una vez por jornada; fuera de ellas el recinto esta cerrado.
JORNADAS = (('Mañana', time(8, 0), time(12, 0)), ('Tarde', time(13, 0), time(18, 0)))

SYNC_SECONDS = 5
BATCH_SIZE = 200            # por debajo del limite de la central (500 registros / 512 KiB)
REQUEST_TIMEOUT = 8

CAMERA_INDEX = 0
CAMERA_SIZE = (1280, 720)   # se pide 720p; el servicio se adapta a lo que entregue la camara
PREVIEW_SIZE = 720
RESULT_SECONDS = 5
STABLE_FRAMES = 5           # cuadros seguidos con un rostro cercano antes de decidir
GONE_FRAMES = 20            # cuadros sin rostro para considerar que la persona se fue
FACE_RETRIES = 3            # intentos por acercamiento si no se reconoce el rostro
MIN_FACE_RATIO = .22        # ancho minimo del rostro respecto del cuadro

ENROLL_SAMPLES = 5
ENROLL_TIMEOUT_SECONDS = 90
ENROLL_SAMPLE_GAP = .4
