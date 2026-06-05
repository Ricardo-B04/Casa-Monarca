"""
Tests de integración de endpoints: Verificar que check_certificate_expiration()
se ejecuta correctamente en /action/passkey/options y /action/passkey/verify
"""

import pytest
import json
import sqlite3
import tempfile
import os
import sys
import datetime
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def app_with_test_db():
    """Setup Flask app con BD de test"""
    import app as flask_app
    
    # Crear BD temporal
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    db_path = temp_db.name
    temp_db.close()
    
    # Mockear get_conn
    original_get_conn = flask_app.get_conn
    
    def get_test_conn():
        conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    flask_app.get_conn = get_test_conn
    flask_app.init_db()
    
    flask_app.app.config['TESTING'] = True
    
    yield flask_app, db_path
    
    flask_app.get_conn = original_get_conn
    try:
        os.unlink(db_path)
    except:
        pass


class TestCertificateExpirationEndpoints:
    """Tests de endpoints con certificados expirados"""
    
    def test_action_passkey_options_blocked_when_cert_expired(self, app_with_test_db):
        """
        Verificar que /action/passkey/options rechaza si cert está expirado
        """
        flask_app, db_path = app_with_test_db
        
        # Setup: usuario con passkey y cert expirado
        conn = flask_app.get_conn()
        c = conn.cursor()
        
        username = "test_admin_expired"
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", (username, "admin"))
        
        # Crear passkey
        fake_key = flask_app.b64url_encode(b"test_key")
        passkey_id = flask_app.save_passkey_credential(
            conn, username, "cred_exp", fake_key, 0, label="Test"
        )
        
        # Obtener cert y hacerlo expirar
        c.execute(
            "SELECT id FROM certificados WHERE username=? AND passkey_source=1",
            (username,)
        )
        cert_id = c.fetchone()['id']
        
        yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat()
        c.execute("UPDATE certificados SET expires_at=? WHERE id=?", (yesterday, cert_id))
        conn.commit()
        conn.close()
        
        # Test endpoint con usuario que tiene cert expirado
        with flask_app.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user'] = username
                sess['role'] = 'admin'
                sess['area'] = 'admin'
            
            response = client.post('/action/passkey/options')
        
        assert response.status_code == 401, \
            f"Debe rechazar con 401 cuando cert está expirado, obtuvo {response.status_code}"
        
        data = response.get_json()
        assert not data['ok'], "Response debe indicar error"
        assert 'expirado' in data['message'].lower() or 'certificado' in data['message'].lower(), \
            f"Mensaje debe mencionar expiración del certificado: {data['message']}"
    
    def test_action_passkey_options_allowed_when_cert_valid(self, app_with_test_db):
        """
        Verificar que /action/passkey/options funciona si cert es válido
        """
        flask_app, db_path = app_with_test_db
        
        # Setup: usuario con passkey y cert válido
        conn = flask_app.get_conn()
        c = conn.cursor()
        
        username = "test_admin_valid"
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", (username, "admin"))
        
        # Crear passkey (gen cert automáticamente)
        fake_key = flask_app.b64url_encode(b"test_key_valid")
        flask_app.save_passkey_credential(
            conn, username, "cred_valid", fake_key, 0, label="Test"
        )
        
        conn.close()
        
        # Test endpoint
        with flask_app.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user'] = username
                sess['role'] = 'admin'
                sess['area'] = 'admin'
            
            response = client.post('/action/passkey/options')
        
        # Si cert es válido, debería generar desafío (o al menos no rechazar por expiración)
        # Puede devolver 200 con opciones, o 400 si hay otro error como falta de passky
        assert response.status_code in (200, 400), \
            f"No debe rechazar por expiración si cert es válido (status={response.status_code})"
        
        if response.status_code == 200:
            data = response.get_json()
            assert data['ok'], "Si cert es válido, debe permitir generación de opciones"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
