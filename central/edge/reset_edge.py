"""Vacia los datos del nodo (rostros, permisos, eventos sin enviar) conservando la base cifrada y su clave.

Detener edge_service.py antes de ejecutarlo.
"""
from getpass import getpass
from edge_db import connect, DB_PATH

TABLES = ['face_templates', 'permissions', 'pending_events', 'actuations', 'students', 'enrollment_reports', 'sync_state']

if __name__ == '__main__':
    if not DB_PATH.is_file(): raise SystemExit('No existe la base cifrada.')
    db = connect(getpass('Clave de la base cifrada: '))
    try:
        existing = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in TABLES:
            if table in existing: print(f'{table}: {db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]} registros')
        if input('Escribe BORRAR para vaciar estos datos: ').strip() != 'BORRAR': raise SystemExit('Cancelado. No se borro nada.')
        with db:
            for table in TABLES:
                if table in existing: db.execute(f'DELETE FROM {table}')
        print('Nodo vaciado. La base cifrada y su clave se conservan.')
    finally:
        db.close()
