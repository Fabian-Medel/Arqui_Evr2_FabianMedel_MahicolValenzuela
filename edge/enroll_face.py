from pathlib import Path
from getpass import getpass
import cv2
import numpy as np
from edge_db import connect, DB_PATH

ROOT = Path(__file__).resolve().parent

def main():
    if not DB_PATH.is_file():
        raise RuntimeError("No existe la base cifrada.")

    student_id = input("Identificador del estudiante: ").strip()
    if not student_id:
        raise ValueError("El identificador no puede estar vacio.")

    connection = connect(getpass("Clave de la base cifrada: "))
    camera = None

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS face_templates (
                student_id TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                embedding BLOB NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        connection.commit()

        existing = connection.execute(
            "SELECT 1 FROM face_templates WHERE student_id = ?",
            (student_id,),
        ).fetchone()

        if existing:
            raise RuntimeError(
                "Este identificador ya tiene un rostro registrado."
            )

        detector = cv2.FaceDetectorYN.create(
            str(ROOT / "models" / "yunet.onnx"),
            "",
            (320, 320),
            0.9,
            0.3,
            5000,
        )
        recognizer = cv2.FaceRecognizerSF.create(
            str(ROOT / "models" / "sface.onnx"), ""
        )

        camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not camera.isOpened():
            raise RuntimeError("No se pudo abrir la camara.")

        print("Mira a la camara con buena iluminacion.")
        print("C: capturar muestra. Q: cancelar.")
        print("Captura 5 muestras con pequenos cambios de posicion.")

        samples = []

        while len(samples) < 5:
            ok, frame = camera.read()
            if not ok:
                raise RuntimeError("La camara no entrega imagen.")

            # Entrada fija para el modelo YuNet descargado.
            height, width = frame.shape[:2]
            side = min(height, width)
            top = (height - side) // 2
            left = (width - side) // 2
            crop = frame[top:top + side, left:left + side]
            image = cv2.resize(crop, (320, 320))

            _, faces = detector.detect(image)
            count = 0 if faces is None else len(faces)
            preview = image.copy()

            if count == 1:
                x, y, w, h = faces[0][:4].astype(int)
                cv2.rectangle(
                    preview, (x, y), (x + w, y + h), (0, 220, 0), 2
                )

            message = (
                f"Muestras: {len(samples)}/5 - C: capturar"
                if count == 1
                else "Debe verse exactamente un rostro"
            )
            cv2.putText(
                preview, message, (8, 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1
            )
            cv2.imshow("SAAD Edge - Registro", preview)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                print("Registro cancelado. No se guardo ninguna plantilla.")
                return

            if key == ord("c"):
                if count != 1:
                    print("Captura rechazada: debe haber un solo rostro.")
                    continue

                aligned = recognizer.alignCrop(image, faces[0])
                feature = recognizer.feature(aligned).flatten()
                norm = np.linalg.norm(feature)

                if not np.isfinite(feature).all() or norm < 1e-8:
                    print("Muestra invalida. Intenta nuevamente.")
                    continue

                samples.append(feature / norm)
                print(f"Muestra {len(samples)}/5 capturada.")

        embedding = np.mean(samples, axis=0)
        norm = np.linalg.norm(embedding)
        if not np.isfinite(embedding).all() or norm < 1e-8:
            raise RuntimeError("No se pudo construir la plantilla.")

        embedding = (embedding / norm).astype("<f4")

        connection.execute("""
            INSERT INTO face_templates
                (student_id, model, embedding, created_at)
            VALUES (?, ?, ?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        """, (
            student_id,
            "sface_2021dec",
            embedding.tobytes(),
        ))
        connection.commit()

        print("Rostro registrado en SQLCipher:", student_id)
        print("No se han concedido permisos de acceso.")

    finally:
        if camera is not None:
            camera.release()
        cv2.destroyAllWindows()
        connection.close()

if __name__ == "__main__":
    main()
