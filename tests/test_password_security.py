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
