"""
Tests E2E para Passkey ↔ Certificate PKI Integration (Fase 2)

Validar flujo completo:
1. Registrar passkey → certificado generado automáticamente
2. Certificado vinculado correctamente al passkey
3. Expiración de cert → passkeys deshabilitados automáticamente
"""

import sqlite3
import tempfile
import os
import sys
import datetime
import pytest
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


class TestPasskeyCertificateIntegration:
    """Tests e2e del flujo passkey → certificado"""
    
    def test_register_passkey_generates_certificate_automatically(self, isolate_db_env):
        """
        E2E: Registrar passkey → certificado generado automáticamente
        
        Flujo:
        1. Crear usuario
        2. Guardar primer passkey
        3. Verificar certificado fue generado
        4. Verificar vinculación entre passkey y cert
        """
        from app import get_conn, save_passkey_credential, b64url_encode
        
        conn = get_conn()
        c = conn.cursor()
        
        # 1. Crear usuario
        username = "e2e_test_user_001"
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", (username, "admin"))
        conn.commit()
        
        # 2. Guardar primer passkey (debe generar cert automáticamente)
        fake_public_key = b64url_encode(b"test_public_key_data")
        passkey_id = save_passkey_credential(
            conn, username, "cred_001", fake_public_key, 0,
            aaguid="aaguid_test", label="Test Passkey"
        )
        
        assert passkey_id is not None, "Passkey no se guardó"
        
        # 3. Verificar que se generó certificado
        c.execute(
            "SELECT id, passkey_source FROM certificados WHERE username=? AND passkey_source=1",
            (username,)
        )
        cert = c.fetchone()
        
        assert cert is not None, "Certificado no fue generado automáticamente"
        cert_id = cert['id']
        
        # 4. Verificar vinculación entre passkey y cert
        c.execute(
            "SELECT user_cert_id FROM passkey_credentials WHERE id=?",
            (passkey_id,)
        )
        pk = c.fetchone()
        
        assert pk['user_cert_id'] == cert_id, "Passkey no está vinculado al certificado"
        
        conn.close()
    
    def test_second_passkey_uses_same_certificate(self, isolate_db_env):
        """
        E2E: Segundo passkey del mismo usuario usa el mismo certificado
        
        Arquitectura N:1: Un certificado por usuario, múltiples passkeys
        """
        from app import get_conn, save_passkey_credential, b64url_encode
        
        conn = get_conn()
        c = conn.cursor()
        
        # Setup
        username = "e2e_test_user_002"
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", (username, "admin"))
        conn.commit()
        
        # Guardar primer passkey
        fake_key = b64url_encode(b"key1")
        pk_id_1 = save_passkey_credential(conn, username, "cred_001", fake_key, 0)
        
        # Obtener certificado generado
        c.execute("SELECT id FROM certificados WHERE username=? AND passkey_source=1", (username,))
        first_cert_id = c.fetchone()['id']
        
        # Guardar segundo passkey
        fake_key_2 = b64url_encode(b"key2")
        pk_id_2 = save_passkey_credential(conn, username, "cred_002", fake_key_2, 0)
        
        # Verificar que ambos passkeys usan el MISMO certificado
        c.execute("SELECT user_cert_id FROM passkey_credentials WHERE id=?", (pk_id_1,))
        pk1_cert_id = c.fetchone()['user_cert_id']
        
        c.execute("SELECT user_cert_id FROM passkey_credentials WHERE id=?", (pk_id_2,))
        pk2_cert_id = c.fetchone()['user_cert_id']
        
        assert pk1_cert_id == pk2_cert_id == first_cert_id, \
            "Múltiples passkeys deben usar el mismo certificado (N:1)"
        
        # Verificar contador de passkeys en certificado
        c.execute("SELECT num_passkeys_using FROM certificados WHERE id=?", (first_cert_id,))
        count = c.fetchone()['num_passkeys_using']
        
        assert count == 2, f"Certificado debe registrar 2 passkeys, tiene {count}"
        
        conn.close()
    
    def test_certificate_expiration_disables_passkeys(self, isolate_db_env):
        """
        E2E: Certificado expirado → todos sus passkeys se deshabilitan automáticamente
        
        Ciclo de vida vinculado:
        - Cert expira → check_certificate_expiration() los deshabilita
        - Passkeys quedan con status='deshabilitado_cert_exp'
        """
        from app import (get_conn, save_passkey_credential, check_certificate_expiration,
                         b64url_encode, parse_datetime)
        
        conn = get_conn()
        c = conn.cursor()
        
        # Setup
        username = "e2e_test_user_003"
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", (username, "admin"))
        conn.commit()
        
        # Crear passkey (genera cert automáticamente)
        fake_key = b64url_encode(b"key_exp")
        save_passkey_credential(conn, username, "cred_exp", fake_key, 0)
        
        # Obtener certificado generado
        c.execute("SELECT id FROM certificados WHERE username=? AND passkey_source=1", (username,))
        cert_id = c.fetchone()['id']
        
        # Modificar fecha de expiración a ayer (simular expiración)
        yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).isoformat()
        c.execute("UPDATE certificados SET expires_at=? WHERE id=?", (yesterday, cert_id))
        conn.commit()
        
        # Verificar que passkey está activo antes de expiración
        c.execute("SELECT status FROM passkey_credentials WHERE username=?", (username,))
        initial_status = c.fetchone()['status']
        assert initial_status == 'activo', f"Passkey debe estar activo, está {initial_status}"
        
        # Ejecutar verificación de expiración
        cert_valid, msg = check_certificate_expiration(conn, username)
        
        assert not cert_valid, "check_certificate_expiration debe retornar False para cert expirado"
        assert "expirado" in msg.lower(), "Mensaje debe mencionar expiración"
        
        # Verificar que passkey se deshabilitó
        c.execute("SELECT status FROM passkey_credentials WHERE username=?", (username,))
        disabled_status = c.fetchone()['status']
        
        assert disabled_status == 'deshabilitado_cert_exp', \
            f"Passkey debe estar deshabilitado, está {disabled_status}"
        
        # Verificar que certificado está marcado como expirado
        c.execute("SELECT status FROM certificados WHERE id=?", (cert_id,))
        cert_status = c.fetchone()['status']
        
        assert cert_status == 'expirado', f"Certificado debe estar expirado, está {cert_status}"
        
        conn.close()
    
    def test_valid_certificate_does_not_disable_passkeys(self, isolate_db_env):
        """
        E2E: Certificado válido NO deshabilita passkeys
        """
        from app import get_conn, save_passkey_credential, check_certificate_expiration, b64url_encode
        
        conn = get_conn()
        c = conn.cursor()
        
        # Setup
        username = "e2e_test_user_004"
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", (username, "admin"))
        conn.commit()
        
        # Crear passkey
        fake_key = b64url_encode(b"key_valid")
        save_passkey_credential(conn, username, "cred_valid", fake_key, 0)
        
        # Verificación de expiración para cert válido
        cert_valid, msg = check_certificate_expiration(conn, username)
        
        # Cert no expiró, así que passkey debe seguir activo
        c.execute("SELECT status FROM passkey_credentials WHERE username=?", (username,))
        status = c.fetchone()['status']
        
        # Si cert era válido, passkey sigue activo
        # (Si no había cert, también retorna True, así que sigue activo)
        assert status == 'activo', f"Passkey debe seguir activo, está {status}"
        
        conn.close()
    
    def test_passkey_increment_counter(self, isolate_db_env):
        """
        E2E: Contador de passkeys se incrementa correctamente
        """
        from app import get_conn, save_passkey_credential, b64url_encode
        
        conn = get_conn()
        c = conn.cursor()
        
        username = "e2e_test_user_005"
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", (username, "admin"))
        conn.commit()
        
        # Primer passkey
        save_passkey_credential(conn, username, "cred_1", b64url_encode(b"k1"), 0)
        
        c.execute("SELECT id FROM certificados WHERE username=? AND passkey_source=1", (username,))
        cert_id = c.fetchone()['id']
        
        c.execute("SELECT num_passkeys_using FROM certificados WHERE id=?", (cert_id,))
        count_1 = c.fetchone()['num_passkeys_using']
        assert count_1 == 1
        
        # Segundo passkey
        save_passkey_credential(conn, username, "cred_2", b64url_encode(b"k2"), 0)
        
        c.execute("SELECT num_passkeys_using FROM certificados WHERE id=?", (cert_id,))
        count_2 = c.fetchone()['num_passkeys_using']
        assert count_2 == 2
        
        # Tercer passkey
        save_passkey_credential(conn, username, "cred_3", b64url_encode(b"k3"), 0)
        
        c.execute("SELECT num_passkeys_using FROM certificados WHERE id=?", (cert_id,))
        count_3 = c.fetchone()['num_passkeys_using']
        assert count_3 == 3
        
        conn.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
