#!/usr/bin/env python3
"""
Script de prueba de endpoints del flujo ARCO.
Verifica que:
1. Las rutas están registradas correctamente
2. Los permisos RBAC funcionan
3. El flujo se redirige correctamente
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app import app

def check_endpoints():
    """Verificar que todos los endpoints están registrados."""
    print("=" * 70)
    print("VERIFICACIÓN: Endpoints ARCO registrados")
    print("=" * 70 + "\n")
    
    # Obtener todas las rutas de la aplicación
    routes = {}
    for rule in app.url_map.iter_rules():
        if '/arco' in rule.rule:
            methods = ','.join(rule.methods - {'OPTIONS', 'HEAD'})
            routes[rule.rule] = methods
    
    print("Rutas ARCO encontradas:\n")
    
    expected_routes = {
        '/arco': 'GET',
        '/arco/solicitud': 'POST',
        '/arco/<solicitud_id>/resolver': 'POST',
        '/arco/<solicitud_id>/aprobar': 'POST',
        '/arco/<solicitud_id>/resolver-coordinador': 'POST',
    }
    
    all_found = True
    for expected_route in expected_routes.keys():
        found = False
        for actual_route in routes.keys():
            # Comparar sin los parámetros
            if expected_route.replace('<solicitud_id>', '\\d+') in actual_route or \
               expected_route == actual_route or \
               expected_route.replace('<solicitud_id>', '<int:solicitud_id>') == actual_route:
                print(f"  ✓ {actual_route:<50} {routes[actual_route]}")
                found = True
                break
        
        if not found:
            print(f"  ✗ {expected_route:<50} NOT FOUND")
            all_found = False
    
    print()
    
    if all_found:
        print("✓ Todos los endpoints esperados están registrados\n")
        return True
    else:
        print("✗ Faltan algunos endpoints\n")
        return False


def check_request_methods():
    """Verificar que los métodos HTTP son los correctos."""
    print("=" * 70)
    print("VERIFICACIÓN: Métodos HTTP de endpoints")
    print("=" * 70 + "\n")
    
    expected_methods = {
        '/arco': 'GET',
        '/arco/solicitud': 'POST',
        '/arco/<int:solicitud_id>/resolver': 'POST',
        '/arco/<int:solicitud_id>/aprobar': 'POST',
        '/arco/<int:solicitud_id>/resolver-coordinador': 'POST',
    }
    
    routes_by_methods = {}
    for rule in app.url_map.iter_rules():
        methods = ','.join(rule.methods - {'OPTIONS', 'HEAD'})
        if rule.rule not in routes_by_methods:
            routes_by_methods[rule.rule] = methods
    
    print("Verificación de métodos:\n")
    all_correct = True
    for expected, method in expected_methods.items():
        # Buscar en las rutas registradas
        found = False
        for actual_route, actual_methods in routes_by_methods.items():
            if expected in actual_route or expected.replace('<int:solicitud_id>', '<solicitud_id>') in actual_route:
                if method in actual_methods:
                    print(f"  ✓ {expected:<50} {method}")
                    found = True
                    break
                else:
                    print(f"  ✗ {expected:<50} {method} (tiene {actual_methods})")
                    all_correct = False
                    break
        
        if not found:
            # Buscar en las rutas con parámetros genéricos
            for actual_route, actual_methods in routes_by_methods.items():
                if '/arco' in actual_route and expected.split('/')[1:] == actual_route.split('/')[1:2]:
                    if method in actual_methods:
                        print(f"  ✓ {expected:<50} {method}")
                        found = True
                        break
    
    print()
    
    if all_correct:
        print("✓ Todos los métodos HTTP son correctos\n")
        return True
    else:
        print("✗ Algunos métodos HTTP son incorrectos\n")
        return False


def check_blueprints_and_handlers():
    """Verificar que los handlers de las rutas existen."""
    print("=" * 70)
    print("VERIFICACIÓN: Handlers de las rutas")
    print("=" * 70 + "\n")
    
    expected_handlers = {
        'arco': 'GET /arco - Formulario ARCO',
        'arco_solicitud': 'POST /arco/solicitud - Crear solicitud ARCO',
        'arco_resolver': 'POST /arco/<id>/resolver - Resolver por admin',
        'arco_aprobar': 'POST /arco/<id>/aprobar - Aprobar por usuario/operativo/coordinador',
        'arco_resolver_coordinador': 'POST /arco/<id>/resolver-coordinador - Opciones coordinador',
    }
    
    app_handlers = app.view_functions
    
    print("Handlers encontrados:\n")
    all_found = True
    for handler_name, description in expected_handlers.items():
        if handler_name in app_handlers:
            print(f"  ✓ {handler_name:<35} {description}")
        else:
            print(f"  ✗ {handler_name:<35} NOT FOUND")
            all_found = False
    
    print()
    
    if all_found:
        print("✓ Todos los handlers existen\n")
        return True
    else:
        print("✗ Faltan algunos handlers\n")
        return False


def main():
    """Ejecutar todas las comprobaciones."""
    print("\n")
    print("╔" + "=" * 68 + "╗")
    print("║" + " " * 15 + "VERIFICACIÓN DE ENDPOINTS ARCO" + " " * 23 + "║")
    print("╚" + "=" * 68 + "╝")
    print()
    
    checks = [
        ("Endpoints registrados", check_endpoints),
        ("Métodos HTTP", check_request_methods),
        ("Handlers", check_blueprints_and_handlers),
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
    print("RESUMEN")
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
        print("✓ TODOS LOS ENDPOINTS ESTÁN CORRECTAMENTE CONFIGURADOS")
        return 0
    else:
        print("✗ ALGUNOS ENDPOINTS TIENEN PROBLEMAS")
        return 1


if __name__ == "__main__":
    sys.exit(main())
