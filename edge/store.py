"""Repository del nodo: unico modulo con SQL sobre la base cifrada (SQLCipher).

La API de acceso y el worker piden operaciones con nombre, como validate() o pending(), sin construir consultas.
Tablas: permissions y students (politica vigente), pending_events y actuations (outbox: synced_at nulo = sin ACK),
face_templates, enrollment_reports y sync_state (version de politica, ultima sincronizacion y secuencia).
"""
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np

import config
from edge_db import connect, DB_PATH  # noqa: F401 (punto de entrada del resto del nodo)

MODEL = 'sface_2021dec'
REJECTED = 'RECHAZADO'

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def migrate(db):
    """Lleva una base existente al esquema actual sin perder datos."""
    # Una version anterior creo face_templates con otras columnas.
    columns = {row[1]: row for row in db.execute('PRAGMA table_info(face_templates)')}
    required = {'student_id', 'model', 'embedding', 'enrolled_at'}
    blocking = [name for name, row in columns.items() if name not in required and row[3] and row[4] is None]
    with db:
        if columns and (not required <= set(columns) or blocking):
            if db.execute('SELECT count(*) FROM face_templates').fetchone()[0] == 0:
                db.execute('DROP TABLE face_templates')
            else:
                db.execute(f'ALTER TABLE face_templates RENAME TO face_templates_old_{datetime.now():%Y%m%d%H%M%S}')
        db.execute('''CREATE TABLE IF NOT EXISTS face_templates (
            student_id TEXT PRIMARY KEY, model TEXT NOT NULL, embedding BLOB NOT NULL, enrolled_at TEXT NOT NULL)''')
        db.execute('CREATE TABLE IF NOT EXISTS students (id TEXT PRIMARY KEY, name TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS enrollment_reports (student_id TEXT PRIMARY KEY, status TEXT NOT NULL, detail TEXT)')
        db.execute('''CREATE TABLE IF NOT EXISTS actuations (
            event_id TEXT PRIMARY KEY, status TEXT NOT NULL, detail TEXT, occurred_at TEXT NOT NULL, synced_at TEXT)''')
        existing = {row[1] for row in db.execute('PRAGMA table_info(pending_events)')}
        for name, kind in (('seq', 'INTEGER'), ('policy_version', 'INTEGER'), ('reason', 'TEXT'),
                           ('jornada', 'TEXT'), ('permission_version', 'INTEGER')):
            if name not in existing: db.execute(f'ALTER TABLE pending_events ADD COLUMN {name} {kind}')
        if 'version' not in {row[1] for row in db.execute('PRAGMA table_info(permissions)')}:
            db.execute('ALTER TABLE permissions ADD COLUMN version INTEGER')

# --- Estado de sincronizacion -------------------------------------------------------------------

def _get(db, name):
    row = db.execute('SELECT value FROM sync_state WHERE name=?', (name,)).fetchone()
    return row[0] if row else None

def _put(db, name, value):
    db.execute('INSERT OR REPLACE INTO sync_state(name,value) VALUES (?,?)', (name, str(value)))

def policy_info(db):
    version, last_sync = _get(db, 'policy_version'), _get(db, 'last_policy_sync')
    age = None
    if last_sync:
        try: age = (datetime.now(timezone.utc) - datetime.fromisoformat(last_sync)).total_seconds()
        except ValueError: pass
    return {'version': int(version) if version is not None else None, 'last_sync': last_sync, 'age_seconds': age}

def apply_snapshot(db, snapshot):
    """Reemplaza la politica de forma atomica. Un estudiante eliminado pierde tambien su plantilla facial."""
    if snapshot.get('replace_snapshot') is not True: raise ValueError('Instantánea de política inválida')
    permissions, students, version = snapshot['permissions'], snapshot['students'], snapshot['policy_version']
    for p in permissions:
        if not isinstance(p.get('student_id'), str) or not isinstance(p.get('zone'), str) or type(p.get('enabled')) is not bool:
            raise ValueError('Permiso inválido en la instantánea')
    if not all(isinstance(s.get('id'), str) and isinstance(s.get('name'), str) for s in students):
        raise ValueError('Estudiante inválido en la instantánea')
    with db:
        db.execute('DELETE FROM permissions')
        db.executemany('INSERT INTO permissions(student_id,zone,enabled,version) VALUES (?,?,?,?)',
                       [(p['student_id'], p['zone'], int(p['enabled']), p.get('version')) for p in permissions])
        db.execute('DELETE FROM students')
        db.executemany('INSERT INTO students(id,name) VALUES (?,?)', [(s['id'], s['name']) for s in students])
        db.execute('DELETE FROM face_templates WHERE student_id NOT IN (SELECT id FROM students)')
        _put(db, 'policy_version', version)
        _put(db, 'last_policy_sync', now_iso())

def confirm_policy(db, version):
    """La central confirmo que la version local sigue vigente."""
    with db:
        _put(db, 'policy_version', version)
        _put(db, 'last_policy_sync', now_iso())

def note_last_seq(db, last_seq):
    """Tras reiniciar la base del nodo, la secuencia continua desde la ultima que conoce la central."""
    with db:
        if int(_get(db, 'event_seq') or 0) < last_seq: _put(db, 'event_seq', last_seq)

def demo_time(db):
    """Hora simulada 'HH:MM', o None si el nodo usa la hora real."""
    return _get(db, 'demo_time')

def set_demo_time(db, value):
    with db:
        if value is None: db.execute("DELETE FROM sync_state WHERE name='demo_time'")
        else: _put(db, 'demo_time', value)

# --- Decision de acceso -------------------------------------------------------------------------

def validate(db, student_id, zone, jornada):
    """Devuelve (permitido, codigo, motivo) solo con datos locales (caso F: denegacion conservadora)."""
    age = policy_info(db)['age_seconds']
    if age is None: return False, 'no_policy', 'Sin política descargada'
    if age < 0 or age > config.POLICY_MAX_AGE_HOURS * 3600:
        return False, 'policy_expired', f'Política vencida: más de {config.POLICY_MAX_AGE_HOURS} h sin sincronizar'
    if jornada is None: return False, 'closed', 'Recinto cerrado'
    row = db.execute('SELECT enabled FROM permissions WHERE student_id=? AND zone=?', (student_id, zone)).fetchone()
    if row and row[0] == 1: return True, 'granted', 'Permiso vigente'
    return False, 'no_permission', 'Sin permiso para esta zona'

def _permission_version(db, student_id, zone):
    row = db.execute('SELECT version FROM permissions WHERE student_id=? AND zone=?', (student_id, zone)).fetchone()
    return row[0] if row else None

def last_grant(db, student_id, zone, jornada):
    """Fecha del ingreso del estudiante en esta jornada. Si le revocaron y devolvieron el permiso, ese ingreso ya no cuenta."""
    row = db.execute('''SELECT occurred_at,permission_version FROM pending_events
                        WHERE student_id=? AND zone=? AND allowed=1 AND jornada=? ORDER BY occurred_at DESC LIMIT 1''',
                     (student_id, zone, jornada.id)).fetchone()
    return row[0] if row and row[1] == _permission_version(db, student_id, zone) else None

def student_name(db, student_id):
    row = db.execute('SELECT name FROM students WHERE id=?', (student_id,)).fetchone()
    return row[0] if row else student_id

# --- Outbox -------------------------------------------------------------------------------------

def record_event(db, student_id, zone, allowed, reason, jornada=None):
    """Persiste la decision antes de mostrarla o actuar (ADR-05), con secuencia, version de politica y jornada."""
    event = {'id': str(uuid4()), 'student_id': student_id, 'zone': zone, 'allowed': allowed,
             'occurred_at': now_iso(), 'reason': reason}
    with db:
        db.execute('''INSERT INTO sync_state(name,value) VALUES ('event_seq','1')
                      ON CONFLICT(name) DO UPDATE SET value=CAST(value AS INTEGER)+1''')
        event['seq'] = int(_get(db, 'event_seq'))
        event['policy_version'] = policy_info(db)['version']
        db.execute('''INSERT INTO pending_events(id,student_id,zone,allowed,occurred_at,seq,policy_version,reason,jornada,permission_version)
                      VALUES (?,?,?,?,?,?,?,?,?,?)''', (event['id'], student_id, zone, int(allowed), event['occurred_at'], event['seq'],
                                                        event['policy_version'], reason, jornada.id if jornada else None,
                                                        _permission_version(db, student_id, zone)))
    return event

def record_actuation(db, event_id, status, detail):
    """El estado fisico se registra aparte de la autorizacion."""
    with db:
        db.execute('INSERT OR REPLACE INTO actuations(event_id,status,detail,occurred_at) VALUES (?,?,?,?)',
                   (event_id, status, detail, now_iso()))

def pending(db, limit=config.BATCH_SIZE):
    """Siguiente lote para la central: eventos sin ACK y estados fisicos cuyo evento ya llego o va en el lote."""
    events = [{'id': r[0], 'student_id': r[1], 'zone': r[2], 'allowed': bool(r[3]), 'occurred_at': r[4],
               'seq': r[5], 'policy_version': r[6], 'reason': r[7]}
              for r in db.execute('''SELECT id,student_id,zone,allowed,occurred_at,seq,policy_version,reason
                                     FROM pending_events WHERE synced_at IS NULL ORDER BY occurred_at LIMIT ?''', (limit,))]
    in_batch = {e['id'] for e in events}
    actuations = [{'event_id': r[0], 'status': r[1], 'detail': r[2], 'occurred_at': r[3]}
                  for r in db.execute('''SELECT a.event_id,a.status,a.detail,a.occurred_at,e.synced_at FROM actuations a
                                         LEFT JOIN pending_events e ON e.id=a.event_id WHERE a.synced_at IS NULL ORDER BY a.occurred_at''')
                  if r[4] is not None or r[0] in in_batch][:limit - len(events)]
    return events, actuations

def acknowledge(db, event_ids, actuation_ids):
    stamp = now_iso()
    with db:
        db.executemany('UPDATE pending_events SET synced_at=? WHERE id=?', [(stamp, i) for i in event_ids])
        db.executemany('UPDATE actuations SET synced_at=? WHERE event_id=?', [(stamp, i) for i in actuation_ids])

def resequence(db, after):
    """Renumera eventos sin ACK tras una colision de secuencia; la central aun no los tiene."""
    with db:
        ids = [r[0] for r in db.execute('SELECT id FROM pending_events WHERE synced_at IS NULL ORDER BY occurred_at')]
        db.executemany('UPDATE pending_events SET seq=? WHERE id=?', [(after + i, event_id) for i, event_id in enumerate(ids, 1)])
        _put(db, 'event_seq', after + len(ids))

def reject(db, ids):
    """Registros que la central rechazo de forma definitiva: se apartan para no bloquear la cola."""
    with db:
        db.executemany('UPDATE pending_events SET synced_at=? WHERE id=?', [(REJECTED, i) for i in ids])
        db.executemany('UPDATE actuations SET synced_at=? WHERE event_id=?', [(REJECTED, i) for i in ids])

def counts(db):
    return {'templates': db.execute('SELECT count(*) FROM face_templates').fetchone()[0],
            'pending_events': db.execute('SELECT count(*) FROM pending_events WHERE synced_at IS NULL').fetchone()[0]}

def recent(db, limit=6):
    rows = db.execute('''SELECT e.id,e.student_id,s.name,e.allowed,e.reason,e.occurred_at,a.status FROM pending_events e
                         LEFT JOIN students s ON s.id=e.student_id LEFT JOIN actuations a ON a.event_id=e.id
                         ORDER BY e.occurred_at DESC LIMIT ?''', (limit,)).fetchall()
    return [{'id': r[0], 'student_id': r[1], 'name': r[2] or r[1] or 'Desconocido', 'allowed': bool(r[3]),
             'reason': r[4], 'occurred_at': r[5], 'physical_status': r[6]} for r in rows]

# --- Plantillas faciales y enrolamiento ---------------------------------------------------------

def templates(db):
    return [(student_id, np.frombuffer(blob, dtype='<f4'))
            for student_id, blob in db.execute('SELECT student_id,embedding FROM face_templates WHERE model=?', (MODEL,))]

def save_template(db, student_id, template):
    with db:
        db.execute('INSERT OR REPLACE INTO face_templates(student_id,model,embedding,enrolled_at) VALUES (?,?,?,?)',
                   (student_id, MODEL, template.astype('<f4').tobytes(), now_iso()))

def report_enrollment(db, student_id, status, detail=None):
    """El resultado se guarda primero; el worker lo envia aunque la central este caida ahora."""
    with db:
        db.execute('INSERT OR REPLACE INTO enrollment_reports(student_id,status,detail) VALUES (?,?,?)',
                   (student_id, status, None if detail is None else detail[:200]))

def enrollment_reports(db):
    return db.execute('SELECT student_id,status,detail FROM enrollment_reports').fetchall()

def clear_enrollment_report(db, student_id):
    with db: db.execute('DELETE FROM enrollment_reports WHERE student_id=?', (student_id,))
