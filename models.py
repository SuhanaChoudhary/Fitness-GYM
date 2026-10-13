"""SQLite persistence layer for ACEest Fitness & Gym.

All statements are parameterised to protect against SQL injection, and the
connection is bound to the Flask application context so each request gets a
clean handle that is closed automatically.
"""

from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List, Optional

from flask import current_app, g
from werkzeug.security import check_password_hash, generate_password_hash

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'Trainer'
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    age INTEGER,
    height_cm REAL,
    weight_kg REAL,
    program TEXT NOT NULL,
    calories INTEGER,
    target_weight_kg REAL,
    target_adherence INTEGER,
    membership_end TEXT
);

CREATE TABLE IF NOT EXISTS progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL,
    week TEXT NOT NULL,
    adherence INTEGER NOT NULL,
    FOREIGN KEY (client_name) REFERENCES clients (name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    client_name TEXT NOT NULL,
    date TEXT NOT NULL,
    workout_type TEXT NOT NULL,
    duration_min INTEGER NOT NULL,
    notes TEXT,
    FOREIGN KEY (client_name) REFERENCES clients (name) ON DELETE CASCADE
);
"""

WORKOUT_TYPES = ("Strength", "Hypertrophy", "Cardio", "Mobility", "Conditioning")


def get_db() -> sqlite3.Connection:
    """Return the request scoped database connection."""
    if "db" not in g:
        connection = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


def close_db(_exception: Optional[BaseException] = None) -> None:
    """Close the connection stored on the application context."""
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db() -> None:
    """Create the schema and seed the default administrator account."""
    db = get_db()
    db.executescript(SCHEMA)
    seed_admin(db)
    db.commit()


def seed_admin(db: sqlite3.Connection) -> None:
    """Create the bootstrap admin user when the users table is empty."""
    existing = db.execute("SELECT 1 FROM users LIMIT 1").fetchone()
    if existing:
        return
    username = os.environ.get("ACEEST_ADMIN_USER", "admin")
    password = os.environ.get("ACEEST_ADMIN_PASSWORD", "ChangeMe123!")
    db.execute(
        "INSERT OR IGNORE INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        # pbkdf2 keeps the image portable; scrypt needs an OpenSSL build that
        # is not present on every Linux/CI runner used by this pipeline.
        (username, generate_password_hash(password, method="pbkdf2:sha256"), "Admin"),
    )


def verify_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Return the user record when the credentials are valid, else None."""
    row = get_db().execute(
        "SELECT username, password_hash, role FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        return None
    return {"username": row["username"], "role": row["role"]}


def list_clients() -> List[Dict[str, Any]]:
    rows = get_db().execute("SELECT * FROM clients ORDER BY name").fetchall()
    return [dict(row) for row in rows]


def get_client(name: str) -> Optional[Dict[str, Any]]:
    row = get_db().execute("SELECT * FROM clients WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def upsert_client(client: Dict[str, Any]) -> Dict[str, Any]:
    """Insert a client or update the existing record with the same name."""
    db = get_db()
    db.execute(
        """
        INSERT INTO clients (
            name, age, height_cm, weight_kg, program, calories,
            target_weight_kg, target_adherence, membership_end
        )
        VALUES (:name, :age, :height_cm, :weight_kg, :program, :calories,
                :target_weight_kg, :target_adherence, :membership_end)
        ON CONFLICT(name) DO UPDATE SET
            age = excluded.age,
            height_cm = excluded.height_cm,
            weight_kg = excluded.weight_kg,
            program = excluded.program,
            calories = excluded.calories,
            target_weight_kg = excluded.target_weight_kg,
            target_adherence = excluded.target_adherence,
            membership_end = excluded.membership_end
        """,
        client,
    )
    db.commit()
    return get_client(client["name"])  # type: ignore[return-value]


def update_client_program(name: str, program: str, calories: Optional[int]) -> None:
    db = get_db()
    db.execute(
        "UPDATE clients SET program = ?, calories = ? WHERE name = ?",
        (program, calories, name),
    )
    db.commit()


def delete_client(name: str) -> int:
    db = get_db()
    cursor = db.execute("DELETE FROM clients WHERE name = ?", (name,))
    db.execute("DELETE FROM progress WHERE client_name = ?", (name,))
    db.execute("DELETE FROM workouts WHERE client_name = ?", (name,))
    db.commit()
    return cursor.rowcount


def add_progress(client_name: str, week: str, adherence: int) -> Dict[str, Any]:
    db = get_db()
    cursor = db.execute(
        "INSERT INTO progress (client_name, week, adherence) VALUES (?, ?, ?)",
        (client_name, week, adherence),
    )
    db.commit()
    return {
        "id": cursor.lastrowid,
        "client_name": client_name,
        "week": week,
        "adherence": adherence,
    }


def list_progress(client_name: str) -> List[Dict[str, Any]]:
    rows = get_db().execute(
        "SELECT id, client_name, week, adherence FROM progress "
        "WHERE client_name = ? ORDER BY week, id",
        (client_name,),
    ).fetchall()
    return [dict(row) for row in rows]


def add_workout(
    client_name: str,
    workout_date: str,
    workout_type: str,
    duration_min: int,
    notes: str = "",
) -> Dict[str, Any]:
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO workouts (client_name, date, workout_type, duration_min, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (client_name, workout_date, workout_type, duration_min, notes),
    )
    db.commit()
    return {
        "id": cursor.lastrowid,
        "client_name": client_name,
        "date": workout_date,
        "workout_type": workout_type,
        "duration_min": duration_min,
        "notes": notes,
    }


def list_workouts(client_name: str) -> List[Dict[str, Any]]:
    rows = get_db().execute(
        "SELECT id, client_name, date, workout_type, duration_min, notes "
        "FROM workouts WHERE client_name = ? ORDER BY date DESC, id DESC",
        (client_name,),
    ).fetchall()
    return [dict(row) for row in rows]
