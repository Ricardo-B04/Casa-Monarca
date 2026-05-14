# Casa Monarca - Plataforma de Registro y Canalizacion

## Descripcion del proyecto
Aplicacion web en Flask para registrar expedientes y canalizarlos por niveles operativos (Usuario, Operativo, Coordinador, Admin), con bitacora, cifrado de datos y control de acceso.

## Caracteristicas principales
- Gestion de usuarios con roles y permisos por nivel.
- Flujo de estados de expediente: `borrador -> en_revision_operativa -> en_revision_coordinacion -> validado_coordinacion -> cerrado`.
- Login con contrasena hasheada.
- Soporte de certificado para roles criticos (admin y coordinador).
- Solicitud de eliminacion por coordinador y resolucion por admin.
- Bitacora de eventos y limpieza manual de bitacora.

## Requisitos de instalacion
- macOS, Linux o Windows.
- Python 3.10+ (recomendado 3.11).
- Entorno virtual Python (`.venv`).
- Paquetes: Flask, cryptography, Werkzeug.

## Instalacion
1. Clonar o descargar el proyecto.
2. Entrar a la carpeta del proyecto.
3. Crear entorno virtual (si no existe):

```bash
python3 -m venv .venv
```

4. Activar entorno virtual.
- macOS/Linux:

```bash
source .venv/bin/activate
```

- Windows (PowerShell):

```powershell
.venv\Scripts\Activate.ps1
```

5. Instalar dependencias:

```bash
.venv/bin/python -m pip install flask cryptography werkzeug
```

## Configuracion
- Verificar que exista [key.key](key.key) para cifrado.
- Al iniciar, la app crea tablas faltantes y cuentas semilla.
- Se generan/actualizan certificados de desarrollo en la carpeta [certs](certs).

### Variables de entorno recomendadas
Antes de desplegar en un entorno no controlado, exporta las siguientes variables de entorno para mejorar seguridad:

- `SECRET_KEY` o `APP_SECRET_KEY`: valor secreto para la sesión de Flask. Debe ser una cadena fuerte (por ejemplo, 32+ bytes aleatorios en base64).
- `FLASK_DEBUG`: `1` para activar `debug` en desarrollo, `0` (por defecto) para desactivar en producción.
- `ENABLE_SESSION_COOKIE_SECURE`: `1` para marcar la cookie de sesión como `Secure` (recomendado en HTTPS), `0` por defecto.
- `SESSION_COOKIE_SAMESITE`: `Lax` por defecto; puede ajustarse a `Strict` si la app no requiere cross-site form posts.

Ejemplo (bash):

```bash
export SECRET_KEY="$(python -c 'import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')"
export FLASK_DEBUG=0
export ENABLE_SESSION_COOKIE_SECURE=1
export SESSION_COOKIE_SAMESITE=Lax
.venv/bin/python app.py
```

Nota: en producción, sirve la app detrás de un proxy HTTPS (Nginx, Caddy) y habilita `ENABLE_SESSION_COOKIE_SECURE=1`.

## Mejoras de seguridad aplicadas (Sprint 1)
Se implementaron varias medidas iniciales de hardening. Resumen rápido:

- CSRF: se añadió protección por token CSRF por sesión en formularios POST. En desarrollo/`TESTING` los tests deshabilitan la verificación para facilitar pruebas automatizadas.
- Cookies: se forzaron flags `HttpOnly` y `SameSite` por defecto; activar `ENABLE_SESSION_COOKIE_SECURE=1` en despliegues HTTPS añade `Secure`.
- Rate-limiting / login lockout: bloqueo temporal por intentos fallidos configurable mediante variables de entorno:
	- `LOGIN_MAX_ATTEMPTS` (por defecto `5`)
	- `LOGIN_WINDOW_SECONDS` (por defecto `300`)
	- `LOGIN_LOCKOUT_SECONDS` (por defecto `900`)
	El estado de bloqueo se persiste en SQLite para sobrevivir reinicios y limpiar el contador cuando corresponde.
- Tests: añadidos tests para el comportamiento de bloqueo de login en `tests/test_password_security.py`.
- Backups cifrados: se añadieron scripts para generar y restaurar copias cifradas de `database.db` usando `key.key`.

### Cómo ejecutar pruebas
Desde la raíz del proyecto (usa el entorno virtual):

```bash
# agregar el proyecto al PYTHONPATH para que `import app` funcione en tests
PYTHONPATH=. .venv/bin/pytest -q
```

Notas operativas:
- En entornos de CI, exporta `SECRET_KEY` mediante un gestor de secretos y activa `ENABLE_SESSION_COOKIE_SECURE=1` si corres pruebas sobre HTTPS.
- Considera usar Redis o una tabla en la base de datos para almacenar contadores de intentos fallidos en producción.


## Uso basico
1. Ejecutar:

```bash
.venv/bin/python app.py
```

2. Abrir en navegador:
- `http://127.0.0.1:5000`

3. Cuentas de prueba:
- `admin_prod / admin123` (requiere [certs/admin_prod.pem](certs/admin_prod.pem))
- `admin_cont / admin123` (requiere [certs/admin_cont.pem](certs/admin_cont.pem))
- `coord_admin / coord123` (requiere [certs/coord_admin.pem](certs/coord_admin.pem))
- `operativo_1 / Operativo_2026!`
 - `usuario_1 / Usuario_2026!X`

4. Ejemplo breve de flujo:
- Usuario crea expediente -> Usuario canaliza -> Operativo canaliza -> Coordinador valida -> Admin cierra.

## Estructura del proyecto
```text
Intentoa2/
|- app.py
|- database.py
|- generate_key.py
|- key.key
|- database.db
|- adminrename.txt
|- templates/
|  |- login.html
|  |- dashboard.html
|  |- survey.html
|  |- colaborador.html
|  |- admin.html
|  |- usuarios.html
|  |- logs.html
|- certs/
|  |- admin_prod.pem
|  |- admin_cont.pem
|  |- coord_admin.pem
|- README.md
|- README.txt
|- TODO.txt
|- CHANGELOG.txt
```

## Contribuciones
Si deseas colaborar:
1. Haz un fork o copia del proyecto.
2. Crea una rama de trabajo para tu cambio.
3. Levanta el proyecto en local y revisa el flujo actual antes de modificar.
4. Realiza cambios pequenos y enfocados.
5. Prueba login, flujo por roles y bitacora.
6. Actualiza README/TODO/CHANGELOG con tus cambios.
7. Envia pull request con descripcion clara del objetivo y pruebas realizadas.

## Pruebas basicas
- Compilacion de sintaxis:

```bash
.venv/bin/python -m py_compile app.py
```

- Prueba de arranque:

```bash
.venv/bin/python app.py
```

- Prueba funcional minima:
- Login por cada rol y avance de un expediente por toda la cadena.

- Prueba de seguridad minima:
- Verificar que admin/coordinador con huella configurada no entren sin certificado.

## Runbook de backup y restore
1. Crear un respaldo cifrado:

```bash
.venv/bin/python tools/backup_db.py
```

2. Confirmar que se genero un archivo `.enc` en `backups/`.

3. Probar la restauracion sobre una copia de trabajo o en un entorno descartable:

```bash
.venv/bin/python tools/restore_db.py backups/db_backup_YYYYMMDDTHHMMSSZ.enc
```

4. Validar que `database.db` vuelve a abrirse y que la app arranca normalmente.

Validacion local realizada durante el cierre de Sprint 1 con respaldo y restauracion exitosos en el entorno de desarrollo.

## Licencia de uso
Pendiente de definir (solo mencion).

## Contacto
Equipo del proyecto Casa Monarca.
Correo sugerido para mantenimiento: `soporte-proyecto@casamonarca.local` (reemplazar por correo real).
