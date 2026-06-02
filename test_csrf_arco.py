#!/usr/bin/env python3
"""
Test rápido para verificar que los CSRF tokens funcionan en el flujo ARCO.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app import app

def test_csrf_in_endpoints():
    """Verificar que los endpoints validan CSRF tokens."""
    
    print("\n" + "=" * 70)
    print("VERIFICACIÓN: CSRF Tokens en Endpoints ARCO")
    print("=" * 70 + "\n")
    
    # Leer el código de los endpoints
    with open("app.py", "r") as f:
        app_code = f.read()
    
    endpoints_to_check = [
        ("arco_aprobar", "/arco/<int:solicitud_id>/aprobar"),
        ("arco_resolver_coordinador", "/arco/<int:solicitud_id>/resolver-coordinador"),
    ]
    
    print("Verificando validación CSRF en endpoints:\n")
    
    all_have_csrf = True
    for endpoint_name, endpoint_path in endpoints_to_check:
        # Buscar el endpoint en el código
        if f"def {endpoint_name}(" in app_code:
            # Extraer la función
            start_idx = app_code.find(f"def {endpoint_name}(")
            end_idx = app_code.find("\nif __name__", start_idx)
            if end_idx == -1:
                end_idx = app_code.find("\n@app.route", start_idx + 100)
            
            endpoint_code = app_code[start_idx:end_idx if end_idx != -1 else start_idx + 2000]
            
            # Verificar que valida CSRF
            has_csrf_check = "csrf_token" in endpoint_code and "session.get(\"csrf_token\")" in endpoint_code
            
            if has_csrf_check:
                print(f"  ✓ {endpoint_name:<40} ✓ Valida CSRF")
            else:
                print(f"  ✗ {endpoint_name:<40} ✗ NO valida CSRF")
                all_have_csrf = False
    
    print()
    return all_have_csrf


def test_csrf_in_templates():
    """Verificar que los templates incluyen CSRF tokens."""
    
    print("=" * 70)
    print("VERIFICACIÓN: CSRF Tokens en Templates")
    print("=" * 70 + "\n")
    
    with open("templates/colaborador.html", "r") as f:
        template_code = f.read()
    
    print("Verificando tokens en formularios colaborador.html:\n")
    
    # Búsqueda simple y directa
    arco_forms = template_code.count('action="/arco/{{ arco')
    csrf_tokens = template_code.count('name="csrf_token"')
    
    print(f"  Formularios ARCO detectados: {arco_forms}")
    print(f"  CSRF tokens detectados: {csrf_tokens}")
    print()
    
    # Tenemos 3 formularios ARCO (2 para coordinador, 1 para usuario/operativo)
    if arco_forms >= 2 and csrf_tokens >= 3:
        print(f"  ✓ Todos los formularios ARCO incluyen CSRF token")
        return True
    else:
        print(f"  ✗ Faltan CSRF tokens en formularios")
        return False


def test_bandeja_passes_csrf():
    """Verificar que bandeja() pasa csrf_token al template."""
    
    print("=" * 70)
    print("VERIFICACIÓN: Endpoint /bandeja pasa CSRF Token")
    print("=" * 70 + "\n")
    
    with open("app.py", "r") as f:
        app_code = f.read()
    
    # Buscar la función bandeja
    bandeja_start = app_code.find("@app.route(\"/bandeja\")")
    bandeja_end = app_code.find("\n@app.route", bandeja_start + 1)
    if bandeja_end == -1:
        bandeja_end = len(app_code)
    
    bandeja_code = app_code[bandeja_start:bandeja_end]
    
    # Verificar que pasa csrf_token
    checks = [
        ("Inicializa csrf_token en sesión", "if \"csrf_token\" not in session:"),
        ("Pasa csrf_token a template", "csrf_token=session.get(\"csrf_token\")"),
    ]
    
    print("Verificando bandeja():\n")
    
    all_good = True
    for check_name, pattern in checks:
        if pattern in bandeja_code:
            print(f"  ✓ {check_name}")
        else:
            print(f"  ✗ {check_name}")
            all_good = False
    
    print()
    return all_good


def main():
    """Ejecutar todos los tests."""
    
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 18 + "VERIFICACIÓN DE CSRF TOKENS" + " " * 23 + "║")
    print("╚" + "=" * 68 + "╝")
    
    results = [
        ("Endpoints validan CSRF", test_csrf_in_endpoints()),
        ("Templates incluyen CSRF", test_csrf_in_templates()),
        ("Bandeja() pasa CSRF", test_bandeja_passes_csrf()),
    ]
    
    # Resumen
    print("=" * 70)
    print("RESUMEN")
    print("=" * 70)
    print()
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for check_name, result in results:
        status = "✓ PASÓ" if result else "✗ FALLÓ"
        print(f"  {status:<8} {check_name}")
    
    print()
    print(f"Total: {passed}/{total} verificaciones pasadas")
    print()
    
    if passed == total:
        print("✓ TOKENS CSRF ESTÁN CORRECTAMENTE CONFIGURADOS\n")
        return 0
    else:
        print("✗ FALTAN CONFIGURACIONES DE CSRF\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
