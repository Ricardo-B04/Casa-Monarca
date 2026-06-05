"""
Tests for enhanced encryption audit logging and passkey-protected key management.
Covers:
  - encryption_metrics table has new audit columns (user, action_detail, active_key_info)
  - record_encryption_metric stores user, action_detail, active_key_info
  - get_active_key_details returns valid JSON string
  - admin_configure_key endpoint rejects requests without a valid passkey session marker
  - admin_activate_key endpoint rejects requests without a valid passkey session marker
  - check_and_consume_passkey_action: verifies action label and expiry from session marker
"""
import sqlite3
import json
import time
import pytest
import datetime

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as app_module
from app import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_test_db(tmp_path):
    """Create a fresh SQLite DB in tmp_path and run init_db() against it."""
    db_path = str(tmp_path / "test_audit.db")
    original = app.config.get("DATABASE", "database.db")
    app.config["DATABASE"] = db_path
    app_module.init_db()
    return db_path, original


def _get_conn(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------------------------
# 1. Schema – encryption_metrics table has new columns
# ---------------------------------------------------------------------------

class TestEncryptionMetricsSchema:
    def test_columns_exist(self, tmp_path):
        db_path, orig = _init_test_db(tmp_path)
        try:
            conn = _get_conn(db_path)
            c = conn.cursor()
            c.execute("PRAGMA table_info(encryption_metrics)")
            cols = {row["name"] for row in c.fetchall()}
            conn.close()
            assert "user" in cols, "Missing 'user' column"
            assert "action_detail" in cols, "Missing 'action_detail' column"
            assert "active_key_info" in cols, "Missing 'active_key_info' column"
        finally:
            app.config["DATABASE"] = orig


# ---------------------------------------------------------------------------
# 2. record_encryption_metric stores audit fields
# ---------------------------------------------------------------------------

class TestRecordEncryptionMetric:
    def test_audit_fields_persisted(self, tmp_path):
        db_path, orig = _init_test_db(tmp_path)
        try:
            app_module.record_encryption_metric(
                op_type="encrypt",
                duration_ms=0.05,
                key_fingerprint="TESTFP001",
                record_id=42,
                status="ok",
                user="testuser@example.com",
                action_detail="cifrado de expediente de prueba",
                active_key_info='{"fingerprint":"TESTFP001","label":"clave-test"}',
            )

            conn = _get_conn(db_path)
            row = conn.execute(
                "SELECT * FROM encryption_metrics ORDER BY id DESC LIMIT 1"
            ).fetchone()
            conn.close()

            assert row["user"] == "testuser@example.com"
            assert row["action_detail"] == "cifrado de expediente de prueba"
            assert "TESTFP001" in row["active_key_info"]
        finally:
            app.config["DATABASE"] = orig


# ---------------------------------------------------------------------------
# 3. get_active_key_details returns a JSON-serialisable string
# ---------------------------------------------------------------------------

class TestGetActiveKeyDetails:
    def test_returns_json_string(self):
        result = app_module.get_active_key_details()
        assert isinstance(result, str), "Should return a string"
        parsed = json.loads(result)
        assert isinstance(parsed, dict), "Should parse to a dict"

    def test_contains_expected_keys(self):
        result = json.loads(app_module.get_active_key_details())
        # Must contain at least one of these informational keys
        assert any(k in result for k in ("fingerprint", "label", "status", "state")), \
            f"Unexpected JSON shape: {result}"


# ---------------------------------------------------------------------------
# 4. HTTP endpoints – passkey session marker enforcement
# ---------------------------------------------------------------------------

@pytest.fixture()
def client_admin(tmp_path):
    """Flask test client with a logged-in admin session pointing at a fresh tmp DB."""
    db_path, orig = _init_test_db(tmp_path)
    app.config["TESTING"] = True

    with app.test_client() as c:
        with c.session_transaction() as sess:
            sess["user"] = "admin_test"
            sess["role"] = "admin"
        yield c

    app.config["DATABASE"] = orig


class TestAdminConfigureKeyEndpoint:
    def test_rejects_without_passkey_marker(self, client_admin):
        """POST /admin/keys/configure without session passkey marker must reject."""
        # No verified_passkey_action in session → should get 400 (passkey missing) or 302
        resp = client_admin.post(
            "/admin/keys/configure",
            json={"label": "nueva-clave"},
            content_type="application/json",
        )
        # 400 = passkey check failed (valid), 302 = redirect to login, 403 = auth failed
        assert resp.status_code in (400, 302, 403), \
            f"Expected 400/302/403 for missing passkey, got {resp.status_code}"

    def test_rejects_with_expired_passkey_marker(self, client_admin):
        """Session marker with an old timestamp must be rejected."""
        with client_admin.session_transaction() as sess:
            sess["verified_passkey_action"] = {
                "action_label": "configurar nueva clave de cifrado",
                "timestamp": time.time() - 9999,  # expired
            }
        resp = client_admin.post(
            "/admin/keys/configure",
            json={"label": "nueva-clave"},
            content_type="application/json",
        )
        assert resp.status_code in (400, 302, 403), \
            f"Expected rejection for expired passkey, got {resp.status_code}"

    def test_rejects_with_wrong_action_label(self, client_admin):
        """Session marker with wrong action label must be rejected."""
        with client_admin.session_transaction() as sess:
            sess["verified_passkey_action"] = {
                "action_label": "accion equivocada",
                "timestamp": time.time(),
            }
        resp = client_admin.post(
            "/admin/keys/configure",
            json={"label": "nueva-clave"},
            content_type="application/json",
        )
        assert resp.status_code in (400, 302, 403), \
            f"Expected rejection for wrong action label, got {resp.status_code}"


class TestAdminActivateKeyEndpoint:
    def test_rejects_without_passkey_marker(self, client_admin):
        """POST /admin/keys/<fp>/activate without passkey marker must reject."""
        resp = client_admin.post("/admin/keys/FAKEFINGERPRINT/activate")
        assert resp.status_code in (400, 302, 403, 404), \
            f"Expected 400/302/403/404, got {resp.status_code}"

    def test_rejects_with_expired_passkey_marker(self, client_admin):
        """POST with expired passkey marker must reject."""
        fp = "a" * 64  # fake SHA-256 fingerprint
        with client_admin.session_transaction() as sess:
            sess["verified_passkey_action"] = {
                "action_label": f"activar clave de cifrado {fp}",
                "timestamp": time.time() - 9999,
            }
        resp = client_admin.post(f"/admin/keys/{fp}/activate")
        assert resp.status_code in (400, 302, 403), \
            f"Expected rejection for expired passkey, got {resp.status_code}"


# ---------------------------------------------------------------------------
# 5. check_and_consume_passkey_action – unit tests
# ---------------------------------------------------------------------------

class TestCheckAndConsumePasskeyAction:
    """Test the server-side passkey action verification helper."""

    def test_missing_marker_returns_false(self):
        with app.test_request_context("/admin/keys/configure", method="POST"):
            # No session marker set
            result = app_module.check_and_consume_passkey_action("configure key")
        assert result is False, "Should be False when no session marker exists"

    def test_wrong_action_label_returns_false(self):
        with app.test_request_context("/admin/keys/configure", method="POST"):
            from flask import session
            session["verified_passkey_action"] = {
                "action_label": "wrong action",
                "timestamp": time.time(),
            }
            result = app_module.check_and_consume_passkey_action("configure key")
        assert result is False, "Should be False for wrong action label"

    def test_expired_marker_returns_false(self):
        with app.test_request_context("/admin/keys/configure", method="POST"):
            from flask import session
            session["verified_passkey_action"] = {
                "action_label": "configure key",
                "timestamp": time.time() - 9999,
            }
            result = app_module.check_and_consume_passkey_action("configure key", max_age_seconds=60)
        assert result is False, "Should be False for expired timestamp"

    def test_valid_marker_returns_true(self):
        with app.test_request_context("/admin/keys/configure", method="POST"):
            from flask import session
            session["verified_passkey_action"] = {
                "action_label": "configure key",
                "timestamp": time.time(),
            }
            result = app_module.check_and_consume_passkey_action("configure key", max_age_seconds=60)
        assert result is True, "Should be True for fresh, matching marker"

    def test_marker_consumed_after_check(self):
        """After a successful check, the marker must be removed from the session."""
        with app.test_request_context("/admin/keys/configure", method="POST"):
            from flask import session
            session["verified_passkey_action"] = {
                "action_label": "configure key",
                "timestamp": time.time(),
            }
            first = app_module.check_and_consume_passkey_action("configure key", max_age_seconds=60)
            second = app_module.check_and_consume_passkey_action("configure key", max_age_seconds=60)
        assert first is True
        assert second is False, "Marker should be consumed after first successful check"
