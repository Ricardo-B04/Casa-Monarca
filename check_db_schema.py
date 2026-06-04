#!/usr/bin/env python3
"""Verificar estructura de base de datos"""

import sqlite3

conn = sqlite3.connect('casa.db')
c = conn.cursor()

try:
    c.execute("PRAGMA table_info(solicitudes_arco)")
    cols = c.fetchall()
    
    print("Columnas en solicitudes_arco:")
    print(f"Total: {len(cols)} columnas\n")
    
    for col in cols:
        col_name = col[1]
        col_type = col[2]
        print(f"  {col_name:<40} {col_type}")
    
    # Verificar qué columnas ARCO multinivel faltan
    print("\n" + "="*60)
    required = [
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
    
    existing_cols = {col[1] for col in cols}
    
    print("Columnas requeridas para ARCO multinivel:")
    missing = []
    for col in required:
        if col in existing_cols:
            print(f"  ✓ {col}")
        else:
            print(f"  ✗ {col} - FALTA")
            missing.append(col)
    
    if missing:
        print(f"\n⚠ {len(missing)} columnas faltando. Ejecutar init_db()...")
    
except Exception as e:
    print(f"Error: {e}")

finally:
    conn.close()
