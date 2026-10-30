"""Jornadas del recinto, en hora local del nodo. Al cerrar una jornada, quienes ingresaron quedan liberados.

simulated ('HH:MM', ver demo_tools.py) reemplaza la hora del dia para demostrar un cambio de jornada sin esperar.
"""
from datetime import datetime
from typing import NamedTuple

import config

class Jornada(NamedTuple):
    id: str         # fecha y nombre: dos ingresos con el mismo id son de la misma jornada
    name: str
    closes: str

def _moment(simulated):
    now = datetime.now()
    if not simulated: return now
    hour, minute = simulated.split(':')
    return now.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)

def current(simulated=None, moment=None):
    """Jornada abierta en este momento, o None si el recinto esta cerrado."""
    moment = moment or _moment(simulated)
    for name, opens, closes in config.JORNADAS:
        if opens <= moment.time() < closes:
            return Jornada(f'{moment:%Y-%m-%d}/{name}', name, f'{closes:%H:%M}')
    return None

def next_opening(simulated=None, moment=None):
    moment = moment or _moment(simulated)
    for _, opens, _ in config.JORNADAS:
        if moment.time() < opens: return f'{opens:%H:%M}'
    return f'{config.JORNADAS[0][1]:%H:%M}'
