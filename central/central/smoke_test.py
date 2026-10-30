"""Prueba de integracion contra la API central y la API sync en ejecucion.

Ejecutar dentro del contenedor api:  docker compose exec -T api python smoke_test.py
Crea registros con prefijo TEST- y los elimina al terminar.
"""
import asyncio
import json
import os
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

import repository as repo

CENTRAL, SYNC = 'http://127.0.0.1:8000', 'http://sync:8000'

def call(path, body=None, token=None, method=None, headers=None, base=CENTRAL, raw=None):
    h = {'Content-Type': 'application/json', **(headers or {})}
    if token: h['Authorization'] = 'Bearer ' + token
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    request = urllib.request.Request(base + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response: return response.status, json.load(response)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)

def edge(path, body=None, method=None, version=None, raw=None):
    extra = {'X-Policy-Version': str(version)} if version is not None else {}
    return call(path, body, method=method, headers={**node_headers, **extra}, base=SYNC, raw=raw)

suffix = uuid.uuid4().hex[:8]
student, other, gone = f'TEST-{suffix}', f'TEST-otro-{suffix}', f'TEST-del-{suffix}'
now = lambda: datetime.now(timezone.utc).isoformat()
def event(seq, sid=None, allowed=True, **extra):
    return {'id': str(uuid.uuid4()), 'student_id': sid or student, 'zone': 'TEST', 'allowed': allowed,
            'occurred_at': now(), 'seq': seq, 'policy_version': 1, 'reason': 'Prueba', **extra}

try:
    # Login y roles
    assert call('/health')[0] == 200
    assert call('/dashboard')[0] in (401, 403)
    assert call('/login', {'username': 'admin', 'password': 'incorrecta'})[0] == 401
    token = call('/login', {'username': 'admin', 'password': os.environ['ADMIN_PASSWORD']})[1]['access_token']

    # Estudiantes y permisos versionados (RF-02)
    start = call('/health')[1]['policy_version']
    assert call('/students', {'id': student, 'name': 'Nombre inicial'}, token, 'PUT')[0] == 200
    assert call('/students', {'id': student, 'name': 'Prueba automatizada'}, token, 'PUT')[0] == 200
    assert call('/students', {'id': other, 'name': 'Otro estudiante'}, token, 'PUT')[0] == 200
    grant = {'student_id': student, 'zone': 'TEST', 'enabled': True, 'expected_version': 0}
    status, body = call('/permissions', grant, token, 'PUT')
    assert status == 200 and body['version'] == 1, body
    status, body = call('/permissions', grant, token, 'PUT')
    assert status == 409, 'una version obsoleta debe rechazarse'
    status, body = call('/permissions', {**grant, 'enabled': False, 'expected_version': 1}, token, 'PUT')
    assert status == 200 and body['version'] == 2
    status, body = call('/permissions', {**grant, 'enabled': True, 'expected_version': 2}, token, 'PUT')
    assert status == 200 and body['version'] == 3
    policy = body['policy_version']
    assert policy >= start + 6
    assert call('/permissions', {**grant, 'student_id': 'TEST-no-existe'}, token, 'PUT')[0] == 404

    # Nodo: politica primero, con cursor de version
    _, node = call(f'/nodes/TEST-{suffix}', {}, token)
    node_headers = {'X-Node-Id': node['node_id'], 'X-Node-Key': node['api_key']}
    assert call('/edge/policies', base=SYNC, headers={**node_headers, 'X-Node-Key': 'mala'})[0] == 401
    status, snap = edge('/edge/policies')
    assert status == 200 and snap['replace_snapshot'] and snap['policy_version'] == policy and snap['node_last_seq'] == 0
    assert {'id': student, 'name': 'Prueba automatizada'} in snap['students']
    assert {'student_id': student, 'zone': 'TEST', 'enabled': True, 'version': 3} in snap['permissions']
    status, same = edge(f'/edge/policies?known_version={policy}', version=policy)
    assert status == 200 and same == {'replace_snapshot': False, 'policy_version': policy, 'node_last_seq': 0}

    # Lote con ACK, idempotencia y conflictos (ADR-05)
    e1, e2 = event(1), event(2, other, allowed=False, reason='Sin permiso para esta zona')
    actuation = {'event_id': e1['id'], 'status': 'simulado', 'detail': 'Sin hardware', 'occurred_at': now()}
    status, ack = edge('/edge/batch', {'events': [e1, e2], 'actuations': [actuation]}, version=policy)
    assert status == 200 and ack == {'accepted_ids': [e1['id'], e2['id']], 'accepted_actuations': [e1['id']]}, ack
    status, ack = edge('/edge/batch', {'events': [e1, e2], 'actuations': [actuation]}, version=policy)
    assert status == 200 and ack['accepted_ids'] == [e1['id'], e2['id']], 'reenviar el mismo lote debe ser idempotente'
    status, body = edge('/edge/batch', {'events': [event(1)]})
    assert status == 409 and body['detail']['code'] == 'seq_conflict'
    status, body = edge('/edge/batch', {'events': [{**e1, 'allowed': False}]})
    assert status == 409 and body['detail']['code'] == 'id_conflict'
    status, body = edge('/edge/batch', {'events': [event(10 + i) for i in range(501)]})
    assert status == 413
    assert edge('/edge/batch', {'events': [{**event(3), 'occurred_at': '2026-01-01T10:00:00'}]})[0] == 422
    assert edge('/edge/batch', raw=b'{"events": [' + b'0' * (513 * 1024) + b']}')[0] == 413
    assert edge('/edge/policies')[1]['node_last_seq'] == 2
    assert edge('/edge/events', event(3))[1]['ok'] is True

    # Enrolamiento facial
    enroll = f'/students/{student}/enrollment'
    assert call(enroll, {'node_id': 'TEST-falta'}, token)[0] == 404
    assert call(enroll, {'node_id': node['node_id']}, token)[0] == 200
    assert [p['student_id'] for p in edge('/edge/enrollments')[1]['enrollments']] == [student]
    assert edge(f'/edge/enrollments/{student}', {'status': 'enrolled'})[0] == 200
    assert edge(f'/edge/enrollments/{student}', {'status': 'enrolled'})[0] == 409

    # Vista del panel: version de politica, nodo al dia y estado fisico del evento
    view = call('/dashboard', token=token)[1]
    assert view['policy_version'] == policy and view['role'] == 'admin'
    assert next(n for n in view['nodes'] if n['id'] == node['node_id'])['applied_policy_version'] == policy
    row = next(e for e in view['events'] if e['id'] == e1['id'])
    assert row['physical_status'] == 'simulado' and row['seq'] == 1 and row['reason'] == 'Prueba'
    assert next(s for s in view['students'] if s['id'] == student)['enrollments'][0]['status'] == 'enrolled'

    # Roles auditor y estudiante (RF-01, RF-06, caso E)
    auditor = {'username': f'TEST-aud-{suffix}', 'password': uuid.uuid4().hex, 'role': 'auditor'}
    assert call('/users', auditor, token)[0] == 201
    assert call('/users', auditor, token)[0] == 409
    assert call('/users', {'username': 'TEST-sin-estudiante', 'password': uuid.uuid4().hex, 'role': 'estudiante'}, token)[0] == 404
    pupil = {'username': student, 'password': uuid.uuid4().hex, 'role': 'estudiante'}
    assert call('/users', pupil, token)[0] == 201
    aud = call('/login', {k: auditor[k] for k in ('username', 'password')})[1]['access_token']
    stu_login = call('/login', {k: pupil[k] for k in ('username', 'password')})[1]
    assert stu_login['role'] == 'estudiante'
    stu = stu_login['access_token']
    for t in (aud, stu):
        assert call('/permissions', {**grant, 'expected_version': None}, t, 'PUT')[0] == 403
        assert call('/students', {'id': student, 'name': 'x'}, t, 'PUT')[0] == 403
        assert call(f'/students/{student}', token=t, method='DELETE')[0] == 403
        assert call(enroll, {'node_id': node['node_id']}, t)[0] == 403
        assert call('/nodes/forbidden', {}, t)[0] == 403
        assert call('/users', auditor, t)[0] == 403
    assert any(e['id'] == e2['id'] for e in call('/events', token=aud)[1]), 'el auditor lee todos los eventos'
    own = call('/dashboard', token=stu)[1]
    assert [s['id'] for s in own['students']] == [student] and own['nodes'] == [] and own['audit'] == []
    assert {e['student_id'] for e in own['events']} == {student}
    assert all(e['student_id'] == student for e in call('/events', token=stu)[1])

    # Eliminar estudiante: desaparece de la politica que reciben los nodos
    assert call('/students', {'id': gone, 'name': 'Para eliminar'}, token, 'PUT')[0] == 200
    assert call('/permissions', {'student_id': gone, 'zone': 'TEST', 'enabled': True}, token, 'PUT')[0] == 200
    assert call(f'/students/{gone}', token=token, method='DELETE')[0] == 200
    assert call(f'/students/{gone}', token=token, method='DELETE')[0] == 404
    snap = edge('/edge/policies')[1]
    assert all(s['id'] != gone for s in snap['students']) and all(p['student_id'] != gone for p in snap['permissions'])
    assert any(a['action'] == 'grant' and a['target'].startswith(student + ':TEST') for a in view['audit'])
    print('PASS: login, roles admin/auditor/estudiante, permisos versionados (409), version de politica con cursor,')
    print('      lotes con ACK idempotente y conflictos 409/413, actuacion, enrolamiento, eliminacion y auditoria.')

    from websockets.asyncio.client import connect
    latest = call('/health')[1]['policy_version']
    async def check_monitor():
        async with connect('ws://127.0.0.1:8000/ws', origin='http://localhost:3000') as ws:
            await ws.send(token)
            assert json.loads(await asyncio.wait_for(ws.recv(), 5))['policy_version'] == latest
            fresh = event(4)
            assert edge('/edge/batch', {'events': [fresh]})[0] == 200
            for _ in range(5):
                if any(e['id'] == fresh['id'] for e in json.loads(await asyncio.wait_for(ws.recv(), 5))['events']): break
            else: raise AssertionError('El evento no llego al monitor en vivo')
        print('PASS: el monitor en vivo (WebSocket) recibe los eventos nuevos.')
    asyncio.run(check_monitor())
finally:
    with repo.connect() as c:
        for sql in ("DELETE FROM actuations WHERE node_id LIKE 'TEST-%%'",
                    "DELETE FROM events WHERE node_id LIKE 'TEST-%%' OR student_id LIKE 'TEST-%%'",
                    "DELETE FROM enrollments WHERE student_id LIKE 'TEST-%%' OR node_id LIKE 'TEST-%%'",
                    "DELETE FROM permissions WHERE student_id LIKE 'TEST-%%'",
                    "DELETE FROM students WHERE id LIKE 'TEST-%%'",
                    "DELETE FROM users WHERE username LIKE 'TEST-%%'",
                    "DELETE FROM nodes WHERE id LIKE 'TEST-%%'",
                    "DELETE FROM audit WHERE actor LIKE 'TEST-%%' OR target LIKE 'TEST-%%' OR target LIKE '%%(TEST-%%'"):
            c.execute(sql)
    print('Datos de prueba eliminados.')
