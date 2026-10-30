"""API sync (artefacto "API sync · HTTPS/mTLS"): unica puerta de los nodos hacia la central.

No publica puertos: solo la alcanza el proxy nginx del 8443, que exige el certificado de cliente del nodo.
Orden de un ciclo del nodo: politica primero (revocaciones antes que nada), luego lote de eventos con ACK.
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError, field_validator

import repository as repo
import security

MAX_BATCH_BYTES = 512 * 1024

@asynccontextmanager
async def lifespan(app):
    with repo.connect() as c: repo.init_schema(c, security.hash_password(os.environ['ADMIN_PASSWORD']))
    yield

app = FastAPI(title='SAAD-Campus · API sync', lifespan=lifespan)

def node(x_node_id: str = Header(), x_node_key: str = Header(), x_policy_version: int | None = Header(default=None)):
    with repo.connect() as c:
        if not security.same_secret(repo.node_key_hash(c, x_node_id), security.node_key_hash(x_node_key)):
            raise HTTPException(401, 'Nodo inválido')
        repo.touch_node(c, x_node_id, x_policy_version)
    return x_node_id

def conflict(error):
    return HTTPException(409, {'code': error.code, 'message': error.message, 'ids': error.ids})

class Event(BaseModel):
    id: UUID
    student_id: str | None = Field(default=None, max_length=80)
    zone: str = Field(min_length=1, max_length=80)
    allowed: bool
    occurred_at: datetime
    seq: int | None = Field(default=None, ge=1)
    policy_version: int | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, max_length=120)

    @field_validator('occurred_at')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None: raise ValueError('La fecha requiere zona horaria')
        return value

class Actuation(BaseModel):
    event_id: UUID
    status: Literal['ack', 'simulado', 'sin_actuador', 'sin_respuesta']
    detail: str | None = Field(default=None, max_length=200)
    occurred_at: datetime

class Batch(BaseModel):
    events: list[Event] = []
    actuations: list[Actuation] = []

class EnrollmentResult(BaseModel):
    status: Literal['enrolled', 'failed']
    detail: str | None = Field(default=None, max_length=200)

@app.get('/edge/policies')
def policies(known_version: int | None = None, node_id=Depends(node)):
    with repo.connect() as c: return repo.policy_snapshot(c, node_id, known_version)

@app.post('/edge/batch')
async def batch(request: Request, node_id=Depends(node)):
    body = await request.body()
    if len(body) > MAX_BATCH_BYTES: raise HTTPException(413, 'El lote supera 512 KiB')
    try: data = Batch.model_validate_json(body)
    except ValidationError as error: raise HTTPException(422, error.errors(include_url=False, include_context=False))
    if len(data.events) + len(data.actuations) > repo.MAX_BATCH_ITEMS: raise HTTPException(413, 'El lote supera 500 registros')
    try:
        # Todo o nada: el nodo solo marca como confirmados los identificadores devueltos.
        with repo.connect() as c:
            accepted = repo.store_events(c, node_id, [e.model_dump() for e in data.events])
            actuations = repo.store_actuations(c, node_id, [a.model_dump() for a in data.actuations])
    except repo.Conflict as error: raise conflict(error)
    return {'accepted_ids': accepted, 'accepted_actuations': actuations}

@app.post('/edge/events')
def ingest(body: Event, node_id=Depends(node)):
    """Envio individual (compatibilidad con sync_once.py). El nodo usa /edge/batch."""
    try:
        with repo.connect() as c: accepted = repo.store_events(c, node_id, [body.model_dump()])
    except repo.Conflict as error: raise conflict(error)
    return {'ok': True, 'accepted_ids': accepted}

@app.get('/edge/enrollments')
def pending_enrollments(node_id=Depends(node)):
    with repo.connect() as c: return {'enrollments': repo.pending_enrollments(c, node_id)}

@app.post('/edge/enrollments/{student_id}')
def finish_enrollment(student_id: str, body: EnrollmentResult, node_id=Depends(node)):
    try:
        with repo.connect() as c:
            repo.finish_enrollment(c, node_id, student_id, body.status, body.detail)
            repo.audit(c, node_id, 'enrollment_' + body.status, student_id)
    except repo.Conflict as error: raise HTTPException(409, error.message)
    return {'ok': True}
