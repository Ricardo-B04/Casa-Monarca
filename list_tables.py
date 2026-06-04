#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect('casa.db')
c = conn.cursor()

c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = c.fetchall()

print("Tablas en base de datos:")
for t in tables:
    print(f"  {t[0]}")

conn.close()
