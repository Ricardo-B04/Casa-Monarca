"""
Tests for Passkey ↔ Certificate PKI linking (Fase 1: Infrastructure)

Tests de unitarios para validar que:
1. Las columnas se crean correctamente en BD
2. derive_certificate_from_first_passkey() genera certificados
3. link_passkey_to_certificate() vincula correctamente
4. No hay duplicación de certificados
"""

import sqlite3
import tempfile
import os
import sys
import datetime
import pytest
from pathlib import Path
from unittest.mock import patch

# Importar desde app.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def isolate_db_env():
    """Aislar cada test con su propia BD temporal y cerrar después"""
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    db_path = temp_db.name
    temp_db.close()
    
    # Patch get_conn para usar BD temporal
    import app
    original_get_conn = app.get_conn
    
    def get_test_conn():
        conn = sqlite3.connect(db_path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    
    app.get_conn = get_test_conn
    
    # Inicializar BD de test
    app.init_db()
    
    yield db_path
    
    # Cleanup: restaurar original
    app.get_conn = original_get_conn
    
    # Cerrar todas las conexiones a la BD
    try:
        conn = original_get_conn()
        conn.close()
    except:
        pass
    
    # Eliminar archivo temporal
    try:
        os.unlink(db_path)
    except:
        pass


class TestPasskeyCertificateMigration:
    """Tests para la migración de columnas en BD"""
    
    def test_columns_created(self, isolate_db_env):
        """Verificar que las columnas necesarias existen"""
        from app import get_conn
        
        conn = get_conn()
        c = conn.cursor()
        
        # Verificar passkey_credentials tiene las columnas nuevas
        c.execute("PRAGMA table_info(passkey_credentials)")
        columns = {row[1]: row[2] for row in c.fetchall()}
        
        assert 'user_cert_id' in columns, "Falta columna user_cert_id"
        assert 'generated_cert_at' in columns, "Falta columna generated_cert_at"
        assert 'cert_revoked_reason' in columns, "Falta columna cert_revoked_reason"
        
        # Verificar certificados tiene las columnas nuevas
        c.execute("PRAGMA table_info(certificados)")
        columns = {row[1]: row[2] for row in c.fetchall()}
        
        assert 'passkey_source' in columns, "Falta columna passkey_source"
        assert 'num_passkeys_using' in columns, "Falta columna num_passkeys_using"
        
        conn.close()
    
    def test_indices_created(self, isolate_db_env):
        """Verificar que los índices se crean correctamente"""
        from app import get_conn
        
        conn = get_conn()
        c = conn.cursor()
        
        # Verificar índices de passkeys
        c.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_passkey%'")
        indices = [row[0] for row in c.fetchall()]
        
        assert 'idx_passkey_user_cert' in indices, "Falta índice idx_passkey_user_cert"
        
        conn.close()


class TestDeriveCertificateFromFirstPasskey:
    """Tests para derive_certificate_from_first_passkey()"""
    
    def test_generate_first_certificate(self, isolate_db_env):
        """Generar certificado para usuario sin certificado previo"""
        from app import get_conn, derive_certificate_from_first_passkey
        
        conn = get_conn()
        
        # Crear usuario de prueba (sin conflicto con datos iniciales)
        c = conn.cursor()
        c.execute(
            "INSERT INTO usuarios (username, rol) VALUES (?, ?)",
            ("cert_testuser_001", "admin")
        )
        conn.commit()
        
        # Generar certificado
        cert_id = derive_certificate_from_first_passkey(conn, "cert_testuser_001", "admin")
        
        assert cert_id is not None, "No se generó certificado"
        assert isinstance(cert_id, int), "cert_id debe ser entero"
        
        # Verificar que se insertó en BD
        c.execute("SELECT id, username, status, passkey_source FROM certificados WHERE id=?", (cert_id,))
        cert = c.fetchone()
        
        assert cert is not None, "Certificado no encontrado en BD"
        assert cert['username'] == 'cert_testuser_001', "Username incorrecto"
        assert cert['status'] == 'activo', "Status debe ser activo"
        assert cert['passkey_source'] == 1, "passkey_source debe ser 1"
        
        conn.close()
    
    def test_no_duplicate_certificates(self, isolate_db_env):
        """No generar duplicados si ya existe certificado activo"""
        from app import get_conn, derive_certificate_from_first_passkey
        
        conn = get_conn()
        
        c = conn.cursor()
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", ("cert_testuser_002", "admin"))
        conn.commit()
        
        # Generar primer certificado
        cert_id_1 = derive_certificate_from_first_passkey(conn, "cert_testuser_002", "admin")
        assert cert_id_1 is not None
        
        # Intentar generar segundo (debe retornar el mismo)
        cert_id_2 = derive_certificate_from_first_passkey(conn, "cert_testuser_002", "admin")
        
        assert cert_id_1 == cert_id_2, "Debe retornar el mismo cert_id, no duplicar"
        
        # Verificar solo hay un certificado
        c.execute("SELECT COUNT(*) as cnt FROM certificados WHERE username=? AND passkey_source=1", ("cert_testuser_002",))
        count = c.fetchone()['cnt']
        
        assert count == 1, f"Esperaba 1 certificado, encontré {count}"
        
        conn.close()
    
    def test_certificate_fields_valid(self, isolate_db_env):
        """Verificar que el certificado tiene campos válidos"""
        from app import get_conn, derive_certificate_from_first_passkey
        
        conn = get_conn()
        
        c = conn.cursor()
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", ("cert_testuser_003", "coordinador"))
        conn.commit()
        
        cert_id = derive_certificate_from_first_passkey(conn, "cert_testuser_003", "coordinador")
        
        c.execute(
            """SELECT 
                cert_fingerprint, public_fp, issued_at, expires_at,
                pem_hash, cert_serial, algorithm 
            FROM certificados WHERE id=?""",
            (cert_id,)
        )
        cert = c.fetchone()
        
        # Validar campos no nulos
        assert cert['cert_fingerprint'] is not None, "cert_fingerprint no debe ser nulo"
        assert cert['public_fp'] is not None, "public_fp no debe ser nulo"
        assert cert['issued_at'] is not None, "issued_at no debe ser nulo"
        assert cert['expires_at'] is not None, "expires_at no debe ser nulo"
        assert cert['pem_hash'] is not None, "pem_hash no debe ser nulo"
        assert cert['cert_serial'] is not None, "cert_serial no debe ser nulo"
        assert cert['algorithm'] is not None, "algorithm no debe ser nulo"
        
        # Validar que issued_at < expires_at
        issued = datetime.datetime.fromisoformat(cert['issued_at'])
        expires = datetime.datetime.fromisoformat(cert['expires_at'])
        assert issued < expires, "issued_at debe ser antes que expires_at"
        
        conn.close()


class TestLinkPasskeyToCertificate:
    """Tests para link_passkey_to_certificate()"""
    
    def test_link_passkey_to_cert(self, isolate_db_env):
        """Vincular un passkey a un certificado"""
        from app import get_conn, derive_certificate_from_first_passkey, link_passkey_to_certificate
        
        conn = get_conn()
        c = conn.cursor()
        
        # Setup: usuario, certificado, passkey
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", ("cert_testuser_004", "admin"))
        conn.commit()
        
        cert_id = derive_certificate_from_first_passkey(conn, "cert_testuser_004", "admin")
        
        # Crear un passkey simulado
        c.execute(
            """INSERT INTO passkey_credentials 
            (username, credential_id, public_key_b64, sign_count, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("cert_testuser_004", "cred123_pk", "dGVzdA==", 0, "activo", str(datetime.datetime.now()), str(datetime.datetime.now()))
        )
        conn.commit()
        passkey_id = c.lastrowid
        
        # Vincular
        result = link_passkey_to_certificate(conn, passkey_id, cert_id, "cert_testuser_004")
        
        assert result is True, "link_passkey_to_certificate debe retornar True"
        
        # Verificar que se vinculó
        c.execute(
            "SELECT user_cert_id, generated_cert_at FROM passkey_credentials WHERE id=?",
            (passkey_id,)
        )
        pk = c.fetchone()
        
        assert pk['user_cert_id'] == cert_id, "passkey debe estar vinculado a cert_id"
        assert pk['generated_cert_at'] is not None, "generated_cert_at debe estar poblado"
        
        conn.close()
    
    def test_increment_passkey_count(self, isolate_db_env):
        """Verificar que incrementa el contador de passkeys"""
        from app import get_conn, derive_certificate_from_first_passkey, link_passkey_to_certificate
        
        conn = get_conn()
        c = conn.cursor()
        
        # Setup
        c.execute("INSERT INTO usuarios (username, rol) VALUES (?, ?)", ("cert_testuser_005", "admin"))
        conn.commit()
        
        cert_id = derive_certificate_from_first_passkey(conn, "cert_testuser_005", "admin")
        
        # Verificar contador inicial
        c.execute("SELECT num_passkeys_using FROM certificados WHERE id=?", (cert_id,))
        initial_count = c.fetchone()['num_passkeys_using']
        
        # Crear y vincular primer passkey
        c.execute(
            """INSERT INTO passkey_credentials 
            (username, credential_id, public_key_b64, sign_count, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("cert_testuser_005", "cred_a_pk5", "dGVzdA==", 0, "activo", str(datetime.datetime.now()), str(datetime.datetime.now()))
        )
        conn.commit()
        pk_id_1 = c.lastrowid
        
        link_passkey_to_certificate(conn, pk_id_1, cert_id, "cert_testuser_005")
        
        # Verificar contador incrementó
        c.execute("SELECT num_passkeys_using FROM certificados WHERE id=?", (cert_id,))
        count_after_1 = c.fetchone()['num_passkeys_using']
        
        assert count_after_1 == initial_count + 1, f"Contador debe incrementar (era {initial_count}, ahora {count_after_1})"
        
        # Crear y vincular segundo passkey
        c.execute(
            """INSERT INTO passkey_credentials 
            (username, credential_id, public_key_b64, sign_count, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("cert_testuser_005", "cred_b_pk5", "dGVzdA==", 0, "activo", str(datetime.datetime.now()), str(datetime.datetime.now()))
        )
        conn.commit()
        pk_id_2 = c.lastrowid
        
        link_passkey_to_certificate(conn, pk_id_2, cert_id, "cert_testuser_005")
        
        # Verificar contador incrementó de nuevo
        c.execute("SELECT num_passkeys_using FROM certificados WHERE id=?", (cert_id,))
        count_after_2 = c.fetchone()['num_passkeys_using']
        
        assert count_after_2 == count_after_1 + 1, f"Contador debe incrementar (era {count_after_1}, ahora {count_after_2})"
        
        conn.close()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

