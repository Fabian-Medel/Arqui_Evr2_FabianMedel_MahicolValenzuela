"""Repository de la central: unico modulo con SQL. Las APIs (app.py, sync_app.py) piden operaciones con nombre.

Cada cambio que afecta lo que deciden los nodos (estudiantes o permisos) incrementa la version de politica,
registrada en policy_changes; los nodos la usan como cursor y la anotan en cada evento.
"""
import os
from datetime import timezone

import psycopg
from psycopg.rows import dict_row

MAX_BATCH_ITEMS = 500

class NotFound(Exception):
    pass

class Conflict(Exception):
    def __init__(self, code, message, ids=()):
        super().__init__(message)
        self.code, self.message, self.ids = code, message, list(ids)

def connect():
    return psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row)

def init_schema(c, admin_hash):
    # Ambos servicios arrancan a la vez; el candado evita crear las mismas tablas en paralelo.
    c.execute('SELECT pg_advisory_xact_lock(4242)')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
      username text PRIMARY KEY, password text NOT NULL, role text NOT NULL);
      CREATE TABLE IF NOT EXISTS students (id text PRIMARY KEY, name text NOT NULL);
      CREATE TABLE IF NOT EXISTS permissions (
      student_id text REFERENCES students(id), zone text, enabled boolean NOT NULL,
      PRIMARY KEY(student_id, zone));
      CREATE TABLE IF NOT EXISTS nodes (id text PRIMARY KEY, key_hash text NOT NULL, last_seen timestamptz);
      CREATE TABLE IF NOT EXISTS events (id uuid PRIMARY KEY, node_id text REFERENCES nodes(id),
      student_id text, zone text NOT NULL, allowed boolean NOT NULL, occurred_at timestamptz NOT NULL,
      received_at timestamptz NOT NULL DEFAULT now());
      CREATE TABLE IF NOT EXISTS audit (id bigserial PRIMARY KEY, actor text NOT NULL,
      action text NOT NULL, target text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
      CREATE TABLE IF NOT EXISTS enrollments (student_id text REFERENCES students(id), node_id text REFERENCES nodes(id),
      status text NOT NULL CHECK (status IN ('pending','enrolled','failed')), detail text,
      requested_by text NOT NULL, requested_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
      PRIMARY KEY(student_id, node_id));
      CREATE TABLE IF NOT EXISTS policy_changes (version bigserial PRIMARY KEY, actor text NOT NULL,
      kind text NOT NULL, target text NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
      CREATE TABLE IF NOT EXISTS actuations (event_id uuid PRIMARY KEY REFERENCES events(id), node_id text REFERENCES nodes(id),
      status text NOT NULL, detail text, occurred_at timestamptz NOT NULL, received_at timestamptz NOT NULL DEFAULT now());
      ALTER TABLE permissions ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1;
      ALTER TABLE permissions ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
      ALTER TABLE events ADD COLUMN IF NOT EXISTS seq bigint;
      ALTER TABLE events ADD COLUMN IF NOT EXISTS policy_version bigint;
      ALTER TABLE events ADD COLUMN IF NOT EXISTS reason text;
      ALTER TABLE nodes ADD COLUMN IF NOT EXISTS applied_policy_version bigint;
      CREATE UNIQUE INDEX IF NOT EXISTS events_node_seq ON events(node_id, seq) WHERE seq IS NOT NULL;''')
    c.execute('INSERT INTO users VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', ('admin', admin_hash, 'admin'))

def audit(c, actor, action, target):
    c.execute('INSERT INTO audit(actor,action,target) VALUES (%s,%s,%s)', (actor, action, target))

def bump_policy(c, actor, kind, target):
    return c.execute('INSERT INTO policy_changes(actor,kind,target) VALUES (%s,%s,%s) RETURNING version',
                     (actor, kind, target)).fetchone()['version']

def policy_version(c):
    return c.execute('SELECT coalesce(max(version),0) AS v FROM policy_changes').fetchone()['v']

# --- Usuarios -------------------------------------------------------------------------------

def find_user(c, username):
    return c.execute('SELECT * FROM users WHERE username=%s', (username,)).fetchone()

def create_user(c, username, password_hash, role):
    if role == 'estudiante' and not student_exists(c, username):
        raise NotFound('Para el rol estudiante, el usuario debe ser el identificador de un estudiante existente')
    try:
        with c.transaction():
            c.execute('INSERT INTO users VALUES (%s,%s,%s)', (username, password_hash, role))
    except psycopg.errors.UniqueViolation:
        raise Conflict('user_exists', 'Usuario existente')

# --- Estudiantes y permisos -----------------------------------------------------------------

def student_exists(c, student_id):
    return c.execute('SELECT 1 FROM students WHERE id=%s', (student_id,)).fetchone() is not None

def save_student(c, actor, student_id, name):
    c.execute('INSERT INTO students VALUES (%s,%s) ON CONFLICT(id) DO UPDATE SET name=excluded.name', (student_id, name))
    return bump_policy(c, actor, 'student', student_id)

def delete_student(c, actor, student_id):
    c.execute('DELETE FROM permissions WHERE student_id=%s', (student_id,))
    c.execute('DELETE FROM enrollments WHERE student_id=%s', (student_id,))
    if not c.execute('DELETE FROM students WHERE id=%s RETURNING id', (student_id,)).fetchone():
        raise NotFound('Estudiante inexistente')
    return bump_policy(c, actor, 'delete_student', student_id)

def save_permission(c, actor, student_id, zone, enabled, expected_version=None):
    """Concede o revoca. Con expected_version (0 = aun no existe) rechaza sobrescribir un cambio ajeno."""
    if not student_exists(c, student_id): raise NotFound('Estudiante inexistente')
    row = c.execute('SELECT version FROM permissions WHERE student_id=%s AND zone=%s FOR UPDATE', (student_id, zone)).fetchone()
    current = row['version'] if row else 0
    if expected_version is not None and expected_version != current:
        raise Conflict('stale_version', 'Otro administrador cambió este permiso. La vista ya se actualizó; revisa y vuelve a intentar.')
    if row:
        version = c.execute('''UPDATE permissions SET enabled=%s, version=version+1, updated_at=now()
                               WHERE student_id=%s AND zone=%s RETURNING version''', (enabled, student_id, zone)).fetchone()['version']
    else:
        version = c.execute('INSERT INTO permissions(student_id,zone,enabled) VALUES (%s,%s,%s) RETURNING version',
                            (student_id, zone, enabled)).fetchone()['version']
    return version, bump_policy(c, actor, 'grant' if enabled else 'revoke', f'{student_id}:{zone}')

# --- Enrolamiento facial (la imagen nunca llega a la central) ---------------------------------

def request_enrollment(c, actor, student_id, node_id):
    if not student_exists(c, student_id): raise NotFound('Estudiante inexistente')
    if not c.execute('SELECT 1 FROM nodes WHERE id=%s', (node_id,)).fetchone(): raise NotFound('Nodo inexistente')
    c.execute('''INSERT INTO enrollments(student_id,node_id,status,requested_by) VALUES (%s,%s,'pending',%s)
                 ON CONFLICT(student_id,node_id) DO UPDATE SET status='pending',detail=NULL,requested_by=excluded.requested_by,
                 requested_at=now(),completed_at=NULL''', (student_id, node_id, actor))

def pending_enrollments(c, node_id):
    return c.execute('''SELECT e.student_id,s.name,e.requested_at FROM enrollments e JOIN students s ON s.id=e.student_id
                        WHERE e.node_id=%s AND e.status='pending' ORDER BY e.requested_at''', (node_id,)).fetchall()

def finish_enrollment(c, node_id, student_id, status, detail):
    done = c.execute('''UPDATE enrollments SET status=%s,detail=%s,completed_at=now()
                        WHERE student_id=%s AND node_id=%s AND status='pending' RETURNING student_id''',
                     (status, detail, student_id, node_id)).fetchone()
    if not done: raise Conflict('no_pending', 'No hay enrolamiento pendiente para este estudiante en este nodo')

# --- Nodos y sincronizacion -------------------------------------------------------------------

def register_node(c, node_id, key_hash):
    c.execute('INSERT INTO nodes(id,key_hash) VALUES (%s,%s) ON CONFLICT(id) DO UPDATE SET key_hash=excluded.key_hash',
              (node_id, key_hash))

def node_key_hash(c, node_id):
    row = c.execute('SELECT key_hash FROM nodes WHERE id=%s', (node_id,)).fetchone()
    return row['key_hash'] if row else None

def touch_node(c, node_id, applied_policy_version):
    c.execute('UPDATE nodes SET last_seen=now(), applied_policy_version=coalesce(%s, applied_policy_version) WHERE id=%s',
              (applied_policy_version, node_id))

def policy_snapshot(c, node_id, known_version=None):
    version = policy_version(c)
    last_seq = c.execute('SELECT coalesce(max(seq),0) AS s FROM events WHERE node_id=%s', (node_id,)).fetchone()['s']
    head = {'policy_version': version, 'node_last_seq': last_seq}
    if known_version == version:
        return {'replace_snapshot': False, **head}
    return {'replace_snapshot': True, **head,
            'permissions': c.execute('SELECT student_id,zone,enabled,version FROM permissions ORDER BY student_id,zone').fetchall(),
            'students': c.execute('SELECT id,name FROM students ORDER BY id').fetchall()}

EVENT_FIELDS = ('student_id', 'zone', 'allowed', 'occurred_at', 'seq', 'policy_version', 'reason')

def store_events(c, node_id, events):
    """Inserta un lote de forma idempotente. Reenviar el mismo evento es aceptado; cambiarlo o repetir su secuencia es 409."""
    accepted = []
    for e in events:
        if e['seq'] is not None:
            clash = c.execute('SELECT id FROM events WHERE node_id=%s AND seq=%s AND id<>%s', (node_id, e['seq'], e['id'])).fetchone()
            if clash: raise Conflict('seq_conflict', f'La secuencia {e["seq"]} ya pertenece a otro evento', [str(e['id'])])
        inserted = c.execute(f'''INSERT INTO events(id,node_id,{','.join(EVENT_FIELDS)}) VALUES (%s,%s,{','.join(['%s'] * len(EVENT_FIELDS))})
                                 ON CONFLICT (id) DO NOTHING RETURNING id''',
                             (e['id'], node_id, *(e[k] for k in EVENT_FIELDS))).fetchone()
        if inserted:
            audit(c, node_id, 'edge_event', str(e['id']))
        else:
            old = c.execute('SELECT * FROM events WHERE id=%s', (e['id'],)).fetchone()
            same = old['node_id'] == node_id and all(old[k] == e[k] for k in ('student_id', 'zone', 'allowed', 'seq')) \
                and old['occurred_at'].astimezone(timezone.utc) == e['occurred_at'].astimezone(timezone.utc)
            if not same: raise Conflict('id_conflict', 'UUID reutilizado con datos diferentes', [str(e['id'])])
        accepted.append(str(e['id']))
    return accepted

def store_actuations(c, node_id, actuations):
    accepted = []
    for a in actuations:
        if not c.execute('SELECT 1 FROM events WHERE id=%s AND node_id=%s', (a['event_id'], node_id)).fetchone():
            raise Conflict('unknown_event', 'Estado de actuación para un evento desconocido', [str(a['event_id'])])
        c.execute('''INSERT INTO actuations(event_id,node_id,status,detail,occurred_at) VALUES (%s,%s,%s,%s,%s)
                     ON CONFLICT (event_id) DO NOTHING''', (a['event_id'], node_id, a['status'], a['detail'], a['occurred_at']))
        accepted.append(str(a['event_id']))
    return accepted

# --- Consultas para el panel (filtradas por rol) ------------------------------------------------

EVENTS_QUERY = '''SELECT e.*, a.status AS physical_status, a.detail AS physical_detail,
    COALESCE(NULLIF(s.name,''), CASE WHEN e.student_id IS NULL THEN 'No identificado' ELSE 'Estudiante eliminado' END) AS student_name
    FROM events e LEFT JOIN students s ON s.id=e.student_id LEFT JOIN actuations a ON a.event_id=e.id
    {where} ORDER BY e.occurred_at DESC LIMIT %s'''

def events(c, student_id=None, limit=100):
    if student_id is None: return c.execute(EVENTS_QUERY.format(where=''), (limit,)).fetchall()
    return c.execute(EVENTS_QUERY.format(where='WHERE e.student_id=%s'), (student_id, limit)).fetchall()

def dashboard(c, user):
    own = user['username'] if user['role'] == 'estudiante' else None
    where, args = ('WHERE s.id=%s', (own,)) if own else ('', ())
    students = c.execute(f'''SELECT s.*, COALESCE(json_agg(json_build_object('node_id',e.node_id,'status',e.status,'detail',e.detail)
        ORDER BY e.node_id) FILTER (WHERE e.node_id IS NOT NULL),'[]') AS enrollments
        FROM students s LEFT JOIN enrollments e ON e.student_id=s.id {where} GROUP BY s.id ORDER BY s.id''', args).fetchall()
    permissions = c.execute(f'''SELECT p.*, s.name AS student_name FROM permissions p JOIN students s ON s.id=p.student_id
        {where} ORDER BY p.student_id,p.zone''', args).fetchall()
    staff = own is None
    return {
        'policy_version': policy_version(c),
        'students': students,
        'permissions': permissions,
        'events': events(c, own),
        'nodes': c.execute('''SELECT id,last_seen,applied_policy_version,
            coalesce(last_seen > now()-interval '30 seconds',false) AS online FROM nodes ORDER BY id''').fetchall() if staff else [],
        'audit': c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100').fetchall() if staff else [],
    }
