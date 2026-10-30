"""Adaptador USB serial (artefacto "Adaptador USB serial · Python"): separa la decision de acceso del controlador fisico.

Tras una autorizacion, el nodo pide POST /open y este adaptador envia OPEN:<event_id> al Arduino por USB (9600 baudios)
y espera ACK:<event_id>. El ACK confirma la respuesta del controlador, no el movimiento mecanico. Sin Arduino se
responde error: nunca se declara una apertura que no ocurrio. Escucha solo en este equipo.

Uso:  python actuator/app.py              detecta el Arduino por USB
      python actuator/app.py --puerto COM3
      python actuator/app.py --simular    maqueta sin hardware; la apertura queda marcada como "simulado"
"""
import argparse
import threading
import time

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

BAUD = 9600
ACK_TIMEOUT = 2.5
ARDUINO_BOOT_SECONDS = 2

class SimulatedGate:
    mode, detail = 'simulado', 'Maqueta sin hardware'

    def open(self, event_id):
        return 'simulado'

    def health(self):
        return {'mode': self.mode, 'detail': self.detail}

class SerialGate:
    """Arduino por USB. Reabre el puerto si se desconecta."""

    def __init__(self, port=None):
        self.port = port
        self._serial = None

    def _find_port(self):
        from serial.tools import list_ports
        for info in list_ports.comports():
            if any(tag in f'{info.description} {info.manufacturer}' for tag in ('Arduino', 'CH340', 'USB-SERIAL', 'USB Serial')):
                return info.device
        return None

    def _connect(self):
        if self._serial and self._serial.is_open: return self._serial
        import serial
        port = self.port or self._find_port()
        if not port: raise ConnectionError('No se encontró un Arduino por USB')
        self._serial = serial.Serial(port, BAUD, timeout=.2, write_timeout=1)
        time.sleep(ARDUINO_BOOT_SECONDS)  # abrir el puerto reinicia el Arduino
        self._serial.reset_input_buffer()
        return self._serial

    def open(self, event_id):
        try:
            link = self._connect()
            link.write(f'OPEN:{event_id}\n'.encode())
            deadline = time.monotonic() + ACK_TIMEOUT
            while time.monotonic() < deadline:
                if link.readline().decode(errors='ignore').strip() == f'ACK:{event_id}': return 'ack'
            return 'sin_respuesta'
        except ImportError:
            return 'sin_actuador'
        except Exception:
            if self._serial: self._serial.close()
            self._serial = None
            return 'sin_actuador'

    def health(self):
        try:
            link = self._connect()
            return {'mode': 'arduino', 'detail': link.port}
        except ImportError:
            return {'mode': 'sin_hardware', 'detail': 'Falta instalar pyserial'}
        except Exception as error:
            if self._serial: self._serial.close()
            self._serial = None
            return {'mode': 'sin_hardware', 'detail': str(error)}

class OpenRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=64)

def build_app(gate):
    app = FastAPI(title='SAAD-Campus · Adaptador USB serial')
    lock = threading.Lock()  # una orden a la vez por el puerto serie

    @app.get('/health')
    def health():
        with lock: return gate.health()

    @app.post('/open')
    def open_gate(body: OpenRequest):
        with lock: status = gate.open(body.event_id)
        if status == 'sin_actuador': raise HTTPException(503, status)
        if status == 'sin_respuesta': raise HTTPException(504, status)
        return {'status': status}

    return app

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Adaptador USB serial del torniquete')
    parser.add_argument('--puerto', help='Puerto serie, por ejemplo COM3. Sin este dato se detecta el Arduino.')
    parser.add_argument('--simular', action='store_true', help='Maqueta sin hardware; la apertura se marca como simulada.')
    options = parser.parse_args()
    uvicorn.run(build_app(SimulatedGate() if options.simular else SerialGate(options.puerto)),
                host='127.0.0.1', port=8002, log_level='warning')
