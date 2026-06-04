#!/usr/bin/env python3
"""
Script para actualizar la BD existente con las nuevas columnas de ARCO.
Este script es seguro: solo agrega columnas si no existen.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Importar la función init_db del app
from app import init_db

def main():
    print("\n" + "=" * 70)
    print("ACTUALIZACIÓN DE BD - NUEVAS COLUMNAS ARCO")
    print("=" * 70 + "\n")
    
    print("Ejecutando init_db()...")
    try:
        init_db()
        print("✓ init_db() completado exitosamente\n")
    except Exception as e:
        print(f"✗ Error durante init_db(): {e}\n")
        return 1
    
    # Verificar que las columnas se agregaron
    print("Verificando nuevas columnas...")
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    
    required_columns = [
        "nivel_actual",
        "aprobado_usuarios",
        "aprobado_usuarios_at",
        "aprobado_usuarios_por",
        "aprobado_operativos",
        "aprobado_operativos_at",
        "aprobado_operativos_por",
        "aprobado_coordinadores",
        "aprobado_coordinadores_at",
        "aprobado_coordinadores_por",
        "reenviado_por_coordinador",
        "reenviado_por_coordinador_at",
        "resuelto_coordinador",
        "resuelto_coordinador_at",
    ]
    
    c.execute("PRAGMA table_info(solicitudes_arco)")
    existing = {row[1] for row in c.fetchall()}
    
    all_exist = True
    for col in required_columns:
        if col in existing:
            print(f"  ✓ {col}")
        else:
            print(f"  ✗ {col} NO EXISTE")
            all_exist = False
    
    conn.close()
    
    if all_exist:
        print("\n✓ Todas las columnas se agregaron correctamente")
        return 0
    else:
        print("\n✗ Faltan algunas columnas. Verifica el script init_db()")
        return 1


if __name__ == "__main__":
    sys.exit(main())
