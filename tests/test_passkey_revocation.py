"""
Tests para funciones de revocación de passkeys y certificados (Fase 3)

Casos:
1. Revocar un passkey individual
2. Revocar último passkey → también revoca certificado
3. Revocar certificado → revoca todos sus passkeys
4. Endpoints devuelven estructura correcta
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


@pytest.fixture(autouse=True)
def isolate_db_env():
    """Aislar cada test con su propia BD temporal"""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    db_path = temp_db.name
    temp_db.close()
    
    import app
    original_get_conn = app.get_conn
    
    def get_test_conn():
        conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    app.get_conn = get_test_conn
    app.init_db()
    
    yield db_path
    
    app.get_conn = original_get_conn
    
    try:
        conn = original_get_conn()
        conn.close()
    except:
        pass
    
    try:
        os.unlink(db_path)
    except:
        pass


class TestRevokePasskey:
    """Tests para revocación de passkeys individuales"""
    
    def test_revoke_passkey(self, isolate_db_env):
        """
        Revocar un passkey individual
        """
        from app import get_conn, save_passkey_credential, revoke_passkey, b64url_encode
        
        conn = get_conn()
        c = conn.cursor()
        
        # Setup
        username = "test_revoke_user_001"
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", (username, "admin"))
        conn.commit()
        
        # Crear passkey
        passkey_id = save_passkey_credential(
            conn, username, "cred_revoke", b64url_encode(b"key"), 0
        )
        
        # Verificar que está activo
        c.execute("SELECT status FROM passkey_credentials WHERE id=?", (passkey_id,))
        assert c.fetchone()['status'] == 'activo'
        
        # Revocar passkey
        success = revoke_passkey(conn, passkey_id, reason="test_revocation")
        assert success, "revoke_passkey debe retornar True"
        
        # Verificar que está revocado
        c.execute(
            "SELECT status, revocation_reason FROM passkey_credentials WHERE id=?",
            (passkey_id,)
        )
        pk = c.fetchone()
        assert pk['status'] == 'revocado', "Passkey debe estar revocado"
        assert 'test_revocation' in pk['revocation_reason'], \
            "Razón debe registrarse en revocation_reason"
        
        conn.close()
    
    def test_revoke_last_passkey_also_revokes_cert(self, isolate_db_env):
        """
        Revocar el último passkey de un usuario → también revoca su certificado
        
        N:1 lifecycle: Si es el último passkey, el certificado pierde su propósito
        """
        from app import get_conn, save_passkey_credential, revoke_passkey_and_cert, b64url_encode
        
        conn = get_conn()
        c = conn.cursor()
        
        # Setup: usuario con 1 passkey
        username = "test_revoke_user_002"
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", (username, "admin"))
        conn.commit()
        
        # Crear passkey (genera cert)
        passkey_id = save_passkey_credential(
            conn, username, "cred_last", b64url_encode(b"key"), 0
        )
        
        # Obtener cert_id
        c.execute(
            "SELECT user_cert_id FROM passkey_credentials WHERE id=?",
            (passkey_id,)
        )
        cert_id = c.fetchone()['user_cert_id']
        assert cert_id is not None, "Passkey debe tener cert_id"
        
        # Verificar cert está activo
        c.execute("SELECT status FROM certificados WHERE id=?", (cert_id,))
        assert c.fetchone()['status'] == 'activo'
        
        # Revocar el último passkey
        success, affected_certs = revoke_passkey_and_cert(
            conn, passkey_id, username, reason="test_revocation"
        )
        
        assert success, "Revocación debe ser exitosa"
        assert cert_id in affected_certs, \
            "Certificado debe estar en lista de afectados"
        
        # Verificar que passkey está revocado
        c.execute("SELECT status FROM passkey_credentials WHERE id=?", (passkey_id,))
        assert c.fetchone()['status'] == 'revocado'
        
        # Verificar que cert está revocado
        c.execute("SELECT status FROM certificados WHERE id=?", (cert_id,))
        cert_status = c.fetchone()['status']
        assert cert_status == 'revocado', \
            f"Certificado debe estar revocado cuando se revoca el último passkey, está {cert_status}"
        
        conn.close()
    
    def test_revoke_one_passkey_does_not_revoke_cert_if_others_exist(self, isolate_db_env):
        """
        Revocar UNA passkey cuando existen MÚLTIPLES → cert no se revoca
        """
        from app import get_conn, save_passkey_credential, revoke_passkey_and_cert, b64url_encode
        
        conn = get_conn()
        c = conn.cursor()
        
        # Setup: usuario con 2 passkeys
        username = "test_revoke_user_003"
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", (username, "admin"))
        conn.commit()
        
        # Crear primer passkey (genera cert)
        pk_id_1 = save_passkey_credential(
            conn, username, "cred_1", b64url_encode(b"key1"), 0
        )
        
        # Obtener cert_id
        c.execute("SELECT user_cert_id FROM passkey_credentials WHERE id=?", (pk_id_1,))
        cert_id = c.fetchone()['user_cert_id']
        
        # Crear segundo passkey (usa mismo cert)
        pk_id_2 = save_passkey_credential(
            conn, username, "cred_2", b64url_encode(b"key2"), 0
        )
        
        # Verificar ambos tienen mismo cert
        c.execute("SELECT user_cert_id FROM passkey_credentials WHERE id=?", (pk_id_2,))
        assert c.fetchone()['user_cert_id'] == cert_id
        
        # Revocar el primer passkey (quedan otros)
        success, affected_certs = revoke_passkey_and_cert(
            conn, pk_id_1, username, reason="test"
        )
        
        assert success
        
        # Certificado DEBE SEGUIR ACTIVO porque hay otro passkey
        c.execute("SELECT status FROM certificados WHERE id=?", (cert_id,))
        cert_status = c.fetchone()['status']
        assert cert_status == 'activo', \
            "Certificado debe seguir activo si hay otros passkeys activos"
        
        # Primer passkey está revocado
        c.execute("SELECT status FROM passkey_credentials WHERE id=?", (pk_id_1,))
        assert c.fetchone()['status'] == 'revocado'
        
        # Segundo passkey sigue activo
        c.execute("SELECT status FROM passkey_credentials WHERE id=?", (pk_id_2,))
        assert c.fetchone()['status'] == 'activo'
        
        conn.close()


class TestRevokeCertificate:
    """Tests para revocación de certificados"""
    
    def test_revoke_certificate_revokes_all_passkeys(self, isolate_db_env):
        """
        Revocar un certificado → revoca TODOS sus passkeys
        """
        from app import get_conn, save_passkey_credential, revoke_certificate_and_passkeys, b64url_encode
        
        conn = get_conn()
        c = conn.cursor()
        
        # Setup: usuario con 3 passkeys, 1 certificado
        username = "test_revoke_user_004"
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", (username, "admin"))
        conn.commit()
        
        # Crear 3 passkeys
        pk_ids = []
        for i in range(3):
            pk_id = save_passkey_credential(
                conn, username, f"cred_{i}", b64url_encode(f"key{i}".encode()), 0
            )
            pk_ids.append(pk_id)
        
        # Obtener cert_id
        c.execute(
            "SELECT user_cert_id FROM passkey_credentials WHERE id=?",
            (pk_ids[0],)
        )
        cert_id = c.fetchone()['user_cert_id']
        
        # Verificar que todos los passkeys tienen el mismo cert
        for pk_id in pk_ids:
            c.execute("SELECT user_cert_id FROM passkey_credentials WHERE id=?", (pk_id,))
            assert c.fetchone()['user_cert_id'] == cert_id
        
        # Revocar el certificado
        success, revoked_count = revoke_certificate_and_passkeys(
            conn, cert_id, reason="test_revocation"
        )
        
        assert success, "Revocación debe ser exitosa"
        assert revoked_count == 3, f"Deben revocarse 3 passkeys, se revocaron {revoked_count}"
        
        # Verificar certificado está revocado
        c.execute("SELECT status FROM certificados WHERE id=?", (cert_id,))
        assert c.fetchone()['status'] == 'revocado'
        
        # Verificar todos los passkeys están revocados
        for pk_id in pk_ids:
            c.execute("SELECT status FROM passkey_credentials WHERE id=?", (pk_id,))
            pk_status = c.fetchone()['status']
            assert pk_status == 'revocado', \
                f"Passkey {pk_id} debe estar revocado, está {pk_status}"
        
        conn.close()


class TestRevokeEndpoints:
    """Tests para endpoints de revocación"""
    
    def test_endpoint_passkey_status_structure(self, isolate_db_env):
        """
        Verificar que /admin/pki/passkey-certificate-status devuelve estructura correcta
        """
        import app as flask_app
        
        # Setup
        conn = flask_app.get_conn()
        c = conn.cursor()
        
        username = "test_endpoint_user_001"
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", (username, "admin"))
        conn.commit()
        
        # Crear 2 passkeys
        for i in range(2):
            flask_app.save_passkey_credential(
                conn, username, f"cred_{i}",
                flask_app.b64url_encode(f"key{i}".encode()), 0, label=f"Test Key {i}"
            )
        
        # Crear otro usuario con cert pero sin passkeys
        username2 = "test_endpoint_user_002"
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", (username2, "admin"))
        conn.commit()
        
        # Test endpoint con app
        flask_app.app.config['TESTING'] = True
        with flask_app.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user'] = 'admin_test'
                sess['role'] = 'admin'
            
            response = client.get('/admin/pki/passkey-certificate-status')
        
        assert response.status_code == 200, \
            f"Endpoint debe retornar 200, retornó {response.status_code}"
        
        data = response.get_json()
        assert data['ok'], "Response debe tener ok: true"
        
        # Verificar estructura del certificados
        certs = data['certificados']
        assert isinstance(certs, list), "certificados debe ser lista"
        assert len(certs) > 0, "Debe haber al menos 1 certificado"
        
        # Verificar estructura de cada certificado
        for cert in certs:
            assert 'cert_id' in cert
            assert 'username' in cert
            assert 'rol' in cert
            assert 'status' in cert
            assert 'num_passkeys_active' in cert
            assert 'passkeys' in cert, "Debe incluir lista de passkeys"
            
            # Verificar estructura de passkeys
            for pk in cert['passkeys']:
                assert 'id' in pk
                assert 'label' in pk
                assert 'status' in pk
                assert 'credential_id' in pk
        
        conn.close()
    
    def test_endpoint_revoke_passkey(self, isolate_db_env):
        """
        Verificar que /admin/pki/revoke-passkey funciona correctamente
        """
        import app as flask_app
        
        # Setup
        conn = flask_app.get_conn()
        c = conn.cursor()
        
        username = "test_endpoint_revoke_pk"
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", (username, "admin"))
        conn.commit()
        
        # Crear passkey
        passkey_id = flask_app.save_passkey_credential(
            conn, username, "cred_revoke", flask_app.b64url_encode(b"key"), 0
        )
        conn.close()
        
        # Test endpoint
        flask_app.app.config['TESTING'] = True
        with flask_app.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user'] = 'admin_test'
                sess['role'] = 'admin'
            
            response = client.post('/admin/pki/revoke-passkey', json={
                'passkey_id': passkey_id,
                'reason': 'test_revocation'
            })
        
        assert response.status_code == 200, \
            f"Endpoint debe retornar 200, retornó {response.status_code}"
        
        data = response.get_json()
        assert data['ok'], "Revocación debe ser exitosa"
        assert data['passkey_id'] == passkey_id
    
    def test_endpoint_revoke_certificate(self, isolate_db_env):
        """
        Verificar que /admin/pki/revoke-certificate funciona correctamente
        """
        import app as flask_app
        
        # Setup
        conn = flask_app.get_conn()
        c = conn.cursor()
        
        username = "test_endpoint_revoke_cert"
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", (username, "admin"))
        conn.commit()
        
        # Crear passkey (gen cert)
        passkey_id = flask_app.save_passkey_credential(
            conn, username, "cred_cert", flask_app.b64url_encode(b"key"), 0
        )
        
        # Obtener cert_id
        c.execute(
            "SELECT user_cert_id FROM passkey_credentials WHERE id=?",
            (passkey_id,)
        )
        cert_id = c.fetchone()['user_cert_id']
        conn.close()
        
        # Test endpoint
        flask_app.app.config['TESTING'] = True
        with flask_app.app.test_client() as client:
            with client.session_transaction() as sess:
                sess['user'] = 'admin_test'
                sess['role'] = 'admin'
            
            response = client.post('/admin/pki/revoke-certificate', json={
                'cert_id': cert_id,
                'reason': 'test_revocation'
            })
        
        assert response.status_code == 200, \
            f"Endpoint debe retornar 200, retornó {response.status_code}"
        
        data = response.get_json()
        assert data['ok'], "Revocación debe ser exitosa"
        assert data['cert_id'] == cert_id
        assert 'revoked_passkeys_count' in data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
