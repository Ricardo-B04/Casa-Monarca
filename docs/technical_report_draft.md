# Reporte Técnico (Borrador)

## 1. Resumen

Sistema de gestión de expedientes desarrollado en Python/Flask con soporte para control de acceso por roles y PKI inicial. Primera etapa completada con hardening de seguridad y fundamentos de autenticación reforzada.

## 2. Arquitectura

**Componentes principales:**
- **Frontend:** templates HTML (login, dashboard, gestión de usuarios, bitácora).
- **Backend:** Flask app (app.py) con gestión de sesiones, validación de roles y challenge-response.
- **Persistencia:** SQLite (database.py, database.db).
- **Seguridad:** módulo PKI interno, CA local, emisión de certificados X.509.
- **Utilitarios:** scripts de backup/restore cifrado (tools/).

## 3. Modelo de datos

**Tablas principales:**
- `usuarios`: cuenta de usuario, rol, hash de contraseña, estado.
- `certificados`: certificados X.509 emitidos, estado (activo/revocado/expirado), huella, vigencia.
- `bitacora`: registro de eventos (login, creación de usuario, canalizaciones, revocaciones).
- `expedientes`: expediente, usuario propietario, estado (borrador/en_revision/validado/cerrado).

## 4. Mejoras de seguridad aplicadas (Sprint 1)

Se implementaron varias medidas iniciales de hardening:

### 4.1 CSRF (Cross-Site Request Forgery)
- Protección por token CSRF por sesión en formularios POST.
- En desarrollo/testing, los tests deshabilitan la verificación para facilitar pruebas automatizadas.

### 4.2 Cookies seguras
- Flags `HttpOnly` y `SameSite` forzados por defecto.
- En despliegues HTTPS, activar `ENABLE_SESSION_COOKIE_SECURE=1` añade flag `Secure`.

### 4.3 Rate-limiting y login lockout
Bloqueo temporal por intentos fallidos:
- `LOGIN_MAX_ATTEMPTS`: máximo de intentos (por defecto 5)
- `LOGIN_WINDOW_SECONDS`: ventana de tiempo (por defecto 300)
- `LOGIN_LOCKOUT_SECONDS`: duración del bloqueo (por defecto 900)

El estado de bloqueo se persiste en SQLite y sobrevive reinicios.

### 4.4 Hashing de contraseñas
- Uso de Werkzeug/bcrypt para hashear contraseñas.
- Comparación segura en login.

### 4.5 Backups cifrados
- Scripts para generar y restaurar copias cifradas de `database.db` usando `key.key`.
- Encriptación AES-256 (via cryptography).

### 4.6 Tests de seguridad
- Tests presentes en `tests/test_password_security.py` para validar bloqueo de login y comportamiento de intentos fallidos.

## 5. Mejoras de PKI aplicadas (Sprint 2)

Se incorporó una CA interna del proyecto para emitir certificados X.509 de roles críticos.

### 5.1 Emisión de certificados
- `admin` y `coordinador` generan un certificado X.509 firmado por la CA local.
- Clave privada cifrada y empaquetada en el mismo archivo `.pem`.
- Soporte para CSR (Certificate Signing Request) para claves privadas generadas localmente.

### 5.2 Validación
- Al iniciar sesión y al ejecutar acciones críticas, la app verifica:
  - Firma de CA
  - Vigencia del certificado
  - Huella del certificado
  - Correspondencia con el usuario
  - Estado (activo/revocado/expirado)

### 5.3 Revocación
- Panel de usuarios permite revocar certificados activos con motivo obligatorio.
- Revocación queda auditada en tabla `certificados` y bitácora.

### 5.4 Custodia de CA
- CA del proyecto se crea automáticamente en `certs/ca_cert.pem` y `certs/ca_key.pem` en la primera emisión.

### 5.5 Flujo operativo
- Si un certificado se revoca o expira, el usuario debe reemitirlo desde `/certificado/setup`.

## 6. Variables de entorno (producción)

Antes de desplegar en entornos no controlados:

```bash
export SECRET_KEY="$(python -c 'import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())')"
export FLASK_DEBUG=0
export ENABLE_SESSION_COOKIE_SECURE=1
export SESSION_COOKIE_SAMESITE=Lax
export LOGIN_MAX_ATTEMPTS=5
export LOGIN_WINDOW_SECONDS=300
export LOGIN_LOCKOUT_SECONDS=900
```

## 7. Pruebas

### 7.1 Tests unitarios
- Presentes en `tests/` (ej: `test_password_security.py`).
- Cobertura: validación de bloqueo de login, hashing, fallos de autenticación.

### 7.2 Ejecución de tests
```bash
PYTHONPATH=. .venv/bin/pytest -q
```

### 7.3 Validación manual
- Login con cada rol (usuario, operativo, coordinador, admin).
- Flujo completo de expediente (crear → revisar → validar → cerrar).
- Backup y restore: `python tools/backup_db.py` y `python tools/restore_db.py backups/<archivo>.enc`.
- Bitácora: verificar que todos los eventos se registren correctamente.

## 8. Despliegue y recomendaciones

### 8.1 Entorno local (desarrollo)
```bash
source .venv/bin/activate
export FLASK_DEBUG=1
python app.py
```

### 8.2 Entorno de producción
- Servir la app detrás de un proxy HTTPS (Nginx, Caddy, etc.).
- Exportar `SECRET_KEY` desde gestor de secretos (no hardcodear).
- Activar `ENABLE_SESSION_COOKIE_SECURE=1`.
- Considerar usar Redis para almacenar contadores de login lockout (escala horizontal).
- Backups periódicos con `python tools/backup_db.py` a almacenamiento externo.

## 9. Plan para siguiente etapa

- Migración de CA a HSM o secret manager (no almacenar en filesystem).
- Escalado de contadores de login lockout (Redis en lugar de SQLite).
- Auditoría extendida y trazabilidad de acciones.
- Integración con directorio LDAP/AD (SSO).
- Despliegue en contenedores (Docker) con CI/CD.

---

Rellenar con diagramas de arquitectura, métricas de prueba y evidencia de validación antes de convertir a LaTeX.
