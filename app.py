from flask import Flask, render_template, request, redirect, session, flash, send_file
import sqlite3
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from argon2.low_level import Type, hash_secret
from werkzeug.security import check_password_hash
import hmac
import datetime
import ast
import hashlib
import os
import base64
import urllib.request
import urllib.error

app = Flask(__name__)
app.secret_key = "secreto_demo"

CERT_VALIDITY_HOURS = 720
PASSWORD_MIN_LENGTH = 12
ARGON2_MEMORY_COST = 65536
ARGON2_TIME_COST = 3
ARGON2_PARALLELISM = 2
ARGON2_HASH_LEN = 32
ARGON2_SALT_LEN = 16
HIBP_TIMEOUT_SECONDS = 4

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
with open("key.key", "rb") as f:
    key = f.read()

cipher = Fernet(key)


def get_conn():
    conn = sqlite3.connect("database.db")
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
            activo INTEGER DEFAULT 1
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT,
            accion TEXT,
            fecha TEXT
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
        CREATE TABLE IF NOT EXISTS certificados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            rol TEXT,
            issued_by TEXT,
            issuer_fingerprint TEXT,
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
            created_at TEXT,
            updated_at TEXT
        )
        """
    )

    # Compatibilidad con bases existentes de la version anterior
    ensure_column(c, "encuestas", "estado", "TEXT DEFAULT 'borrador'")
    ensure_column(c, "encuestas", "creado_por", "TEXT")
    ensure_column(c, "encuestas", "nivel_actual", "TEXT")
    ensure_column(c, "encuestas", "created_at", "TEXT")
    ensure_column(c, "encuestas", "updated_at", "TEXT")

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

    ensure_column(c, "certificados", "rol", "TEXT")
    ensure_column(c, "certificados", "issued_by", "TEXT")
    ensure_column(c, "certificados", "issuer_fingerprint", "TEXT")
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
    ensure_column(c, "certificados", "created_at", "TEXT")
    ensure_column(c, "certificados", "updated_at", "TEXT")

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

    conn.commit()
    conn.close()


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


def log(usuario, accion):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO logs (usuario, accion, fecha) VALUES (?, ?, ?)",
        (usuario, accion, str(datetime.datetime.now())),
    )
    conn.commit()
    conn.close()


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

    default_users = [
        ("admin_prod", "admin123", "admin", None, 0),
        ("admin_cont", "admin123", "admin", None, 1),
        ("coord_admin", "coord123", "coordinador", "Administracion", 0),
        ("operativo_1", "oper123", "operativo", None, 0),
        ("usuario_1", "user123", "usuario", None, 0),
    ]

    for username, password, rol, area, contingency in default_users:
        c.execute("SELECT id FROM usuarios WHERE username=?", (username,))
        if c.fetchone() is None:
            salt = generate_password_salt()
            c.execute(
                """
                INSERT INTO usuarios (
                    username, password_hash, rol, area, is_contingency, activo,
                    must_change_password, password_updated_at, password_algo, password_salt
                )
                VALUES (?, ?, ?, ?, ?, 1, 1, ?, 'argon2id', ?)
                """,
                (
                    username,
                    hash_password_argon2id(password, salt),
                    rol,
                    area,
                    contingency,
                    str(datetime.datetime.now()),
                    encode_salt(salt),
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


def bootstrap_dev_certificates():
    conn = get_conn()
    c = conn.cursor()

    defaults = {
        "admin_prod": ("admin", "admin123"),
        "admin_cont": ("admin", "admin123"),
        "coord_admin": ("coordinador", "coord123"),
    }

    for username, (role, _password) in defaults.items():
        c.execute(
            "SELECT id FROM usuarios WHERE username=?",
            (username,),
        )
        row = c.fetchone()
        if not row:
            continue

        c.execute(
            "SELECT id FROM certificados WHERE username=?",
            (username,),
        )
        if c.fetchone() is not None:
            continue

        create_pending_certificate(conn, username, role, "system", None)

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


def store_pem_file(username, pem_bytes):
    os.makedirs("certs", exist_ok=True)
    pem_path = os.path.join("certs", f"{username}.pem")
    with open(pem_path, "wb") as pem_file:
        pem_file.write(pem_bytes)
    return pem_path


def load_private_key_from_pem(pem_bytes, passphrase):
    return serialization.load_pem_private_key(
        pem_bytes,
        password=passphrase.encode("utf-8"),
    )


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

    now = datetime.datetime.now()
    issued_at = str(now)
    expires_at = str(now + datetime.timedelta(hours=CERT_VALIDITY_HOURS))
    status = "activo"
    serial = hashlib.sha256(
        f"{username}{issued_at}{os.urandom(8)}".encode()
    ).hexdigest()[:16]

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = serialize_private_key_encrypted(private_key, passphrase)
    public_bytes = serialize_public_key(private_key.public_key())

    pem_hash = hash_bytes(private_pem)
    public_fp = compute_public_fingerprint(public_bytes)
    pem_path = store_pem_file(username, private_pem)

    c = conn.cursor()
    c.execute(
        """
        INSERT INTO certificados (
            username, rol, issued_by, issuer_fingerprint, issued_at, expires_at,
            status, pem_hash, public_fp, cert_serial, pem_path, algorithm,
            last_used_at, revoked_at, revoked_by, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            username,
            role,
            issued_by,
            issuer_fingerprint,
            issued_at,
            expires_at,
            status,
            pem_hash,
            public_fp,
            serial,
            pem_path,
            "RSA-2048/AES-256-CBC",
            None,
            None,
            None,
            issued_at,
            issued_at,
        ),
    )

    return {"pem_hash": pem_hash, "public_fp": public_fp}


def create_pending_certificate(conn, username, role, issued_by, issuer_fingerprint):
    now = str(datetime.datetime.now())
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO certificados (
            username, rol, issued_by, issuer_fingerprint, status,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            username,
            role,
            issued_by,
            issuer_fingerprint,
            "pendiente",
            now,
            now,
        ),
    )
    return c.lastrowid


def activate_pending_certificate(conn, cert_id, username, role, passphrase, issued_by, issuer_fingerprint):
    now = datetime.datetime.now()
    issued_at = str(now)
    expires_at = str(now + datetime.timedelta(hours=CERT_VALIDITY_HOURS))
    status = "activo"
    serial = hashlib.sha256(
        f"{username}{issued_at}{os.urandom(8)}".encode()
    ).hexdigest()[:16]

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = serialize_private_key_encrypted(private_key, passphrase)
    public_bytes = serialize_public_key(private_key.public_key())

    pem_hash = hash_bytes(private_pem)
    public_fp = compute_public_fingerprint(public_bytes)
    pem_path = store_pem_file(username, private_pem)

    c = conn.cursor()
    c.execute(
        """
        UPDATE certificados
        SET issued_by=?, issuer_fingerprint=?, issued_at=?, expires_at=?, status=?,
            pem_hash=?, public_fp=?, cert_serial=?, pem_path=?, algorithm=?,
            last_used_at=?, revoked_at=?, revoked_by=?, updated_at=?
        WHERE id=?
        """,
        (
            issued_by,
            issuer_fingerprint,
            issued_at,
            expires_at,
            status,
            pem_hash,
            public_fp,
            serial,
            pem_path,
            "RSA-2048/AES-256-CBC",
            None,
            None,
            None,
            issued_at,
            cert_id,
        ),
    )

    return {"pem_hash": pem_hash, "public_fp": public_fp}


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


def is_cert_expired(cert_row):
    exp_dt = parse_datetime(cert_row["expires_at"])
    if not exp_dt:
        return False
    return exp_dt < datetime.datetime.now()


def update_cert_status(conn, cert_id, status, revoked_by=None):
    now = str(datetime.datetime.now())
    c = conn.cursor()
    if status == "revocado":
        c.execute(
            """
            UPDATE certificados
            SET status=?, revoked_at=?, revoked_by=?, updated_at=?
            WHERE id=?
            """,
            (status, now, revoked_by, now, cert_id),
        )
    else:
        c.execute(
            "UPDATE certificados SET status=?, updated_at=? WHERE id=?",
            (status, now, cert_id),
        )


def validate_encrypted_pem(cert_row, pem_bytes, passphrase):
    if cert_row["pem_hash"] and hash_bytes(pem_bytes) != cert_row["pem_hash"]:
        return False, "El archivo no coincide con el certificado registrado.", None

    try:
        private_key = load_private_key_from_pem(pem_bytes, passphrase)
    except Exception:
        return False, "Passphrase invalida o PEM corrupto.", None

    public_bytes = serialize_public_key(private_key.public_key())
    public_fp = compute_public_fingerprint(public_bytes)

    if cert_row["public_fp"] and public_fp != cert_row["public_fp"]:
        return False, "El certificado no corresponde al usuario.", None

    return True, None, public_fp


def validate_certificate_for_user(conn, username, pem_bytes, passphrase):
    cert_row = get_active_certificate(conn, username)
    if not cert_row:
        return False, "No hay un certificado activo. Debes configurarlo.", None

    if is_cert_expired(cert_row):
        update_cert_status(conn, cert_row["id"], "expirado")
        return False, "Tu certificado ha expirado. Debes reemitirlo.", None

    ok, message, public_fp = validate_encrypted_pem(cert_row, pem_bytes, passphrase)
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

    passphrase = request.form.get("action_cert_passphrase", "")
    if not passphrase:
        flash("Se requiere la passphrase del certificado.")
        return False, None

    conn = get_conn()
    ok, message, public_fp = validate_certificate_for_user(
        conn,
        session.get("user"),
        cert_file.read(),
        passphrase,
    )
    conn.commit()
    conn.close()

    if not ok:
        flash(message)
        return False, None

    return True, public_fp


def decrypt_data(blob_value):
    try:
        decoded = cipher.decrypt(blob_value).decode()
        return ast.literal_eval(decoded)
    except Exception:
        return None


def parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except Exception:
        return None


def require_login():
    return "user" in session and session.get("role") in ROLE_LABELS


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
        return redirect("/password/update")

    if not session.get("cert_setup_required"):
        return None

    if not session.get("user"):
        session.pop("cert_setup_required", None)
        return None

    if request.path.startswith("/static"):
        return None

    if request.path in ("/", "/certificado/setup", "/logout"):
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

    if request.method == "POST":
        passphrase = request.form.get("passphrase", "")
        passphrase_confirm = request.form.get("passphrase_confirm", "")

        if not passphrase or len(passphrase) < 10:
            flash("La passphrase debe tener al menos 10 caracteres.")
            conn.close()
            return render_template("cert_setup.html")

        if passphrase != passphrase_confirm:
            flash("Las passphrases no coinciden.")
            conn.close()
            return render_template("cert_setup.html")

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
            return render_template("cert_setup.html")

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
    return render_template("cert_setup.html")


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


@app.route("/", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "SELECT * FROM usuarios WHERE username=? AND activo=1",
            (username,),
        )
        user = c.fetchone()
        conn.close()

        if user and user["password_hash"] and verify_user_password(user, password):
            if password_is_legacy_or_weak(user, password):
                session["user"] = user["username"]
                session["role"] = user["rol"]
                session["area"] = user["area"]
                session["password_change_required"] = True
                log(user["username"], "Inicio de sesion (cambio de contrasena obligatorio)")
                return redirect("/password/update")

            if user["rol"] in ("admin", "coordinador"):
                conn = get_conn()
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
                    return render_template("login.html", error=error)

                cert_file = request.files.get("cert_file")
                if not cert_file or not cert_file.filename:
                    conn.close()
                    error = "Este usuario requiere certificado digital (.pem)."
                    return render_template("login.html", error=error)

                passphrase = request.form.get("cert_passphrase", "")
                if not passphrase:
                    conn.close()
                    error = "Debes ingresar la passphrase del certificado."
                    return render_template("login.html", error=error)

                ok, message, _public_fp = validate_certificate_for_user(
                    conn,
                    user["username"],
                    cert_file.read(),
                    passphrase,
                )
                if not ok:
                    conn.close()
                    error = message
                    return render_template("login.html", error=error)

                conn.commit()
                conn.close()

            session["user"] = user["username"]
            session["role"] = user["rol"]
            session["area"] = user["area"]
            session.pop("cert_setup_required", None)
            session.pop("password_change_required", None)
            log(user["username"], "Inicio de sesion")
            return redirect(role_home(user["rol"]))

        error = "Usuario o contrasena incorrectos"

    return render_template("login.html", error=error)


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
            "nombre": request.form.get("nombre", "").strip(),
            "apellido_materno": request.form.get("apellido_materno", "").strip(),
            "apellido_paterno": request.form.get("apellido_paterno", "").strip(),
            "pais": request.form.get("pais", "").strip(),
            "edad": request.form.get("edad", "").strip(),
            "tiempo_estancia": request.form.get("tiempo_estancia", "").strip(),
            "capturado_por": session.get("user"),
            "rol_capturador": session.get("role"),
        }

        encrypted = cipher.encrypt(str(data).encode())

        conn = get_conn()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO encuestas (datos, estado, creado_por, nivel_actual, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                encrypted,
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
    if not require_role("admin"):
        return redirect("/")

    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT id, datos, estado, creado_por, created_at FROM encuestas ORDER BY id DESC"
    )
    rows = c.fetchall()

    expedientes = []
    for row in rows:
        d = decrypt_data(row["datos"])
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

    conn.close()

    return render_template("admin.html", expedientes=expedientes, solicitudes=solicitudes)


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
    conn.close()

    expedientes = []
    for row in rows:
        d = decrypt_data(row["datos"])
        if not d:
            continue
        d["id"] = row["id"]
        d["estado"] = row["estado"]
        d["creado_por"] = row["creado_por"]
        d["updated_at"] = row["updated_at"]
        expedientes.append(d)

    return render_template("colaborador.html", datos=expedientes, role=session.get("role"))


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

    ok, _ = verify_action_certificate("avance de expediente")
    if not ok:
        conn.close()
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

    ok, _ = verify_action_certificate("solicitud de eliminacion")
    if not ok:
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
    if not require_role("admin"):
        return redirect("/")

    ok, _ = verify_action_certificate("resolucion de solicitud")
    if not ok:
        return redirect("/admin")

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
    if not require_role("admin"):
        return redirect("/")

    conn = get_conn()
    c = conn.cursor()

    if request.method == "POST":
        ok, issuer_fingerprint = verify_action_certificate("creacion de usuario")
        if not ok:
            conn.close()
            return redirect("/usuarios")

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
                    issuer_fingerprint,
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


@app.route("/eliminar-usuario/<int:user_id>", methods=["POST"])
def eliminar_usuario(user_id):
    if not require_role("admin"):
        return redirect("/")

    ok, _ = verify_action_certificate("eliminacion de usuario")
    if not ok:
        return redirect("/usuarios")

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
    if not require_role("admin"):
        return redirect("/")

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM logs ORDER BY id DESC")
    data = c.fetchall()
    conn.close()

    return render_template("logs.html", logs=data)


@app.route("/logs/clear", methods=["POST"])
def clear_logs():
    if not require_role("admin"):
        return redirect("/")

    ok, _ = verify_action_certificate("limpieza de bitacora")
    if not ok:
        return redirect("/logs")

    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM logs")
    conn.commit()
    conn.close()

    flash("Bitacora limpiada")
    return redirect("/logs")


@app.route("/certificado/<int:cert_id>/descargar", methods=["POST"])
def descargar_certificado(cert_id):
    if not require_role("admin"):
        return redirect("/")

    ok, _ = verify_action_certificate("descarga de certificado")
    if not ok:
        return redirect("/usuarios")

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

    filename = f"{cert['username']}.pem"
    return send_file(
        cert["pem_path"],
        as_attachment=True,
        download_name=filename,
        mimetype="application/x-pem-file",
    )


@app.route("/logout")
def logout():
    log(session.get("user", "desconocido"), "Cerro sesion")
    session.clear()
    return redirect("/")


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if not require_login():
        return redirect("/")

    conn = get_conn()
    c = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_contact":
            email = request.form.get("email", "").strip() or None
            phone = request.form.get("phone", "").strip() or None
            full_name = request.form.get("full_name", "").strip() or None

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

            session.pop("password_change_required", None)
            log(session.get("user"), "Actualizo su contrasena (perfil)")
            flash("Contrasena actualizada correctamente.")
            return redirect(role_home(session.get("role")))

    c.execute(
        "SELECT username, rol, area, activo, password_updated_at, email, phone, full_name FROM usuarios WHERE username=?",
        (session.get("user"),),
    )
    user = c.fetchone()
    conn.close()

    return render_template("profile.html", user=user, role_label=ROLE_LABELS.get(session.get("role"), session.get("role")))


if __name__ == "__main__":
    init_db()
    create_default_accounts()
    bootstrap_dev_certificates()
    app.run(debug=True)
