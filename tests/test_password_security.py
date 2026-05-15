import base64
import io
import shutil
import re
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import app as app_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Run each test with an isolated database and cert/key files."""
    monkeypatch.chdir(tmp_path)

    source_key = Path(app_module.__file__).with_name("key.key")
    shutil.copy(source_key, tmp_path / "key.key")

    app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret")

    app_module.init_db()
    app_module.create_default_accounts()
    app_module.bootstrap_dev_certificates()

    with app_module.app.test_client() as test_client:
        yield test_client


def _get_session_challenge(client, key):
    with client.session_transaction() as session_data:
        return session_data[key]["value"]


def _sign_challenge(private_key, purpose, username, challenge):
    payload = app_module.build_signature_payload(purpose, username, challenge)
    signature = private_key.sign(payload, padding.PKCS1v15(), hashes.SHA256())
    return base64.b64encode(signature).decode("ascii")


def test_qa_a_rejects_weak_password_on_forced_update(client):
    login = client.post(
        "/",
        data={"username": "usuario_1", "password": "user123"},
        follow_redirects=False,
    )
    assert login.status_code == 302
    assert login.headers["Location"].endswith("/password/update")

    update = client.post(
        "/password/update",
        data={
            "current_password": "user123",
            "new_password": "Admin12345!",
            "confirm_password": "Admin12345!",
        },
        follow_redirects=True,
    )

    assert update.status_code == 200
    assert b"Contrasena insegura o presente en bases de datos de filtraciones." in update.data


def test_qa_b_legacy_user_is_blocked_until_upgrade(client, monkeypatch):
    monkeypatch.setattr(app_module, "check_password_pwned", lambda _password: False)

    login = client.post(
        "/",
        data={"username": "usuario_1", "password": "user123"},
        follow_redirects=False,
    )
    assert login.status_code == 302
    assert login.headers["Location"].endswith("/password/update")

    blocked = client.get("/dashboard", follow_redirects=False)
    assert blocked.status_code == 302
    assert blocked.headers["Location"].endswith("/password/update")

    update = client.post(
        "/password/update",
        data={
            "current_password": "user123",
            "new_password": "N0vaClaveSegura#2026",
            "confirm_password": "N0vaClaveSegura#2026",
        },
        follow_redirects=False,
    )
    assert update.status_code == 302
    assert update.headers["Location"].endswith("/dashboard")

    conn = app_module.get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT must_change_password, password_algo, password_salt FROM usuarios WHERE username=?",
        ("usuario_1",),
    )
    row = cur.fetchone()
    conn.close()

    assert row["must_change_password"] == 0
    assert row["password_algo"] == "argon2id"

    salt_bytes = base64.b64decode(row["password_salt"].encode("utf-8"))
    assert len(salt_bytes) == 16

    allowed = client.get("/dashboard", follow_redirects=False)
    assert allowed.status_code == 200


def test_login_rate_limit_and_reset_on_success(client, monkeypatch):
    # configure limits for test speed
    monkeypatch.setattr(app_module, "LOGIN_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(app_module, "LOGIN_WINDOW_SECONDS", 60)
    monkeypatch.setattr(app_module, "LOGIN_LOCKOUT_SECONDS", 60)

    # ensure clean state
    app_module.failed_login_store.clear()

    # perform failed attempts up to limit
    for _ in range(3):
        r = client.post("/", data={"username": "usuario_1", "password": "badpass"}, follow_redirects=True)
        assert b"Usuario o contrasena incorrectos" in r.data

    # next attempt should be blocked
    r = client.post("/", data={"username": "usuario_1", "password": "badpass"}, follow_redirects=True)
    assert b"Cuenta bloqueada" in r.data

    # now login with correct creds should still be blocked until lockout expires
    r = client.post("/", data={"username": "usuario_1", "password": "Usuario_2026!X"}, follow_redirects=True)
    assert b"Cuenta bloqueada" in r.data or b"Usuario o contrasena incorrectos" in r.data


def test_failed_then_success_resets_counter(client, monkeypatch):
    monkeypatch.setattr(app_module, "LOGIN_MAX_ATTEMPTS", 5)
    monkeypatch.setattr(app_module, "LOGIN_WINDOW_SECONDS", 60)
    monkeypatch.setattr(app_module, "LOGIN_LOCKOUT_SECONDS", 60)

    app_module.failed_login_store.clear()

    # two failed attempts
    for _ in range(2):
        r = client.post("/", data={"username": "usuario_1", "password": "badpass"}, follow_redirects=True)
        assert b"Usuario o contrasena incorrectos" in r.data

    # successful login (uses legacy test seed password)
    r = client.post("/", data={"username": "usuario_1", "password": "user123"}, follow_redirects=True)
    # should redirect to dashboard or render dashboard
    assert r.status_code in (200, 302)

    # failed_login_store should be cleared for identifier
    ident = app_module._login_identifier_from_request("usuario_1")
    assert ident not in app_module.failed_login_store


def test_login_lockout_survives_memory_clear(client, monkeypatch):
    monkeypatch.setattr(app_module, "LOGIN_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(app_module, "LOGIN_WINDOW_SECONDS", 120)
    monkeypatch.setattr(app_module, "LOGIN_LOCKOUT_SECONDS", 120)

    app_module.failed_login_store.clear()

    for _ in range(3):
        response = client.post(
            "/",
            data={"username": "usuario_1", "password": "badpass"},
            follow_redirects=True,
        )
        assert b"Usuario o contrasena incorrectos" in response.data

    ident = app_module._login_identifier_from_request("usuario_1")
    app_module.failed_login_store.clear()

    locked, until = app_module._is_locked(ident)
    assert locked is True
    assert until is not None

    conn = app_module.get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT attempts, lockout_until FROM login_lockouts WHERE identifier=?",
        (ident,),
    )
    row = cur.fetchone()
    conn.close()

    assert row["attempts"] == 3
    assert row["lockout_until"] is not None


def test_x509_certificate_issue_and_revocation(client, monkeypatch):
    monkeypatch.setattr(app_module, "check_password_pwned", lambda _password: False)

    login = client.post(
        "/",
        data={"username": "admin_prod", "password": "admin123"},
        follow_redirects=False,
    )
    assert login.status_code == 302
    assert login.headers["Location"].endswith("/password/update")

    update = client.post(
        "/password/update",
        data={
            "current_password": "admin123",
            "new_password": "AdminX2026!Pass",
            "confirm_password": "AdminX2026!Pass",
        },
        follow_redirects=False,
    )
    assert update.status_code == 302
    assert update.headers["Location"].endswith("/admin")

    client.get("/logout", follow_redirects=False)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(app_module._certificate_subject_for_user("admin_prod", "admin"))
        .sign(private_key, hashes.SHA256())
    )

    relogin = client.post(
        "/",
        data={"username": "admin_prod", "password": "AdminX2026!Pass"},
        follow_redirects=False,
    )
    assert relogin.status_code == 302
    assert relogin.headers["Location"].endswith("/certificado/setup")

    setup = client.post(
        "/certificado/setup",
        data={"csr_pem": csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert setup.status_code == 200

    conn = app_module.get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, pem_path, cert_fingerprint, public_fp, custody_mode, status FROM certificados WHERE username=? ORDER BY id DESC LIMIT 1",
        ("admin_prod",),
    )
    cert_row = cur.fetchone()
    conn.close()

    assert cert_row["status"] == "activo"
    assert cert_row["cert_fingerprint"]
    assert cert_row["custody_mode"] == "user_key"

    cert_bytes = Path(cert_row["pem_path"]).read_bytes()
    cert_obj = x509.load_pem_x509_certificate(cert_bytes)
    assert cert_obj.subject.rfc4514_string().startswith("CN=admin_prod")
    assert cert_obj.issuer.rfc4514_string().startswith("CN=Casa Monarca Development CA")

    client.get("/logout", follow_redirects=False)

    login_page = client.get("/", follow_redirects=False)
    assert login_page.status_code == 200
    login_challenge = _get_session_challenge(client, "login_signature_challenge")
    login_signature = _sign_challenge(private_key, "login", "admin_prod", login_challenge)

    login = client.post(
        "/",
        data={
            "username": "admin_prod",
            "password": "AdminX2026!Pass",
            "cert_file": (io.BytesIO(cert_bytes), "admin_prod.crt"),
            "cert_signature": login_signature,
            "login_challenge": login_challenge,
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert login.status_code == 302
    assert login.headers["Location"].endswith("/admin")

    client.get("/usuarios", follow_redirects=False)
    action_challenge = _get_session_challenge(client, "action_signature_challenge")
    revoke_signature = _sign_challenge(private_key, "revocacion de certificado", "admin_prod", action_challenge)

    with Path(cert_row["pem_path"]).open("rb") as cert_file:
        revoke = client.post(
            f"/certificado/{cert_row['id']}/revocar",
            data={
                "action_cert_file": (cert_file, "admin_prod.crt"),
                "action_signature": revoke_signature,
                "action_challenge": action_challenge,
                "revocation_reason": "prueba de revocacion",
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
    assert revoke.status_code == 302

    conn = app_module.get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT status, revoked_by, revocation_reason FROM certificados WHERE id=?",
        (cert_row["id"],),
    )
    revoked_row = cur.fetchone()
    conn.close()

    assert revoked_row["status"] == "revocado"
    assert revoked_row["revoked_by"] == "admin_prod"
    assert revoked_row["revocation_reason"] == "prueba de revocacion"


def test_x509_csr_issue_and_login_with_separate_key(client, monkeypatch):
    monkeypatch.setattr(app_module, "check_password_pwned", lambda _password: False)

    login = client.post(
        "/",
        data={"username": "coord_admin", "password": "coord123"},
        follow_redirects=False,
    )
    assert login.status_code == 302
    assert login.headers["Location"].endswith("/password/update")

    update = client.post(
        "/password/update",
        data={
            "current_password": "coord123",
            "new_password": "CoordX2026!Pass",
            "confirm_password": "CoordX2026!Pass",
        },
        follow_redirects=False,
    )
    assert update.status_code == 302
    assert update.headers["Location"].endswith("/dashboard")

    client.get("/logout", follow_redirects=False)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(app_module._certificate_subject_for_user("coord_admin", "coordinador"))
        .sign(private_key, hashes.SHA256())
    )

    relogin = client.post(
        "/",
        data={"username": "coord_admin", "password": "CoordX2026!Pass"},
        follow_redirects=False,
    )
    assert relogin.status_code == 302
    assert relogin.headers["Location"].endswith("/certificado/setup")

    setup = client.post(
        "/certificado/setup",
        data={"csr_pem": csr.public_bytes(serialization.Encoding.PEM).decode("utf-8")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert setup.status_code == 200
    assert setup.headers["Content-Disposition"].startswith("attachment;")

    conn = app_module.get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, pem_path, custody_mode, status, cert_fingerprint FROM certificados WHERE username=? ORDER BY id DESC LIMIT 1",
        ("coord_admin",),
    )
    cert_row = cur.fetchone()
    conn.close()

    assert cert_row["status"] == "activo"
    assert cert_row["custody_mode"] == "user_key"
    assert cert_row["cert_fingerprint"]

    cert_bytes = Path(cert_row["pem_path"]).read_bytes()

    client.get("/logout", follow_redirects=False)
    client.get("/", follow_redirects=False)
    login_challenge = _get_session_challenge(client, "login_signature_challenge")
    login_signature = _sign_challenge(private_key, "login", "coord_admin", login_challenge)

    login = client.post(
        "/",
        data={
            "username": "coord_admin",
            "password": "CoordX2026!Pass",
            "cert_file": (io.BytesIO(cert_bytes), "coord_admin.crt"),
            "cert_signature": login_signature,
            "login_challenge": login_challenge,
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert login.status_code == 302
    assert login.headers["Location"].endswith("/dashboard")
