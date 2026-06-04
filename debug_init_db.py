#!/usr/bin/env python3
"""Debug de init_db()"""

import sys
from pathlib import Path
import traceback

sys.path.insert(0, str(Path(__file__).parent))

try:
    print("Intentando importar app...")
    from app import init_db, get_conn
    print("✓ Importación exitosa\n")
    
    print("Ejecutando init_db()...")
    init_db()
    print("✓ init_db() completado\n")
    
    print("Verificando conexión...")
    conn = get_conn()
    c = conn.cursor()
    print("✓ Conexión exitosa\n")
    
    print("Listando tablas...")
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = c.fetchall()
    print(f"Total de tablas: {len(tables)}\n")
    
    for table in tables:
        table_name = table[0]
        c.execute(f"PRAGMA table_info({table_name})")
        cols = c.fetchall()
        print(f"  {table_name}: {len(cols)} columnas")
    
    print("\nVerificando solicitudes_arco específicamente...")
    c.execute("SELECT count(*) as cnt FROM sqlite_master WHERE type='table' AND name='solicitudes_arco'")
    result = c.fetchone()
    if result and result[0] > 0:
        print("✓ Tabla solicitudes_arco existe")
        c.execute("PRAGMA table_info(solicitudes_arco)")
        cols = c.fetchall()
        print(f"  {len(cols)} columnas:")
        for col in cols:
            print(f"    - {col[1]} ({col[2]})")
    else:
        print("✗ Tabla solicitudes_arco NO existe")
    
    conn.close()
    
except Exception as e:
    print(f"✗ Error: {e}")
    traceback.print_exc()
