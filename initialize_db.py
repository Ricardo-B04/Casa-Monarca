#!/usr/bin/env python3
"""Inicializar base de datos y verificar"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app import init_db
import sqlite3

print("Inicializando base de datos...")
init_db()
print("✓ init_db() completado\n")

# Verificar
conn = sqlite3.connect('casa.db')
c = conn.cursor()

c.execute("PRAGMA table_info(solicitudes_arco)")
cols = c.fetchall()

print(f"Columnas en solicitudes_arco: {len(cols)}\n")

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

print("Verificación de columnas ARCO multinivel:")
missing = 0
for col in required:
    if col in existing_cols:
        print(f"  ✓ {col}")
    else:
        print(f"  ✗ {col}")
        missing += 1

if missing == 0:
    print(f"\n✓ TODAS LAS COLUMNAS PRESENTES - Base de datos lista")
    sys.exit(0)
else:
    print(f"\n✗ {missing} columnas faltando")
    sys.exit(1)

conn.close()
