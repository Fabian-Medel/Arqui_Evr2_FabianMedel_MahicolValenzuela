"""Strategy de verificacion facial: el flujo de acceso usa FaceVerificationStrategy sin conocer el algoritmo.

SFaceStrategy reconoce rostros reales con los modelos YuNet y SFace de OpenCV. UnavailableStrategy es el fallo
seguro: si el verificador no puede operar, nadie es reconocido y el acceso se deniega. Para sustituir el proveedor
basta otra subclase. SAAD_FACE_STRATEGY=deshabilitado fuerza la estrategia de fallo seguro.
"""
import os
from abc import ABC, abstractmethod
from typing import NamedTuple

import numpy as np

import config

DETECT_SIZE = 320
DETECTION_SCORE = .9
# Valores iniciales de demostracion: requieren calibracion con pruebas propias.
MATCH_THRESHOLD = .50
MIN_MARGIN = .08
DUPLICATE_THRESHOLD = .50
MIN_CONSISTENCY = .60

class Match(NamedTuple):
    student_id: str | None
    score: float | None
    code: str   # match, no_match, ambiguous, no_templates, invalid_capture, unavailable

class FaceVerificationStrategy(ABC):
    name = ''
    ready = False
    detail = ''

    @abstractmethod
    def detect(self, image):
        """Lista de rostros detectados en una imagen cuadrada."""

    @abstractmethod
    def embed(self, image, face):
        """Vector unitario del rostro, o None si la captura no sirve."""

    def identify(self, image, face, templates):
        """Busca al mejor candidato entre las plantillas locales (1:N)."""
        feature = self.embed(image, face)
        if feature is None: return Match(None, None, 'invalid_capture')
        scored = sorted(((float(np.dot(feature, t)), sid) for sid, t in templates if t.shape == feature.shape), reverse=True)
        if not scored: return Match(None, None, 'no_templates')
        score, student_id = scored[0]
        if score < MATCH_THRESHOLD: return Match(None, score, 'no_match')
        if len(scored) > 1 and score - scored[1][0] < MIN_MARGIN: return Match(None, score, 'ambiguous')
        return Match(student_id, score, 'match')

    def build_template(self, samples):
        """Promedia las capturas del enrolamiento; None si no parecen de una misma persona quieta."""
        template = np.mean(samples, axis=0)
        template /= np.linalg.norm(template)
        if min(float(np.dot(s, template)) for s in samples) < MIN_CONSISTENCY: return None
        return template.astype('<f4')

    def duplicate_of(self, student_id, template, templates):
        """Estudiante distinto cuya plantilla coincide con este rostro."""
        for other, existing in templates:
            if other != student_id and existing.shape == template.shape and float(np.dot(existing, template)) >= DUPLICATE_THRESHOLD:
                return other
        return None

class SFaceStrategy(FaceVerificationStrategy):
    name = 'YuNet + SFace'
    ready = True

    def __init__(self, models):
        import cv2
        self._cv2 = cv2
        self._detector = cv2.FaceDetectorYN.create(str(models / 'yunet.onnx'), '', (DETECT_SIZE, DETECT_SIZE), DETECTION_SCORE, .3, 5000)
        self._recognizer = cv2.FaceRecognizerSF.create(str(models / 'sface.onnx'), '')

    def detect(self, image):
        # Se detecta en baja resolucion por velocidad; el rostro se recorta del cuadro original por calidad.
        small = self._cv2.resize(image, (DETECT_SIZE, DETECT_SIZE), interpolation=self._cv2.INTER_AREA)
        _, faces = self._detector.detect(small)
        if faces is None: return []
        scaled = faces.copy()
        scaled[:, :14] *= image.shape[0] / DETECT_SIZE
        return list(scaled)

    def embed(self, image, face):
        feature = self._recognizer.feature(self._recognizer.alignCrop(image, face)).flatten()
        norm = np.linalg.norm(feature)
        return feature / norm if np.isfinite(feature).all() and norm > 1e-8 else None

class UnavailableStrategy(FaceVerificationStrategy):
    name = 'No disponible'

    def __init__(self, detail):
        self.detail = detail

    def detect(self, image):
        return []

    def embed(self, image, face):
        return None

    def identify(self, image, face, templates):
        return Match(None, None, 'unavailable')

def select_strategy():
    if os.environ.get('SAAD_FACE_STRATEGY') == 'deshabilitado':
        return UnavailableStrategy('Deshabilitado por configuración')
    missing = [name for name in ('yunet.onnx', 'sface.onnx') if not (config.MODELS / name).is_file()]
    if missing: return UnavailableStrategy('Faltan modelos: ' + ', '.join(missing))
    try: return SFaceStrategy(config.MODELS)
    except Exception as error: return UnavailableStrategy(f'No se pudo cargar: {error}')
