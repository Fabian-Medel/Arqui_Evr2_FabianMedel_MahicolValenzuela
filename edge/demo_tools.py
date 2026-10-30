"""Herramientas para demostrar el nodo.

  python demo_tools.py estado       muestra version de politica, jornada, rostros y eventos sin confirmar
  python demo_tools.py vencer       caso F: simula 73 h sin sincronizar (usar en Modo Isla: al reconectar se corrige solo)
  python demo_tools.py hora 13:05   simula esa hora para las jornadas; el kiosco lo indica en pantalla
  python demo_tools.py hora real    vuelve a la hora real
"""
import re
import sys
from datetime import datetime, timedelta, timezone
from getpass import getpass

import config
import schedule
import store
from edge_db import connect, DB_PATH

def estado(db):
    info, counts = store.policy_info(db), store.counts(db)
    simulated = store.demo_time(db)
    jornada = schedule.current(simulated)
    print('Version de politica:', info['version'])
    print('Ultima sincronizacion:', info['last_sync'])
    print('Hora simulada:', simulated or 'no, hora real')
    print('Jornada:', f'{jornada.name}, cierra a las {jornada.closes}' if jornada else f'recinto cerrado, abre a las {schedule.next_opening(simulated)}')
    print('Rostros enrolados:', counts['templates'])
    print('Eventos sin confirmar por la central:', counts['pending_events'])

def vencer(db):
    moment = datetime.now(timezone.utc) - timedelta(hours=config.POLICY_MAX_AGE_HOURS + 1)
    with db: db.execute("UPDATE sync_state SET value=? WHERE name='last_policy_sync'", (moment.isoformat(),))
    print(f'Ultima sincronizacion movida a hace {config.POLICY_MAX_AGE_HOURS + 1} horas. El nodo denegara por politica vencida.')

def hora(db, value):
    if value == 'real':
        store.set_demo_time(db, None)
        print('El nodo vuelve a usar la hora real.')
    elif re.fullmatch(r'([01]\d|2[0-3]):[0-5]\d', value):
        store.set_demo_time(db, value)
        jornada = schedule.current(value)
        print(f'Hora simulada: {value}.', f'Jornada {jornada.name}.' if jornada else 'Recinto cerrado.')
    else:
        raise SystemExit('Usa el formato HH:MM, por ejemplo 13:05, o la palabra real.')

if __name__ == '__main__':
    commands = {'estado': (estado, 2), 'vencer': (vencer, 2), 'hora': (hora, 3)}
    if len(sys.argv) < 2 or sys.argv[1] not in commands or len(sys.argv) != commands[sys.argv[1]][1]:
        raise SystemExit(__doc__)
    if not DB_PATH.is_file(): raise SystemExit('No existe la base cifrada.')
    db = connect(getpass('Clave de la base cifrada: '))
    try:
        store.migrate(db)
        commands[sys.argv[1]][0](db, *sys.argv[2:])
    finally:
        db.close()
