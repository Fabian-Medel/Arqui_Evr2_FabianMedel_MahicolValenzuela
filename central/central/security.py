"""Credenciales de la central: contrasenas Argon2, tokens JWT de 30 minutos y claves de nodo."""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

ROLES = ('admin', 'auditor', 'estudiante')
_passwords = PasswordHash.recommended()
_DUMMY = _passwords.hash('dummy-password')

def hash_password(password):
    return _passwords.hash(password)

def verify_password(password, stored):
    # Sin usuario se verifica igual contra un hash ficticio: el tiempo no revela si el usuario existe.
    return _passwords.verify(password, stored or _DUMMY) and stored is not None

def issue_token(username):
    return jwt.encode({'sub': username, 'exp': datetime.now(timezone.utc) + timedelta(minutes=30)},
                      os.environ['JWT_SECRET'], algorithm='HS256')

def token_subject(token):
    """Devuelve el usuario del token o None si es invalido o vencio."""
    try:
        return jwt.decode(token, os.environ['JWT_SECRET'], algorithms=['HS256'], options={'require': ['exp', 'sub']})['sub']
    except jwt.PyJWTError:
        return None

def new_node_key():
    key = secrets.token_urlsafe(32)
    return key, node_key_hash(key)

def node_key_hash(key):
    return hashlib.sha256(key.encode()).hexdigest()

def same_secret(a, b):
    return a is not None and b is not None and secrets.compare_digest(a, b)
