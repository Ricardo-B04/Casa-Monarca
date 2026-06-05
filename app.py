from flask import Flask, render_template, request, redirect, session, flash, send_file, jsonify, has_request_context
import sqlite3
from cryptography import x509
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID
from argon2.low_level import Type, hash_secret
from werkzeug.security import check_password_hash
import hmac
import datetime
import ast
import hashlib
import os
import base64
import secrets
import urllib.request
import urllib.error
import time
import re
import socket
import sys
import json
import traceback
from config import config

try:
    from webauthn import (
        generate_registration_options,
        verify_registration_response,
        generate_authentication_options,
        verify_authentication_response,
        options_to_json,
    )
    from webauthn.helpers.structs import (
        AttestationConveyancePreference,
        AuthenticatorSelectionCriteria,
        PublicKeyCredentialDescriptor,
        UserVerificationRequirement,
        RegistrationCredential,
        AuthenticationCredential,
        AuthenticatorAttestationResponse,
        AuthenticatorAssertionResponse,
    )
    WEBAUTHN_AVAILABLE = True
except Exception:
    WEBAUTHN_AVAILABLE = False

app = Flask(__name__)

# Load configuration from config.py based on environment
env = os.environ.get("FLASK_ENV", "development")
app.config.from_object(config[env])

# Application constants (not affected by environment-specific config)
CERT_PRODUCT_ALGORITHM = "X509/RSA-2048/AES-256-CBC"
CERT_CA_COMMON_NAME = "Casa Monarca Development CA"
CERT_CA_ORG = "Casa Monarca"
CERT_CA_COUNTRY = "MX"
ARGON2_MEMORY_COST = 65536
ARGON2_TIME_COST = 3
ARGON2_PARALLELISM = 2
ARGON2_HASH_LEN = 32
ARGON2_SALT_LEN = 16
HIBP_TIMEOUT_SECONDS = 4

# Get configuration values (now centralized in config.py)
CERT_VALIDITY_HOURS = app.config.get("CERT_VALIDITY_HOURS", 720)
CERT_CA_CERT_PATH = app.config.get("CERT_CA_CERT_PATH", "certs/ca_cert.pem")
CERT_CA_KEY_PATH = app.config.get("CERT_CA_KEY_PATH", "certs/ca_key.pem")
PASSWORD_MIN_LENGTH = app.config.get("PASSWORD_MIN_LENGTH", 12)
LOGIN_MAX_ATTEMPTS = app.config.get("LOGIN_MAX_ATTEMPTS", 5)
LOGIN_WINDOW_SECONDS = app.config.get("LOGIN_WINDOW_SECONDS", 300)
LOGIN_LOCKOUT_SECONDS = app.config.get("LOGIN_LOCKOUT_SECONDS", 900)
SIGNATURE_CHALLENGE_TTL_SECONDS = app.config.get("SIGNATURE_CHALLENGE_TTL_SECONDS", 300)
PASSKEY_ENABLED = app.config.get("PASSKEY_ENABLED", True)
PASSKEY_ENFORCE_CRITICAL = app.config.get("PASSKEY_ENFORCE_CRITICAL", False)
PASSKEY_RP_ID = app.config.get("PASSKEY_RP_ID", "localhost")
PASSKEY_RP_NAME = app.config.get("PASSKEY_RP_NAME", "Casa Monarca")
PASSKEY_ORIGIN = app.config.get("PASSKEY_ORIGIN", "http://localhost:5000")
PASSKEY_TIMEOUT_MS = app.config.get("PASSKEY_TIMEOUT_MS", 60000)
PASSKEY_MAX_CREDENTIALS_PER_USER = app.config.get("PASSKEY_MAX_CREDENTIALS_PER_USER", 5)

# Backward-compatible in-memory cache for failed login attempts.
failed_login_store = {}

COMMON_WEAK_PASSWORDS = {
    "password",
    "password123",
    "admin123",
    "admin12345",
    "admin12345!",
    "qwerty123",
    "12345678",
    "123456789",
    "welcome123",
}

COORDINATOR_AREAS = [
    "Administracion",
    "Legal",
    "Psicosocial",
    "Humanitario",
    "Comunicacion",
]

ROLE_LABELS = {
    "admin": "Administrador",
    "coordinador": "Coordinador",
    "operativo": "Operativo",
    "usuario": "Usuario",
}

# Cargar llave de cifrado para datos sensibles
ENCRYPTION_KEY_PATH = app.config.get("ENCRYPTION_KEY_PATH", "key.key")
ENCRYPTION_LEGACY_KEY_PATHS = app.config.get("ENCRYPTION_LEGACY_KEY_PATHS", [])
DATA_ENCRYPTION_LATENCY_WARNING_SECONDS = app.config.get(
    "ENCRYPTION_LATENCY_WARNING_SECONDS", 0.25
)

def _load_key_bytes(key_path):
    with open(key_path, "rb") as f:
        return f.read()


def _build_keyring(primary_path, legacy_paths):
    keyring = []
    seen_fingerprints = set()

    ordered_paths = [primary_path] + list(legacy_paths or [])
    for index, key_path in enumerate(ordered_paths):
        try:
            key_bytes = _load_key_bytes(key_path)
        except FileNotFoundError:
            continue

        fingerprint = hashlib.sha256(key_bytes).hexdigest()
        if fingerprint in seen_fingerprints:
            continue

        seen_fingerprints.add(fingerprint)
        keyring.append(
            {
                "path": key_path,
                "fingerprint": fingerprint,
                "key_bytes": key_bytes,
                "cipher": Fernet(key_bytes),
                "is_primary": index == 0,
            }
        )

    return keyring


ENCRYPTION_KEYRING = _build_keyring(ENCRYPTION_KEY_PATH, ENCRYPTION_LEGACY_KEY_PATHS)
if not ENCRYPTION_KEYRING:
    raise FileNotFoundError(f"No se pudo cargar ninguna llave de cifrado desde {ENCRYPTION_KEY_PATH}")

DATA_ENCRYPTION_KEY_FINGERPRINT = ENCRYPTION_KEYRING[0]["fingerprint"]
cipher = ENCRYPTION_KEYRING[0]["cipher"]


def get_cipher_for_fingerprint(fingerprint=None):
    if fingerprint:
        for entry in ENCRYPTION_KEYRING:
            if entry["fingerprint"] == fingerprint:
                return entry["cipher"]

    return cipher


def load_keyring():
    """Loads all encryption keys dynamically from config and the database, rebuilding the keyring."""
    global ENCRYPTION_KEYRING, DATA_ENCRYPTION_KEY_FINGERPRINT, cipher

    # 1. Start with the keys defined in the configuration files
    keyring_paths = [ENCRYPTION_KEY_PATH] + list(ENCRYPTION_LEGACY_KEY_PATHS or [])

    # 2. Query the database table encryption_keys to retrieve other registered keys
    try:
        conn = sqlite3.connect("database.db")
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='encryption_keys'")
        if c.fetchone():
            c.execute("SELECT source_path, state FROM encryption_keys")
            db_keys = c.fetchall()
            # Order such that 'activo' keys are first, so they take precedence for active encryption
            db_keys = sorted(db_keys, key=lambda k: 0 if k["state"] == "activo" else 1)
            for r in db_keys:
                path = r["source_path"]
                if path and os.path.exists(path):
                    if r["state"] == "activo":
                        if path in keyring_paths:
                            # Move to front
                            keyring_paths.remove(path)
                        keyring_paths.insert(0, path)
                    else:
                        if path not in keyring_paths:
                            keyring_paths.append(path)
        conn.close()
    except Exception as e:
        print(f"Error loading keys from database: {e}")

    # Remove duplicate paths while preserving ordering (active first)
    seen = set()
    unique_paths = []
    for p in keyring_paths:
        if p not in seen:
            seen.add(p)
            unique_paths.append(p)

    # Rebuild the keyring list
    new_keyring = []
    seen_fingerprints = set()
    for index, key_path in enumerate(unique_paths):
        try:
            with open(key_path, "rb") as f:
                key_bytes = f.read()
        except FileNotFoundError:
            continue

        fingerprint = hashlib.sha256(key_bytes).hexdigest()
        if fingerprint in seen_fingerprints:
            continue

        seen_fingerprints.add(fingerprint)
        new_keyring.append(
            {
                "path": key_path,
                "fingerprint": fingerprint,
                "key_bytes": key_bytes,
                "cipher": Fernet(key_bytes),
                "is_primary": len(new_keyring) == 0,  # First successful key in list is primary
            }
        )

    if new_keyring:
        ENCRYPTION_KEYRING = new_keyring
        DATA_ENCRYPTION_KEY_FINGERPRINT = new_keyring[0]["fingerprint"]
        cipher = new_keyring[0]["cipher"]
        for idx, entry in enumerate(ENCRYPTION_KEYRING):
            entry["is_primary"] = (idx == 0)


def get_active_key_details():
    """Returns a JSON string describing the currently active encryption key."""
    try:
        db_path = app.config.get("DATABASE", "database.db")
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT key_fingerprint, source_path, state, notes FROM encryption_keys WHERE state='activo' LIMIT 1")
        row = c.fetchone()
        conn.close()
        if row:
            return json.dumps({
                "fingerprint": row["key_fingerprint"],
                "fingerprint_short": row["key_fingerprint"][:12],
                "source_path": row["source_path"],
                "state": row["state"],
                "notes": row["notes"],
            })
    except Exception:
        pass

    # Fallback to in-memory keyring
    if ENCRYPTION_KEYRING:
        active = ENCRYPTION_KEYRING[0]
        return json.dumps({
            "fingerprint": active["fingerprint"],
            "fingerprint_short": active["fingerprint"][:12],
            "source_path": active.get("path", ""),
            "state": "activo",
            "notes": "clave en memoria",
        })
    return json.dumps({"status": "sin clave activa"})


# Perform initial dynamic reload of keyring
load_keyring()


def get_conn():
    db_path = app.config.get("DATABASE", "database.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_column(cursor, table_name, column_name, column_definition):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    if column_name not in columns:
        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS encuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datos BLOB,
            encryption_key_fingerprint TEXT,
            encrypted_at TEXT,
            estado TEXT DEFAULT 'borrador',
            creado_por TEXT,
            nivel_actual TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            rol TEXT,
            area TEXT,
            cert_fingerprint TEXT,
            is_contingency INTEGER DEFAULT 0,
            activo INTEGER DEFAULT 1,
            passkey_enrollment_required INTEGER DEFAULT 0
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT,
            accion TEXT,
            fecha TEXT,
            categoria TEXT DEFAULT 'operacion',
            detalle TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS encryption_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_fingerprint TEXT UNIQUE,
            source_path TEXT,
            state TEXT DEFAULT 'activo',
            created_at TEXT,
            activated_at TEXT,
            retired_at TEXT,
            last_seen_at TEXT,
            usage_count INTEGER DEFAULT 0,
            last_operation TEXT,
            notes TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS encryption_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            op_type TEXT,
            duration_ms REAL,
            key_fingerprint TEXT,
            record_id INTEGER,
            status TEXT,
            user TEXT,
            action_detail TEXT,
            active_key_info TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS reencrypt_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            new_key_fingerprint TEXT,
            requested_by TEXT,
            status TEXT DEFAULT 'queued',
            created_at TEXT,
            started_at TEXT,
            finished_at TEXT,
            batch_size INTEGER DEFAULT 500,
            processed_count INTEGER DEFAULT 0,
            total_count INTEGER,
            last_update TEXT,
            notes TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS solicitudes_eliminacion (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            encuesta_id INTEGER,
            solicitante TEXT,
            motivo TEXT,
            estado TEXT DEFAULT 'pendiente',
            atendido_por TEXT,
            fecha_solicitud TEXT,
            fecha_resolucion TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS login_lockouts (
            identifier TEXT PRIMARY KEY,
            attempts INTEGER NOT NULL DEFAULT 0,
            first_ts REAL NOT NULL DEFAULT 0,
            lockout_until REAL
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS certificados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            rol TEXT,
            issued_by TEXT,
            issuer_fingerprint TEXT,
            cert_fingerprint TEXT,
            issued_at TEXT,
            expires_at TEXT,
            status TEXT,
            pem_hash TEXT,
            public_fp TEXT,
            cert_serial TEXT,
            pem_path TEXT,
            algorithm TEXT,
            last_used_at TEXT,
            revoked_at TEXT,
            revoked_by TEXT,
            revocation_reason TEXT,
            created_at TEXT,
            updated_at TEXT,
            custody_mode TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS passkey_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            credential_id TEXT NOT NULL UNIQUE,
            public_key_b64 TEXT NOT NULL,
            sign_count INTEGER NOT NULL DEFAULT 0,
            aaguid TEXT,
            transports TEXT,
            label TEXT,
            status TEXT NOT NULL DEFAULT 'activo',
            created_at TEXT,
            updated_at TEXT,
            last_used_at TEXT,
            revoked_at TEXT,
            revoked_by TEXT,
            revocation_reason TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS solicitudes_arco (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            -- Datos de contacto del solicitante
            nombre_solicitante  TEXT NOT NULL,
            correo              TEXT NOT NULL,
            telefono            TEXT,
            curp_id             TEXT NOT NULL,
            -- Acción solicitada
            accion              TEXT NOT NULL,  -- acceso | rectificacion | cancelacion | oposicion
            -- Datos para localizar expediente
            nombre_pila         TEXT,
            primer_apellido     TEXT,
            segundo_apellido    TEXT,
            fecha_nacimiento    TEXT,
            pais_origen         TEXT,
            departamento_estado TEXT,
            fecha_atencion      TEXT,
            folio_expediente    TEXT,
            -- Fundamentación
            motivo              TEXT NOT NULL,
            datos_correctos     TEXT,
            info_adicional      TEXT,
            -- Control interno
            estado              TEXT DEFAULT 'pendiente',  -- pendiente | en_revision | atendida | rechazada
            created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
            atendida_por        TEXT,
            atendida_at         DATETIME,
            notas_admin         TEXT
        )
        """
    )

    # Compatibilidad con bases existentes de la version anterior
    ensure_column(c, "encuestas", "estado", "TEXT DEFAULT 'borrador'")
    ensure_column(c, "encuestas", "creado_por", "TEXT")
    ensure_column(c, "encuestas", "nivel_actual", "TEXT")
    ensure_column(c, "encuestas", "created_at", "TEXT")
    ensure_column(c, "encuestas", "updated_at", "TEXT")
    ensure_column(c, "encuestas", "encryption_key_fingerprint", "TEXT")
    ensure_column(c, "encuestas", "encrypted_at", "TEXT")

    ensure_column(c, "usuarios", "password_hash", "TEXT")
    ensure_column(c, "usuarios", "area", "TEXT")
    ensure_column(c, "usuarios", "cert_fingerprint", "TEXT")
    ensure_column(c, "usuarios", "is_contingency", "INTEGER DEFAULT 0")
    ensure_column(c, "usuarios", "activo", "INTEGER DEFAULT 1")
    ensure_column(c, "usuarios", "must_change_password", "INTEGER DEFAULT 1")
    ensure_column(c, "usuarios", "password_updated_at", "TEXT")
    ensure_column(c, "usuarios", "password_algo", "TEXT")
    ensure_column(c, "usuarios", "password_salt", "TEXT")
    # Campos opcionales para perfil de usuario
    ensure_column(c, "usuarios", "email", "TEXT")
    ensure_column(c, "usuarios", "phone", "TEXT")
    ensure_column(c, "usuarios", "full_name", "TEXT")
    ensure_column(c, "usuarios", "passkey_enrollment_required", "INTEGER DEFAULT 0")

    ensure_column(c, "logs", "categoria", "TEXT DEFAULT 'operacion'")
    ensure_column(c, "logs", "detalle", "TEXT")
    ensure_column(c, "encryption_metrics", "user", "TEXT")
    ensure_column(c, "encryption_metrics", "action_detail", "TEXT")
    ensure_column(c, "encryption_metrics", "active_key_info", "TEXT")

    now = str(datetime.datetime.now())
    for entry in ENCRYPTION_KEYRING:
        is_primary = 1 if entry["fingerprint"] == DATA_ENCRYPTION_KEY_FINGERPRINT else 0
        state = "activo" if is_primary else "legada"
        notes = (
            "Llave activa cargada al iniciar la aplicacion"
            if is_primary
            else "Llave historica disponible para descifrado"
        )
        c.execute(
            """
            INSERT OR IGNORE INTO encryption_keys (
                key_fingerprint, source_path, state, created_at, activated_at, last_seen_at, usage_count, last_operation, notes
            ) VALUES (?, ?, ?, ?, ?, ?, 0, 'bootstrap', ?)
            """,
            (
                entry["fingerprint"],
                entry["path"],
                state,
                now,
                now,
                now,
                notes,
            ),
        )
        c.execute(
            """
            UPDATE encryption_keys
            SET source_path=?, state=?, last_seen_at=?, last_operation=?
            WHERE key_fingerprint=?
            """,
            (
                entry["path"],
                state,
                now,
                "bootstrap",
                entry["fingerprint"],
            ),
        )

    # Nuevas columnas para flujo multinivel de solicitudes ARCO
    ensure_column(c, "solicitudes_arco", "nivel_actual", "TEXT DEFAULT 'usuarios'")
    ensure_column(c, "solicitudes_arco", "aprobado_usuarios", "INTEGER DEFAULT 0")
    ensure_column(c, "solicitudes_arco", "aprobado_usuarios_at", "DATETIME")
    ensure_column(c, "solicitudes_arco", "aprobado_usuarios_por", "TEXT")
    ensure_column(c, "solicitudes_arco", "aprobado_operativos", "INTEGER DEFAULT 0")
    ensure_column(c, "solicitudes_arco", "aprobado_operativos_at", "DATETIME")
    ensure_column(c, "solicitudes_arco", "aprobado_operativos_por", "TEXT")
    ensure_column(c, "solicitudes_arco", "aprobado_coordinadores", "INTEGER DEFAULT 0")
    ensure_column(c, "solicitudes_arco", "aprobado_coordinadores_at", "DATETIME")
    ensure_column(c, "solicitudes_arco", "aprobado_coordinadores_por", "TEXT")
    ensure_column(c, "solicitudes_arco", "reenviado_por_coordinador", "INTEGER DEFAULT 0")
    ensure_column(c, "solicitudes_arco", "reenviado_por_coordinador_at", "DATETIME")
    ensure_column(c, "solicitudes_arco", "resuelto_coordinador", "INTEGER DEFAULT 0")
    ensure_column(c, "solicitudes_arco", "resuelto_coordinador_at", "DATETIME")

    ensure_column(c, "certificados", "rol", "TEXT")
    ensure_column(c, "certificados", "issued_by", "TEXT")
    ensure_column(c, "certificados", "issuer_fingerprint", "TEXT")
    ensure_column(c, "certificados", "cert_fingerprint", "TEXT")
    ensure_column(c, "certificados", "issued_at", "TEXT")
    ensure_column(c, "certificados", "expires_at", "TEXT")
    ensure_column(c, "certificados", "status", "TEXT")
    ensure_column(c, "certificados", "pem_hash", "TEXT")
    ensure_column(c, "certificados", "public_fp", "TEXT")
    ensure_column(c, "certificados", "cert_serial", "TEXT")
    ensure_column(c, "certificados", "pem_path", "TEXT")
    ensure_column(c, "certificados", "algorithm", "TEXT")
    ensure_column(c, "certificados", "last_used_at", "TEXT")
    ensure_column(c, "certificados", "revoked_at", "TEXT")
    ensure_column(c, "certificados", "revoked_by", "TEXT")
    ensure_column(c, "certificados", "revocation_reason", "TEXT")
    ensure_column(c, "certificados", "created_at", "TEXT")
    ensure_column(c, "certificados", "updated_at", "TEXT")
    ensure_column(c, "certificados", "custody_mode", "TEXT")

    ensure_column(c, "login_lockouts", "attempts", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(c, "login_lockouts", "first_ts", "REAL NOT NULL DEFAULT 0")
    ensure_column(c, "login_lockouts", "lockout_until", "REAL")

    ensure_column(c, "passkey_credentials", "username", "TEXT")
    ensure_column(c, "passkey_credentials", "credential_id", "TEXT")
    ensure_column(c, "passkey_credentials", "public_key_b64", "TEXT")
    ensure_column(c, "passkey_credentials", "sign_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(c, "passkey_credentials", "aaguid", "TEXT")
    ensure_column(c, "passkey_credentials", "transports", "TEXT")
    ensure_column(c, "passkey_credentials", "label", "TEXT")
    ensure_column(c, "passkey_credentials", "status", "TEXT NOT NULL DEFAULT 'activo'")
    ensure_column(c, "passkey_credentials", "created_at", "TEXT")
    ensure_column(c, "passkey_credentials", "updated_at", "TEXT")
    ensure_column(c, "passkey_credentials", "last_used_at", "TEXT")
    ensure_column(c, "passkey_credentials", "revoked_at", "TEXT")
    ensure_column(c, "passkey_credentials", "revoked_by", "TEXT")
    ensure_column(c, "passkey_credentials", "revocation_reason", "TEXT")

    c.execute("CREATE INDEX IF NOT EXISTS idx_passkey_username ON passkey_credentials(username)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_passkey_status ON passkey_credentials(status)")

    c.execute(
        """
        UPDATE certificados
        SET status='pendiente'
        WHERE (pem_path IS NULL OR pem_path='')
            AND status IS NOT 'activo'
        """
    )

    c.execute(
        """
        UPDATE usuarios
        SET must_change_password=1
        WHERE must_change_password IS NULL
        """
    )

    c.execute(
        """
        UPDATE usuarios
        SET password_algo='legacy'
        WHERE (password_algo IS NULL OR password_algo='')
          AND password_hash IS NOT NULL
        """
    )

    c.execute(
        """
        UPDATE usuarios
        SET must_change_password=1
        WHERE password_algo!='argon2id'
        """
    )

    # Migrate: Link passkeys with certificates (Fase 1: Infrastructure)
    ensure_column(c, "passkey_credentials", "user_cert_id", "INTEGER")
    ensure_column(c, "passkey_credentials", "generated_cert_at", "TEXT")
    ensure_column(c, "passkey_credentials", "cert_revoked_reason", "TEXT")
    
    ensure_column(c, "certificados", "passkey_source", "INTEGER DEFAULT 0")
    ensure_column(c, "certificados", "num_passkeys_using", "INTEGER DEFAULT 0")
    
    c.execute("CREATE INDEX IF NOT EXISTS idx_passkey_user_cert ON passkey_credentials(user_cert_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_cert_user_passkey_source ON certificados(username, passkey_source)")

    conn.commit()
    conn.close()
    load_keyring()


PERMISSIONS = {
    "admin": {"create", "read", "update", "delete"},
    "coordinador": {"create", "read", "update"},
    "operativo": {"create", "read"},
    "usuario": {"create"},
}


def has_permission(action):
    role = session.get("role")
    if not role:
        return False
    return action in PERMISSIONS.get(role, set())


def log(usuario, accion, categoria="operacion", detalle=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO logs (usuario, accion, fecha, categoria, detalle) VALUES (?, ?, ?, ?, ?)",
        (usuario, accion, str(datetime.datetime.now()), categoria, detalle),
    )
    conn.commit()
    conn.close()


def _touch_encryption_key(operation, fingerprint=None):
    target_fingerprint = fingerprint or DATA_ENCRYPTION_KEY_FINGERPRINT
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(
            """
            UPDATE encryption_keys
            SET usage_count = usage_count + 1,
                last_seen_at = ?,
                last_operation = ?
            WHERE key_fingerprint = ?
            """,
            (str(datetime.datetime.now()), operation, target_fingerprint),
        )
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()


def record_encryption_metric(op_type, duration_ms, key_fingerprint=None, record_id=None, status='ok', user=None, action_detail=None, active_key_info=None):
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO encryption_metrics (
                timestamp, op_type, duration_ms, key_fingerprint, record_id, status, user, action_detail, active_key_info
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(datetime.datetime.now()),
                op_type,
                float(duration_ms) * 1000.0,
                key_fingerprint,
                record_id,
                status,
                user,
                action_detail,
                active_key_info or get_active_key_details()
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        # avoid metric failures affecting main flow
        try:
            conn.close()
        except Exception:
            pass


def get_encryption_metrics(limit=500):
    """Return recent encryption metrics grouped by op_type (chronological)."""
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        "SELECT op_type, duration_ms, timestamp, user, action_detail, active_key_info FROM encryption_metrics ORDER BY id DESC LIMIT ?",
        (limit,),
    )
    rows = c.fetchall()
    conn.close()

    data = {"encrypt": [], "decrypt": []}
    # rows are newest first; reverse to get chronological order
    for r in reversed(rows):
        op = r["op_type"]
        duration = float(r["duration_ms"]) if r["duration_ms"] is not None else 0.0
        ts = r["timestamp"]
        user_val = r["user"]
        action_val = r["action_detail"]
        active_key_val = r["active_key_info"]
        if op not in data:
            data[op] = []
        data[op].append({
            "duration_ms": duration,
            "timestamp": ts,
            "user": user_val,
            "action_detail": action_val,
            "active_key_info": active_key_val
        })

    stats = {}
    for op, items in data.items():
        durations = [it["duration_ms"] for it in items]
        if durations:
            avg = sum(durations) / len(durations)
            mn = min(durations)
            mx = max(durations)
        else:
            avg = mn = mx = 0.0
        stats[op] = {"avg": avg, "min": mn, "max": mx, "count": len(durations)}

    return {"series": data, "stats": stats}


@app.route('/admin/cifrado/metrics')
def admin_cifrado_metrics():
    if not require_role('admin', 'coordinador'):
        return jsonify({"error": "unauthorized"}), 403
    res = get_encryption_metrics(limit=500)
    return jsonify(res)

def enqueue_reencrypt_job(new_key_fingerprint, requested_by, batch_size=500, notes=None):
    conn = get_conn()
    c = conn.cursor()
    now = str(datetime.datetime.now())
    c.execute(
        """
        INSERT INTO reencrypt_jobs (new_key_fingerprint, requested_by, status, created_at, batch_size, processed_count, last_update, notes)
        VALUES (?, ?, 'queued', ?, ?, 0, ?, ?)
        """,
        (new_key_fingerprint, requested_by, now, batch_size, now, notes),
    )
    job_id = c.lastrowid
    conn.commit()
    conn.close()
    return job_id


@app.route("/admin/keys/configure", methods=["POST"])
def admin_configure_key():
    if not require_role("admin", "coordinador"):
        return jsonify({"ok": False, "message": "Unauthorized"}), 403

    # CSRF protection
    if not validate_csrf():
        return jsonify({"ok": False, "message": "CSRF token missing or invalid"}), 400

    # Passkey signature check
    if not check_and_consume_passkey_action("configurar nueva clave de cifrado"):
        return jsonify({"ok": False, "message": "Falta la firma de passkey para esta accion sensible o ya ha expirado"}), 400

    custom_path = request.form.get("source_path") or request.json.get("source_path") if request.is_json else request.form.get("source_path")
    if custom_path:
        custom_path = custom_path.strip()

    now = str(datetime.datetime.now())
    
    try:
        if custom_path:
            # Load existing key file
            if not os.path.exists(custom_path):
                return jsonify({"ok": False, "message": f"El archivo de clave no existe en la ruta: {custom_path}"}), 400
            with open(custom_path, "rb") as f:
                key_bytes = f.read()
            # Validate Fernet key format (must be 32 base64-encoded bytes, i.e., length is 44 characters)
            try:
                # Test with Fernet constructor
                Fernet(key_bytes)
            except Exception:
                return jsonify({"ok": False, "message": "El archivo especificado no contiene una clave Fernet valida"}), 400
                
            fingerprint = hashlib.sha256(key_bytes).hexdigest()
            notes = f"Clave registrada manualmente en la ruta: {custom_path}"
            target_path = custom_path
        else:
            # Generate new key dynamically on server
            new_key = Fernet.generate_key()
            fingerprint = hashlib.sha256(new_key).hexdigest()
            
            # Save it to keys/ folder
            keys_dir = "keys"
            os.makedirs(keys_dir, exist_ok=True)
            target_path = os.path.join(keys_dir, f"key_{fingerprint[:12]}.key")
            with open(target_path, "wb") as f:
                f.write(new_key)
                
            notes = f"Generada automaticamente via panel de cifrado"
            
        # Check if already registered
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT * FROM encryption_keys WHERE key_fingerprint=?", (fingerprint,))
        exists = c.fetchone()
        
        if exists:
            # Just reload and return success if it's already there
            conn.close()
            load_keyring()
            return jsonify({"ok": True, "fingerprint": fingerprint, "message": "La clave ya estaba registrada y ha sido cargada."})
            
        # Insert into db as a legacy key (state = 'legada')
        c.execute(
            """
            INSERT INTO encryption_keys (
                key_fingerprint, source_path, state, created_at, activated_at, last_seen_at, last_operation, notes
            ) VALUES (?, ?, 'legada', ?, NULL, ?, 'created', ?)
            """,
            (fingerprint, target_path, now, now, notes),
        )
        conn.commit()
        conn.close()
        
        # Load keys to keyring in memory
        load_keyring()
        
        log(session.get("user"), f"Configuro clave de cifrado {fingerprint[:12]}", categoria="seguridad")
        
        return jsonify({"ok": True, "fingerprint": fingerprint, "message": "Clave configurada y cargada exitosamente."})
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "message": f"Error al configurar la clave: {str(e)}"}), 500


@app.route("/admin/keys/<fp>/activate", methods=["POST"])
def admin_activate_key(fp):
    if not require_role("admin", "coordinador"):
        return jsonify({"ok": False, "message": "Unauthorized"}), 403

    # CSRF protection
    if not validate_csrf():
        return jsonify({"ok": False, "message": "CSRF token missing or invalid"}), 400

    # Passkey signature check
    if not check_and_consume_passkey_action(f"activar clave de cifrado {fp}"):
        return jsonify({"ok": False, "message": "Falta la firma de passkey para esta accion sensible o ya ha expirado"}), 400

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM encryption_keys WHERE key_fingerprint=?", (fp,))
    row = c.fetchone()
    now = str(datetime.datetime.now())

    if not row:
        # Insert a new record if provided key not present; source_path optional
        source_path = request.form.get("source_path") or request.json.get("source_path") if request.is_json else None
        c.execute(
            """
            INSERT INTO encryption_keys (key_fingerprint, source_path, state, created_at, activated_at, last_seen_at, last_operation)
            VALUES (?, ?, 'activo', ?, ?, ?, 'activated')
            """,
            (fp, source_path or '', now, now, now),
        )
    else:
        # Mark existing active key(s) as retiring (except the one being activated)
        c.execute(
            "UPDATE encryption_keys SET state='retiring' WHERE state='activo' AND key_fingerprint != ?",
            (fp,),
        )
        # Activate selected key
        c.execute(
            "UPDATE encryption_keys SET state='activo', activated_at=?, last_seen_at=?, last_operation='activated' WHERE key_fingerprint=?",
            (now, now, fp),
        )

    conn.commit()
    conn.close()

    # Dynamically update the keyring in memory
    load_keyring()

    # Enqueue re-encrypt job
    job_id = enqueue_reencrypt_job(fp, session.get("user") or "sistema")

    log(session.get("user"), f"Activo llave de cifrado {fp[:12]} y encolo re-cifrado job {job_id}", categoria="seguridad")

    return jsonify({"ok": True, "job_id": job_id, "message": "Key activated and re-encrypt enqueued"})


def _login_identifier_from_request(provided_username=None):
    # Prefer username if provided, else fallback to remote IP
    if provided_username:
        return f"user:{provided_username}"
    addr = request.remote_addr or "unknown"
    return f"ip:{addr}"


def _get_failed_login_record(identifier):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT identifier, attempts, first_ts, lockout_until FROM login_lockouts WHERE identifier=?",
        (identifier,),
    )
    rec = c.fetchone()
    conn.close()
    return rec


def _save_failed_login_record(identifier, attempts, first_ts, lockout_until=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO login_lockouts (identifier, attempts, first_ts, lockout_until)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(identifier) DO UPDATE SET
            attempts=excluded.attempts,
            first_ts=excluded.first_ts,
            lockout_until=excluded.lockout_until
        """,
        (identifier, attempts, first_ts, lockout_until),
    )
    conn.commit()
    conn.close()


def _delete_failed_login_record(identifier):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM login_lockouts WHERE identifier=?", (identifier,))
    conn.commit()
    conn.close()


def _is_locked(identifier):
    rec = failed_login_store.get(identifier)
    if not rec:
        db_rec = _get_failed_login_record(identifier)
        if db_rec:
            rec = {
                "attempts": db_rec["attempts"],
                "first_ts": db_rec["first_ts"],
                "lockout_until": db_rec["lockout_until"],
            }
            failed_login_store[identifier] = rec
    if not rec:
        return False, None
    now = time.time()
    if rec.get("lockout_until") and rec["lockout_until"] > now:
        return True, rec["lockout_until"]
    # If past lockout or window expired, reset
    first = rec.get("first_ts", 0)
    if now - first > LOGIN_WINDOW_SECONDS:
        failed_login_store.pop(identifier, None)
        _delete_failed_login_record(identifier)
        return False, None
    return False, None


def _record_failed(identifier):
    now = time.time()
    rec = failed_login_store.get(identifier)
    if not rec:
        db_rec = _get_failed_login_record(identifier)
        if db_rec:
            rec = {
                "attempts": db_rec["attempts"],
                "first_ts": db_rec["first_ts"],
                "lockout_until": db_rec["lockout_until"],
            }
        else:
            rec = {"attempts": 0, "first_ts": now}

    if now - rec.get("first_ts", 0) > LOGIN_WINDOW_SECONDS:
        rec["attempts"] = 1
        rec["first_ts"] = now
        rec.pop("lockout_until", None)
        failed_login_store[identifier] = rec
        _save_failed_login_record(identifier, rec["attempts"], rec["first_ts"])
        return rec

    rec["attempts"] = rec.get("attempts", 0) + 1
    if rec["attempts"] >= LOGIN_MAX_ATTEMPTS:
        rec["lockout_until"] = now + LOGIN_LOCKOUT_SECONDS
    else:
        rec.pop("lockout_until", None)
    failed_login_store[identifier] = rec
    _save_failed_login_record(identifier, rec["attempts"], rec["first_ts"], rec.get("lockout_until"))
    return rec


def _clear_failed(identifier):
    failed_login_store.pop(identifier, None)
    _delete_failed_login_record(identifier)


def generate_password_salt():
    return os.urandom(ARGON2_SALT_LEN)


def encode_salt(salt_bytes):
    return base64.b64encode(salt_bytes).decode("utf-8")


def decode_salt(salt_value):
    if not salt_value:
        return None
    try:
        return base64.b64decode(salt_value.encode("utf-8"))
    except Exception:
        return None


def hash_password_argon2id(password, salt_bytes):
    hashed = hash_secret(
        secret=password.encode("utf-8"),
        salt=salt_bytes,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LEN,
        type=Type.ID,
    )
    return hashed.decode("utf-8")


def verify_password_argon2id(stored_hash, password, salt_value):
    salt_bytes = decode_salt(salt_value)
    if not salt_bytes:
        return False

    expected = hash_password_argon2id(password, salt_bytes)
    return hmac.compare_digest(stored_hash, expected)


def password_has_minimum_entropy(password):
    if len(password or "") < PASSWORD_MIN_LENGTH:
        return False

    pw = password or ""
    has_upper = any(ch.isupper() for ch in pw)
    has_lower = any(ch.islower() for ch in pw)
    has_digit = any(ch.isdigit() for ch in pw)
    has_symbol = any(not ch.isalnum() for ch in pw)
    categories = sum([has_upper, has_lower, has_digit, has_symbol])
    if categories < 3:
        return False

    if pw.lower() in COMMON_WEAK_PASSWORDS:
        return False

    return True


def validate_email_address(email):
    if not email:
        return True
    if len(email) > 254:
        return False
    # Simple RFC-adjacent sanity check
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    return re.match(pattern, email) is not None


def validate_phone_number(phone):
    if not phone:
        return True
    # Allow +, digits, spaces, hyphens, parentheses. Normalize to digits for length check.
    cleaned = phone.strip()
    # remove common separators
    cleaned_digits = re.sub(r"[\s\-().]", "", cleaned)
    # allow leading +
    if cleaned_digits.startswith("+"):
        digits_only = re.sub(r"[^0-9]", "", cleaned_digits[1:])
    else:
        digits_only = re.sub(r"[^0-9]", "", cleaned_digits)

    if len(digits_only) < 7 or len(digits_only) > 20:
        return False
    return True


def check_password_pwned(password):
    sha1_hex = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix = sha1_hex[:5]
    suffix = sha1_hex[5:]
    url = f"https://api.pwnedpasswords.com/range/{prefix}"

    req = urllib.request.Request(url, headers={"User-Agent": "CasaMonarca/1.0"})
    with urllib.request.urlopen(req, timeout=HIBP_TIMEOUT_SECONDS) as response:
        body = response.read().decode("utf-8", errors="ignore")

    for line in body.splitlines():
        parts = line.split(":")
        if len(parts) != 2:
            continue
        if parts[0].strip().upper() == suffix:
            return True

    return False


def validate_new_password_policy(password):
    if not password_has_minimum_entropy(password):
        return False, "Contrasena insegura o presente en bases de datos de filtraciones.", None

    try:
        if check_password_pwned(password):
            return False, "Contrasena insegura o presente en bases de datos de filtraciones.", None
    except (urllib.error.URLError, TimeoutError, ValueError):
        return True, None, "No se pudo validar HIBP en este momento. Continuando sin bloqueo."

    return True, None, None


def password_is_legacy_or_weak(user_row, raw_password):
    if user_row["must_change_password"] == 1:
        return True

    if user_row["password_algo"] != "argon2id":
        return True

    if not password_has_minimum_entropy(raw_password):
        return True

    return False


def verify_user_password(user_row, raw_password):
    algo = user_row["password_algo"]
    if algo == "argon2id":
        return verify_password_argon2id(
            user_row["password_hash"],
            raw_password,
            user_row["password_salt"],
        )

    if user_row["password_hash"]:
        return check_password_hash(user_row["password_hash"], raw_password)

    return False


def create_default_accounts():
    conn = get_conn()
    c = conn.cursor()

    if app.config.get("TESTING", False):
        # Keep legacy test passwords when running tests to preserve existing test expectations
        default_users = [
            ("admin_prod", "admin123", "admin", None, 0, 0),
            ("admin_cont", "admin123", "admin", None, 1, 0),
            ("coord_admin", "coord123", "coordinador", "Administracion", 0, 0),
            ("operativo_1", "oper123", "operativo", None, 0, 0),
            ("usuario_1", "user123", "usuario", None, 0, 0),
        ]
    else:
        default_users = [
            ("admin_prod", "AdminProdX2026!", "admin", None, 0, 1),
            ("admin_cont", "AdminContX2026!", "admin", None, 1, 1),
            ("coord_admin", "CoordAdminX2026!", "coordinador", "Administracion", 0, 1),
            ("operativo_1", "Operativo_2026!", "operativo", None, 0, 0),
            ("usuario_1", "Usuario_2026!X", "usuario", None, 0, 0),
        ]

    for username, password, rol, area, contingency, passkey_required in default_users:
        salt = generate_password_salt()
        password_hash = hash_password_argon2id(password, salt)
        c.execute("SELECT id FROM usuarios WHERE username=?", (username,))
        existing = c.fetchone()
        if existing is None:
            salt = generate_password_salt()
            c.execute(
                """
                INSERT INTO usuarios (
                    username, password_hash, rol, area, is_contingency, activo,
                    passkey_enrollment_required,
                    must_change_password, password_updated_at, password_algo, password_salt
                )
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, 'argon2id', ?)
                """,
                (
                    username,
                    hash_password_argon2id(password, salt),
                    rol,
                    area,
                    contingency,
                    passkey_required,
                    0 if not app.config.get("TESTING", False) else 1,
                    str(datetime.datetime.now()),
                    encode_salt(salt),
                ),
            )
        elif not app.config.get("TESTING", False):
            c.execute(
                """
                UPDATE usuarios
                SET password_hash=?, rol=?, area=?, is_contingency=?, activo=1,
                    passkey_enrollment_required=?,
                    must_change_password=0, password_updated_at=?, password_algo='argon2id',
                    password_salt=?
                WHERE username=?
                """,
                (
                    password_hash,
                    rol,
                    area,
                    contingency,
                    passkey_required,
                    str(datetime.datetime.now()),
                    encode_salt(salt),
                    username,
                ),
            )

    # Migracion de contrasenas antiguas en texto plano si existe la columna old
    c.execute("PRAGMA table_info(usuarios)")
    cols = [row[1] for row in c.fetchall()]
    if "password" in cols:
        c.execute(
            "SELECT id, password, password_hash FROM usuarios WHERE password IS NOT NULL"
        )
        for row in c.fetchall():
            plain = row[1]
            current_hash = row[2]
            if plain and not current_hash:
                salt = generate_password_salt()
                c.execute(
                    """
                    UPDATE usuarios
                    SET password_hash=?, password_algo='argon2id', password_salt=?,
                        password_updated_at=?, must_change_password=1
                    WHERE id=?
                    """,
                    (
                        hash_password_argon2id(plain, salt),
                        encode_salt(salt),
                        str(datetime.datetime.now()),
                        row[0],
                    ),
                )

    conn.commit()
    conn.close()


def _demo_private_key_path(username):
    if username == "admin_cont":
        return "admin_cont_demo.key"
    return f"{username}_demo.key"


def _load_or_create_demo_private_key(username, passphrase):
    key_path = _demo_private_key_path(username)
    if os.path.exists(key_path):
        try:
            with open(key_path, "rb") as key_file:
                return serialization.load_pem_private_key(
                    key_file.read(),
                    password=passphrase.encode("utf-8") if passphrase else None,
                )
        except Exception:
            pass

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with open(key_path, "wb") as key_file:
        key_file.write(serialize_private_key_encrypted(private_key, passphrase))
    return private_key


def _build_demo_csr(username, role, private_key):
    return (
        x509.CertificateSigningRequestBuilder()
        .subject_name(_certificate_subject_for_user(username, role))
        .sign(private_key, hashes.SHA256())
    )


def _cleanup_legacy_certificate_files():
    os.makedirs("certs", exist_ok=True)
    legacy_artifacts = {
        "admin_prod.pem",
        "admin_cont.pem",
        "coord_admin.pem",
        "admin_prod_demo.key",
        "admin_cont_demo.key",
        "coord_admin_demo.key",
    }
    for entry in os.scandir("certs"):
        if entry.is_file() and entry.name in legacy_artifacts:
            try:
                os.remove(entry.path)
            except OSError:
                pass


def bootstrap_dev_certificates():
    conn = get_conn()
    c = conn.cursor()

    defaults = {
        "admin_prod": ("admin", "AdminProdX2026!"),
        "admin_cont": ("admin", "AdminContX2026!"),
        "coord_admin": ("coordinador", "CoordAdminX2026!"),
    }

    if app.config.get("TESTING", False):
        conn.close()
        return

    _cleanup_legacy_certificate_files()

    for username, (role, passphrase) in defaults.items():
        c.execute(
            "SELECT id FROM usuarios WHERE username=?",
            (username,),
        )
        row = c.fetchone()
        if not row:
            continue

        # Preserve existing passkeys: if the user already has active passkeys,
        # do not delete them and do not force reenrollment on bootstrap.
        c.execute("DELETE FROM certificados WHERE username=?", (username,))
        c.execute(
            "SELECT COUNT(1) as cnt FROM passkey_credentials WHERE username=? AND status='activo'",
            (username,),
        )
        cnt_row = c.fetchone()
        has_passkeys = (cnt_row and cnt_row[0])
        if not has_passkeys:
            # No existing passkeys: ensure clean state and require enrollment
            c.execute("DELETE FROM passkey_credentials WHERE username=?", (username,))
            c.execute(
                """
                UPDATE usuarios
                SET cert_fingerprint=NULL,
                    must_change_password=0,
                    passkey_enrollment_required=1,
                    password_updated_at=?
                WHERE username=?
                """,
                (str(datetime.datetime.now()), username),
            )
        else:
            # Preserve passkeys and clear enrollment requirement
            c.execute(
                """
                UPDATE usuarios
                SET cert_fingerprint=NULL,
                    must_change_password=0,
                    passkey_enrollment_required=0,
                    password_updated_at=?
                WHERE username=?
                """,
                (str(datetime.datetime.now()), username),
            )

    conn.commit()
    conn.close()


def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()


def serialize_private_key_encrypted(private_key, passphrase):
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.BestAvailableEncryption(
            passphrase.encode("utf-8")
        ),
    )


def serialize_public_key(public_key):
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def compute_public_fingerprint(public_bytes):
    return hash_bytes(public_bytes)


def b64url_encode(raw_bytes):
    if raw_bytes is None:
        return None
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode("ascii")


def b64url_decode(raw_text):
    if not raw_text:
        return None
    padding_len = (4 - len(raw_text) % 4) % 4
    return base64.urlsafe_b64decode(raw_text + ("=" * padding_len))


def get_active_passkeys(conn, username):
    c = conn.cursor()
    c.execute(
        """
        SELECT * FROM passkey_credentials
        WHERE username=? AND status='activo'
        ORDER BY created_at DESC, id DESC
        """,
        (username,),
    )
    return c.fetchall()


def get_active_passkey_by_credential(conn, username, credential_id):
    c = conn.cursor()
    c.execute(
        """
        SELECT * FROM passkey_credentials
        WHERE username=? AND credential_id=? AND status='activo'
        ORDER BY id DESC LIMIT 1
        """,
        (username, credential_id),
    )
    return c.fetchone()


def save_passkey_credential(conn, username, credential_id, public_key_b64, sign_count, aaguid=None, transports=None, label=None):
    now = str(datetime.datetime.now())
    c = conn.cursor()
    
    # Obtener rol del usuario para generar cert
    c.execute("SELECT rol FROM usuarios WHERE username=?", (username,))
    user_row = c.fetchone()
    if not user_row:
        print(f"Warning: Usuario {username} no encontrado al guardar passkey")
        return None
    
    role = user_row['rol']
    
    c.execute(
        """
        INSERT INTO passkey_credentials (
            username, credential_id, public_key_b64, sign_count,
            aaguid, transports, label, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'activo', ?, ?)
        """,
        (
            username,
            credential_id,
            public_key_b64,
            sign_count,
            aaguid,
            transports,
            label,
            now,
            now,
        ),
    )
    
    passkey_id = c.lastrowid
    
    # NUEVO: Si es el primer passkey activo → generar certificado automáticamente
    c.execute(
        """
        SELECT COUNT(*) as cnt FROM passkey_credentials 
        WHERE username=? AND status='activo' AND id != ?
        """,
        (username, passkey_id)
    )
    other_active = c.fetchone()['cnt']
    
    if other_active == 0:
        # Este es el PRIMER passkey activo: generar certificado
        cert_id = derive_certificate_from_first_passkey(conn, username, role)
        
        if cert_id:
            # Vincular este passkey con el certificado generado
            link_passkey_to_certificate(conn, passkey_id, cert_id, username)
            print(f"✓ Certificado PKI generado automáticamente para {username} (cert_id={cert_id})")
            log(username, f"Certificado PKI generado automáticamente desde primer passkey", categoria="seguridad")
        else:
            print(f"Warning: No se pudo generar certificado para {username} al registrar passkey")
    else:
        # Este NO es el primer passkey: vincular al certificado existente del usuario
        c.execute(
            """
            SELECT id FROM certificados 
            WHERE username=? AND passkey_source=1 AND status='activo'
            LIMIT 1
            """,
            (username,)
        )
        existing_cert = c.fetchone()
        if existing_cert:
            cert_id = existing_cert['id']
            link_passkey_to_certificate(conn, passkey_id, cert_id, username)
    
    c.execute(
        """
        UPDATE usuarios
        SET passkey_enrollment_required=0
        WHERE username=?
        """,
        (username,),
    )
    
    conn.commit()
    return passkey_id



def update_passkey_usage(conn, passkey_id, sign_count):
    now = str(datetime.datetime.now())
    c = conn.cursor()
    c.execute(
        """
        UPDATE passkey_credentials
        SET sign_count=?, last_used_at=?, updated_at=?
        WHERE id=?
        """,
        (sign_count, now, now, passkey_id),
    )


def cose_key_to_public_key(cose_public_key_b64):
    """
    Convierte una clave pública COSE (formato WebAuthn base64url) a cryptography.PublicKey.
    
    Este es un helper para futura compatibilidad. Por ahora, retorna None ya que
    los certificados se generan a nivel de usuario, no por passkey específico.
    
    Args:
        cose_public_key_b64: Clave pública COSE en base64url
        
    Returns:
        PublicKey object o None si no se puede convertir
    """
    try:
        cose_bytes = b64url_decode(cose_public_key_b64)
        if not cose_bytes:
            return None
        
        # COSE keys son estructuras CBOR que requieren parsing especial
        # Por ahora solo registramos que esto sería necesario en futuro
        # cuando queramos certificados por passkey específico
        return None
    except Exception as e:
        print(f"COSE key conversion error (expected for now): {e}")
        return None


def derive_certificate_from_first_passkey(conn, username, role):
    """
    Genera UN certificado PKI para el usuario cuando registra su primer passkey activo.
    
    Arquitectura N:1: Múltiples passkeys → 1 certificado por usuario
    
    El certificado se vincula al usuario, no a un passkey específico.
    Se reutiliza para todos sus passkeys mientras esté activo.
    
    Args:
        conn: Conexión a BD
        username: Username del usuario
        role: Rol del usuario (admin, coordinador, etc)
        
    Returns:
        int: cert_id del certificado creado o existente
        None: Si hay error
    """
    c = conn.cursor()
    now = str(datetime.datetime.now())
    
    try:
        # 1. Verificar si ya existe un certificado PKI activo para este usuario
        #    (No generamos duplicados)
        c.execute(
            """
            SELECT id FROM certificados 
            WHERE username=? AND passkey_source=1 AND status IN ('activo', 'pendiente')
            LIMIT 1
            """,
            (username,)
        )
        existing = c.fetchone()
        if existing:
            return existing['id']
        
        # 2. Generar certificado con clave pública temporal
        #    (Será una clave de usuario genérica, no vinculada a passkey específico)
        from cryptography.hazmat.primitives.asymmetric import rsa
        
        # Usar una clave RSA estándar para el certificado de usuario
        # En futuro, podría usarse la clave pública del passkey
        user_private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048
        )
        user_public_key = user_private_key.public_key()
        
        # 3. Construir certificado firmado
        cert_data = _build_signed_certificate_from_public_key(username, role, user_public_key)
        
        # 4. Insertar en tabla certificados
        cert_pem = cert_data.get('bundle_pem', b'').decode('utf-8') if isinstance(cert_data.get('bundle_pem'), bytes) else cert_data.get('bundle_pem', '')
        
        c.execute(
            """
            INSERT INTO certificados (
                username, rol, issued_by, issuer_fingerprint,
                cert_fingerprint, issued_at, expires_at, status,
                pem_hash, public_fp, cert_serial, algorithm,
                passkey_source, num_passkeys_using, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                role,
                'passkey_system',  # Indica que fue generado automáticamente
                '',  # issuer_fingerprint se omite en auto-gen
                cert_data.get('cert_fingerprint'),
                cert_data.get('issued_at'),
                cert_data.get('expires_at'),
                'activo',
                cert_data.get('pem_hash'),
                cert_data.get('public_fp'),
                cert_data.get('serial'),
                cert_data.get('algorithm'),
                1,  # passkey_source = True
                0,  # num_passkeys_using (se actualizará)
                now,
                now
            )
        )
        
        cert_id = c.lastrowid
        conn.commit()
        
        print(f"Certificate generated for user {username} from passkey (cert_id={cert_id})")
        return cert_id
        
    except Exception as e:
        print(f"Error deriving certificate from passkey for {username}: {e}")
        traceback.print_exc()
        return None


def link_passkey_to_certificate(conn, passkey_id, cert_id, username):
    """
    Vincula un passkey registrado con su certificado PKI.
    
    Args:
        conn: Conexión a BD
        passkey_id: ID del passkey en tabla passkey_credentials
        cert_id: ID del certificado en tabla certificados
        username: Username para validación
        
    Returns:
        bool: True si se vinculó exitosamente
    """
    c = conn.cursor()
    now = str(datetime.datetime.now())
    
    try:
        # Vincular passkey con certificado
        c.execute(
            """
            UPDATE passkey_credentials 
            SET user_cert_id=?, generated_cert_at=?, updated_at=?
            WHERE id=? AND username=?
            """,
            (cert_id, now, now, passkey_id, username)
        )
        
        # Incrementar contador de passkeys usando este certificado
        c.execute(
            """
            UPDATE certificados
            SET num_passkeys_using = num_passkeys_using + 1
            WHERE id=?
            """,
            (cert_id,)
        )
        
        conn.commit()
        return True
        
    except Exception as e:
        print(f"Error linking passkey {passkey_id} to cert {cert_id}: {e}")
        return False


def check_certificate_expiration(conn, username):
    """
    Verifica si el certificado PKI del usuario ha expirado.
    Si expiró → deshabilita TODOS sus passkeys.
    
    Ciclo de vida vinculado:
    - Cert expira → Passkeys se deshabilitan automáticamente
    - Previene uso de passkeys con certificados vencidos
    
    Args:
        conn: Conexión a BD
        username: Username a verificar
        
    Returns:
        (bool, str): (certificado_válido, mensaje)
            True: Certificado activo y válido
            False: Certificado expirado o no existe
    """
    c = conn.cursor()
    
    try:
        # Buscar certificado PKI activo del usuario
        c.execute(
            """
            SELECT id, expires_at, status FROM certificados 
            WHERE username=? AND passkey_source=1 AND status='activo'
            LIMIT 1
            """,
            (username,)
        )
        cert = c.fetchone()
        
        if not cert:
            # No hay certificado PKI generado desde passkey
            return True, "No hay certificado PKI vinculado (normal si no usa passkeys)"
        
        # Verificar si expiró
        now = datetime.datetime.now()
        expires = parse_datetime(cert['expires_at'])
        
        if expires and expires < now:
            # CERTIFICADO EXPIRADO: Deshabilitar passkeys
            c.execute(
                """
                UPDATE passkey_credentials 
                SET status='deshabilitado_cert_exp'
                WHERE username=? AND status='activo'
                """,
                (username,)
            )
            
            # Marcar certificado como expirado
            c.execute(
                """
                UPDATE certificados
                SET status='expirado'
                WHERE id=?
                """,
                (cert['id'],)
            )
            
            conn.commit()
            
            # Loguear evento
            log(username, "Certificado PKI expirado - passkeys deshabilitados automáticamente", 
                categoria="seguridad")
            
            return False, "Tu certificado ha expirado. Contacta a un administrador para renovarlo."
        
        # Certificado válido
        return True, "Certificado válido"
        
    except Exception as e:
        print(f"Error checking certificate expiration for {username}: {e}")
        return True, "No se pudo verificar certificado (error interno)"


def revoke_passkey(conn, passkey_id, reason="user_request"):
    """
    Revoca un passkey individual.
    
    Args:
        conn: Conexión a BD
        passkey_id: ID del passkey en tabla passkey_credentials
        reason: Razón de revocación
        
    Returns:
        bool: True si fue exitoso
    """
    c = conn.cursor()
    now = str(datetime.datetime.now())
    
    try:
        c.execute(
            """
            UPDATE passkey_credentials 
            SET status='revocado', revocation_reason=?, revoked_at=?, updated_at=?
            WHERE id=?
            """,
            (reason, now, now, passkey_id)
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"Error revoking passkey {passkey_id}: {e}")
        return False


def revoke_passkey_and_cert(conn, passkey_id, username, reason="user_request"):
    """
    Revoca un passkey. Si es el último passkey activo del usuario,
    también revoca su certificado PKI (N:1 lifecycle).
    
    Args:
        conn: Conexión a BD
        passkey_id: ID del passkey
        username: Username propietario del passkey
        reason: Razón de revocación
        
    Returns:
        (bool, list): (success, list_of_affected_cert_ids)
    """
    c = conn.cursor()
    now = str(datetime.datetime.now())
    affected_certs = []
    cert_was_revoked = False
    
    try:
        # 1. Revocar el passkey
        c.execute(
            """
            UPDATE passkey_credentials 
            SET status='revocado', revocation_reason=?, revoked_at=?, updated_at=?
            WHERE id=? AND username=?
            """,
            (reason, now, now, passkey_id, username)
        )
        
        # 2. Obtener cert_id del passkey revocado
        c.execute(
            "SELECT user_cert_id FROM passkey_credentials WHERE id=?",
            (passkey_id,)
        )
        passkey = c.fetchone()
        if not passkey:
            conn.commit()
            return False, []
        
        cert_id = passkey['user_cert_id']
        if not cert_id:
            conn.commit()
            return True, []
        
        # 3. Verificar si quedan passkeys activos para este usuario
        c.execute(
            """
            SELECT COUNT(*) as cnt FROM passkey_credentials 
            WHERE username=? AND user_cert_id=? AND status='activo'
            """,
            (username, cert_id)
        )
        count = c.fetchone()['cnt']
        
        # 4. Si no quedan passkeys activos, revocar el certificado
        if count == 0:
            c.execute(
                """
                UPDATE certificados 
                SET status='revocado', revocation_reason=?, revoked_at=?, updated_at=?
                WHERE id=?
                """,
                (reason, now, now, cert_id)
            )
            affected_certs.append(cert_id)
            cert_was_revoked = True
        
        conn.commit()
        
        # Log después del commit
        if cert_was_revoked:
            log(username, f"Certificado PKI revocado automáticamente (revocación de último passkey): {reason}",
                categoria="seguridad")
        log(username, f"Passkey revocado: {reason}", categoria="seguridad")
        
        return True, affected_certs
        
    except Exception as e:
        print(f"Error revoking passkey {passkey_id}: {e}")
        traceback.print_exc()
        return False, []


def revoke_certificate_and_passkeys(conn, cert_id, reason="expiration_or_admin"):
    """
    Revoca un certificado PKI y TODOS sus passkeys asociados.
    
    Args:
        conn: Conexión a BD
        cert_id: ID del certificado en tabla certificados
        reason: Razón de revocación
        
    Returns:
        (bool, int): (success, number_of_passkeys_revoked)
    """
    c = conn.cursor()
    now = str(datetime.datetime.now())
    
    try:
        # 1. Obtener info del certificado
        c.execute(
            "SELECT username FROM certificados WHERE id=?",
            (cert_id,)
        )
        cert = c.fetchone()
        if not cert:
            return False, 0
        
        username = cert['username']
        
        # 2. Revocar el certificado
        c.execute(
            """
            UPDATE certificados 
            SET status='revocado', revocation_reason=?, revoked_at=?, updated_at=?
            WHERE id=?
            """,
            (reason, now, now, cert_id)
        )
        
        # 3. Contar y revocar TODOS los passkeys del certificado
        c.execute(
            """
            UPDATE passkey_credentials 
            SET status='revocado', revocation_reason=?, revoked_at=?, updated_at=?
            WHERE user_cert_id=? AND status='activo'
            """,
            (reason, now, now, cert_id)
        )
        
        # Contar cuántos se revocaron
        c.execute(
            """
            SELECT COUNT(*) as cnt FROM passkey_credentials 
            WHERE user_cert_id=? AND status='revocado'
            """,
            (cert_id,)
        )
        revoked_count = c.fetchone()['cnt']
        
        conn.commit()
        
        # Log después del commit
        log(username, f"Certificado PKI revocado: {reason}. {revoked_count} passkeys también revocados.",
            categoria="seguridad")
        
        return True, revoked_count
        
    except Exception as e:
        print(f"Error revoking certificate {cert_id}: {e}")
        traceback.print_exc()
        return False, 0


def store_pem_file(username, pem_bytes):
    os.makedirs("certs", exist_ok=True)
    pem_path = os.path.join("certs", f"{username}.pem")
    with open(pem_path, "wb") as pem_file:
        pem_file.write(pem_bytes)
    return pem_path


def load_private_key_from_pem(pem_bytes, passphrase):
    return serialization.load_pem_private_key(
        pem_bytes,
        password=passphrase.encode("utf-8") if passphrase else None,
    )


def _certificate_authority_name():
    return x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, CERT_CA_COUNTRY),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, CERT_CA_ORG),
            x509.NameAttribute(NameOID.COMMON_NAME, CERT_CA_COMMON_NAME),
        ]
    )


_certificate_authority_cache = None


def _load_or_create_certificate_authority():
    global _certificate_authority_cache
    if _certificate_authority_cache:
        return _certificate_authority_cache

    os.makedirs("certs", exist_ok=True)
    if os.path.exists(CERT_CA_CERT_PATH) and os.path.exists(CERT_CA_KEY_PATH):
        try:
            with open(CERT_CA_KEY_PATH, "rb") as key_file:
                ca_key = serialization.load_pem_private_key(key_file.read(), password=None)
            with open(CERT_CA_CERT_PATH, "rb") as cert_file:
                ca_cert = x509.load_pem_x509_certificate(cert_file.read())
            _certificate_authority_cache = (ca_key, ca_cert)
            return _certificate_authority_cache
        except Exception as e:
            # Si no se puede cargar la CA existente, crear una nueva
            # (Esto puede pasar si el archivo está corrompido o usa cifrado desconocido)
            print(f"Warning: No se pudo cargar CA existente, generando nueva: {e}")
            pass

    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    ca_name = _certificate_authority_name()
    now = datetime.datetime.utcnow()
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(private_key=ca_key, algorithm=hashes.SHA256())
    )

    with open(CERT_CA_KEY_PATH, "wb") as key_file:
        key_file.write(
            ca_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    with open(CERT_CA_CERT_PATH, "wb") as cert_file:
        cert_file.write(ca_cert.public_bytes(serialization.Encoding.PEM))

    _certificate_authority_cache = (ca_key, ca_cert)
    return _certificate_authority_cache


def _certificate_subject_for_user(username, role):
    return x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, CERT_CA_COUNTRY),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, CERT_CA_ORG),
            x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, role),
            x509.NameAttribute(NameOID.COMMON_NAME, username),
        ]
    )


def _extract_pem_block(pem_bytes, label_pattern):
    match = re.search(
        rb"-----BEGIN " + label_pattern + rb"-----.*?-----END " + label_pattern + rb"-----",
        pem_bytes,
        flags=re.S,
    )
    if not match:
        return None
    return match.group(0)


def _extract_pem_certificate(pem_bytes):
    return _extract_pem_block(pem_bytes, rb"CERTIFICATE")


def _extract_pem_private_key(pem_bytes):
    match = re.search(
        rb"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        pem_bytes,
        flags=re.S,
    )
    if not match:
        return None
    return match.group(0)


def _signature_challenge_key(scope):
    return f"{scope}_signature_challenge"


def issue_signature_challenge(scope, username=None):
    challenge = secrets.token_urlsafe(32)
    session[_signature_challenge_key(scope)] = {
        "value": challenge,
        "username": username,
        "issued_at": time.time(),
    }
    return challenge


def get_signature_challenge(scope, username=None):
    challenge_row = session.get(_signature_challenge_key(scope))
    if not challenge_row:
        return issue_signature_challenge(scope, username)

    issued_at = challenge_row.get("issued_at", 0)
    if time.time() - issued_at > SIGNATURE_CHALLENGE_TTL_SECONDS:
        return issue_signature_challenge(scope, challenge_row.get("username") or username)

    return challenge_row.get("value")


def consume_signature_challenge(scope):
    session.pop(_signature_challenge_key(scope), None)


def decode_signature_value(signature_text=None, signature_file=None):
    if signature_file and getattr(signature_file, "filename", ""):
        signature_bytes = signature_file.read()
        if signature_bytes:
            return signature_bytes

    if not signature_text:
        return None

    cleaned = signature_text.strip().replace("\n", "")
    if not cleaned:
        return None

    try:
        return base64.b64decode(cleaned, validate=True)
    except Exception:
        try:
            return bytes.fromhex(cleaned)
        except Exception:
            return None


def build_signature_payload(purpose, username, challenge):
    return f"CasaMonarca|{purpose}|{username}|{challenge}".encode("utf-8")


@app.context_processor
def inject_signature_challenges():
    return {
        "login_signature_challenge": get_signature_challenge("login"),
        "action_signature_challenge": get_signature_challenge("action", session.get("user")),
    }


def verify_certificate_challenge_response(cert_row, pem_bytes, challenge, signature_bytes, purpose, username):
    custody_mode = cert_row["custody_mode"] or "server_bundle"

    if cert_row["status"] == "revocado":
        return False, "El certificado esta revocado.", None

    if cert_row["status"] != "activo":
        return False, "No hay un certificado activo. Debes configurarlo.", None

    ca_key, ca_cert = _load_or_create_certificate_authority()
    cert_bytes = _extract_pem_certificate(pem_bytes)
    if not cert_bytes:
        return False, "El archivo PEM del certificado es invalido.", None

    try:
        cert = x509.load_pem_x509_certificate(cert_bytes)
    except Exception:
        return False, "El archivo PEM del certificado es invalido.", None

    cert_fingerprint = hash_bytes(cert.public_bytes(serialization.Encoding.PEM))
    uploaded_cert_hash = hash_bytes(pem_bytes)
    if cert_row["pem_hash"] not in (uploaded_cert_hash, cert_fingerprint):
        return False, "El archivo no coincide con el certificado registrado.", None

    if not _verify_certificate_signature(cert, ca_cert):
        return False, "La firma del certificado no corresponde a la CA autorizada.", None

    now = datetime.datetime.now(datetime.timezone.utc)
    cert_not_valid_before = getattr(cert, "not_valid_before_utc", None)
    cert_not_valid_after = getattr(cert, "not_valid_after_utc", None)
    if cert_not_valid_before is None:
        cert_not_valid_before = cert.not_valid_before.replace(tzinfo=datetime.timezone.utc)
    if cert_not_valid_after is None:
        cert_not_valid_after = cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)

    if cert_not_valid_before > now or cert_not_valid_after < now:
        return False, "Tu certificado ha expirado. Debes reemitirlo.", None

    cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    ou_attrs = cert.subject.get_attributes_for_oid(NameOID.ORGANIZATIONAL_UNIT_NAME)
    subject_cn = cn_attrs[0].value if cn_attrs else None
    subject_ou = ou_attrs[0].value if ou_attrs else None

    if subject_cn and subject_cn != cert_row["username"]:
        return False, "El certificado no corresponde al usuario.", None

    if subject_ou and subject_ou != cert_row["rol"]:
        return False, "El certificado no corresponde al rol del usuario.", None

    if cert_row["cert_fingerprint"] and cert_fingerprint != cert_row["cert_fingerprint"]:
        return False, "La huella del certificado no coincide con el registro.", None

    public_fp = _certificate_public_key_fingerprint(cert)
    if cert_row["public_fp"] and public_fp != cert_row["public_fp"]:
        return False, "El certificado no corresponde al usuario.", None

    expected_payload = build_signature_payload(purpose, username, challenge)
    try:
        cert.public_key().verify(
            signature_bytes,
            expected_payload,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except Exception:
        return False, "La firma del desafio no corresponde a la clave privada.", None

    if custody_mode == "user_key" and uploaded_cert_hash != cert_row["pem_hash"]:
        return False, "El archivo del certificado no coincide con el registro.", None

    return True, None, public_fp


def _extract_pem_csr(pem_bytes):
    return _extract_pem_block(pem_bytes, rb"CERTIFICATE REQUEST")


def _certificate_public_key_fingerprint(cert):
    return hash_bytes(cert.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ))


def _build_signed_certificate_from_public_key(username, role, public_key):
    ca_key, ca_cert = _load_or_create_certificate_authority()
    now = datetime.datetime.utcnow().replace(microsecond=0)
    issued_at = now.isoformat()
    expires_at = (now + datetime.timedelta(hours=CERT_VALIDITY_HOURS)).isoformat()

    cert = (
        x509.CertificateBuilder()
        .subject_name(_certificate_subject_for_user(username, role))
        .issuer_name(ca_cert.subject)
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(hours=CERT_VALIDITY_HOURS))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(public_key),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_cert.public_key()),
            critical=False,
        )
        .sign(private_key=ca_key, algorithm=hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    public_bytes = serialize_public_key(public_key)

    return {
        "issued_at": issued_at,
        "expires_at": expires_at,
        "serial": f"{cert.serial_number:x}"[:16],
        "pem_hash": hash_bytes(cert_pem),
        "cert_fingerprint": hash_bytes(cert_pem),
        "public_fp": compute_public_fingerprint(public_bytes),
        "bundle_pem": cert_pem,
        "algorithm": CERT_PRODUCT_ALGORITHM,
    }


def _build_signed_certificate_bundle(username, role, passphrase):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = serialize_private_key_encrypted(private_key, passphrase)
    cert_data = _build_signed_certificate_from_public_key(username, role, private_key.public_key())
    bundle_pem = cert_data["bundle_pem"] + private_pem

    return {
        "issued_at": cert_data["issued_at"],
        "expires_at": cert_data["expires_at"],
        "serial": cert_data["serial"],
        "pem_hash": hash_bytes(bundle_pem),
        "cert_fingerprint": cert_data["cert_fingerprint"],
        "public_fp": cert_data["public_fp"],
        "bundle_pem": bundle_pem,
        "algorithm": CERT_PRODUCT_ALGORITHM,
    }


def _build_signed_certificate_from_csr(username, role, csr_pem):
    csr_bytes = csr_pem.encode("utf-8") if isinstance(csr_pem, str) else csr_pem
    csr = x509.load_pem_x509_csr(csr_bytes)
    if not csr.is_signature_valid:
        raise ValueError("La CSR es invalida.")

    cn_attrs = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    ou_attrs = csr.subject.get_attributes_for_oid(NameOID.ORGANIZATIONAL_UNIT_NAME)
    if not cn_attrs or cn_attrs[0].value != username:
        raise ValueError("La CSR no corresponde al usuario.")
    if ou_attrs and ou_attrs[0].value != role:
        raise ValueError("La CSR no corresponde al rol del usuario.")

    cert_data = _build_signed_certificate_from_public_key(username, role, csr.public_key())
    cert_data["csr_fingerprint"] = hash_bytes(csr.public_bytes(serialization.Encoding.PEM))
    return cert_data


def _verify_certificate_signature(cert, ca_cert):
    try:
        ca_cert.public_key().verify(
            cert.signature,
            cert.tbs_certificate_bytes,
            padding.PKCS1v15(),
            cert.signature_hash_algorithm,
        )
        return True
    except Exception:
        return False


def issue_user_certificate(
    conn,
    username,
    role,
    passphrase,
    issued_by,
    issuer_fingerprint,
):
    if role not in ("admin", "coordinador"):
        return None

    cert_data = _build_signed_certificate_bundle(username, role, passphrase)
    pem_path = store_pem_file(username, cert_data["bundle_pem"])

    c = conn.cursor()
    c.execute(
        """
        INSERT INTO certificados (
            username, rol, issued_by, issuer_fingerprint, cert_fingerprint,
            issued_at, expires_at, status, pem_hash, public_fp, cert_serial,
            pem_path, algorithm, last_used_at, revoked_at, revoked_by,
            revocation_reason, created_at, updated_at, custody_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            username,
            role,
            issued_by,
            issuer_fingerprint,
            cert_data["cert_fingerprint"],
            cert_data["issued_at"],
            cert_data["expires_at"],
            "activo",
            cert_data["pem_hash"],
            cert_data["public_fp"],
            cert_data["serial"],
            pem_path,
            cert_data["algorithm"],
            None,
            None,
            None,
            None,
            cert_data["issued_at"],
            cert_data["issued_at"],
            "server_bundle",
        ),
    )

    return {"pem_hash": cert_data["pem_hash"], "public_fp": cert_data["public_fp"]}


def issue_user_certificate_from_csr(conn, username, role, csr_pem, issued_by, issuer_fingerprint):
    if role not in ("admin", "coordinador"):
        return None

    cert_data = _build_signed_certificate_from_csr(username, role, csr_pem)
    pem_path = store_pem_file(username, cert_data["bundle_pem"])

    c = conn.cursor()
    c.execute(
        """
        INSERT INTO certificados (
            username, rol, issued_by, issuer_fingerprint, cert_fingerprint,
            issued_at, expires_at, status, pem_hash, public_fp, cert_serial,
            pem_path, algorithm, last_used_at, revoked_at, revoked_by,
            revocation_reason, created_at, updated_at, custody_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            username,
            role,
            issued_by,
            issuer_fingerprint,
            cert_data["cert_fingerprint"],
            cert_data["issued_at"],
            cert_data["expires_at"],
            "activo",
            cert_data["pem_hash"],
            cert_data["public_fp"],
            cert_data["serial"],
            pem_path,
            cert_data["algorithm"],
            None,
            None,
            None,
            None,
            cert_data["issued_at"],
            cert_data["issued_at"],
            "user_key",
        ),
    )

    return {"pem_hash": cert_data["pem_hash"], "public_fp": cert_data["public_fp"]}


def create_pending_certificate(conn, username, role, issued_by, issuer_fingerprint):
    now = str(datetime.datetime.now())
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO certificados (
            username, rol, issued_by, issuer_fingerprint, status,
            created_at, updated_at, custody_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            username,
            role,
            issued_by,
            issuer_fingerprint,
            "pendiente",
            now,
            now,
            "user_key",
        ),
    )
    return c.lastrowid


def activate_pending_certificate(conn, cert_id, username, role, passphrase, issued_by, issuer_fingerprint):
    cert_data = _build_signed_certificate_bundle(username, role, passphrase)
    pem_path = store_pem_file(username, cert_data["bundle_pem"])

    c = conn.cursor()
    c.execute(
        """
        UPDATE certificados
        SET issued_by=?, issuer_fingerprint=?, cert_fingerprint=?, issued_at=?, expires_at=?, status=?,
            pem_hash=?, public_fp=?, cert_serial=?, pem_path=?, algorithm=?,
            last_used_at=?, revoked_at=?, revoked_by=?, revocation_reason=?, updated_at=?, custody_mode=?
        WHERE id=?
        """,
        (
            issued_by,
            issuer_fingerprint,
            cert_data["cert_fingerprint"],
            cert_data["issued_at"],
            cert_data["expires_at"],
            "activo",
            cert_data["pem_hash"],
            cert_data["public_fp"],
            cert_data["serial"],
            pem_path,
            cert_data["algorithm"],
            None,
            None,
            None,
            None,
            cert_data["issued_at"],
            "server_bundle",
            cert_id,
        ),
    )

    return {"pem_hash": cert_data["pem_hash"], "public_fp": cert_data["public_fp"]}


def activate_pending_certificate_from_csr(conn, cert_id, username, role, csr_pem, issued_by, issuer_fingerprint):
    cert_data = _build_signed_certificate_from_csr(username, role, csr_pem)
    pem_path = store_pem_file(username, cert_data["bundle_pem"])

    c = conn.cursor()
    c.execute(
        """
        UPDATE certificados
        SET issued_by=?, issuer_fingerprint=?, cert_fingerprint=?, issued_at=?, expires_at=?, status=?,
            pem_hash=?, public_fp=?, cert_serial=?, pem_path=?, algorithm=?,
            last_used_at=?, revoked_at=?, revoked_by=?, revocation_reason=?, updated_at=?, custody_mode=?
        WHERE id=?
        """,
        (
            issued_by,
            issuer_fingerprint,
            cert_data["cert_fingerprint"],
            cert_data["issued_at"],
            cert_data["expires_at"],
            "activo",
            cert_data["pem_hash"],
            cert_data["public_fp"],
            cert_data["serial"],
            pem_path,
            cert_data["algorithm"],
            None,
            None,
            None,
            None,
            cert_data["issued_at"],
            "user_key",
            cert_id,
        ),
    )

    return {"pem_hash": cert_data["pem_hash"], "public_fp": cert_data["public_fp"]}


def get_active_certificate(conn, username):
    c = conn.cursor()
    c.execute(
        """
        SELECT * FROM certificados
        WHERE username=? AND status='activo'
        ORDER BY issued_at DESC LIMIT 1
        """,
        (username,),
    )
    return c.fetchone()


def get_pending_certificate(conn, username):
    c = conn.cursor()
    c.execute(
        """
        SELECT * FROM certificados
        WHERE username=? AND status='pendiente'
        ORDER BY created_at DESC LIMIT 1
        """,
        (username,),
    )
    return c.fetchone()


def get_latest_certificate(conn, username):
    c = conn.cursor()
    c.execute(
        """
        SELECT * FROM certificados
        WHERE username=?
        ORDER BY issued_at DESC, created_at DESC, id DESC LIMIT 1
        """,
        (username,),
    )
    return c.fetchone()


def is_cert_expired(cert_row):
    exp_dt = parse_datetime(cert_row["expires_at"])
    if not exp_dt:
        return False
    return exp_dt < datetime.datetime.now()


def update_cert_status(conn, cert_id, status, revoked_by=None, revocation_reason=None):
    now = str(datetime.datetime.now())
    c = conn.cursor()
    if status == "revocado":
        c.execute(
            """
            UPDATE certificados
            SET status=?, revoked_at=?, revoked_by=?, revocation_reason=?, updated_at=?
            WHERE id=?
            """,
            (status, now, revoked_by, revocation_reason, now, cert_id),
        )
    else:
        c.execute(
            "UPDATE certificados SET status=?, updated_at=? WHERE id=?",
            (status, now, cert_id),
        )


def revoke_certificate(conn, cert_id, revoked_by, revocation_reason):
    update_cert_status(conn, cert_id, "revocado", revoked_by=revoked_by, revocation_reason=revocation_reason)


def validate_encrypted_pem(cert_row, pem_bytes, passphrase, key_bytes=None):
    custody_mode = cert_row["custody_mode"] or "server_bundle"

    if cert_row["status"] == "revocado":
        return False, "El certificado esta revocado.", None

    if cert_row["status"] != "activo":
        return False, "No hay un certificado activo. Debes configurarlo.", None

    if custody_mode == "user_key":
        if not key_bytes:
            return False, "Debes adjuntar tu llave privada local.", None
        if cert_row["pem_hash"] and hash_bytes(pem_bytes) != cert_row["pem_hash"]:
            return False, "El archivo del certificado no coincide con el registro.", None
    else:
        if cert_row["pem_hash"] and hash_bytes(pem_bytes) != cert_row["pem_hash"]:
            return False, "El archivo no coincide con el certificado registrado.", None

    ca_key, ca_cert = _load_or_create_certificate_authority()
    cert_bytes = _extract_pem_certificate(pem_bytes)
    cert = None
    if cert_bytes:
        try:
            cert = x509.load_pem_x509_certificate(cert_bytes)
        except Exception:
            return False, "El archivo PEM del certificado es invalido.", None

    key_source = key_bytes if key_bytes is not None else pem_bytes
    try:
        private_key = load_private_key_from_pem(key_source, passphrase)
    except Exception:
        return False, "Passphrase invalida o llave PEM corrupta.", None

    public_bytes = serialize_public_key(private_key.public_key())
    public_fp = compute_public_fingerprint(public_bytes)

    if cert:
        if not _verify_certificate_signature(cert, ca_cert):
            return False, "La firma del certificado no corresponde a la CA autorizada.", None

        now = datetime.datetime.now(datetime.timezone.utc)
        cert_not_valid_before = getattr(cert, "not_valid_before_utc", None)
        cert_not_valid_after = getattr(cert, "not_valid_after_utc", None)
        if cert_not_valid_before is None:
            cert_not_valid_before = cert.not_valid_before.replace(tzinfo=datetime.timezone.utc)
        if cert_not_valid_after is None:
            cert_not_valid_after = cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)

        if cert_not_valid_before > now or cert_not_valid_after < now:
            return False, "Tu certificado ha expirado. Debes reemitirlo.", None

        cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        ou_attrs = cert.subject.get_attributes_for_oid(NameOID.ORGANIZATIONAL_UNIT_NAME)
        subject_cn = cn_attrs[0].value if cn_attrs else None
        subject_ou = ou_attrs[0].value if ou_attrs else None

        if subject_cn and subject_cn != cert_row["username"]:
            return False, "El certificado no corresponde al usuario.", None

        if subject_ou and subject_ou != cert_row["rol"]:
            return False, "El certificado no corresponde al rol del usuario.", None

        cert_fingerprint = hash_bytes(cert.public_bytes(serialization.Encoding.PEM))
        if cert_row["cert_fingerprint"] and cert_fingerprint != cert_row["cert_fingerprint"]:
            return False, "La huella del certificado no coincide con el registro.", None

        if not _certificate_public_key_fingerprint(cert) == public_fp:
            return False, "La llave publica del certificado no coincide con la llave privada.", None

    if cert_row["public_fp"] and public_fp != cert_row["public_fp"]:
        return False, "El certificado no corresponde al usuario.", None

    return True, None, public_fp


def validate_certificate_for_user(conn, username, pem_bytes, challenge, signature_bytes, purpose):
    latest_cert = get_latest_certificate(conn, username)
    if latest_cert and latest_cert["status"] == "revocado":
        return False, "Tu certificado esta revocado. Debes reemitirlo.", None

    cert_row = get_active_certificate(conn, username)
    if not cert_row:
        return False, "No hay un certificado activo. Debes configurarlo.", None

    if is_cert_expired(cert_row):
        update_cert_status(conn, cert_row["id"], "expirado")
        return False, "Tu certificado ha expirado. Debes reemitirlo.", None

    ok, message, public_fp = verify_certificate_challenge_response(
        cert_row,
        pem_bytes,
        challenge,
        signature_bytes,
        purpose,
        username,
    )
    if not ok:
        return False, message, None

    c = conn.cursor()
    c.execute(
        "UPDATE certificados SET last_used_at=? WHERE id=?",
        (str(datetime.datetime.now()), cert_row["id"]),
    )
    return True, None, public_fp


def verify_action_certificate(action_label):
    role = session.get("role")
    if role not in ("admin", "coordinador"):
        return True, None

    cert_file = request.files.get("action_cert_file")
    if not cert_file or not cert_file.filename:
        flash(f"Se requiere certificado para firmar: {action_label}.")
        return False, None

    challenge = request.form.get("action_challenge", "").strip()
    challenge_row = session.get(_signature_challenge_key("action"))
    if not challenge or not challenge_row or challenge_row.get("value") != challenge:
        flash("El desafio de firma no es valido o ya expiró.")
        return False, None

    if challenge_row.get("username") and challenge_row.get("username") != session.get("user"):
        flash("El desafio de firma no corresponde al usuario autenticado.")
        return False, None

    consume_signature_challenge("action")

    signature_bytes = decode_signature_value(
        request.form.get("action_signature", ""),
        request.files.get("action_signature_file"),
    )
    if not signature_bytes:
        flash("Se requiere la firma del desafio para firmar la accion.")
        return False, None

    conn = get_conn()
    ok, message, public_fp = validate_certificate_for_user(
        conn,
        session.get("user"),
        cert_file.read(),
        challenge,
        signature_bytes,
        action_label,
    )
    conn.commit()
    conn.close()

    if not ok:
        flash(message)
        return False, None

    consume_signature_challenge("action")

    return True, public_fp


def _decrypt_payload_with_keyring(blob_value):
    payload_fingerprint = None
    payload = None

    if isinstance(blob_value, (bytes, bytearray)) and blob_value.startswith(b"fp:"):
        header, _, encrypted_payload = blob_value.partition(b"\n")
        if header.startswith(b"fp:"):
            payload_fingerprint = header[3:].decode(errors="ignore") or None
            blob_value = encrypted_payload

    decode_candidates = []
    if payload_fingerprint:
        decode_candidates.append(
            (payload_fingerprint, get_cipher_for_fingerprint(payload_fingerprint))
        )

    decode_candidates.append((DATA_ENCRYPTION_KEY_FINGERPRINT, cipher))
    for entry in ENCRYPTION_KEYRING:
        candidate = (entry["fingerprint"], entry["cipher"])
        if candidate not in decode_candidates:
            decode_candidates.append(candidate)

    last_error = None
    used_fingerprint = None
    for candidate_fingerprint, candidate_cipher in decode_candidates:
        try:
            decoded = candidate_cipher.decrypt(blob_value).decode()
            payload = ast.literal_eval(decoded)
            used_fingerprint = candidate_fingerprint
            break
        except Exception as exc:
            last_error = exc

    if payload is None:
        raise last_error or ValueError("No fue posible descifrar el expediente")

    return payload, used_fingerprint


def _determine_default_action(op_type):
    if has_request_context():
        path = request.path
        method = request.method
        if path == "/admin":
            return "Visualizar panel de administracion (lectura)"
        elif path == "/bandeja":
            return "Visualizar bandeja (lectura)"
        elif path == "/survey":
            if method == "POST":
                return "Crear nuevo expediente (escritura)"
            return "Visualizar formulario de expediente (lectura)"
        elif path.startswith("/admin/cifrado"):
            return "Operacion de mantenimiento de cifrado"
        return f"Ruta {path} [{method}]"
    return "Operación del sistema en segundo plano"


def decrypt_data(blob_value, log_events=True, user=None, action_detail=None):
    started_at = time.perf_counter()
    
    # Resolve user
    if user is None:
        if has_request_context():
            user = session.get("user") or "sistema"
        else:
            user = "sistema"
            
    # Resolve action_detail
    if action_detail is None:
        action_detail = _determine_default_action("decrypt")
        
    active_key = get_active_key_details()

    try:
        payload, used_fingerprint = _decrypt_payload_with_keyring(blob_value)

        elapsed = time.perf_counter() - started_at
        _touch_encryption_key("decrypt", used_fingerprint)
        record_encryption_metric('decrypt', elapsed, used_fingerprint, None, 'ok', user, action_detail, active_key)
        if log_events and elapsed >= DATA_ENCRYPTION_LATENCY_WARNING_SECONDS:
            log(
                "sistema",
                "Descifrado de expediente con latencia moderada",
                categoria="seguridad",
                detalle=f"latencia={elapsed:.3f}s; llave={used_fingerprint[:12] if used_fingerprint else DATA_ENCRYPTION_KEY_FINGERPRINT[:12]}; usuario={user}; accion={action_detail}",
            )
        return payload
    except Exception:
        elapsed = time.perf_counter() - started_at
        # record failing decrypt metric
        try:
            record_encryption_metric('decrypt', elapsed, None, None, 'error', user, action_detail, active_key)
        except Exception:
            pass
        if log_events:
            log(
                "sistema",
                "Fallo el descifrado de un expediente",
                categoria="seguridad",
                detalle=f"llave={DATA_ENCRYPTION_KEY_FINGERPRINT[:12]}; usuario={user}; accion={action_detail}",
            )
        return None


def encrypt_data(payload, user=None, action_detail=None):
    started_at = time.perf_counter()
    
    # Resolve user
    if user is None:
        if has_request_context():
            user = session.get("user") or "sistema"
        else:
            user = "sistema"
            
    # Resolve action_detail
    if action_detail is None:
        action_detail = _determine_default_action("encrypt")
        
    active_key = get_active_key_details()

    token = cipher.encrypt(str(payload).encode())
    elapsed = time.perf_counter() - started_at
    _touch_encryption_key("encrypt", DATA_ENCRYPTION_KEY_FINGERPRINT)
    try:
        record_encryption_metric('encrypt', elapsed, DATA_ENCRYPTION_KEY_FINGERPRINT, None, 'ok', user, action_detail, active_key)
    except Exception:
        pass
    if elapsed >= DATA_ENCRYPTION_LATENCY_WARNING_SECONDS:
        log(
            "sistema",
            "Cifrado de expediente con latencia moderada",
            categoria="seguridad",
            detalle=f"latencia={elapsed:.3f}s; llave={DATA_ENCRYPTION_KEY_FINGERPRINT[:12]}; usuario={user}; accion={action_detail}",
        )
    return b"fp:" + DATA_ENCRYPTION_KEY_FINGERPRINT.encode() + b"\n" + token


def get_encryption_inventory():
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT key_fingerprint, source_path, state, created_at, activated_at,
               retired_at, last_seen_at, usage_count, last_operation, notes
        FROM encryption_keys
        ORDER BY created_at DESC, id DESC
        """
    )
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def reencrypt_all_surveys():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, datos, encryption_key_fingerprint FROM encuestas ORDER BY id ASC")
    rows = c.fetchall()

    updated = 0
    skipped = 0
    failed = []

    for row in rows:
        current_fp = row["encryption_key_fingerprint"]
        if current_fp == DATA_ENCRYPTION_KEY_FINGERPRINT:
            skipped += 1
            continue

        try:
            payload = decrypt_data(
                row["datos"],
                log_events=False,
                user=session.get("user") if has_request_context() else "sistema",
                action_detail=f"Descifrado para re-cifrado de expediente #{row['id']} por rotación"
            )
            if payload is None:
                raise ValueError("No fue posible descifrar el expediente")

            refreshed = encrypt_data(
                payload,
                user=session.get("user") if has_request_context() else "sistema",
                action_detail=f"Re-cifrado de expediente #{row['id']} por rotación"
            )
            c.execute(
                """
                UPDATE encuestas
                SET datos=?, encryption_key_fingerprint=?, encrypted_at=?, updated_at=?
                WHERE id=?
                """,
                (
                    refreshed,
                    DATA_ENCRYPTION_KEY_FINGERPRINT,
                    str(datetime.datetime.now()),
                    str(datetime.datetime.now()),
                    row["id"],
                ),
            )
            updated += 1
        except Exception as exc:
            failed.append({"id": row["id"], "error": str(exc)})

    conn.commit()
    conn.close()

    return {"updated": updated, "skipped": skipped, "failed": failed}


def parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except Exception:
        return None


def require_login():
    return "user" in session and session.get("role") in ROLE_LABELS


@app.before_request
def ensure_csrf_token():
    # Ensure a per-session CSRF token exists
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)


def validate_csrf():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        # Look for token in form or header
        token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
        if not token or token != session.get("csrf_token"):
            return False
    return True


@app.before_request
def csrf_protect():
    # In tests, skip CSRF enforcement to simplify automated tests
    if app.config.get("TESTING", False):
        return None

    # Skip for safe methods or static files
    if request.method == "GET" or request.path.startswith("/static"):
        return None
    # Allow file downloads without CSRF if safe endpoint (GET only)
    ok = validate_csrf()
    if not ok:
        return "CSRF token missing or invalid", 400


@app.after_request
def enforce_cookie_flags(response):
    # Ensure Set-Cookie headers include HttpOnly, Secure (when enabled) and SameSite
    try:
        samesite = app.config.get("SESSION_COOKIE_SAMESITE", "Lax")
        secure_flag = bool(app.config.get("SESSION_COOKIE_SECURE", False))

        set_cookie_headers = response.headers.get_all("Set-Cookie")
        if not set_cookie_headers:
            return response

        # Rebuild headers ensuring flags
        new_headers = []
        for hdr in set_cookie_headers:
            cookie = hdr
            if "HttpOnly" not in cookie:
                cookie += "; HttpOnly"
            if secure_flag and "Secure" not in cookie:
                cookie += "; Secure"
            if "SameSite" not in cookie:
                cookie += f"; SameSite={samesite}"
            new_headers.append(cookie)

        # Replace existing Set-Cookie headers
        del response.headers["Set-Cookie"]
        for h in new_headers:
            response.headers.add("Set-Cookie", h)
    except Exception:
        # Never break response on header post-processing
        pass
    return response


def require_role(*roles):
    return session.get("role") in roles


@app.before_request
def enforce_certificate_setup():
    if session.get("password_change_required"):
        if not session.get("user"):
            session.pop("password_change_required", None)
            return None
        if request.path.startswith("/static"):
            return None
        if request.path in ("/", "/password/update", "/logout"):
            return None
        if request.path.startswith("/auth/passkey/") or request.path.startswith("/action/passkey/") or request.path == "/auth/check-passkey-required":
            return None
        return redirect("/password/update")

    if session.get("passkey_enrollment_required"):
        if not session.get("user"):
            session.pop("passkey_enrollment_required", None)
            return None
        if request.path.startswith("/static"):
            return None
        if request.path in ("/", "/profile", "/logout"):
            return None
        if request.path.startswith("/auth/passkey/") or request.path.startswith("/action/passkey/") or request.path == "/auth/check-passkey-required":
            return None
        return redirect("/profile")

    if not session.get("cert_setup_required"):
        return None

    if not session.get("user"):
        session.pop("cert_setup_required", None)
        return None

    if request.path.startswith("/static"):
        return None

    if request.path in ("/", "/certificado/setup", "/logout"):
        return None

    if request.path.startswith("/auth/passkey/") or request.path.startswith("/action/passkey/"):
        return None

    return redirect("/certificado/setup")


def role_home(role):
    if role == "admin":
        return "/admin"
    return "/dashboard"


@app.route("/certificado/setup", methods=["GET", "POST"])
def certificado_setup():
    if not require_login():
        return redirect("/")

    role = session.get("role")
    if role not in ("admin", "coordinador"):
        return redirect("/dashboard")

    conn = get_conn()
    active_cert = get_active_certificate(conn, session.get("user"))
    if active_cert:
        session.pop("cert_setup_required", None)
        conn.close()
        return redirect(role_home(role))

    pending_cert = get_pending_certificate(conn, session.get("user"))

    legacy_bundle_mode = bool(
        pending_cert and (pending_cert["custody_mode"] or "server_bundle") == "server_bundle"
    )

    def render_setup_page():
        return render_template("cert_setup.html", legacy_bundle_mode=legacy_bundle_mode)

    if request.method == "POST":
        csr_text = request.form.get("csr_pem", "").strip()
        csr_file = request.files.get("csr_file")
        if csr_file and csr_file.filename:
            csr_file_bytes = csr_file.read()
            if csr_file_bytes:
                csr_text = csr_file_bytes.decode("utf-8", errors="ignore")

        if csr_text:
            try:
                if pending_cert:
                    issued_by = pending_cert["issued_by"] or session.get("user")
                    issuer_fp = pending_cert["issuer_fingerprint"]
                    cert_info = activate_pending_certificate_from_csr(
                        conn,
                        pending_cert["id"],
                        session.get("user"),
                        role,
                        csr_text,
                        issued_by,
                        issuer_fp,
                    )
                else:
                    cert_info = issue_user_certificate_from_csr(
                        conn,
                        session.get("user"),
                        role,
                        csr_text,
                        session.get("user"),
                        None,
                    )
            except ValueError as exc:
                conn.close()
                flash(str(exc))
                return render_setup_page()

            if not cert_info:
                conn.close()
                flash("No fue posible emitir el certificado.")
                return render_setup_page()

            c = conn.cursor()
            c.execute(
                "UPDATE usuarios SET cert_fingerprint=? WHERE username=?",
                (cert_info["public_fp"], session.get("user")),
            )
            conn.commit()

            session.pop("cert_setup_required", None)
            log(session.get("user"), "Configuro su certificado desde CSR")
            flash("Certificado emitido correctamente.")

            c = conn.cursor()
            c.execute(
                "SELECT pem_path FROM certificados WHERE username=? AND status='activo' ORDER BY issued_at DESC, created_at DESC, id DESC LIMIT 1",
                (session.get("user"),),
            )
            issued_row = c.fetchone()
            conn.close()

            if issued_row and issued_row["pem_path"] and os.path.exists(issued_row["pem_path"]):
                return send_file(
                    issued_row["pem_path"],
                    as_attachment=True,
                    download_name=f"{session.get('user')}.crt",
                    mimetype="application/x-pem-file",
                )

            return redirect(role_home(role))

        if pending_cert and (pending_cert["custody_mode"] or "user_key") == "user_key":
            flash("Este certificado pendiente requiere una CSR. Genera la CSR en tu equipo y vuelve a cargarla.")
            conn.close()
            return render_setup_page()

        passphrase = request.form.get("passphrase", "")
        passphrase_confirm = request.form.get("passphrase_confirm", "")

        if not passphrase or len(passphrase) < 10:
            flash("La passphrase debe tener al menos 10 caracteres.")
            conn.close()
            return render_setup_page()

        if passphrase != passphrase_confirm:
            flash("Las passphrases no coinciden.")
            conn.close()
            return render_setup_page()

        if pending_cert:
            issued_by = pending_cert["issued_by"] or session.get("user")
            issuer_fp = pending_cert["issuer_fingerprint"]
            cert_info = activate_pending_certificate(
                conn,
                pending_cert["id"],
                session.get("user"),
                role,
                passphrase,
                issued_by,
                issuer_fp,
            )
        else:
            cert_info = issue_user_certificate(
                conn,
                session.get("user"),
                role,
                passphrase,
                session.get("user"),
                None,
            )

        if not cert_info:
            conn.close()
            flash("No fue posible emitir el certificado.")
            return render_setup_page()

        c = conn.cursor()
        c.execute(
            "UPDATE usuarios SET cert_fingerprint=? WHERE username=?",
            (cert_info["public_fp"], session.get("user")),
        )
        conn.commit()
        conn.close()

        session.pop("cert_setup_required", None)
        log(session.get("user"), "Configuro su certificado")
        flash("Certificado configurado correctamente.")
        return redirect(role_home(role))

    conn.close()
    return render_setup_page()


@app.route("/password/update", methods=["GET", "POST"])
def password_update():
    if not session.get("user"):
        return redirect("/")

    if not session.get("password_change_required"):
        return redirect(role_home(session.get("role")))

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM usuarios WHERE username=? AND activo=1",
            (session.get("user"),),
        )
        user = c.fetchone()

        if not user or not verify_user_password(user, current_password):
            conn.close()
            flash("Contrasena actual incorrecta.")
            return render_template("password_update.html")

        if new_password != confirm_password:
            conn.close()
            flash("La nueva contrasena y su confirmacion no coinciden.")
            return render_template("password_update.html")

        if new_password == current_password:
            conn.close()
            flash("La nueva contrasena debe ser diferente a la actual.")
            return render_template("password_update.html")

        valid, error, warning = validate_new_password_policy(new_password)
        if warning:
            flash(warning)

        if not valid:
            conn.close()
            flash(error)
            return render_template("password_update.html")

        salt = generate_password_salt()
        c.execute(
            """
            UPDATE usuarios
            SET password_hash=?, password_algo='argon2id', password_salt=?,
                password_updated_at=?, must_change_password=0
            WHERE username=?
            """,
            (
                hash_password_argon2id(new_password, salt),
                encode_salt(salt),
                str(datetime.datetime.now()),
                session.get("user"),
            ),
        )
        conn.commit()
        conn.close()

        session.pop("password_change_required", None)
        log(session.get("user"), "Actualizo su contrasena")
        flash("Contrasena actualizada correctamente.")
        return redirect(role_home(session.get("role")))

    return render_template("password_update.html")


def next_status_for_role(role):
    mapping = {
        "usuario": ("borrador", "en_revision_operativa"),
        "operativo": ("en_revision_operativa", "en_revision_coordinacion"),
        "coordinador": ("en_revision_coordinacion", "validado_coordinacion"),
        "admin": ("validado_coordinacion", "cerrado"),
    }
    return mapping.get(role)


def can_delete_user(target_user):
    if session.get("role") != "admin":
        return False
    if target_user["rol"] == "admin" and target_user["is_contingency"] == 1:
        return False
    return True


def render_login_page(error=None):
    consume_signature_challenge("login")
    return render_template(
        "login.html",
        error=error,
        passkey_enabled=PASSKEY_ENABLED and WEBAUTHN_AVAILABLE,
        passkey_rp_id=PASSKEY_RP_ID,
    )


@app.route("/", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "GET":
        return render_login_page()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        identifier = _login_identifier_from_request(username)
        locked, until = _is_locked(identifier)
        if locked:
            lock_minutes = int((until - time.time()) // 60) + 1
            error = f"Cuenta bloqueada por intentos fallidos. Intenta en {lock_minutes} minutos."
            return render_login_page(error)

        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM usuarios WHERE username=? AND activo=1",
            (username,),
        )
        user = c.fetchone()
        conn.close()

        if user and user["password_hash"] and verify_user_password(user, password):
            # successful login: clear failed attempts for identifier
            _clear_failed(identifier)
            if password_is_legacy_or_weak(user, password):
                session["user"] = user["username"]
                session["role"] = user["rol"]
                session["area"] = user["area"]
                session["password_change_required"] = True
                log(user["username"], "Inicio de sesion (cambio de contrasena obligatorio)")
                return redirect("/password/update")

            if user["rol"] in ("admin", "coordinador"):
                conn = get_conn()
                active_passkeys = get_active_passkeys(conn, user["username"])
                if PASSKEY_ENABLED and active_passkeys:
                    conn.close()
                    error = "Este usuario usa passkey. Selecciona 'Entrar con passkey'."
                    return render_login_page(error)

                enrollment_required = bool(user["passkey_enrollment_required"])
                if PASSKEY_ENABLED and (PASSKEY_ENFORCE_CRITICAL or enrollment_required) and not active_passkeys:
                    conn.close()
                    session["user"] = user["username"]
                    session["role"] = user["rol"]
                    session["area"] = user["area"]
                    session["passkey_enrollment_required"] = True
                    flash("Debes registrar una passkey antes de continuar.")
                    log(user["username"], "Inicio de sesion (passkey pendiente)")
                    return redirect("/profile")

                active_cert = get_active_certificate(conn, user["username"])
                if not active_cert:
                    pending_cert = get_pending_certificate(conn, user["username"])
                    conn.close()
                    session["user"] = user["username"]
                    session["role"] = user["rol"]
                    session["area"] = user["area"]
                    session["cert_setup_required"] = True
                    if pending_cert:
                        flash("Debes configurar tu certificado para continuar.")
                    else:
                        flash("No hay certificado activo. Debes configurarlo.")
                    log(user["username"], "Inicio de sesion (certificado pendiente)")
                    return redirect("/certificado/setup")

                if is_cert_expired(active_cert):
                    update_cert_status(conn, active_cert["id"], "expirado")
                    conn.commit()
                    conn.close()
                    error = "Tu certificado ha expirado. Solicita reemision."
                    return render_login_page(error)

                cert_file = request.files.get("cert_file")
                if not cert_file or not cert_file.filename:
                    conn.close()
                    error = "Este usuario requiere certificado digital (.pem)."
                    return render_login_page(error)

                challenge = request.form.get("login_challenge", "").strip()
                challenge_row = session.get(_signature_challenge_key("login"))
                if not challenge or not challenge_row or challenge_row.get("value") != challenge:
                    conn.close()
                    error = "El desafio de firma no es valido o ya expiró."
                    return render_login_page(error)

                consume_signature_challenge("login")

                signature_bytes = decode_signature_value(
                    request.form.get("cert_signature", ""),
                    request.files.get("cert_signature_file"),
                )
                if not signature_bytes:
                    conn.close()
                    error = "Debes proporcionar la firma del desafio."
                    return render_login_page(error)

                ok, message, _public_fp = validate_certificate_for_user(
                    conn,
                    user["username"],
                    cert_file.read(),
                    challenge,
                    signature_bytes,
                    "login",
                )
                if not ok:
                    conn.close()
                    error = message
                    return render_login_page(error)

                conn.commit()
                conn.close()

            session["user"] = user["username"]
            session["role"] = user["rol"]
            session["area"] = user["area"]
            session.pop("cert_setup_required", None)
            session.pop("password_change_required", None)
            log(user["username"], "Inicio de sesion")
            return redirect(role_home(user["rol"]))

        # record failed attempt
        _record_failed(identifier)
        error = "Usuario o contrasena incorrectos"

    return render_login_page(error)


@app.route("/auth/passkey/register/options", methods=["POST"])
def passkey_register_options():
    if not require_login():
        return jsonify({"ok": False, "message": "Sesion no valida."}), 401

    if session.get("role") not in ("admin", "coordinador"):
        return jsonify({"ok": False, "message": "Solo roles criticos pueden registrar passkeys."}), 403

    if not PASSKEY_ENABLED:
        return jsonify({"ok": False, "message": "Passkeys deshabilitadas por configuracion."}), 503

    if not WEBAUTHN_AVAILABLE:
        return jsonify({"ok": False, "message": "Dependencia WebAuthn no disponible en el servidor."}), 503

    conn = get_conn()
    active_passkeys = get_active_passkeys(conn, session.get("user"))
    if len(active_passkeys) >= PASSKEY_MAX_CREDENTIALS_PER_USER:
        conn.close()
        return jsonify({
            "ok": False,
            "message": f"Limite alcanzado: maximo {PASSKEY_MAX_CREDENTIALS_PER_USER} passkeys activas.",
        }), 400

    exclude_credentials = [
        PublicKeyCredentialDescriptor(id=b64url_decode(row["credential_id"]))
        for row in active_passkeys
    ]
    conn.close()

    options = generate_registration_options(
        rp_id=PASSKEY_RP_ID,
        rp_name=PASSKEY_RP_NAME,
        user_id=session.get("user").encode("utf-8"),
        user_name=session.get("user"),
        user_display_name=session.get("user"),
        timeout=PASSKEY_TIMEOUT_MS,
        attestation=AttestationConveyancePreference.NONE,
        authenticator_selection=AuthenticatorSelectionCriteria(
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
        exclude_credentials=exclude_credentials,
    )
    options_json = json.loads(options_to_json(options))

    session["pending_passkey_registration"] = {
        "username": session.get("user"),
        "challenge": options_json["challenge"],
        "issued_at": time.time(),
    }

    return jsonify({"ok": True, "publicKey": options_json})


@app.route("/auth/passkey/register/verify", methods=["POST"])
def passkey_register_verify():
    if not require_login():
        return jsonify({"ok": False, "message": "Sesion no valida."}), 401

    if session.get("role") not in ("admin", "coordinador"):
        return jsonify({"ok": False, "message": "Solo roles criticos pueden registrar passkeys."}), 403

    if not PASSKEY_ENABLED:
        return jsonify({"ok": False, "message": "Passkeys deshabilitadas por configuracion."}), 503

    if not WEBAUTHN_AVAILABLE:
        return jsonify({"ok": False, "message": "Dependencia WebAuthn no disponible en el servidor."}), 503

    pending = session.get("pending_passkey_registration")
    if not pending or pending.get("username") != session.get("user"):
        return jsonify({"ok": False, "message": "No hay un registro de passkey pendiente."}), 400

    if time.time() - pending.get("issued_at", 0) > SIGNATURE_CHALLENGE_TTL_SECONDS:
        session.pop("pending_passkey_registration", None)
        return jsonify({"ok": False, "message": "El desafio de registro expiro."}), 400

    body = request.get_json(silent=True) or {}
    credential_payload = body.get("credential")
    label = (body.get("label") or "").strip() or None
    if not credential_payload:
        return jsonify({"ok": False, "message": "Falta la respuesta de credencial WebAuthn."}), 400

    try:
        # Normalize payload keys and decode base64url fields to bytes for the library
        try:
            cred = dict(credential_payload)
            # rawId -> raw_id (bytes)
            if "rawId" in cred:
                cred["raw_id"] = b64url_decode(cred.pop("rawId"))
            # response fields -> build AuthenticatorAttestationResponse
            resp = cred.get("response") or {}
            client_data = b64url_decode(resp.get("clientDataJSON")) if "clientDataJSON" in resp else None
            att_obj = b64url_decode(resp.get("attestationObject")) if "attestationObject" in resp else None
            transports = resp.get("transports") if isinstance(resp.get("transports"), list) else None
            resp_obj = AuthenticatorAttestationResponse(
                client_data_json=client_data,
                attestation_object=att_obj,
                transports=transports,
            )
            cred["response"] = resp_obj
            credential_obj = RegistrationCredential(**cred)
        except Exception as e:
            traceback.print_exc()
            return jsonify({"ok": False, "message": f"Carga de credential invalida: {e}"}), 400

        verification = verify_registration_response(
            credential=credential_obj,
            expected_challenge=b64url_decode(pending.get("challenge")),
            expected_origin=request.scheme + "://" + request.host,
            expected_rp_id=PASSKEY_RP_ID,
            require_user_verification=True,
        )
    except Exception as e:
        traceback.print_exc()
        return jsonify({"ok": False, "message": f"No se pudo verificar el registro de passkey: {str(e)}"}), 400

    credential_id = b64url_encode(verification.credential_id)
    credential_public_key = b64url_encode(verification.credential_public_key)
    aaguid = str(verification.aaguid) if getattr(verification, "aaguid", None) else None
    transports = None
    response_obj = credential_payload.get("response") or {}
    if isinstance(response_obj.get("transports"), list):
        transports = ",".join(response_obj.get("transports"))

    conn = get_conn()
    save_passkey_credential(
        conn,
        session.get("user"),
        credential_id,
        credential_public_key,
        int(verification.sign_count),
        aaguid=aaguid,
        transports=transports,
        label=label,
    )
    conn.commit()
    conn.close()

    session.pop("pending_passkey_registration", None)
    log(session.get("user"), "Registro una nueva passkey")
    return jsonify({"ok": True, "message": "Passkey registrada correctamente."})


@app.route("/auth/check-passkey-required", methods=["POST"])
def check_passkey_required():
    """
    Valida credenciales de usuario y retorna si requiere passkey.
    Útil para password managers que necesitan saber si continuar con passkey automáticamente.
    """
    if not PASSKEY_ENABLED:
        return jsonify({"ok": True, "requires_passkey": False, "message": "Passkeys deshabilitadas"}), 200

    if not WEBAUTHN_AVAILABLE:
        return jsonify({"ok": True, "requires_passkey": False, "message": "WebAuthn no disponible"}), 200

    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""

    if not username or not password:
        return jsonify({"ok": False, "message": "Usuario y contraseña son obligatorios."}), 400

    identifier = _login_identifier_from_request(username)
    locked, until = _is_locked(identifier)
    if locked:
        lock_minutes = int((until - time.time()) // 60) + 1
        return jsonify({
            "ok": False,
            "message": f"Cuenta bloqueada por intentos fallidos. Intenta en {lock_minutes} minutos.",
        }), 429

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM usuarios WHERE username=? AND activo=1", (username,))
    user = c.fetchone()
    
    if not user or not user["password_hash"] or not verify_user_password(user, password):
        conn.close()
        _record_failed(identifier)
        return jsonify({"ok": False, "message": "Usuario o contraseña incorrectos."}), 401

    # Check if password is legacy or weak - if so, don't allow passkey flow
    if password_is_legacy_or_weak(user, password):
        conn.close()
        return jsonify({
            "ok": True,
            "requires_passkey": False,
            "message": "Debe cambiar contraseña antes de continuar",
            "redirect": "/password/update"
        }), 200

    # Check if user is admin/coordinador and has active passkeys
    requires_passkey = False
    if user["rol"] in ("admin", "coordinador"):
        active_passkeys = get_active_passkeys(conn, user["username"])
        if active_passkeys:
            requires_passkey = True

    conn.close()

    return jsonify({
        "ok": True,
        "requires_passkey": requires_passkey,
        "username": user["username"],
        "role": user["rol"],
    }), 200


@app.route("/auth/passkey/login/options", methods=["POST"])
def passkey_login_options():
    if not PASSKEY_ENABLED:
        return jsonify({"ok": False, "message": "Passkeys deshabilitadas por configuracion."}), 503

    if not WEBAUTHN_AVAILABLE:
        return jsonify({"ok": False, "message": "Dependencia WebAuthn no disponible en el servidor."}), 503

    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""

    if not username or not password:
        return jsonify({"ok": False, "message": "Usuario y contrasena son obligatorios."}), 400

    identifier = _login_identifier_from_request(username)
    locked, until = _is_locked(identifier)
    if locked:
        lock_minutes = int((until - time.time()) // 60) + 1
        return jsonify({
            "ok": False,
            "message": f"Cuenta bloqueada por intentos fallidos. Intenta en {lock_minutes} minutos.",
        }), 429

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM usuarios WHERE username=? AND activo=1", (username,))
    user = c.fetchone()
    if not user or not user["password_hash"] or not verify_user_password(user, password):
        conn.close()
        _record_failed(identifier)
        return jsonify({"ok": False, "message": "Usuario o contrasena incorrectos."}), 401

    if password_is_legacy_or_weak(user, password):
        conn.close()
        _clear_failed(identifier)
        session["user"] = user["username"]
        session["role"] = user["rol"]
        session["area"] = user["area"]
        session["password_change_required"] = True
        log(user["username"], "Inicio de sesion (cambio de contrasena obligatorio)")
        return jsonify({"ok": False, "message": "Debes cambiar la contrasena antes de usar passkey.", "redirect": "/password/update"}), 403

    if user["rol"] not in ("admin", "coordinador"):
        conn.close()
        return jsonify({"ok": False, "message": "Este usuario no requiere passkey para autenticarse."}), 400

    active_passkeys = get_active_passkeys(conn, username)
    if not active_passkeys:
        conn.close()
        return jsonify({"ok": False, "message": "No hay passkeys activas para este usuario."}), 400

    allow_credentials = [
        PublicKeyCredentialDescriptor(id=b64url_decode(row["credential_id"]))
        for row in active_passkeys
    ]
    conn.close()

    options = generate_authentication_options(
        rp_id=PASSKEY_RP_ID,
        timeout=PASSKEY_TIMEOUT_MS,
        user_verification=UserVerificationRequirement.REQUIRED,
        allow_credentials=allow_credentials,
    )
    options_json = json.loads(options_to_json(options))

    session["pending_passkey_login"] = {
        "username": user["username"],
        "role": user["rol"],
        "area": user["area"],
        "identifier": identifier,
        "challenge": options_json["challenge"],
        "issued_at": time.time(),
    }

    return jsonify({"ok": True, "publicKey": options_json})


@app.route("/auth/passkey/login/verify", methods=["POST"])
def passkey_login_verify():
    if not PASSKEY_ENABLED:
        return jsonify({"ok": False, "message": "Passkeys deshabilitadas por configuracion."}), 503

    if not WEBAUTHN_AVAILABLE:
        return jsonify({"ok": False, "message": "Dependencia WebAuthn no disponible en el servidor."}), 503

    pending = session.get("pending_passkey_login")
    if not pending:
        return jsonify({"ok": False, "message": "No hay autenticacion passkey pendiente."}), 400

    if time.time() - pending.get("issued_at", 0) > SIGNATURE_CHALLENGE_TTL_SECONDS:
        session.pop("pending_passkey_login", None)
        return jsonify({"ok": False, "message": "El desafio de passkey expiro."}), 400

    body = request.get_json(silent=True) or {}
    credential_payload = body.get("credential")
    if not credential_payload:
        return jsonify({"ok": False, "message": "Falta la assertion WebAuthn."}), 400

    credential_id = credential_payload.get("id") or credential_payload.get("rawId")
    if not credential_id:
        return jsonify({"ok": False, "message": "Credential ID invalido."}), 400

    conn = get_conn()
    passkey_row = get_active_passkey_by_credential(conn, pending.get("username"), credential_id)
    if not passkey_row:
        conn.close()
        _record_failed(pending.get("identifier"))
        session.pop("pending_passkey_login", None)
        return jsonify({"ok": False, "message": "Passkey no encontrada o revocada."}), 401

    try:
        # Normalize authentication payload and decode base64url fields
        try:
            cred = dict(credential_payload)
            if "rawId" in cred:
                cred["raw_id"] = b64url_decode(cred.pop("rawId"))
            resp = cred.get("response") or {}
            client_data = b64url_decode(resp.get("clientDataJSON")) if "clientDataJSON" in resp else None
            auth_data = b64url_decode(resp.get("authenticatorData")) if "authenticatorData" in resp else None
            signature = b64url_decode(resp.get("signature")) if "signature" in resp else None
            user_handle = b64url_decode(resp.get("userHandle")) if "userHandle" in resp else None
            resp_obj = AuthenticatorAssertionResponse(
                client_data_json=client_data,
                authenticator_data=auth_data,
                signature=signature,
                user_handle=user_handle,
            )
            cred["response"] = resp_obj
            auth_cred = AuthenticationCredential(**cred)
        except Exception as e:
            conn.close()
            _record_failed(pending.get("identifier"))
            session.pop("pending_passkey_login", None)
            traceback.print_exc()
            return jsonify({"ok": False, "message": f"Carga de assertion invalida: {e}"}), 400

        verification = verify_authentication_response(
            credential=auth_cred,
            expected_challenge=b64url_decode(pending.get("challenge")),
            expected_origin=request.scheme + "://" + request.host,
            expected_rp_id=PASSKEY_RP_ID,
            credential_public_key=b64url_decode(passkey_row["public_key_b64"]),
            credential_current_sign_count=int(passkey_row["sign_count"] or 0),
            require_user_verification=True,
        )
    except Exception:
        conn.close()
        _record_failed(pending.get("identifier"))
        session.pop("pending_passkey_login", None)
        return jsonify({"ok": False, "message": "No se pudo validar la assertion passkey."}), 401

    update_passkey_usage(conn, passkey_row["id"], int(verification.new_sign_count))
    conn.commit()
    conn.close()

    _clear_failed(pending.get("identifier"))
    session["user"] = pending.get("username")
    session["role"] = pending.get("role")
    session["area"] = pending.get("area")
    session.pop("cert_setup_required", None)
    session.pop("password_change_required", None)
    session.pop("pending_passkey_login", None)
    log(session.get("user"), "Inicio de sesion con passkey")

    return jsonify({"ok": True, "redirect": role_home(session.get("role"))})


@app.route("/action/passkey/options", methods=["POST"])
def action_passkey_options():
    """Genera opciones de desafío WebAuthn para firmar una acción sensible."""
    if not PASSKEY_ENABLED:
        return jsonify({"ok": False, "message": "Passkeys deshabilitadas por configuracion."}), 503
    
    if not WEBAUTHN_AVAILABLE:
        return jsonify({"ok": False, "message": "Dependencia WebAuthn no disponible en el servidor."}), 503
    
    if not require_login():
        return jsonify({"ok": False, "message": "No autenticado."}), 401
    
    username = session.get("user")
    role = session.get("role")
    
    if role not in ("admin", "coordinador"):
        return jsonify({"ok": False, "message": "Este usuario no puede firmar acciones sensibles."}), 403
    
    conn = get_conn()
    
    # NUEVO: Verificar que el certificado PKI no haya expirado
    cert_valid, cert_msg = check_certificate_expiration(conn, username)
    if not cert_valid:
        conn.close()
        return jsonify({"ok": False, "message": cert_msg}), 401
    
    active_passkeys = get_active_passkeys(conn, username)
    conn.close()
    
    if not active_passkeys:
        return jsonify({"ok": False, "message": "No hay passkeys activas. Registra una desde tu perfil."}), 400
    
    allow_credentials = [
        PublicKeyCredentialDescriptor(id=b64url_decode(row["credential_id"]))
        for row in active_passkeys
    ]
    
    options = generate_authentication_options(
        rp_id=PASSKEY_RP_ID,
        timeout=PASSKEY_TIMEOUT_MS,
        user_verification=UserVerificationRequirement.REQUIRED,
        allow_credentials=allow_credentials,
    )
    options_json = json.loads(options_to_json(options))
    
    # Guardar en sesión para verificación posterior
    session["pending_action_passkey"] = {
        "username": username,
        "challenge": options_json["challenge"],
        "issued_at": time.time(),
    }
    
    return jsonify({"ok": True, "publicKey": options_json})


@app.route("/action/passkey/verify", methods=["POST"])
def action_passkey_verify():
    """Verifica la firma WebAuthn de una acción sensible."""
    if not PASSKEY_ENABLED:
        return jsonify({"ok": False, "message": "Passkeys deshabilitadas por configuracion."}), 503
    
    if not WEBAUTHN_AVAILABLE:
        return jsonify({"ok": False, "message": "Dependencia WebAuthn no disponible en el servidor."}), 503
    
    if not require_login():
        return jsonify({"ok": False, "message": "No autenticado."}), 401
    
    pending = session.get("pending_action_passkey")
    if not pending:
        return jsonify({"ok": False, "message": "No hay firma de accion pendiente."}), 400
    
    # Verificar que el desafío no haya expirado
    if time.time() - pending.get("issued_at", 0) > SIGNATURE_CHALLENGE_TTL_SECONDS:
        session.pop("pending_action_passkey", None)
        return jsonify({"ok": False, "message": "El desafio de firma expiro."}), 400
    
    body = request.get_json(silent=True) or {}
    credential_payload = body.get("credential")
    if not credential_payload:
        return jsonify({"ok": False, "message": "Falta la assertion WebAuthn."}), 400
    
    credential_id = credential_payload.get("id") or credential_payload.get("rawId")
    if not credential_id:
        return jsonify({"ok": False, "message": "Credential ID invalido."}), 400
    
    username = session.get("user")
    action_label = body.get("action_label", "accion sensible")
    
    conn = get_conn()
    
    # NUEVO: Verificar que el certificado PKI no haya expirado
    cert_valid, cert_msg = check_certificate_expiration(conn, username)
    if not cert_valid:
        conn.close()
        session.pop("pending_action_passkey", None)
        return jsonify({"ok": False, "message": cert_msg}), 401
    
    passkey_row = get_active_passkey_by_credential(conn, username, credential_id)
    if not passkey_row:
        conn.close()
        session.pop("pending_action_passkey", None)
        return jsonify({"ok": False, "message": "Passkey no encontrada o revocada."}), 401
    
    try:
        # Normalizar el payload de autenticación y decodificar campos base64url
        cred = dict(credential_payload)
        if "rawId" in cred:
            cred["raw_id"] = b64url_decode(cred.pop("rawId"))
        resp = cred.get("response") or {}
        client_data = b64url_decode(resp.get("clientDataJSON")) if "clientDataJSON" in resp else None
        auth_data = b64url_decode(resp.get("authenticatorData")) if "authenticatorData" in resp else None
        signature = b64url_decode(resp.get("signature")) if "signature" in resp else None
        user_handle = b64url_decode(resp.get("userHandle")) if "userHandle" in resp else None
        resp_obj = AuthenticatorAssertionResponse(
            client_data_json=client_data,
            authenticator_data=auth_data,
            signature=signature,
            user_handle=user_handle,
        )
        cred["response"] = resp_obj
        auth_cred = AuthenticationCredential(**cred)
    except Exception as e:
        conn.close()
        session.pop("pending_action_passkey", None)
        traceback.print_exc()
        return jsonify({"ok": False, "message": f"Assertion invalida: {e}"}), 400
    
    try:
        verification = verify_authentication_response(
            credential=auth_cred,
            expected_challenge=b64url_decode(pending.get("challenge")),
            expected_origin=request.scheme + "://" + request.host,
            expected_rp_id=PASSKEY_RP_ID,
            credential_public_key=b64url_decode(passkey_row["public_key_b64"]),
            credential_current_sign_count=int(passkey_row["sign_count"] or 0),
            require_user_verification=True,
        )
    except Exception:
        conn.close()
        session.pop("pending_action_passkey", None)
        return jsonify({"ok": False, "message": "No se pudo validar la assertion passkey."}), 401
    
    # Actualizar sign_count del passkey y registrar uso
    update_passkey_usage(conn, passkey_row["id"], int(verification.new_sign_count))
    conn.commit()
    conn.close()
    
    # Limpiar sesión
    session.pop("pending_action_passkey", None)
    
    # Registrar la acción en logs con fingerprint de passkey como prueba de no repudio
    passkey_fp = hashlib.sha256(b64url_decode(passkey_row["credential_id"])).hexdigest()[:16]
    log(username, f"{action_label} (passkey: {passkey_fp})")

    # Registrar la verificación en sesión para su consumo en endpoints subsecuentes
    session["verified_passkey_action"] = {
        "action_label": action_label,
        "timestamp": time.time(),
        "passkey_fp": passkey_fp
    }
    session.modified = True
    
    return jsonify({"ok": True, "message": "Accion firmada exitosamente"})


def check_and_consume_passkey_action(expected_action_label, max_age_seconds=60):
    """Checks if the user has recently signed the given action using a passkey."""
    verified = session.get("verified_passkey_action")
    if not verified:
        # Log para debugging
        print(f"DEBUG: No verified_passkey_action en sesión para usuario {session.get('user')}")
        return False
        
    label_match = (verified.get("action_label") == expected_action_label)
    time_match = (time.time() - verified.get("timestamp", 0) <= max_age_seconds)
    
    # Log para debugging
    if not label_match:
        print(f"DEBUG: Label mismatch - esperado: '{expected_action_label}', actual: '{verified.get('action_label')}'")
    if not time_match:
        print(f"DEBUG: Time expired - age: {time.time() - verified.get('timestamp', 0)}s, max: {max_age_seconds}s")
    
    # Consume marker
    session.pop("verified_passkey_action", None)
    session.modified = True
    
    return label_match and time_match


@app.route("/dashboard")
def dashboard():
    if not require_login():
        return redirect("/")

    role = session.get("role")
    conn = get_conn()
    c = conn.cursor()

    # Bandeja por rol para mostrar pendientes
    if role == "usuario":
        c.execute(
            "SELECT id, estado, created_at FROM encuestas WHERE creado_por=? ORDER BY id DESC",
            (session.get("user"),),
        )
    elif role == "operativo":
        c.execute(
            "SELECT id, estado, created_at FROM encuestas WHERE estado='en_revision_operativa' ORDER BY id DESC"
        )
    elif role == "coordinador":
        c.execute(
            "SELECT id, estado, created_at FROM encuestas WHERE estado='en_revision_coordinacion' ORDER BY id DESC"
        )
    else:
        c.execute(
            "SELECT id, estado, created_at FROM encuestas WHERE estado='validado_coordinacion' ORDER BY id DESC"
        )

    pendientes = c.fetchall()
    conn.close()

    return render_template(
        "dashboard.html",
        role=ROLE_LABELS.get(role, role),
        role_key=role,
        pendientes=pendientes,
        can_create=has_permission("create"),
        can_read=has_permission("read"),
        can_access_bandeja=has_permission("read") or role == "usuario",
        can_update=has_permission("update"),
        can_delete=has_permission("delete"),
    )


@app.route("/survey", methods=["GET", "POST"])
def survey():
    if not require_login() or not has_permission("create"):
        return redirect("/")

    if request.method == "POST":
        data = {
            "fecha_ingreso": str(datetime.datetime.now()),
            "nombre_pila": request.form.get("nombre_pila", "").strip(),
            "primer_apellido": request.form.get("primer_apellido", "").strip(),
            "segundo_apellido": request.form.get("segundo_apellido", "").strip(),
            "pais_origen": request.form.get("pais_origen", "").strip(),
            "fecha_nacimiento": request.form.get("fecha_nacimiento", "").strip(),
            "edad": request.form.get("edad", "").strip(),
            "genero": request.form.get("genero", "").strip(),
            "estado_civil": request.form.get("estado_civil", "").strip(),
            "grupo_poblacion": request.form.get("grupo_poblacion", "").strip(),
            "departamento_estado": request.form.get("departamento_estado", "").strip(),
            "telefono": request.form.get("telefono", "").strip(),
            "fecha_atencion": request.form.get("fecha_atencion", "").strip(),
            "capturado_por": session.get("user"),
            "rol_capturador": session.get("role"),
        }

        encrypted = encrypt_data(data, user=session.get("user"), action_detail="Registro de nuevo expediente")
        encrypted_at = str(datetime.datetime.now())

        conn = get_conn()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO encuestas (
                datos,
                encryption_key_fingerprint,
                encrypted_at,
                estado,
                creado_por,
                nivel_actual,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                encrypted,
                DATA_ENCRYPTION_KEY_FINGERPRINT,
                encrypted_at,
                "borrador" if session.get("role") == "usuario" else "en_revision_operativa",
                session.get("user"),
                "usuario" if session.get("role") == "usuario" else "operativo",
                str(datetime.datetime.now()),
                str(datetime.datetime.now()),
            ),
        )
        conn.commit()
        new_id = c.lastrowid
        conn.close()

        log(session.get("user"), f"Creo expediente {new_id}")
        flash("Registro creado. Puedes canalizarlo desde tu bandeja.")
        return redirect("/dashboard")

    return render_template("survey.html")


@app.route("/admin")
def admin():
    if not require_role("admin", "coordinador"):
        return redirect("/")

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id, datos, estado, creado_por, created_at FROM encuestas ORDER BY id DESC"
    )
    rows = c.fetchall()

    expedientes = []
    for row in rows:
        d = decrypt_data(row["datos"], user=session.get("user"), action_detail=f"Lectura de expediente #{row['id']} en panel admin")
        if not d:
            continue
        d["id"] = row["id"]
        d["estado"] = row["estado"]
        d["creado_por"] = row["creado_por"]
        d["created_at"] = row["created_at"]
        expedientes.append(d)

    c.execute(
        "SELECT * FROM solicitudes_eliminacion WHERE estado='pendiente' ORDER BY id DESC"
    )
    solicitudes = c.fetchall()

    # Solicitudes ARCO prioritarias (reenviadas por coordinadores)
    c.execute(
        """SELECT * FROM solicitudes_arco 
           WHERE nivel_actual='admin' AND reenviado_por_coordinador=1
             AND estado != 'atendida' AND estado != 'rechazada'
           ORDER BY reenviado_por_coordinador_at DESC"""
    )
    solicitudes_arco_prioritarias = c.fetchall()

    # Solicitudes ARCO directas (flujo antiguo, sin pasar por aprobadores)
    c.execute(
        """SELECT * FROM solicitudes_arco 
           WHERE (nivel_actual IN ('usuarios', 'operativos', 'coordinadores', 'resuelto')
                  OR (nivel_actual='admin' AND reenviado_por_coordinador=0))
           AND estado != 'atendida' AND estado != 'rechazada'
           ORDER BY created_at DESC"""
    )
    solicitudes_arco_directas = c.fetchall()

    conn.close()

    return render_template(
        "admin.html",
        expedientes=expedientes,
        solicitudes=solicitudes,
        solicitudes_arco_prioritarias=solicitudes_arco_prioritarias,
        solicitudes_arco_directas=solicitudes_arco_directas,
    )

@app.route("/bandeja")
def bandeja():
    role = session.get("role")
    can_access_bandeja = role == "usuario" or has_permission("read")

    if not require_login() or not can_access_bandeja:
        return redirect("/")

    conn = get_conn()
    c = conn.cursor()

    if role == "operativo":
        c.execute(
            "SELECT id, datos, estado, creado_por, updated_at FROM encuestas WHERE estado='en_revision_operativa' ORDER BY id DESC"
        )
    elif role == "coordinador":
        c.execute(
            "SELECT id, datos, estado, creado_por, updated_at FROM encuestas WHERE estado='en_revision_coordinacion' ORDER BY id DESC"
        )
    elif role == "admin":
        c.execute(
            "SELECT id, datos, estado, creado_por, updated_at FROM encuestas WHERE estado='validado_coordinacion' ORDER BY id DESC"
        )
    else:
        c.execute(
            "SELECT id, datos, estado, creado_por, updated_at FROM encuestas WHERE creado_por=? ORDER BY id DESC",
            (session.get("user"),),
        )

    rows = c.fetchall()
    
    # Cargar solicitudes ARCO según el nivel del usuario
    solicitudes_arco = []
    if role in ("usuario", "operativo", "coordinador"):
        nivel_map = {
            "usuario": "usuarios",
            "operativo": "operativos", 
            "coordinador": "coordinadores"
        }
        nivel = nivel_map.get(role)
        c.execute(
            "SELECT * FROM solicitudes_arco WHERE nivel_actual=? ORDER BY created_at DESC",
            (nivel,)
        )
        solicitudes_arco = c.fetchall()
    
    conn.close()

    expedientes = []
    for row in rows:
        d = decrypt_data(row["datos"], user=session.get("user"), action_detail=f"Lectura de expediente #{row['id']} en bandeja")
        if not d:
            continue
        d["id"] = row["id"]
        d["estado"] = row["estado"]
        d["creado_por"] = row["creado_por"]
        d["updated_at"] = row["updated_at"]
        expedientes.append(d)

    # Asegurar que el CSRF token existe en la sesión
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    
    return render_template(
        "colaborador.html",
        datos=expedientes,
        role=session.get("role"),
        solicitudes_arco=solicitudes_arco,
        action_signature_challenge=session.get("action_signature_challenge", ""),
        csrf_token=session.get("csrf_token")
    )


@app.route("/encuesta/<int:encuesta_id>/avanzar", methods=["POST"])
def avanzar_encuesta(encuesta_id):
    if not require_login():
        return redirect("/")

    role = session.get("role")
    if role != "usuario" and not has_permission("read"):
        return redirect("/")

    transition = next_status_for_role(role)
    if not transition:
        flash("Tu rol no puede avanzar expedientes.")
        return redirect("/bandeja")

    expected_status, new_status = transition

    # Validación de passkey para roles administrativos (coordinador, admin)
    if role in ("coordinador", "admin"):
        action_label = f"expediente #{encuesta_id}"
        if not check_and_consume_passkey_action(action_label):
            flash("Se requiere firma mediante passkey para esta acción.")
            return redirect("/bandeja")

    conn = get_conn()
    c = conn.cursor()

    if role == "usuario":
        c.execute(
            "SELECT id, estado, creado_por FROM encuestas WHERE id=?",
            (encuesta_id,),
        )
        row = c.fetchone()
        if not row or row["creado_por"] != session.get("user"):
            conn.close()
            flash("No puedes canalizar este expediente.")
            return redirect("/bandeja")
    else:
        c.execute("SELECT id, estado FROM encuestas WHERE id=?", (encuesta_id,))
        row = c.fetchone()

    if not row or row["estado"] != expected_status:
        conn.close()
        flash("El expediente no esta en el estado esperado.")
        return redirect("/bandeja")

    c.execute(
        "UPDATE encuestas SET estado=?, updated_at=? WHERE id=?",
        (new_status, str(datetime.datetime.now()), encuesta_id),
    )
    conn.commit()
    conn.close()

    log(session.get("user"), f"Cambio expediente {encuesta_id} a estado {new_status}")
    flash("Expediente actualizado correctamente.")
    return redirect("/bandeja")


@app.route("/solicitar-eliminacion/<int:encuesta_id>", methods=["POST"])
def solicitar_eliminacion(encuesta_id):
    if not require_role("coordinador"):
        return redirect("/")

    # Validación de passkey para coordinador
    action_label = f"expediente #{encuesta_id}"
    if not check_and_consume_passkey_action(action_label):
        flash("Se requiere firma mediante passkey para esta acción.")
        return redirect("/bandeja")

    motivo = request.form.get("motivo", "").strip()
    if not motivo:
        flash("Debes escribir un motivo para solicitar eliminacion.")
        return redirect("/bandeja")

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO solicitudes_eliminacion (encuesta_id, solicitante, motivo, estado, fecha_solicitud)
        VALUES (?, ?, ?, 'pendiente', ?)
        """,
        (encuesta_id, session.get("user"), motivo, str(datetime.datetime.now())),
    )
    conn.commit()
    conn.close()

    log(session.get("user"), f"Solicito eliminacion de expediente {encuesta_id}")
    flash("Solicitud de eliminacion enviada al administrador.")
    return redirect("/bandeja")


@app.route("/solicitud/<int:solicitud_id>/resolver", methods=["POST"])
def resolver_solicitud(solicitud_id):
    if not require_role("admin", "coordinador"):
        return redirect("/")

    decision = request.form.get("decision")
    if decision not in ("aprobar", "rechazar"):
        return redirect("/admin")

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM solicitudes_eliminacion WHERE id=? AND estado='pendiente'",
        (solicitud_id,),
    )
    solicitud = c.fetchone()
    if not solicitud:
        conn.close()
        flash("Solicitud no encontrada o ya atendida.")
        return redirect("/admin")

    action_log = None
    if decision == "aprobar":
        c.execute("DELETE FROM encuestas WHERE id=?", (solicitud["encuesta_id"],))
        new_status = "aprobada"
        action_log = f"Elimino expediente {solicitud['encuesta_id']} por solicitud"
    else:
        new_status = "rechazada"

    c.execute(
        """
        UPDATE solicitudes_eliminacion
        SET estado=?, atendido_por=?, fecha_resolucion=?
        WHERE id=?
        """,
        (new_status, session.get("user"), str(datetime.datetime.now()), solicitud_id),
    )

    conn.commit()
    conn.close()

    if action_log:
        log(session.get("user"), action_log)
    log(session.get("user"), f"Resolvio solicitud {solicitud_id} como {new_status}")
    flash("Solicitud resuelta.")
    return redirect("/admin")


@app.route("/usuarios", methods=["GET", "POST"])
def usuarios():
    if not require_role("admin", "coordinador"):
        return redirect("/")

    conn = get_conn()
    c = conn.cursor()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        rol = request.form.get("rol", "usuario")
        area = request.form.get("area")
        is_contingency = 1 if request.form.get("is_contingency") == "1" else 0

        if rol not in ROLE_LABELS:
            flash("Rol invalido")
            conn.close()
            return redirect("/usuarios")

        if rol != "coordinador":
            area = None

        # Verificar firma de passkey para crear usuarios admin/coordinador
        if rol in ("admin", "coordinador"):
            if not check_and_consume_passkey_action("creacion de usuario"):
                flash("Se requiere firma de passkey para crear usuarios administrativos")
                conn.close()
                return redirect("/usuarios")

        try:
            salt = generate_password_salt()
            c.execute(
                """
                INSERT INTO usuarios (
                    username, password_hash, rol, area, cert_fingerprint, is_contingency, activo,
                    must_change_password, password_updated_at, password_algo, password_salt
                )
                VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?, 'argon2id', ?)
                """,
                (
                    username,
                    hash_password_argon2id(password, salt),
                    rol,
                    area,
                    None,
                    is_contingency,
                    str(datetime.datetime.now()),
                    encode_salt(salt),
                ),
            )
            conn.commit()

            if rol in ("admin", "coordinador"):
                create_pending_certificate(
                    conn,
                    username,
                    rol,
                    session.get("user"),
                    None,
                )
                conn.commit()

            log(session.get("user"), f"Creo usuario {username} con rol {rol}")
            if rol in ("admin", "coordinador"):
                flash("Usuario creado. Debe configurar su certificado.")
            else:
                flash("Usuario creado")
        except sqlite3.IntegrityError:
            flash("El usuario ya existe")

        conn.close()
        return redirect("/usuarios")

    c.execute("SELECT * FROM usuarios ORDER BY rol, username")
    lista_usuarios = c.fetchall()

    c.execute("SELECT * FROM certificados ORDER BY issued_at DESC, created_at DESC")
    cert_rows = c.fetchall()
    certificados = []
    now = datetime.datetime.now()
    for row in cert_rows:
        exp_dt = parse_datetime(row["expires_at"])
        status = row["status"]
        if exp_dt and exp_dt < now:
            status = "expirado"
        cert = dict(row)
        cert["status"] = status
        cert["hash_short"] = (row["pem_hash"] or "-")[:12]
        cert["public_short"] = (row["public_fp"] or "-")[:12]
        cert["issuer_short"] = (row["issuer_fingerprint"] or "-")[:12]
        certificados.append(cert)

    c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 100")
    lista_logs = c.fetchall()

    conn.close()

    return render_template(
        "usuarios.html",
        lista_usuarios=lista_usuarios,
        lista_logs=lista_logs,
        certificados=certificados,
        role_labels=ROLE_LABELS,
        coordinator_areas=COORDINATOR_AREAS,
    )


@app.route("/admin/identidades")
def admin_identidades():
    if not require_role("admin", "coordinador"):
        return redirect("/")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM usuarios ORDER BY rol, username")
    lista_usuarios = c.fetchall()
    c.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 100")
    lista_logs = c.fetchall()
    conn.close()

    return render_template(
        "admin_identidades.html",
        lista_usuarios=lista_usuarios,
        lista_logs=lista_logs,
        role_labels=ROLE_LABELS,
    )


@app.route("/admin/pki")
def admin_pki():
    if not require_role("admin", "coordinador"):
        return redirect("/")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM certificados ORDER BY issued_at DESC, created_at DESC")
    cert_rows = c.fetchall()
    conn.close()

    certificados = []
    now = datetime.datetime.now()
    resumen = {
        "activo": 0,
        "pendiente": 0,
        "expirado": 0,
        "revocado": 0,
    }
    for row in cert_rows:
        exp_dt = parse_datetime(row["expires_at"])
        status = row["status"]
        if exp_dt and exp_dt < now and status != "revocado":
            status = "expirado"
        cert = dict(row)
        cert["status"] = status or "pendiente"
        cert["hash_short"] = (row["pem_hash"] or "-")[:12]
        cert["public_short"] = (row["public_fp"] or "-")[:12]
        cert["issuer_short"] = (row["issuer_fingerprint"] or "-")[:12]
        certificados.append(cert)
        if cert["status"] in resumen:
            resumen[cert["status"]] += 1

    return render_template(
        "admin_pki.html",
        certificados=certificados,
        resumen=resumen,
    )


@app.route("/admin/pki/passkey-certificate-status")
def admin_pki_passkey_status():
    """
    Endpoint JSON: Retorna mapeo completo certificado ↔ passkeys
    Estructura: [{cert_id, username, rol, status, num_passkeys_active, passkeys: [...]}]
    """
    if not require_role("admin", "coordinador"):
        return jsonify({"ok": False, "message": "No autorizado"}), 403
    
    try:
        conn = get_conn()
        c = conn.cursor()
        
        # Obtener todos los certificados PKI
        c.execute(
            """
            SELECT id, username, rol, status, passkey_source, num_passkeys_using, issued_at, expires_at
            FROM certificados 
            WHERE passkey_source=1
            ORDER BY issued_at DESC
            """
        )
        cert_rows = c.fetchall()
        
        certificados = []
        now = datetime.datetime.now()
        
        for cert_row in cert_rows:
            cert_id = cert_row['id']
            username = cert_row['username']
            
            # Obtener passkeys de este certificado
            c.execute(
                """
                SELECT id, credential_id, label, status, created_at
                FROM passkey_credentials
                WHERE user_cert_id=?
                ORDER BY created_at DESC
                """,
                (cert_id,)
            )
            passkey_rows = c.fetchall()
            
            passkeys = [
                {
                    'id': pk['id'],
                    'credential_id': pk['credential_id'][:16] + '...' if len(pk['credential_id']) > 16 else pk['credential_id'],
                    'label': pk['label'] or '(sin etiqueta)',
                    'status': pk['status'],
                    'created_at': pk['created_at'],
                }
                for pk in passkey_rows
            ]
            
            # Contar passkeys activos
            num_active = sum(1 for pk in passkeys if pk['status'] == 'activo')
            
            # Determinar status del certificado
            cert_status = cert_row['status']
            expires_at = parse_datetime(cert_row['expires_at'])
            if expires_at and expires_at < now and cert_status != 'revocado':
                cert_status = 'expirado'
            
            certificados.append({
                'cert_id': cert_id,
                'username': username,
                'rol': cert_row['rol'],
                'status': cert_status,
                'num_passkeys_total': len(passkeys),
                'num_passkeys_active': num_active,
                'issued_at': cert_row['issued_at'],
                'expires_at': cert_row['expires_at'],
                'passkeys': passkeys,
            })
        
        conn.close()
        
        return jsonify({
            'ok': True,
            'certificados': certificados,
        })
        
    except Exception as e:
        print(f"Error fetching passkey-certificate status: {e}")
        traceback.print_exc()
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route("/admin/pki/revoke-passkey", methods=["POST"])
def admin_revoke_passkey():
    """
    Endpoint: Revoca un passkey individual
    Body: {passkey_id, reason}
    """
    if not require_role("admin", "coordinador"):
        return jsonify({"ok": False, "message": "No autorizado"}), 403
    
    try:
        body = request.get_json(silent=True) or {}
        passkey_id = body.get('passkey_id')
        reason = body.get('reason', 'admin_revocation')
        
        if not passkey_id:
            return jsonify({"ok": False, "message": "passkey_id requerido"}), 400
        
        conn = get_conn()
        c = conn.cursor()
        
        # Obtener datos del passkey
        c.execute(
            "SELECT username FROM passkey_credentials WHERE id=?",
            (passkey_id,)
        )
        pk_row = c.fetchone()
        if not pk_row:
            conn.close()
            return jsonify({"ok": False, "message": "Passkey no encontrado"}), 404
        
        username = pk_row['username']
        
        # Revocar passkey y cert si aplica
        success, affected_certs = revoke_passkey_and_cert(
            conn, passkey_id, username, reason=reason
        )
        
        conn.close()
        
        if not success:
            return jsonify({"ok": False, "message": "Error revocando passkey"}), 500
        
        # Log la acción
        log(
            session.get('user'),
            f"Revocó passkey {passkey_id} de usuario {username}: {reason}",
            categoria="seguridad",
            detalle=f"Certificados afectados: {affected_certs}"
        )
        
        return jsonify({
            'ok': True,
            'passkey_id': passkey_id,
            'affected_certs': affected_certs,
            'message': f'Passkey revocado. {len(affected_certs)} certificado(s) también revocado(s).'
        })
        
    except Exception as e:
        print(f"Error revoking passkey: {e}")
        traceback.print_exc()
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route("/admin/pki/revoke-certificate", methods=["POST"])
def admin_revoke_certificate():
    """
    Endpoint: Revoca un certificado y todos sus passkeys
    Body: {cert_id, reason}
    """
    if not require_role("admin", "coordinador"):
        return jsonify({"ok": False, "message": "No autorizado"}), 403
    
    try:
        body = request.get_json(silent=True) or {}
        cert_id = body.get('cert_id')
        reason = body.get('reason', 'admin_revocation')
        
        if not cert_id:
            return jsonify({"ok": False, "message": "cert_id requerido"}), 400
        
        conn = get_conn()
        
        # Obtener info del certificado
        c = conn.cursor()
        c.execute("SELECT username FROM certificados WHERE id=?", (cert_id,))
        cert_row = c.fetchone()
        if not cert_row:
            conn.close()
            return jsonify({"ok": False, "message": "Certificado no encontrado"}), 404
        
        username = cert_row['username']
        
        # Revocar certificado y todos sus passkeys
        success, revoked_count = revoke_certificate_and_passkeys(
            conn, cert_id, reason=reason
        )
        
        conn.close()
        
        if not success:
            return jsonify({"ok": False, "message": "Error revocando certificado"}), 500
        
        # Log la acción
        log(
            session.get('user'),
            f"Revocó certificado {cert_id} de usuario {username}: {reason}. {revoked_count} passkeys revocados.",
            categoria="seguridad"
        )
        
        return jsonify({
            'ok': True,
            'cert_id': cert_id,
            'revoked_passkeys_count': revoked_count,
            'message': f'Certificado revocado. {revoked_count} passkey(s) también revocado(s).'
        })
        
    except Exception as e:
        print(f"Error revoking certificate: {e}")
        traceback.print_exc()
        return jsonify({'ok': False, 'message': str(e)}), 500


@app.route("/admin/cifrado", methods=["GET", "POST"])
def admin_cifrado():
    if not require_role("admin", "coordinador"):
        return redirect("/")

    if request.method == "POST":
        if not validate_csrf():
            return jsonify({"ok": False, "message": "CSRF token missing or invalid"}), 400

        # Passkey signature check
        if not check_and_consume_passkey_action("re-cifrar expedientes de la base de datos"):
            return jsonify({"ok": False, "message": "Falta la firma de passkey para esta accion sensible o ya ha expirado"}), 400

        action = request.form.get("action")
        if action != "reencrypt":
            return jsonify({"ok": False, "message": "Accion no reconocida."}), 400

        result = reencrypt_all_surveys()
        log(
            session.get("user"),
            f"Re-cifro expedientes: {result['updated']} actualizados, {result['skipped']} omitidos",
            categoria="seguridad",
            detalle=json.dumps(result, ensure_ascii=False),
        )
        return jsonify({"ok": True, **result})

    return render_template(
        "admin_cifrado.html",
        encryption_inventory=get_encryption_inventory(),
    )


@app.route('/admin/cifrado/jobs')
def admin_cifrado_jobs():
    if not require_role('admin', 'coordinador'):
        return jsonify({'ok': False, 'message': 'unauthorized'}), 403

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id,new_key_fingerprint,requested_by,status,created_at,started_at,finished_at,processed_count,total_count,notes FROM reencrypt_jobs ORDER BY id DESC"
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    # shorten fingerprints for display
    for r in rows:
        r['new_key_fingerprint_short'] = (r.get('new_key_fingerprint') or '')[:12]
    return jsonify({'ok': True, 'jobs': rows})


@app.route("/eliminar-usuario/<int:user_id>", methods=["POST"])
def eliminar_usuario(user_id):
    if not require_role("admin"):
        return redirect("/")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM usuarios WHERE id=?", (user_id,))
    target = c.fetchone()

    if not target:
        conn.close()
        flash("Usuario no encontrado")
        return redirect("/usuarios")

    if target["username"] == session.get("user"):
        conn.close()
        flash("No puedes eliminar tu propia cuenta en sesion")
        return redirect("/usuarios")

    if not can_delete_user(target):
        conn.close()
        flash("No puedes eliminar esta cuenta")
        return redirect("/usuarios")

    c.execute("DELETE FROM usuarios WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

    log(session.get("user"), f"Elimino usuario {target['username']}")
    flash("Usuario eliminado")
    return redirect("/usuarios")


@app.route("/logs")
def logs():
    if not require_role("admin", "coordinador"):
        return redirect("/")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY id DESC")
    data = c.fetchall()
    conn.close()

    # Agrupar logs por fecha
    logs_by_date = {}
    unique_users = set()
    unique_actions_set = set()
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    events_today = 0

    for log in data:
        fecha_str = log['fecha']
        fecha_date = fecha_str[:10]  # YYYY-MM-DD
        hora = fecha_str[11:19]  # HH:MM:SS

        if fecha_date not in logs_by_date:
            logs_by_date[fecha_date] = []
        
        logs_by_date[fecha_date].append({
            'hora': hora,
            'usuario': log['usuario'],
            'accion': log['accion'],
            'fecha_completa': fecha_str
        })

        unique_users.add(log['usuario'])
        unique_actions_set.add(log['accion'])
        
        if fecha_date == today:
            events_today += 1

    # Ordenar fechas descendentes (más recientes primero)
    sorted_dates = sorted(logs_by_date.keys(), reverse=True)

    unique_users_list = sorted(list(unique_users))

    return render_template(
        "logs.html",
        logs_by_date=logs_by_date,
        sorted_dates=sorted_dates,
        total_events=len(data),
        events_today=events_today,
        unique_users_count=len(unique_users),
        unique_users_list=unique_users_list,
        unique_actions=list(sorted(unique_actions_set))
    )


@app.route("/logs/clear", methods=["POST"])
def clear_logs():
    if not require_role("admin"):
        return redirect("/")

    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM logs")
    conn.commit()
    conn.close()

    flash("Bitacora limpiada")
    return redirect("/logs")


@app.route("/certificado/<int:cert_id>/descargar", methods=["POST"])
def descargar_certificado(cert_id):
    if not require_role("admin", "coordinador"):
        return redirect("/")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM certificados WHERE id=?", (cert_id,))
    cert = c.fetchone()
    conn.close()

    if not cert:
        flash("Certificado no encontrado.")
        return redirect("/usuarios")

    if cert["status"] != "activo":
        flash("El certificado no esta activo para exportacion.")
        return redirect("/usuarios")

    if not cert["pem_path"] or not os.path.exists(cert["pem_path"]):
        flash("Archivo PEM cifrado no disponible.")
        return redirect("/usuarios")

    custody_mode = cert["custody_mode"] or "server_bundle"
    filename = f"{cert['username']}.crt" if custody_mode == "user_key" else f"{cert['username']}.pem"
    return send_file(
        cert["pem_path"],
        as_attachment=True,
        download_name=filename,
        mimetype="application/x-pem-file",
    )


@app.route("/certificado/<int:cert_id>/revocar", methods=["POST"])
def revocar_certificado(cert_id):
    if not require_role("admin", "coordinador"):
        return redirect("/")

    motivo = request.form.get("revocation_reason", "").strip()
    if not motivo:
        flash("Debes indicar un motivo para revocar el certificado.")
        return redirect("/usuarios")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM certificados WHERE id=?", (cert_id,))
    cert = c.fetchone()
    if not cert:
        conn.close()
        flash("Certificado no encontrado.")
        return redirect("/usuarios")

    if cert["status"] == "revocado":
        conn.close()
        flash("El certificado ya estaba revocado.")
        return redirect("/usuarios")

    revoke_certificate(conn, cert_id, session.get("user"), motivo)
    conn.commit()
    conn.close()

    log(session.get("user"), f"Revoco certificado de {cert['username']}: {motivo}")
    flash("Certificado revocado correctamente.")
    return redirect("/usuarios")


@app.route("/logout")
def logout():
    log(session.get("user", "desconocido"), "Cerro sesion")
    session.clear()
    return redirect("/")


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if not require_login():
        return redirect("/")

    if session.get("passkey_enrollment_required"):
        session["passkey_enrollment_required"] = True

    conn = get_conn()
    c = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_contact":
            email = request.form.get("email", "").strip() or None
            phone = request.form.get("phone", "").strip() or None
            full_name = request.form.get("full_name", "").strip() or None

            # Validate email and phone (optional fields)
            if email and not validate_email_address(email):
                conn.close()
                flash("Direccion de correo invalida.")
                return redirect("/profile")

            if phone and not validate_phone_number(phone):
                conn.close()
                flash("Numero de telefono invalido. Incluye codigo de pais si aplica.")
                return redirect("/profile")

            # Normalize email and phone before storing
            if email:
                email = email.lower()

            if phone:
                cleaned = phone.strip()
                cleaned_digits = re.sub(r"[\s\-().]", "", cleaned)
                if cleaned_digits.startswith("+"):
                    normalized_phone = "+" + re.sub(r"[^0-9]", "", cleaned_digits[1:])
                else:
                    normalized_phone = re.sub(r"[^0-9]", "", cleaned_digits)
                phone = normalized_phone

            c.execute(
                "UPDATE usuarios SET email=?, phone=?, full_name=? WHERE username=?",
                (email, phone, full_name, session.get("user")),
            )
            conn.commit()
            conn.close()
            log(session.get("user"), "Actualizo datos de perfil")
            flash("Datos de perfil actualizados.")
            return redirect("/profile")

        if action == "change_password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")

            c.execute(
                "SELECT * FROM usuarios WHERE username=? AND activo=1",
                (session.get("user"),),
            )
            user = c.fetchone()

            if not user or not verify_user_password(user, current_password):
                conn.close()
                flash("Contrasena actual incorrecta.")
                return redirect("/profile")

            if new_password != confirm_password:
                conn.close()
                flash("La nueva contrasena y su confirmacion no coinciden.")
                return redirect("/profile")

            if new_password == current_password:
                conn.close()
                flash("La nueva contrasena debe ser diferente a la actual.")
                return redirect("/profile")

            valid, error, warning = validate_new_password_policy(new_password)
            if warning:
                flash(warning)

            if not valid:
                conn.close()
                flash(error)
                return redirect("/profile")

            salt = generate_password_salt()
            c.execute(
                """
                UPDATE usuarios
                SET password_hash=?, password_algo='argon2id', password_salt=?,
                    password_updated_at=?, must_change_password=0
                WHERE username=?
                """,
                (
                    hash_password_argon2id(new_password, salt),
                    encode_salt(salt),
                    str(datetime.datetime.now()),
                    session.get("user"),
                ),
            )
            conn.commit()
            conn.close()

            session.pop("passkey_enrollment_required", None)
            session.pop("password_change_required", None)
            log(session.get("user"), "Actualizo su contrasena (perfil)")
            flash("Contrasena actualizada correctamente.")
            return redirect(role_home(session.get("role")))

        if action == "revoke_passkey":
            passkey_id = request.form.get("passkey_id", "").strip()
            c.execute(
                """
                UPDATE passkey_credentials
                SET status='revocado', revoked_at=?, revoked_by=?, revocation_reason=?, updated_at=?
                WHERE id=? AND username=? AND status='activo'
                """,
                (
                    str(datetime.datetime.now()),
                    session.get("user"),
                    "Revocada por el usuario desde perfil",
                    str(datetime.datetime.now()),
                    passkey_id,
                    session.get("user"),
                ),
            )
            conn.commit()
            conn.close()
            log(session.get("user"), f"Revoco passkey {passkey_id}")
            flash("Passkey revocada correctamente.")
            return redirect("/profile")

    c.execute(
        "SELECT username, rol, area, activo, password_updated_at, email, phone, full_name, passkey_enrollment_required FROM usuarios WHERE username=?",
        (session.get("user"),),
    )
    user = c.fetchone()

    c.execute(
        """
        SELECT id, label, aaguid, transports, sign_count, status, created_at, last_used_at
        FROM passkey_credentials
        WHERE username=?
        ORDER BY created_at DESC, id DESC
        """,
        (session.get("user"),),
    )
    passkeys = c.fetchall()
    conn.close()

    return render_template(
        "profile.html",
        user=user,
        role_label=ROLE_LABELS.get(session.get("role"), session.get("role")),
        passkeys=passkeys,
        passkey_enabled=PASSKEY_ENABLED and WEBAUTHN_AVAILABLE,
        passkey_enrollment_required=bool(session.get("passkey_enrollment_required") or (user and user["passkey_enrollment_required"])),
    )


@app.route("/arco")
def arco():
    # Asegura que el csrf_token exista en sesión (igual que en /login)
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(32)
    return render_template("arco.html")


@app.route("/arco/solicitud", methods=["POST"])
def arco_solicitud():
    # Validar CSRF
    token_form = request.form.get("csrf_token", "")
    if not token_form or token_form != session.get("csrf_token"):
        return {"ok": False, "message": "Token inválido."}, 403

    # Campos requeridos
    nombre_solicitante = request.form.get("nombre_solicitante", "").strip()
    correo             = request.form.get("correo", "").strip()
    curp_id            = request.form.get("curp_id", "").strip()
    accion             = request.form.get("accion", "").strip()
    motivo             = request.form.get("motivo", "").strip()

    if not all([nombre_solicitante, correo, curp_id, accion, motivo]):
        return {"ok": False, "message": "Faltan campos obligatorios."}, 400

    if accion not in ("acceso", "rectificacion", "cancelacion", "oposicion"):
        return {"ok": False, "message": "Acción no válida."}, 400

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO solicitudes_arco (
            nombre_solicitante, correo, telefono, curp_id,
            accion,
            nombre_pila, primer_apellido, segundo_apellido,
            fecha_nacimiento, pais_origen, departamento_estado,
            fecha_atencion, folio_expediente,
            motivo, datos_correctos, info_adicional
        ) VALUES (?,?,?,?, ?,?,?,?,?,?,?,?,?, ?,?,?)
    """, (
        nombre_solicitante,
        correo,
        request.form.get("telefono", "").strip(),
        curp_id,
        accion,
        request.form.get("nombre_pila", "").strip(),
        request.form.get("primer_apellido", "").strip(),
        request.form.get("segundo_apellido", "").strip(),
        request.form.get("fecha_nacimiento", "").strip(),
        request.form.get("pais_origen", "").strip(),
        request.form.get("departamento_estado", "").strip(),
        request.form.get("fecha_atencion", "").strip(),
        request.form.get("folio_expediente", "").strip(),
        motivo,
        request.form.get("datos_correctos", "").strip(),
        request.form.get("info_adicional", "").strip(),
    ))
    conn.commit()
    conn.close()

    return {"ok": True, "message": "Tu solicitud fue registrada. Recibirás respuesta en un plazo máximo de 20 días hábiles."}

@app.route("/arco/<int:solicitud_id>/resolver", methods=["POST"])
def arco_resolver(solicitud_id):
    if not require_role("admin", "coordinador"):
        return redirect("/")

    token_form = request.form.get("csrf_token", "")
    if not token_form or token_form != session.get("csrf_token"):
        abort(403)

    decision = request.form.get("decision")
    if decision not in ("atendida", "rechazada"):
        abort(400)

    conn = get_conn()
    conn.execute(
        "UPDATE solicitudes_arco SET estado=?, atendida_por=?, atendida_at=CURRENT_TIMESTAMP WHERE id=?",
        (decision, session.get("username"), solicitud_id)
    )
    conn.commit()
    conn.close()

    flash(f"Solicitud ARCO #{solicitud_id} marcada como {decision}.")
    return redirect("/admin")


@app.route("/arco/<int:solicitud_id>/aprobar", methods=["POST"])
def arco_aprobar(solicitud_id):
    """
    Endpoint para usuarios, operativos y coordinadores
    para aprobar solicitudes ARCO y avanzarlas al siguiente nivel.
    """
    role = session.get("role")
    
    if not require_login():
        return redirect("/")
    
    # Validar CSRF token
    token_form = request.form.get("csrf_token", "")
    if not token_form or token_form != session.get("csrf_token"):
        flash("Token de seguridad inválido. Intenta nuevamente.")
        return redirect("/bandeja")
    
    # Validar que el rol tiene permisos
    if role not in ("usuario", "operativo", "coordinador"):
        flash("Tu rol no puede aprobar solicitudes ARCO.")
        return redirect("/bandeja")
    
    # Mapeo rol → nivel_actual esperado
    rol_a_nivel = {
        "usuario": "usuarios",
        "operativo": "operativos",
        "coordinador": "coordinadores"
    }
    
    # Mapeo nivel → siguiente nivel
    siguiente_nivel = {
        "usuarios": "operativos",
        "operativos": "coordinadores",
        "coordinadores": "admin"
    }
    
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM solicitudes_arco WHERE id=?",
        (solicitud_id,)
    )
    solicitud = c.fetchone()
    
    if not solicitud:
        conn.close()
        flash("Solicitud ARCO no encontrada.")
        return redirect("/bandeja")
    
    # Validar que la solicitud está en el nivel correcto para este rol
    expected_level = rol_a_nivel.get(role)
    if solicitud["nivel_actual"] != expected_level:
        conn.close()
        flash("Esta solicitud ARCO no está pendiente de tu aprobación.")
        return redirect("/bandeja")
    
    # Aprobar: actualizar columna correspondiente y avanzar al siguiente nivel
    try:
        if role == "usuario":
            c.execute(
                """UPDATE solicitudes_arco 
                   SET aprobado_usuarios=1, aprobado_usuarios_at=CURRENT_TIMESTAMP,
                       aprobado_usuarios_por=?, nivel_actual=?
                   WHERE id=?""",
                (session.get("user"), siguiente_nivel["usuarios"], solicitud_id)
            )
        elif role == "operativo":
            c.execute(
                """UPDATE solicitudes_arco 
                   SET aprobado_operativos=1, aprobado_operativos_at=CURRENT_TIMESTAMP,
                       aprobado_operativos_por=?, nivel_actual=?
                   WHERE id=?""",
                (session.get("user"), siguiente_nivel["operativos"], solicitud_id)
            )
        elif role == "coordinador":
            # Coordinador aprueba pero aún no envía a admin (lo hace en resolver-coordinador)
            c.execute(
                """UPDATE solicitudes_arco 
                   SET aprobado_coordinadores=1, aprobado_coordinadores_at=CURRENT_TIMESTAMP,
                       aprobado_coordinadores_por=?
                   WHERE id=?""",
                (session.get("user"), solicitud_id)
            )
        
        conn.commit()
        log(session.get("user"), f"Aprobó solicitud ARCO #{solicitud_id}")
        flash(f"Solicitud ARCO #{solicitud_id} aprobada correctamente.")
    except Exception as e:
        conn.rollback()
        flash(f"Error al aprobar solicitud: {str(e)}")
    finally:
        conn.close()
    
    return redirect("/bandeja")


@app.route("/arco/<int:solicitud_id>/resolver-coordinador", methods=["POST"])
def arco_resolver_coordinador(solicitud_id):
    """
    Opción especial para coordinadores: marcar como resuelta (sin enviar a admin)
    o enviar a admin como prioritaria.
    """
    if not require_role("coordinador"):
        return redirect("/")
    
    # Validar CSRF token
    token_form = request.form.get("csrf_token", "")
    if not token_form or token_form != session.get("csrf_token"):
        flash("Token de seguridad inválido. Intenta nuevamente.")
        return redirect("/bandeja")
    
    decision = request.form.get("decision", "").strip()
    
    if decision not in ("resuelta", "enviar_admin"):
        flash("Decisión no válida.")
        return redirect("/bandeja")
    
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM solicitudes_arco WHERE id=?",
        (solicitud_id,)
    )
    solicitud = c.fetchone()
    
    if not solicitud:
        conn.close()
        flash("Solicitud ARCO no encontrada.")
        return redirect("/bandeja")
    
    # Validar que está en el nivel coordinadores
    if solicitud["nivel_actual"] != "coordinadores":
        conn.close()
        flash("Esta solicitud ARCO no está pendiente en tu nivel.")
        return redirect("/bandeja")
    
    # Normalize decision names to support old UI labels or slight variants
    decision_aliases = {
        "resuelta": "resuelta",
        "resuelto": "resuelta",
        "enviar_admin": "enviar_admin",
        "reenviar_admin": "enviar_admin",
        "enviar a admin": "enviar_admin",
        "enviar a administrador": "enviar_admin",
    }
    decision = decision_aliases.get(decision, decision)

    try:
        if decision == "resuelta":
            c.execute(
                """UPDATE solicitudes_arco 
                   SET aprobado_coordinadores=1,
                       aprobado_coordinadores_at=CURRENT_TIMESTAMP,
                       aprobado_coordinadores_por=?,
                       resuelto_coordinador=1,
                       resuelto_coordinador_at=CURRENT_TIMESTAMP,
                       nivel_actual='resuelto', estado='atendida'
                   WHERE id=?""",
                (session.get("user"), solicitud_id)
            )
            flash_message = f"Solicitud ARCO #{solicitud_id} marcada como resuelta."
            log_message = f"Marcó ARCO #{solicitud_id} como resuelta (coordinador)"
        elif decision == "enviar_admin":
            c.execute(
                """UPDATE solicitudes_arco 
                   SET aprobado_coordinadores=1,
                       aprobado_coordinadores_at=CURRENT_TIMESTAMP,
                       aprobado_coordinadores_por=?,
                       reenviado_por_coordinador=1,
                       reenviado_por_coordinador_at=CURRENT_TIMESTAMP,
                       nivel_actual='admin'
                   WHERE id=?""",
                (session.get("user"), solicitud_id)
            )
            flash_message = f"Solicitud ARCO #{solicitud_id} reenviada al administrador como prioritaria."
            log_message = f"Reenviró ARCO #{solicitud_id} a admin (coordinador)"
        else:
            conn.close()
            flash("Decisión no válida.")
            return redirect("/bandeja")

        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f"Error al procesar solicitud: {str(e)}")
        conn.close()
        return redirect("/bandeja")
    finally:
        conn.close()

    log(session.get("user"), log_message)
    flash(flash_message)
    
    return redirect("/bandeja")

if __name__ == "__main__":
    init_db()
    create_default_accounts()
    bootstrap_dev_certificates()
    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    
    # Parse command line arguments
    port = int(os.environ.get("PORT", os.environ.get("APP_PORT", "5000")))
    if "--port" in sys.argv:
        port_idx = sys.argv.index("--port")
        if port_idx + 1 < len(sys.argv):
            try:
                port = int(sys.argv[port_idx + 1])
            except ValueError:
                print(f"Invalid port: {sys.argv[port_idx + 1]}")
                sys.exit(1)
    
    def _port_is_available(candidate_port):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return sock.connect_ex(("127.0.0.1", candidate_port)) != 0

    requested_port = port
    while port < requested_port + 20 and not _port_is_available(port):
        port += 1

    if port != requested_port:
        print(f"Port {requested_port} is in use; starting on {port} instead.")

    # Auto-update PASSKEY_ORIGIN if port differs from 5000
    if port != 5000 and "PASSKEY_ORIGIN" not in os.environ:
        PASSKEY_ORIGIN = f"http://localhost:{port}"
    
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
