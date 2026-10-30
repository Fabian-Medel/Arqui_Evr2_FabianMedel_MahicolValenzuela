"""API central (artefacto "API central · FastAPI · RBAC"): login, roles, estudiantes, permisos versionados,
enrolamientos, nodos y monitor en vivo para el panel. Escucha solo en 127.0.0.1:8000 del equipo central."""
import asyncio
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

import repository as repo
import security

PANEL_ORIGINS = ['http://localhost:3000', 'http://127.0.0.1:3000']

@asynccontextmanager
async def lifespan(app):
    with repo.connect() as c: repo.init_schema(c, security.hash_password(os.environ['ADMIN_PASSWORD']))
    yield

app = FastAPI(title='SAAD-Campus · API central', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=PANEL_ORIGINS,
                   allow_methods=['GET', 'POST', 'PUT', 'DELETE'], allow_headers=['Authorization', 'Content-Type'])

def http_error(error):
    if isinstance(error, repo.NotFound): return HTTPException(404, str(error))
    return HTTPException(409, error.message)

# --- Roles ------------------------------------------------------------------------------------

def authenticate(token):
    username = security.token_subject(token)
    with repo.connect() as c: user = repo.find_user(c, username) if username else None
    if not user: raise HTTPException(401, 'Sesión inválida o vencida')
    return {'username': user['username'], 'role': user['role']}

def current(auth: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    return authenticate(auth.credentials)

def admin(user=Depends(current)):
    if user['role'] != 'admin': raise HTTPException(403, 'Requiere administrador')
    return user

# --- Modelos ----------------------------------------------------------------------------------

class Login(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)

class UserCreate(Login):
    password: str = Field(min_length=12, max_length=256)
    role: Literal['admin', 'auditor', 'estudiante']

class Student(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)

class Permission(BaseModel):
    student_id: str = Field(min_length=1, max_length=80)
    zone: str = Field(min_length=1, max_length=80)
    enabled: bool
    expected_version: int | None = Field(default=None, ge=0)

class EnrollmentRequest(BaseModel):
    node_id: str = Field(min_length=1, max_length=80)

# --- Rutas ------------------------------------------------------------------------------------

@app.get('/health')
def health():
    with repo.connect() as c: return {'status': 'ok', 'policy_version': repo.policy_version(c)}

@app.post('/login')
def login(body: Login):
    with repo.connect() as c:
        user = repo.find_user(c, body.username)
        valid = security.verify_password(body.password, user['password'] if user else None)
        repo.audit(c, body.username, 'login_ok' if valid else 'login_failed', 'session')
    if not valid: raise HTTPException(401, 'Credenciales incorrectas')
    return {'access_token': security.issue_token(user['username']), 'token_type': 'bearer', 'role': user['role']}

@app.post('/users', status_code=201)
def create_user(body: UserCreate, user=Depends(admin)):
    try:
        with repo.connect() as c:
            repo.create_user(c, body.username, security.hash_password(body.password), body.role)
            repo.audit(c, user['username'], 'create_user', f'{body.username} ({body.role})')
    except (repo.NotFound, repo.Conflict) as error: raise http_error(error)
    return {'ok': True}

@app.put('/students')
def save_student(body: Student, user=Depends(admin)):
    with repo.connect() as c:
        version = repo.save_student(c, user['username'], body.id, body.name)
        repo.audit(c, user['username'], 'save_student', body.id)
    return {'ok': True, 'policy_version': version}

# Los eventos se conservan como historial. Los nodos borran la plantilla facial al sincronizar,
# porque el estudiante deja de aparecer en la politica.
@app.delete('/students/{student_id}')
def delete_student(student_id: str, user=Depends(admin)):
    try:
        with repo.connect() as c:
            version = repo.delete_student(c, user['username'], student_id)
            repo.audit(c, user['username'], 'delete_student', student_id)
    except repo.NotFound as error: raise http_error(error)
    return {'ok': True, 'policy_version': version}

@app.put('/permissions')
def save_permission(body: Permission, user=Depends(admin)):
    try:
        with repo.connect() as c:
            version, policy = repo.save_permission(c, user['username'], body.student_id, body.zone, body.enabled, body.expected_version)
            repo.audit(c, user['username'], 'grant' if body.enabled else 'revoke', f'{body.student_id}:{body.zone} v{version}')
    except (repo.NotFound, repo.Conflict) as error: raise http_error(error)
    return {'ok': True, 'version': version, 'policy_version': policy}

@app.post('/students/{student_id}/enrollment')
def request_enrollment(student_id: str, body: EnrollmentRequest, user=Depends(admin)):
    try:
        with repo.connect() as c:
            repo.request_enrollment(c, user['username'], student_id, body.node_id)
            repo.audit(c, user['username'], 'request_enrollment', f'{student_id}:{body.node_id}')
    except repo.NotFound as error: raise http_error(error)
    return {'ok': True}

@app.post('/nodes/{node_id}')
def register_node(node_id: str, user=Depends(admin)):
    key, key_hash = security.new_node_key()
    with repo.connect() as c:
        repo.register_node(c, node_id, key_hash)
        repo.audit(c, user['username'], 'rotate_node_key', node_id)
    return {'node_id': node_id, 'api_key': key}

@app.get('/events')
def list_events(limit: int = 100, user=Depends(current)):
    with repo.connect() as c:
        return repo.events(c, user['username'] if user['role'] == 'estudiante' else None, max(1, min(limit, 500)))

@app.get('/dashboard')
def dashboard(user=Depends(current)):
    with repo.connect() as c: return {'role': user['role'], 'username': user['username'], **repo.dashboard(c, user)}

def live_view(token):
    user = authenticate(token)
    with repo.connect() as c:
        return jsonable_encoder({'role': user['role'], 'username': user['username'], 'server_time': datetime.now().astimezone(),
                                 **repo.dashboard(c, user)})

@app.websocket('/ws')
async def monitor(ws: WebSocket):
    if ws.headers.get('origin') not in PANEL_ORIGINS:
        await ws.close(code=1008); return
    await ws.accept()
    try:
        token = await asyncio.wait_for(ws.receive_text(), timeout=10)
        while True:
            await ws.send_json(await asyncio.to_thread(live_view, token))
            await asyncio.sleep(1)
    except (WebSocketDisconnect, HTTPException, asyncio.TimeoutError):
        try: await ws.close(code=1008)
        except RuntimeError: pass
