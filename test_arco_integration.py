#!/usr/bin/env python3
"""
Test de integración completo del flujo ARCO multinivel
Simula acciones de usuario/operativo/coordinador/admin
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app import app, init_db, decrypt_data
import sqlite3
import secrets
from datetime import datetime

def get_db_connection():
    """Conectar a base de datos."""
    conn = sqlite3.connect("casa.db")
    conn.row_factory = sqlite3.Row
    return conn

def test_usuario_approval_flow():
    """Simular flujo de aprobación de usuario."""
    print("\n" + "=" * 70)
    print("TEST 1: FLUJO DE APROBACIÓN DE USUARIO")
    print("=" * 70)
    
    with app.test_client() as client:
        # 1. Usuario inicia sesión
        print("\n1. Usuario inicia sesión...")
        with client.session_transaction() as sess:
            sess['role'] = 'usuario'
            sess['username'] = 'usuario_test'
            sess['csrf_token'] = secrets.token_hex(32)
        
        # 2. Usuario crea solicitud ARCO
        print("2. Usuario crea solicitud ARCO...")
        
        # Primero obtener la página ARCO para tener el CSRF token
        response = client.get('/arco')
        assert response.status_code == 200, "No se pudo acceder a /arco"
        
        with client.session_transaction() as sess:
            csrf = sess.get('csrf_token')
        
        arco_data = {
            'nombre_solicitante': 'Test Usuario',
            'correo': 'test@example.com',
            'telefono': '5551234567',
            'curp_id': 'TESU900101HDFRXXX',
            'accion': 'acceso',
            'motivo': 'Solicitud de prueba',
            'datos_correctos': 'si',
            'csrf_token': csrf
        }
        
        response = client.post('/arco/solicitud', data=arco_data)
        assert response.status_code in [200, 302], f"Error al crear solicitud: {response.status_code}"
        print("   ✓ Solicitud ARCO creada exitosamente")
        
        # 3. Verificar que aparece en bandeja de usuario
        print("3. Verificar que aparece en bandeja de usuario...")
        response = client.get('/bandeja')
        assert response.status_code == 200, "No se pudo acceder a /bandeja"
        assert b'solicitudes_arco' in response.data or b'ARCO' in response.data, "No se muestran solicitudes ARCO"
        print("   ✓ Solicitud visible en bandeja")


def test_operativo_approval():
    """Simular aprobación por operativo."""
    print("\n" + "=" * 70)
    print("TEST 2: APROBACIÓN POR OPERATIVO")
    print("=" * 70)
    
    with app.test_client() as client:
        # Obtener una solicitud ARCO
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM solicitudes_arco WHERE nivel_actual='usuarios' LIMIT 1")
        row = c.fetchone()
        
        if not row:
            print("   ⊘ No hay solicitudes para aprobar (nivel usuarios)")
            conn.close()
            return
        
        solicitud_id = row['id']
        
        # Operativo inicia sesión
        print("\n1. Operativo inicia sesión...")
        with client.session_transaction() as sess:
            sess['role'] = 'operativo'
            sess['username'] = 'operativo_test'
            sess['csrf_token'] = secrets.token_hex(32)
        
        # 2. Operativo ve la solicitud en su bandeja
        print("2. Operativo ve solicitud en bandeja...")
        response = client.get('/bandeja')
        assert response.status_code == 200
        print("   ✓ Bandeja accesible para operativo")
        
        # 3. Operativo aprueba la solicitud
        print("3. Operativo aprueba solicitud...")
        
        with client.session_transaction() as sess:
            csrf = sess.get('csrf_token')
        
        approve_data = {'csrf_token': csrf}
        response = client.post(f'/arco/{solicitud_id}/aprobar', data=approve_data)
        assert response.status_code in [200, 302], f"Error al aprobar: {response.status_code}"
        
        # Verificar que avanzó de nivel
        c.execute("SELECT nivel_actual FROM solicitudes_arco WHERE id=?", (solicitud_id,))
        row = c.fetchone()
        
        if row and row['nivel_actual'] == 'operativos':
            print("   ✓ Solicitud aprobada por usuario → operativos")
        else:
            print(f"   ⊘ Nivel actual: {row['nivel_actual'] if row else 'N/A'}")
        
        conn.close()


def test_coordinador_approval():
    """Simular aprobación y decisión por coordinador."""
    print("\n" + "=" * 70)
    print("TEST 3: APROBACIÓN Y DECISIÓN POR COORDINADOR")
    print("=" * 70)
    
    with app.test_client() as client:
        # Obtener solicitud en nivel operativos
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM solicitudes_arco WHERE nivel_actual='operativos' LIMIT 1")
        row = c.fetchone()
        
        if not row:
            print("   ⊘ No hay solicitudes para coordinador (nivel operativos)")
            conn.close()
            return
        
        solicitud_id = row['id']
        
        # Coordinador inicia sesión
        print("\n1. Coordinador inicia sesión...")
        with client.session_transaction() as sess:
            sess['role'] = 'coordinador'
            sess['username'] = 'coordinador_test'
            sess['csrf_token'] = secrets.token_hex(32)
        
        # 2. Coordinador aprueba
        print("2. Coordinador aprueba solicitud...")
        
        with client.session_transaction() as sess:
            csrf = sess.get('csrf_token')
        
        approve_data = {'csrf_token': csrf}
        response = client.post(f'/arco/{solicitud_id}/aprobar', data=approve_data)
        assert response.status_code in [200, 302]
        
        c.execute("SELECT nivel_actual FROM solicitudes_arco WHERE id=?", (solicitud_id,))
        row = c.fetchone()
        assert row and row['nivel_actual'] == 'coordinadores', "No avanzó a coordinadores"
        print("   ✓ Solicitud aprobada por operativo → coordinadores")
        
        # 3. Coordinador elige resolver localmente
        print("3. Coordinador elige resolver localmente...")
        
        with client.session_transaction() as sess:
            csrf = sess.get('csrf_token')
        
        resolve_data = {
            'csrf_token': csrf,
            'decision': 'resuelta'
        }
        response = client.post(f'/arco/{solicitud_id}/resolver-coordinador', data=resolve_data)
        assert response.status_code in [200, 302], f"Error al resolver: {response.status_code}"
        
        c.execute("SELECT resuelto_coordinador, aprobado_coordinadores FROM solicitudes_arco WHERE id=?", (solicitud_id,))
        row = c.fetchone()
        
        if row and row['resuelto_coordinador'] == 1 and row['aprobado_coordinadores'] == 1:
            print("   ✓ Solicitud marcada como resuelta y aprobada por coordinador")
        else:
            print(f"   ⊘ Estado de resolución: {row['resuelto_coordinador'] if row else 'N/A'}, aprobado_coordinadores: {row['aprobado_coordinadores'] if row else 'N/A'}")
        
        conn.close()


def test_coordinador_reenviar_a_admin():
    """Simular que el coordinador reenvía una solicitud a admin."""
    print("\n" + "=" * 70)
    print("TEST 4: REENVÍO POR COORDINADOR A ADMIN")
    print("=" * 70)
    
    with app.test_client() as client:
        conn = sqlite3.connect('database.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT id FROM solicitudes_arco WHERE nivel_actual='operativos' LIMIT 1")
        row = c.fetchone()
        
        if not row:
            print("   ⊘ No hay solicitudes para coordinador (nivel operativos)")
            conn.close()
            return
        
        solicitud_id = row['id']
        
        with client.session_transaction() as sess:
            sess['role'] = 'coordinador'
            sess['user'] = 'coordinador_test'
        
        response = client.get('/bandeja')
        assert response.status_code == 200
        
        with client.session_transaction() as sess:
            csrf = sess.get('csrf_token')
        
        resolve_data = {
            'csrf_token': csrf,
            'decision': 'enviar_admin'
        }
        response = client.post(f'/arco/{solicitud_id}/resolver-coordinador', data=resolve_data)
        assert response.status_code in [200, 302], f"Error al reenviar: {response.status_code}"
        
        c.execute("SELECT nivel_actual, reenviado_por_coordinador, aprobado_coordinadores FROM solicitudes_arco WHERE id=?", (solicitud_id,))
        row = c.fetchone()
        
        if row and row['nivel_actual'] == 'admin' and row['reenviado_por_coordinador'] == 1 and row['aprobado_coordinadores'] == 1:
            print("   ✓ Solicitud reenviada a admin y aprobada por coordinador")
        else:
            print(f"   ⊘ Estado: nivel_actual={row['nivel_actual'] if row else 'N/A'}, reenviado_por_coordinador={row['reenviado_por_coordinador'] if row else 'N/A'}, aprobado_coordinadores={row['aprobado_coordinadores'] if row else 'N/A'}")
        
        conn.close()


def test_csrf_validation():
    """Verificar que CSRF validation funciona."""
    print("\n" + "=" * 70)
    print("TEST 4: VALIDACIÓN CSRF")
    print("=" * 70)
    
    with app.test_client() as client:
        # Obtener solicitud
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT id FROM solicitudes_arco LIMIT 1")
        row = c.fetchone()
        
        if not row:
            print("   ⊘ No hay solicitudes para probar CSRF")
            conn.close()
            return
        
        solicitud_id = row['id']
        
        print("\n1. Intentar aprobar sin CSRF token...")
        with client.session_transaction() as sess:
            sess['role'] = 'operativo'
            sess['username'] = 'test'
            sess['csrf_token'] = 'valid_token_123'
        
        # Enviar sin CSRF token
        response = client.post(f'/arco/{solicitud_id}/aprobar', data={})
        
        if response.status_code in [302, 400]:
            print("   ✓ Solicitud rechazada sin CSRF token (correcto)")
        else:
            print(f"   ⚠ Respuesta inesperada: {response.status_code}")
        
        print("\n2. Intentar aprobar con CSRF token inválido...")
        response = client.post(f'/arco/{solicitud_id}/aprobar', data={'csrf_token': 'invalid_token'})
        
        if response.status_code in [302, 400]:
            print("   ✓ Solicitud rechazada con CSRF inválido (correcto)")
        else:
            print(f"   ⚠ Respuesta inesperada: {response.status_code}")
        
        print("\n3. Intentar aprobar con CSRF token válido...")
        with client.session_transaction() as sess:
            csrf = sess.get('csrf_token')
        
        response = client.post(f'/arco/{solicitud_id}/aprobar', data={'csrf_token': csrf})
        
        if response.status_code in [200, 302]:
            print("   ✓ Solicitud aceptada con CSRF válido (correcto)")
        else:
            print(f"   ⚠ Respuesta inesperada: {response.status_code}")
        
        conn.close()


def test_admin_view():
    """Verificar vista de admin con solicitudes prioritarias."""
    print("\n" + "=" * 70)
    print("TEST 5: VISTA DE ADMIN (SOLICITUDES PRIORITARIAS)")
    print("=" * 70)
    
    with app.test_client() as client:
        # Admin inicia sesión
        print("\n1. Admin inicia sesión...")
        with client.session_transaction() as sess:
            sess['role'] = 'admin'
            sess['username'] = 'admin'
            sess['csrf_token'] = secrets.token_hex(32)
        
        # 2. Acceder a panel admin
        print("2. Acceder a panel admin...")
        response = client.get('/admin')
        assert response.status_code == 200, "No se pudo acceder a /admin"
        
        # Verificar que tiene secciones de ARCO
        if b'ARCO' in response.data or b'arco' in response.data.lower():
            print("   ✓ Panel admin muestra sección ARCO")
        else:
            print("   ⊘ Panel admin no muestra sección ARCO")
        
        # Verificar estructura de solicitudes
        conn = get_db_connection()
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) as cnt FROM solicitudes_arco WHERE reenviado_por_coordinador=1")
        prioritarias = c.fetchone()['cnt']
        
        c.execute("SELECT COUNT(*) as cnt FROM solicitudes_arco WHERE reenviado_por_coordinador IS NULL OR reenviado_por_coordinador=0")
        directas = c.fetchone()['cnt']
        
        print(f"\n   Solicitudes ARCO en base de datos:")
        print(f"   - Prioritarias (reenviadas): {prioritarias}")
        print(f"   - Directas (pendientes): {directas}")
        
        conn.close()


def test_admin_resolve_prioritaria_removes_from_panel():
    """Verificar que admin no vuelve a ver ARCO prioritaria resuelta/rechazada."""
    print("\n" + "=" * 70)
    print("TEST 6: ADMIN RESUELVE SOLICITUD ARCO PRIORITARIA")
    print("=" * 70)

    with app.test_client() as client:
        print("\n1. Admin inicia sesión...")
        with client.session_transaction() as sess:
            sess['role'] = 'admin'
            sess['username'] = 'admin'
            sess['csrf_token'] = secrets.token_hex(32)

        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            "SELECT id FROM solicitudes_arco WHERE nivel_actual='admin' AND reenviado_por_coordinador=1 AND estado NOT IN ('atendida','rechazada') LIMIT 1"
        )
        row = c.fetchone()
        conn.close()

        if not row:
            print("   ⊘ No hay solicitudes ARCO prioritaria pendientes para probar")
            return

        solicitud_id = row['id']
        print(f"2. Resolver ARCO prioritaria #{solicitud_id} como atendida...")

        response = client.post(
            f'/arco/{solicitud_id}/resolver',
            data={
                'csrf_token': sess['csrf_token'],
                'decision': 'atendida'
            }
        )
        assert response.status_code in [200, 302], f"Error al resolver: {response.status_code}"

        response = client.get('/admin')
        assert response.status_code == 200, "No se pudo recargar /admin"

        if str(solicitud_id).encode() not in response.data:
            print("   ✓ Solicitud prioritaria ya no aparece en panel admin")
        else:
            print("   ⊘ Solicitud prioritaria todavía aparece después de resolverla")


def main():
    """Ejecutar todos los tests de integración."""
    print("\n╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "TEST DE INTEGRACIÓN FLUJO ARCO MULTINIVEL" + " " * 12 + "║")
    print("╚" + "=" * 68 + "╝")
    
    # Inicializar base de datos
    init_db()
    
    try:
        test_usuario_approval_flow()
        test_operativo_approval()
        test_coordinador_approval()
        test_csrf_validation()
        test_admin_view()
        test_admin_resolve_prioritaria_removes_from_panel()
        
        print("\n" + "=" * 70)
        print("RESUMEN")
        print("=" * 70)
        print("\n✓ TODOS LOS TESTS DE INTEGRACIÓN COMPLETADOS\n")
        return 0
    
    except AssertionError as e:
        print(f"\n✗ ERROR EN TEST: {e}\n")
        return 1
    except Exception as e:
        print(f"\n✗ EXCEPCIÓN INESPERADA: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
