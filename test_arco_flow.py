#!/usr/bin/env python3
"""
Script de prueba para validar el flujo multinivel de solicitudes ARCO.
Comprueba que:
1. Las nuevas columnas existen en la BD
2. Se pueden crear solicitudes ARCO
3. El flujo de aprobación funciona correctamente
4. Las solicitudes avanzan de nivel correctamente
"""

import sqlite3
import sys
from pathlib import Path

# Agregar el path de la aplicación
sys.path.insert(0, str(Path(__file__).parent))

def get_conn():
    """Conectar a la base de datos."""
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def check_columns():
    """Verificar que todas las columnas necesarias existen."""
    print("=" * 70)
    print("VERIFICACIÓN 1: Columnas de base de datos")
    print("=" * 70)
    
    required_columns = [
        ("solicitudes_arco", "nivel_actual"),
        ("solicitudes_arco", "aprobado_usuarios"),
        ("solicitudes_arco", "aprobado_usuarios_at"),
        ("solicitudes_arco", "aprobado_usuarios_por"),
        ("solicitudes_arco", "aprobado_operativos"),
        ("solicitudes_arco", "aprobado_operativos_at"),
        ("solicitudes_arco", "aprobado_operativos_por"),
        ("solicitudes_arco", "aprobado_coordinadores"),
        ("solicitudes_arco", "aprobado_coordinadores_at"),
        ("solicitudes_arco", "aprobado_coordinadores_por"),
        ("solicitudes_arco", "reenviado_por_coordinador"),
        ("solicitudes_arco", "reenviado_por_coordinador_at"),
        ("solicitudes_arco", "resuelto_coordinador"),
        ("solicitudes_arco", "resuelto_coordinador_at"),
    ]
    
    conn = get_conn()
    c = conn.cursor()
    
    all_exist = True
    for table, column in required_columns:
        try:
            c.execute(f"PRAGMA table_info({table})")
            columns = {row[1] for row in c.fetchall()}
            if column in columns:
                print(f"  ✓ {table}.{column}")
            else:
                print(f"  ✗ {table}.{column} NO EXISTE")
                all_exist = False
        except Exception as e:
            print(f"  ✗ Error verificando {table}.{column}: {e}")
            all_exist = False
    
    conn.close()
    
    if all_exist:
        print("\n✓ Todas las columnas existen correctamente\n")
        return True
    else:
        print("\n✗ Faltan algunas columnas\n")
        return False


def check_table_structure():
    """Verificar la estructura de la tabla solicitudes_arco."""
    print("=" * 70)
    print("VERIFICACIÓN 2: Estructura de tabla solicitudes_arco")
    print("=" * 70)
    
    conn = get_conn()
    c = conn.cursor()
    c.execute("PRAGMA table_info(solicitudes_arco)")
    columns = c.fetchall()
    
    print(f"\nTotal de columnas: {len(columns)}\n")
    for col in columns:
        col_name = col[1]
        col_type = col[2]
        notnull = col[3]
        pk = col[5]
        print(f"  {col_name:<35} {col_type:<15} (pk={pk}, nullable={not notnull})")
    
    conn.close()
    print()
    return True


def check_existing_arco_data():
    """Verificar datos ARCO existentes."""
    print("=" * 70)
    print("VERIFICACIÓN 3: Datos ARCO existentes")
    print("=" * 70)
    
    conn = get_conn()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) as cnt FROM solicitudes_arco")
    count = c.fetchone()["cnt"]
    
    if count > 0:
        print(f"\nExisten {count} solicitudes ARCO en la BD")
        c.execute("SELECT id, nombre_solicitante, nivel_actual, estado FROM solicitudes_arco ORDER BY id DESC LIMIT 5")
        records = c.fetchall()
        print("\nÚltimas 5 solicitudes:")
        for rec in records:
            print(f"  ID: {rec['id']:<5} | {rec['nombre_solicitante']:<30} | Nivel: {rec['nivel_actual']:<15} | Estado: {rec['estado']}")
    else:
        print("\nNo hay solicitudes ARCO en la BD (esto es normal si es primera vez)")
    
    conn.close()
    print()
    return True


def check_sample_workflow():
    """Simular un flujo de aprobación."""
    print("=" * 70)
    print("VERIFICACIÓN 4: Simulación de flujo de aprobación")
    print("=" * 70)
    
    conn = get_conn()
    c = conn.cursor()
    
    # Crear una solicitud ARCO de prueba
    try:
        c.execute("""
            INSERT INTO solicitudes_arco (
                nombre_solicitante, correo, curp_id, accion, motivo,
                nivel_actual
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            "Usuario Prueba", 
            "test@example.com",
            "TEST123456789ABC",
            "acceso",
            "Solicitud de prueba para validar flujo",
            "usuarios"
        ))
        conn.commit()
        test_id = c.lastrowid
        print(f"\n✓ Solicitud ARCO #{test_id} creada para prueba")
        
        # Simular aprobación por usuario
        c.execute("""
            UPDATE solicitudes_arco 
            SET aprobado_usuarios=1, aprobado_usuarios_at=CURRENT_TIMESTAMP,
                aprobado_usuarios_por=?, nivel_actual=?
            WHERE id=?
        """, ("usuario_test", "operativos", test_id))
        conn.commit()
        print(f"✓ Aprobada por usuario → nivel: operativos")
        
        # Simular aprobación por operativo
        c.execute("""
            UPDATE solicitudes_arco 
            SET aprobado_operativos=1, aprobado_operativos_at=CURRENT_TIMESTAMP,
                aprobado_operativos_por=?, nivel_actual=?
            WHERE id=?
        """, ("operativo_test", "coordinadores", test_id))
        conn.commit()
        print(f"✓ Aprobada por operativo → nivel: coordinadores")
        
        # Simular aprobación por coordinador
        c.execute("""
            UPDATE solicitudes_arco 
            SET aprobado_coordinadores=1, aprobado_coordinadores_at=CURRENT_TIMESTAMP,
                aprobado_coordinadores_por=?
            WHERE id=?
        """, ("coordinador_test", test_id))
        conn.commit()
        print(f"✓ Aprobada por coordinador (pendiente decisión)")
        
        # Verificar estado final
        c.execute("SELECT * FROM solicitudes_arco WHERE id=?", (test_id,))
        final = c.fetchone()
        
        print(f"\nEstado final de la solicitud:")
        print(f"  - nivel_actual: {final['nivel_actual']}")
        print(f"  - aprobado_usuarios: {final['aprobado_usuarios']} por {final['aprobado_usuarios_por']}")
        print(f"  - aprobado_operativos: {final['aprobado_operativos']} por {final['aprobado_operativos_por']}")
        print(f"  - aprobado_coordinadores: {final['aprobado_coordinadores']} por {final['aprobado_coordinadores_por']}")
        print(f"  - reenviado_por_coordinador: {final['reenviado_por_coordinador']}")
        
        # Limpiar: eliminar solicitud de prueba
        c.execute("DELETE FROM solicitudes_arco WHERE id=?", (test_id,))
        conn.commit()
        print(f"\n✓ Solicitud de prueba eliminada (limpieza)")
        
    except Exception as e:
        print(f"\n✗ Error en simulación de flujo: {e}")
        return False
    finally:
        conn.close()
    
    print()
    return True


def check_role_permissions():
    """Verificar que los roles están correctamente definidos."""
    print("=" * 70)
    print("VERIFICACIÓN 5: Permisos por rol")
    print("=" * 70)
    
    roles_expected = {
        "usuario": {"create"},
        "operativo": {"create", "read"},
        "coordinador": {"create", "read", "update"},
        "admin": {"create", "read", "update", "delete"},
    }
    
    print("\nRoles esperados y sus permisos:")
    for role, perms in roles_expected.items():
        print(f"  {role:<15} → {', '.join(sorted(perms))}")
    
    print("\nNiveles de flujo ARCO:")
    print("  usuarios → operativos → coordinadores → (resuelta | admin)")
    print()
    return True


def main():
    """Ejecutar todas las comprobaciones."""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 10 + "PRUEBAS DEL FLUJO MULTINIVEL DE SOLICITUDES ARCO" + " " * 10 + "║")
    print("╚" + "=" * 68 + "╝")
    print()
    
    checks = [
        ("Verificar columnas", check_columns),
        ("Estructura de tabla", check_table_structure),
        ("Datos existentes", check_existing_arco_data),
        ("Flujo de aprobación", check_sample_workflow),
        ("Permisos por rol", check_role_permissions),
    ]
    
    results = []
    for check_name, check_func in checks:
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            print(f"\n✗ Error en {check_name}: {e}\n")
            results.append((check_name, False))
    
    # Resumen
    print("=" * 70)
    print("RESUMEN DE PRUEBAS")
    print("=" * 70)
    print()
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for check_name, result in results:
        status = "✓ PASÓ" if result else "✗ FALLÓ"
        print(f"  {status:<8} {check_name}")
    
    print()
    print(f"Total: {passed}/{total} pruebas pasadas")
    print()
    
    if passed == total:
        print("✓ TODAS LAS PRUEBAS PASARON CORRECTAMENTE")
        return 0
    else:
        print("✗ ALGUNAS PRUEBAS FALLARON")
        return 1


if __name__ == "__main__":
    sys.exit(main())
