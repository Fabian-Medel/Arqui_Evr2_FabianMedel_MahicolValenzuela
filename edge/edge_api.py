from contextlib import asynccontextmanager
from getpass import getpass

import uvicorn
from fastapi import FastAPI, HTTPException
from edge_db import connect, DB_PATH

@asynccontextmanager
async def lifespan(app):
    if not DB_PATH.is_file():
        raise RuntimeError("No existe la base cifrada. Ejecuta edge_db.py primero.")

    password = getpass("Clave de la base cifrada: ")

    connection = connect(password)
    try:
        for table in ("permissions", "pending_events", "sync_state"):
            connection.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
    finally:
        connection.close()

    app.state.db_password = password
    try:
        yield
    finally:
        app.state.db_password = None

app = FastAPI(title="SAAD-Campus Edge", lifespan=lifespan)

@app.get("/")
def root():
    return {
        "service": "SAAD-Campus Edge",
        "health": "/health",
        "docs": "/docs",
    }

@app.get("/health")
def health():
    try:
        connection = connect(app.state.db_password)
        try:
            connection.execute("SELECT 1 FROM permissions LIMIT 1").fetchone()
        finally:
            connection.close()
    except Exception:
        raise HTTPException(status_code=503, detail="Base cifrada no disponible")

    return {
        "status": "ok",
        "node_id": "edge-01",
        "service": "SAAD-Campus Edge",
        "recognition_ready": False,
        "database_ready": True,
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
