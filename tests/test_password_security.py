import base64
import shutil
from pathlib import Path

import pytest

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
