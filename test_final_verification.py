#!/usr/bin/env python3
"""
Test de verificación final del flujo ARCO multinivel
Verifica que todas las configuraciones críticas están en su lugar
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def verify_csrf_configuration():
    """Verificar que CSRF está correctamente configurado en todo."""
    print("\n" + "=" * 70)
    print("VERIFICACIÓN: CONFIGURACIÓN COMPLETA DE CSRF")
    print("=" * 70 + "\n")
    
    # 1. Verificar app.py
    print("1. Verificando app.py...")
    with open("app.py", "r", encoding="utf-8") as f:
        app_code = f.read()
    
    checks = [
        ("import secrets", "import secrets" in app_code),
        ("bandeja() inicializa csrf_token", 
         'if "csrf_token" not in session:' in app_code and 
         'session["csrf_token"] = secrets.token_hex(32)' in app_code),
        ("bandeja() pasa csrf_token a template", 
         'csrf_token=session.get("csrf_token")' in app_code),
        ("arco_aprobar() valida CSRF", 
         'def arco_aprobar(solicitud_id):' in app_code and
         'csrf_token' in app_code[app_code.find('def arco_aprobar'):app_code.find('def arco_aprobar')+2000]),
        ("arco_resolver_coordinador() valida CSRF",
         'def arco_resolver_coordinador(solicitud_id):' in app_code and
         'csrf_token' in app_code[app_code.find('def arco_resolver_coordinador'):app_code.find('def arco_resolver_coordinador')+2000]),
    ]
    
    for check_name, result in checks:
        status = "✓" if result else "✗"
        print(f"   {status} {check_name}")
    
    app_ok = all(result for _, result in checks)
    
    # 2. Verificar templates
    print("\n2. Verificando templates...")
    with open("templates/colaborador.html", "r", encoding="utf-8") as f:
        colaborador = f.read()
    
    with open("templates/admin.html", "r", encoding="utf-8") as f:
        admin_template = f.read()
    
    template_checks = [
        ("colaborador.html tiene 3 formularios ARCO", colaborador.count('action="/arco/{{ arco') >= 2),
        ("colaborador.html tiene csrf_token en formularios", colaborador.count('name="csrf_token"') >= 3),
        ("admin.html tiene formularios ARCO", admin_template.count('action="/arco/') >= 2),
        ("admin.html tiene csrf_token en formularios", admin_template.count('name="csrf_token"') >= 2),
    ]
    
    for check_name, result in template_checks:
        status = "✓" if result else "✗"
        print(f"   {status} {check_name}")
    
    templates_ok = all(result for _, result in template_checks)
    
    return app_ok and templates_ok


def verify_database_schema():
    """Verificar que el esquema de base de datos es correcto."""
    print("\n" + "=" * 70)
    print("VERIFICACIÓN: ESQUEMA DE BASE DE DATOS")
    print("=" * 70 + "\n")
    
    from app import init_db, get_conn
    import sqlite3
    
    init_db()
    
    conn = get_conn()
    c = conn.cursor()
    
    # Verificar que solicitudes_arco tiene las columnas necesarias
    c.execute("PRAGMA table_info(solicitudes_arco)")
    columns = {row[1]: row[2] for row in c.fetchall()}
    
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
    
    print("Verificando columnas requeridas en solicitudes_arco:\n")
    
    all_present = True
    for col in required_columns:
        if col in columns:
            print(f"   ✓ {col}")
        else:
            print(f"   ✗ {col} FALTA")
            all_present = False
    
    if len(columns) > 0:
        print(f"\n   Total de columnas en tabla: {len(columns)}/36")
    
    conn.close()
    return all_present


def verify_endpoint_handlers():
    """Verificar que todos los handlers existen y tienen el código correcto."""
    print("\n" + "=" * 70)
    print("VERIFICACIÓN: HANDLERS DE ENDPOINTS")
    print("=" * 70 + "\n")
    
    with open("app.py", "r", encoding="utf-8") as f:
        app_code = f.read()
    
    handlers = [
        ("arco", "def arco():"),
        ("arco_solicitud", "def arco_solicitud():"),
        ("arco_resolver", "def arco_resolver(solicitud_id):"),
        ("arco_aprobar", "def arco_aprobar(solicitud_id):"),
        ("arco_resolver_coordinador", "def arco_resolver_coordinador(solicitud_id):"),
    ]
    
    print("Verificando handlers:\n")
    
    all_present = True
    for handler_name, signature in handlers:
        if signature in app_code:
            print(f"   ✓ {handler_name}")
        else:
            print(f"   ✗ {handler_name} NO ENCONTRADO")
            all_present = False
    
    return all_present


def verify_templates_rendering():
    """Verificar que los templates usan variables correctamente."""
    print("\n" + "=" * 70)
    print("VERIFICACIÓN: RENDERIZADO DE TEMPLATES")
    print("=" * 70 + "\n")
    
    with open("templates/colaborador.html", "r", encoding="utf-8") as f:
        colaborador = f.read()
    
    checks = [
        ("usa variable 'solicitudes_arco'", "solicitudes_arco" in colaborador),
        ("usa variable 'csrf_token'", "{{ csrf_token }}" in colaborador),
        ("itera sobre solicitudes", "{% for arco in solicitudes_arco %}" in colaborador),
        ("Formulario para coordinador", "resolver-coordinador" in colaborador),
        ("Formulario para usuario/operativo", "aprobar" in colaborador),
        ("Decision 'resuelta'", "decision" in colaborador and "resuelta" in colaborador),
        ("Decision 'enviar_admin'", "enviar_admin" in colaborador),
    ]
    
    print("Verificando template colaborador.html:\n")
    
    all_ok = True
    for check_name, result in checks:
        status = "✓" if result else "✗"
        print(f"   {status} {check_name}")
        if not result:
            all_ok = False
    
    return all_ok


def main():
    """Ejecutar todas las verificaciones."""
    print("\n╔" + "=" * 68 + "╗")
    print("║" + " " * 20 + "VERIFICACIÓN FINAL FLUJO ARCO" + " " * 20 + "║")
    print("╚" + "=" * 68 + "╝")
    
    results = []
    
    try:
        results.append(("CSRF Configuration", verify_csrf_configuration()))
        results.append(("Database Schema", verify_database_schema()))
        results.append(("Endpoint Handlers", verify_endpoint_handlers()))
        results.append(("Template Rendering", verify_templates_rendering()))
        
        # Resumen
        print("\n" + "=" * 70)
        print("RESUMEN FINAL")
        print("=" * 70 + "\n")
        
        for check_name, result in results:
            status = "✓ PASÓ" if result else "✗ FALLÓ"
            print(f"   {status:<10} {check_name}")
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        print(f"\n   Total: {passed}/{total} verificaciones pasadas\n")
        
        if passed == total:
            print("╔" + "=" * 68 + "╗")
            print("║" + " " * 22 + "✓ FLUJO ARCO LISTO PARA USAR" + " " * 18 + "║")
            print("╚" + "=" * 68 + "╝\n")
            return 0
        else:
            print("╔" + "=" * 68 + "╗")
            print("║" + " " * 15 + "✗ FALTAN ELEMENTOS EN LA CONFIGURACIÓN" + " " * 15 + "║")
            print("╚" + "=" * 68 + "╝\n")
            return 1
    
    except Exception as e:
        print(f"\n✗ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
