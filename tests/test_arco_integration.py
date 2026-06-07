"""Integration tests for the multilevel ARCO request workflow.

Covers the full approval pipeline described in IMPLEMENTACION_ARCO_MULTINIVEL.md:
    /arco (public form) -> usuarios -> operativos -> coordinadores
        -> coordinador resolves locally OR escalates to admin
"""
import secrets
import shutil
import time
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

    with app_module.app.test_client() as test_client:
        yield test_client


def _login_as(client, role, username):
    """Inject an authenticated session, bypassing the login form."""
    token = secrets.token_hex(32)
    with client.session_transaction() as sess:
        sess["user"] = username
        sess["role"] = role
        sess["csrf_token"] = token
    return token


def _grant_passkey_action(client, username, action_label="accion verificada"):
    """Simulate a freshly-completed per-action passkey signature.

    Mirrors the `action_passkey_verified` marker that
    `consume_action_passkey_verification` expects, the same approach used
    by tests/test_encryption_audit.py for `verified_passkey_action`.
    """
    with client.session_transaction() as sess:
        sess["action_passkey_verified"] = {
            "username": username,
            "action_label": action_label,
            "issued_at": time.time(),
        }


def _submit_arco_solicitud(client, **field_overrides):
    resp = client.get("/arco")
    assert resp.status_code == 200
    with client.session_transaction() as sess:
        csrf = sess["csrf_token"]

    data = {
        "nombre_solicitante": "Test Usuario",
        "correo": "test@example.com",
        "telefono": "5551234567",
        "curp_id": "TESU900101HDFRXXX",
        "accion": "acceso",
        "motivo": "Solicitud de prueba",
        "datos_correctos": "si",
        "csrf_token": csrf,
    }
    data.update(field_overrides)

    resp = client.post("/arco/solicitud", data=data)
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["ok"] is True

    conn = app_module.get_conn()
    row = conn.execute(
        "SELECT id FROM solicitudes_arco WHERE curp_id=? ORDER BY id DESC LIMIT 1",
        (data["curp_id"],),
    ).fetchone()
    conn.close()
    return row["id"]


def _solicitud(solicitud_id):
    conn = app_module.get_conn()
    row = conn.execute(
        "SELECT * FROM solicitudes_arco WHERE id=?", (solicitud_id,)
    ).fetchone()
    conn.close()
    return row


def test_arco_flow_resolved_locally_by_coordinador(client):
    solicitud_id = _submit_arco_solicitud(client, curp_id="ARCO000001AAAAAAA")
    assert _solicitud(solicitud_id)["nivel_actual"] == "usuarios"

    token = _login_as(client, "usuario", "usuario_test")
    resp = client.post(f"/arco/{solicitud_id}/aprobar", data={"csrf_token": token})
    assert resp.status_code == 302
    assert _solicitud(solicitud_id)["nivel_actual"] == "operativos"

    token = _login_as(client, "operativo", "operativo_test")
    resp = client.post(f"/arco/{solicitud_id}/aprobar", data={"csrf_token": token})
    assert resp.status_code == 302
    assert _solicitud(solicitud_id)["nivel_actual"] == "coordinadores"

    token = _login_as(client, "coordinador", "coordinador_test")
    _grant_passkey_action(client, "coordinador_test")
    resp = client.post(f"/arco/{solicitud_id}/aprobar", data={"csrf_token": token})
    assert resp.status_code == 302
    assert _solicitud(solicitud_id)["aprobado_coordinadores"] == 1

    _grant_passkey_action(client, "coordinador_test")
    resp = client.post(
        f"/arco/{solicitud_id}/resolver-coordinador",
        data={"csrf_token": token, "decision": "resuelta"},
    )
    assert resp.status_code == 302

    row = _solicitud(solicitud_id)
    assert row["nivel_actual"] == "resuelto"
    assert row["estado"] == "atendida"
    assert row["resuelto_coordinador"] == 1


def test_arco_flow_escalated_to_admin_and_resolved(client):
    solicitud_id = _submit_arco_solicitud(client, curp_id="ARCO000002BBBBBBB")

    token = _login_as(client, "usuario", "usuario_test")
    client.post(f"/arco/{solicitud_id}/aprobar", data={"csrf_token": token})

    token = _login_as(client, "operativo", "operativo_test")
    client.post(f"/arco/{solicitud_id}/aprobar", data={"csrf_token": token})

    token = _login_as(client, "coordinador", "coordinador_test")
    _grant_passkey_action(client, "coordinador_test")
    client.post(f"/arco/{solicitud_id}/aprobar", data={"csrf_token": token})

    _grant_passkey_action(client, "coordinador_test")
    resp = client.post(
        f"/arco/{solicitud_id}/resolver-coordinador",
        data={"csrf_token": token, "decision": "enviar_admin"},
    )
    assert resp.status_code == 302

    row = _solicitud(solicitud_id)
    assert row["nivel_actual"] == "admin"
    assert row["reenviado_por_coordinador"] == 1

    # Match the rendered card markup, not flash-message text (both contain "ARCO #<id>")
    marker = f'<div class="solicitud-title">ARCO #{solicitud_id}</div>'.encode()

    token = _login_as(client, "admin", "admin_test")
    resp = client.get("/admin")
    assert resp.status_code == 200
    assert marker in resp.data

    _grant_passkey_action(
        client, "admin_test", action_label="resolucion de solicitud (atendida)"
    )
    resp = client.post(
        f"/arco/{solicitud_id}/resolver",
        data={"csrf_token": token, "decision": "atendida"},
    )
    assert resp.status_code == 302
    assert _solicitud(solicitud_id)["estado"] == "atendida"

    resp = client.get("/admin")
    assert marker not in resp.data


def test_arco_aprobar_requires_valid_csrf_token(client):
    solicitud_id = _submit_arco_solicitud(client, curp_id="ARCO000003CCCCCCC")
    token = _login_as(client, "usuario", "usuario_test")

    resp = client.post(f"/arco/{solicitud_id}/aprobar", data={"csrf_token": "token-invalido"})
    assert resp.status_code == 302
    assert _solicitud(solicitud_id)["nivel_actual"] == "usuarios"

    resp = client.post(f"/arco/{solicitud_id}/aprobar", data={"csrf_token": token})
    assert resp.status_code == 302
    assert _solicitud(solicitud_id)["nivel_actual"] == "operativos"


def test_arco_aprobar_requires_passkey_signature_for_coordinador(client):
    solicitud_id = _submit_arco_solicitud(client, curp_id="ARCO000004DDDDDDD")

    token = _login_as(client, "usuario", "usuario_test")
    client.post(f"/arco/{solicitud_id}/aprobar", data={"csrf_token": token})

    token = _login_as(client, "operativo", "operativo_test")
    client.post(f"/arco/{solicitud_id}/aprobar", data={"csrf_token": token})

    # Coordinador sin verificacion de passkey reciente: no debe avanzar de nivel
    token = _login_as(client, "coordinador", "coordinador_test")
    resp = client.post(f"/arco/{solicitud_id}/aprobar", data={"csrf_token": token})
    assert resp.status_code == 302
    row = _solicitud(solicitud_id)
    assert row["nivel_actual"] == "coordinadores"
    assert row["aprobado_coordinadores"] in (0, None)

    _grant_passkey_action(client, "coordinador_test")
    resp = client.post(f"/arco/{solicitud_id}/aprobar", data={"csrf_token": token})
    assert resp.status_code == 302
    assert _solicitud(solicitud_id)["aprobado_coordinadores"] == 1
