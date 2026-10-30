from pathlib import Path
from getpass import getpass
from sqlcipher3 import dbapi2 as sqlcipher

DB_PATH = Path(__file__).resolve().parent / "data" / "edge.db"

def connect(password):
    if not password:
        raise ValueError("La clave no puede estar vacia.")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlcipher.connect(str(DB_PATH))

    try:
        escaped = password.replace("'", "''")
        connection.execute(f"PRAGMA key = '{escaped}'")
        connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
    except Exception:
        connection.close()
        raise

def initialize(password):
    connection = connect(password)
    try:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS permissions (
                student_id TEXT NOT NULL,
                zone TEXT NOT NULL,
                enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
                PRIMARY KEY (student_id, zone)
            );

            CREATE TABLE IF NOT EXISTS pending_events (
                id TEXT PRIMARY KEY,
                student_id TEXT,
                zone TEXT NOT NULL,
                allowed INTEGER NOT NULL CHECK(allowed IN (0, 1)),
                occurred_at TEXT NOT NULL,
                synced_at TEXT
            );

            CREATE TABLE IF NOT EXISTS sync_state (
                name TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        connection.commit()
    finally:
        connection.close()

if __name__ == "__main__":
    existing = DB_PATH.exists()
    password = getpass("Clave de la base cifrada: ")

    if not existing:
        if len(password) < 16:
            raise SystemExit("Usa una clave de al menos 16 caracteres.")
        if password != getpass("Repite la clave: "):
            raise SystemExit("Las claves no coinciden.")

    initialize(password)

    connection = connect(password)
    try:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        print("Base cifrada creada y reabierta correctamente.")
        print("Archivo:", DB_PATH)
        print("Tablas:", ", ".join(row[0] for row in tables))
    finally:
        connection.close()
