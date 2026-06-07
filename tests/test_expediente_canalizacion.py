"""Integration tests for the expediente (case file) routing/canalización workflow.

Covers the status pipeline driven by /encuesta/<id>/avanzar and described in
next_status_for_role():
    borrador -> en_revision_operativa -> en_revision_coordinacion
        -> validado_coordinacion -> cerrado
with passkey-signature verification required for coordinador/admin transitions.
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


def _grant_passkey_action(client, action_label):
    """Simulate a freshly-completed per-action passkey signature.

    Mirrors the `verified_passkey_action` marker that
    check_and_consume_passkey_action expects (same technique used by
    tests/test_arco_integration.py for the analogous ARCO check).
    """
    with client.session_transaction() as sess:
        sess["verified_passkey_action"] = {
            "action_label": action_label,
            "timestamp": time.time(),
        }


SURVEY_FORM_FIELDS = {
    "nombre_pila": "Ana",
    "primer_apellido": "Garcia",
    "segundo_apellido": "Lopez",
    "pais_origen": "Honduras",
    "fecha_nacimiento": "1990-01-01",
    "edad": "34",
    "genero": "F",
    "estado_civil": "soltera",
    "grupo_poblacion": "migrante",
    "departamento_estado": "Nuevo Leon",
    "telefono": "8112345678",
    "fecha_atencion": "2026-06-01",
}


def _create_expediente(client, creado_por="usuario_test"):
    token = _login_as(client, "usuario", creado_por)
    data = {"csrf_token": token, **SURVEY_FORM_FIELDS}

    resp = client.post("/survey", data=data, follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/dashboard")

    conn = app_module.get_conn()
    row = conn.execute(
        "SELECT id FROM encuestas WHERE creado_por=? ORDER BY id DESC LIMIT 1",
        (creado_por,),
    ).fetchone()
    conn.close()
    return row["id"]


def _expediente(expediente_id):
    conn = app_module.get_conn()
    row = conn.execute(
        "SELECT * FROM encuestas WHERE id=?", (expediente_id,)
    ).fetchone()
    conn.close()
    return row


def test_canalizacion_full_cycle_borrador_to_cerrado(client):
    expediente_id = _create_expediente(client, "usuario_test")
    assert _expediente(expediente_id)["estado"] == "borrador"

    action_label = f"expediente #{expediente_id}"

    # usuario: borrador -> en_revision_operativa (sin passkey)
    token = _login_as(client, "usuario", "usuario_test")
    resp = client.post(f"/encuesta/{expediente_id}/avanzar", data={"csrf_token": token})
    assert resp.status_code == 302
    assert _expediente(expediente_id)["estado"] == "en_revision_operativa"

    # operativo: en_revision_operativa -> en_revision_coordinacion (sin passkey)
    token = _login_as(client, "operativo", "operativo_test")
    resp = client.post(f"/encuesta/{expediente_id}/avanzar", data={"csrf_token": token})
    assert resp.status_code == 302
    assert _expediente(expediente_id)["estado"] == "en_revision_coordinacion"

    # coordinador: en_revision_coordinacion -> validado_coordinacion (requiere passkey)
    token = _login_as(client, "coordinador", "coordinador_test")
    _grant_passkey_action(client, action_label)
    resp = client.post(f"/encuesta/{expediente_id}/avanzar", data={"csrf_token": token})
    assert resp.status_code == 302
    assert _expediente(expediente_id)["estado"] == "validado_coordinacion"

    # admin: validado_coordinacion -> cerrado (requiere passkey)
    token = _login_as(client, "admin", "admin_test")
    _grant_passkey_action(client, action_label)
    resp = client.post(f"/encuesta/{expediente_id}/avanzar", data={"csrf_token": token})
    assert resp.status_code == 302
    assert _expediente(expediente_id)["estado"] == "cerrado"


def test_usuario_cannot_advance_expediente_de_otro_usuario(client):
    expediente_id = _create_expediente(client, "usuario_test")

    token = _login_as(client, "usuario", "otro_usuario")
    resp = client.post(f"/encuesta/{expediente_id}/avanzar", data={"csrf_token": token})
    assert resp.status_code == 302
    assert _expediente(expediente_id)["estado"] == "borrador"


def test_avanzar_rejects_expediente_en_estado_incorrecto(client):
    expediente_id = _create_expediente(client, "usuario_test")

    # El expediente sigue en 'borrador'; un operativo no puede canalizarlo todavia
    token = _login_as(client, "operativo", "operativo_test")
    resp = client.post(f"/encuesta/{expediente_id}/avanzar", data={"csrf_token": token})
    assert resp.status_code == 302
    assert _expediente(expediente_id)["estado"] == "borrador"


def test_coordinador_requiere_firma_passkey_para_avanzar(client):
    expediente_id = _create_expediente(client, "usuario_test")
    action_label = f"expediente #{expediente_id}"

    token = _login_as(client, "usuario", "usuario_test")
    client.post(f"/encuesta/{expediente_id}/avanzar", data={"csrf_token": token})

    token = _login_as(client, "operativo", "operativo_test")
    client.post(f"/encuesta/{expediente_id}/avanzar", data={"csrf_token": token})

    # Sin verificacion de passkey reciente: la transicion no debe ocurrir
    token = _login_as(client, "coordinador", "coordinador_test")
    resp = client.post(f"/encuesta/{expediente_id}/avanzar", data={"csrf_token": token})
    assert resp.status_code == 302
    assert _expediente(expediente_id)["estado"] == "en_revision_coordinacion"

    # Con la firma simulada, si avanza
    _grant_passkey_action(client, action_label)
    resp = client.post(f"/encuesta/{expediente_id}/avanzar", data={"csrf_token": token})
    assert resp.status_code == 302
    assert _expediente(expediente_id)["estado"] == "validado_coordinacion"


def test_expediente_visible_en_bandeja_segun_rol_y_estado(client):
    expediente_id = _create_expediente(client, "usuario_test")

    token = _login_as(client, "usuario", "usuario_test")
    client.post(f"/encuesta/{expediente_id}/avanzar", data={"csrf_token": token})

    # En 'en_revision_operativa': visible para operativo, con sus datos descifrados
    _login_as(client, "operativo", "operativo_test")
    resp = client.get("/bandeja")
    assert resp.status_code == 200
    assert f"Expediente #{expediente_id}".encode() in resp.data
    assert b"Estado: en_revision_operativa" in resp.data
    assert "Ana Garcia".encode() in resp.data
    assert b"Pais: Honduras" in resp.data

    # ...pero no para coordinador (filtra por estado esperado de su nivel)
    _login_as(client, "coordinador", "coordinador_test")
    resp = client.get("/bandeja")
    assert resp.status_code == 200
    assert f"Expediente #{expediente_id}".encode() not in resp.data
