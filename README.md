# Casa Monarca

## Descripción del proyecto

Aplicación web en Flask para gestionar expedientes y su canalización por niveles operativos (Usuario, Operativo, Coordinador, Admin). Incluye control de acceso por roles, bitácora y soporte inicial de PKI para acciones críticas.

## Características principales

- Gestión de usuarios con roles y permisos diferenciados por nivel.
- Flujo de estados de expedientes: borrador → en revisión → validado → cerrado.
- Login con contraseña hasheada y challenge-response con certificados X.509 para roles críticos (admin, coordinador).
- Certificados digitales y validación de firma para acciones administrativas.
- Bitácora de eventos completa.
- Scripts de backup/restore con cifrado.

## Requisitos de instalación

- **Sistemas operativos:** macOS, Linux, Windows.
- **Python:** versión 3.10+ (recomendado 3.11).
- **Entorno virtual:** `.venv` (recomendado).
- **Dependencias clave:** Flask, cryptography, Werkzeug.

## Instalación

1. Clonar o descargar el repositorio.
2. Acceder a la carpeta del proyecto.
3. Crear entorno virtual (si no existe):

```bash
python3 -m venv .venv
```

4. Activar el entorno virtual:
   - **macOS/Linux:**
   ```bash
   source .venv/bin/activate
   ```
   - **Windows (PowerShell):**
   ```powershell
   .venv\Scripts\Activate.ps1
   ```

5. Instalar dependencias:

```bash
.venv/bin/python -m pip install flask cryptography werkzeug
```

## Configuración

- **Clave de cifrado:** asegurar que exista `key.key` en la raíz (o generar una nueva con `python generate_key.py`).
- **Base de datos:** la app crea tablas automáticamente en `database.db` en el primer arranque.
- **Certificados de desarrollo:** se generan certificados X.509 demo en `certs/` para `admin_prod`, `admin_cont` y `coord_admin`.
- **Variables de entorno importantes (producción):**
  - `SECRET_KEY`: valor secreto para sesiones Flask (generar: `python -c 'import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'`).
  - `FLASK_DEBUG`: `0` para producción, `1` para desarrollo.
  - `ENABLE_SESSION_COOKIE_SECURE`: `1` en HTTPS para marcar cookies como `Secure`.
  - `SESSION_COOKIE_SAMESITE`: `Lax` (por defecto) o `Strict`.

## Uso básico

1. **Ejecutar la aplicación:**

```bash
.venv/bin/python app.py
```

2. **Acceder en navegador:** `http://127.0.0.1:5000`

3. **Cuentas de prueba incluidas:**
   - `admin_prod / AdminProdX2026!` (requiere certificado)
   - `admin_cont / AdminContX2026!` (requiere certificado)
   - `coord_admin / CoordAdminX2026!` (requiere certificado)
   - `operativo_1 / Operativo_2026!`
   - `usuario_1 / Usuario_2026!X`

4. **Flujo operativo básico:**
   - Usuario inicia sesión y crea expediente.
   - Usuario canaliza el expediente.
   - Operativo lo revisa y canaliza.
   - Coordinador lo valida.
   - Admin lo cierra.

Para detalles avanzados sobre challenge-response, certificados y flujos complejos, consultar `docs/user_manual_draft.md`.

## Estructura del proyecto

```text
Intentoa2/
├── app.py                    # Aplicación principal Flask
├── database.py               # Módulo de datos y esquema
├── generate_key.py           # Script para generar/regenerar key.key
├── key.key                   # Clave de cifrado (generada automáticamente)
├── database.db               # Base de datos SQLite (generada en primer arranque)
├── README.md                 # Este archivo
├── LICENSE                   # Licencia de código abierto (MIT)
├── DEVELOPERS.md             # Nombres y contacto de desarrolladores
├── CONTRIBUTING.md           # Guía de contribuciones
├── DOCUMENTATION_CHECKLIST.md # Progreso de documentación
├── templates/
│  ├── login.html
│  ├── dashboard.html
│  ├── survey.html
│  ├── colaborador.html
│  ├── admin.html
│  ├── usuarios.html
│  ├── logs.html
│  └── password_update.html
├── static/
│  └── style.css
├── certs/                    # Certificados X.509 de desarrollo
│  ├── ca_cert.pem
│  ├── ca_key.pem
│  ├── admin_prod.pem
│  ├── admin_cont.pem
│  └── coord_admin.pem
├── tools/
│  ├── backup_db.py           # Script de backup cifrado
│  └── restore_db.py          # Script de restore
├── tests/
│  └── test_password_security.py
├── docs/                     # Documentación de entrega
│  ├── user_manual_draft.md
│  ├── technical_report_draft.md
│  ├── executive_report_draft.md
│  └── sdk_draft.md
└── TODO.txt                  # Lista de tareas pendientes
```

## Contribuciones

¿Cómo colaborar con el proyecto?

1. **Obtener el código:** clonar o descargar el repositorio.
2. **Familiarizarse:** revisar este README, la estructura del proyecto y ejecutar pruebas locales.
3. **Crear rama de trabajo:** usar nombre descriptivo (ej: `feature/validacion-mejorada` o `fix/login-timeout`).
4. **Desarrollar:** hacer cambios pequeños y enfocados.
5. **Probar localmente:**
   - Login con diferentes roles.
   - Flujo completo de expediente.
   - Comandos de backup/restore.
6. **Actualizar documentación:** modificar README, TODO o CHANGELOG si corresponde.
7. **Enviar PR:** describir claramente el objetivo y pruebas realizadas.

## Pruebas básicas

- **Verificar sintaxis Python:**
  ```bash
  .venv/bin/python -m py_compile app.py
  ```

- **Ejecutar suite de tests:**
  ```bash
  PYTHONPATH=. .venv/bin/pytest -q
  ```

- **Prueba manual de arranque:**
  ```bash
  .venv/bin/python app.py
  # Verificar que la app está disponible en http://127.0.0.1:5000
  ```

- **Validación mínima:** login con al menos un rol operativo y un rol administrativo; avanzar un expediente por todo el flujo; revisar bitácora.

## Licencia

Este proyecto usa licencia **MIT** (código abierto). Ver archivo `LICENSE` para detalles completos.

## Contacto

Desarrolladores y contacto disponibles en archivo `DEVELOPERS.md`.

---

**Nota:** documentación detallada (reportes técnico/ejecutivo, manual completo de usuario, detalles de PKI, guías de despliegue) disponible en carpeta `docs/` como borradores Markdown para refinar y convertir a LaTeX/Word según rúbrica de entrega.
Equipo del proyecto Casa Monarca.
Correo sugerido para mantenimiento: `soporte-proyecto@casamonarca.local` (reemplazar por correo real).
