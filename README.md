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

   **macOS/Linux:**

   ```bash
   source .venv/bin/activate
   ```

   **Windows (PowerShell):**

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

Para detalles avanzados sobre challenge-response, certificados y flujos complejos, consultar el `docs/manual_desarrollador.pdf` (manual de desarrollador / SDK) y el `docs/manual_usuario.pdf` (manual de usuario).

## Estructura del proyecto

```text
casa-monarca-app/
├── app.py                    # Aplicación principal Flask (rutas, esquema, crypto, PKI)
├── config.py                 # Configuración por entorno (Development/Production/Testing)
├── generate_key.py           # Script para generar/regenerar key.key
├── requirements.txt          # Dependencias de Python
├── setup.sh                  # Setup inicial (venv, deps, .env, key.key, carpetas)
├── key.key                   # Clave de cifrado Fernet (generada; no se versiona)
├── database.db               # Base de datos SQLite (generada en primer arranque; no se versiona)
├── README.md                 # Este archivo
├── LICENSE                   # Licencia de código abierto (MIT)
├── DEVELOPERS.md             # Nombres y contacto de desarrolladores
├── CONTRIBUTING.md           # Guía de contribuciones
├── TODO.md                   # Pendientes para producción
├── CHANGELOG.txt             # Historial de cambios (general)
├── Changelog-Backend.txt     # Cambios de backend
├── Changelog-Frontend.txt    # Cambios de frontend
├── DOCUMENTATION_CHECKLIST.md # Progreso de documentación
├── IMPLEMENTACION_ARCO_MULTINIVEL.md # Notas de diseño del flujo ARCO
├── templates/                # Plantillas Jinja2 (HTML)
├── static/                   # Archivos estáticos (style.css, action-passkey.js)
├── certs/                    # Certificados X.509 de desarrollo (generados; no se versionan)
├── tools/
│  ├── backup_db.py           # Backup cifrado de la BD
│  ├── restore_db.py          # Restore de la BD
│  └── reencrypt_worker.py    # Worker de re-cifrado por rotación de llaves
├── tests/                    # Suite de pruebas (pytest)
└── docs/                     # Entregables de documentación
   ├── reporte_técnico.pdf                     # Reporte Técnico
   ├── reporte_ejecutivo.pdf                   # Reporte Ejecutivo
   ├── manual_usuario.pdf                      # Manual de Usuario
   ├── manual_desarrollador.pdf                # Manual de desarrollador / SDK
   ├── sdk_draft.md                            # Notas del SDK
   └── fuentes/                                # Código fuente LaTeX de la documentación
      ├── reporte_técnico.tex
      ├── reporte_ejecutivo.tex
      ├── manual_usuario.tex
      ├── manual_desarrollador.tex
      └── imagenes/                            # Imágenes de los documentos
         ├── tecnologico-de-monterrey-blue.png # Logo compartido
         ├── reporte_tecnico/                  # Imágenes del reporte técnico
         ├── reporte_ejecutivo/                # Imágenes del reporte ejecutivo
         └── manual_usuario/                   # Imágenes del manual de usuario
```

> Nota: para regenerar un PDF, compilar el `.tex` correspondiente desde `docs/fuentes/` con `pdflatex`. Cada documento resuelve sus imágenes vía `\graphicspath{{imagenes/<documento>/}{imagenes/}}` (su subcarpeta + el logo compartido).

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

**Nota:** la documentación detallada (reporte técnico, reporte ejecutivo, manual de usuario y manual de desarrollador/SDK) está disponible en la carpeta `docs/` como PDFs finales, junto con sus fuentes editables (`.tex` y `sdk_draft.md`).
Equipo del proyecto Casa Monarca.
Correo sugerido para mantenimiento: `soporte-proyecto@casamonarca.local` (reemplazar por correo real).
