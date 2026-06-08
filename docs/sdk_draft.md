# Casa Monarca — Documentación Técnica

> Documento de referencia técnica del backend de Casa Monarca, una aplicación Flask de gestión de
> expedientes ("encuestas") para una organización de atención humanitaria a personas migrantes.
> Esta versión del documento describe **el estado real del repositorio** (single-file backend en
> `app.py`, ~5 600 líneas) en su versión cercana a la final, y sustituye una versión previa del
> borrador que describía una arquitectura genérica/idealizada que no correspondía al código.

---

## Índice

1. [Descripción General](#descripción-general)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Stack Tecnológico](#stack-tecnológico)
4. [Estructura del Proyecto](#estructura-del-proyecto)
5. [Configuración del Entorno](#configuración-del-entorno)
6. [Instalación y Ejecución](#instalación-y-ejecución)
7. [Base de Datos](#base-de-datos)
8. [Rutas HTTP (interfaz web)](#rutas-http-interfaz-web)
9. [Flujos y Lógica de Negocio](#flujos-y-lógica-de-negocio)
10. [Seguridad: Cifrado, PKI y Passkeys en detalle](#seguridad-cifrado-pki-y-passkeys-en-detalle)
11. [Auditoría, CSRF y Manejo de Errores](#auditoría-csrf-y-manejo-de-errores)
12. [Pruebas](#pruebas)
13. [Despliegue y Mantenimiento](#despliegue-y-mantenimiento)
14. [Preguntas Frecuentes (FAQ)](#preguntas-frecuentes-faq)
15. [Q&A de Estudio — Criptografía y Ciberseguridad](#qa-de-estudio--criptografía-y-ciberseguridad)

---

## Descripción General

Casa Monarca es una aplicación web **Flask server-side renderizada** (HTML + Jinja2, sin API
JSON/REST) que digitaliza el levantamiento y seguimiento de **expedientes** (tabla `encuestas`,
también llamados "encuestas" en el código y la UI) de personas atendidas. Los expedientes pasan
por un flujo de revisión escalonado entre cuatro roles operativos.

### Roles (`ROLE_LABELS` / `PERMISSIONS`, `app.py:108-116` y `app.py:692`)

| Rol | Etiqueta | Permisos (`PERMISSIONS`) |
|---|---|---|
| `usuario` | Usuario | `create` |
| `operativo` | Operativo | `create`, `read` |
| `coordinador` | Coordinador | `create`, `read`, `update` |
| `admin` | Administrador | `create`, `read`, `update`, `delete` |

`has_permission(action)` (`app.py:700`) consulta este diccionario contra el rol en sesión;
`require_role(*roles)` (`app.py:3150`) es el decorador usado para restringir rutas completas.

### Ciclo de vida del expediente

`next_status_for_role()` (`app.py:3433`) define la máquina de estados que gobierna el botón
"Avanzar" de cada expediente:

```
borrador → en_revision_operativa → en_revision_coordinacion → validado_coordinacion → cerrado
```

Cada transición sólo la puede ejecutar el rol al que le corresponde revisar ese estado (operativo,
luego coordinador, luego admin), reforzando la separación de funciones.

### Lo que el sistema SÍ hace

- Autenticación con **Argon2id**, bloqueo por intentos fallidos (`login_lockouts`) y verificación
  de contraseñas filtradas vía **HIBP** (k-anonimato, `check_password_pwned`, `app.py:1175`).
- **Cifrado de campo** de los datos sensibles del expediente (columna `encuestas.datos`) con
  **Fernet**, soportando **rotación de llaves** mediante un *keyring* con huellas SHA-256
  (`encryption_keys`, `encryption_metrics`, `reencrypt_jobs`).
- **PKI X.509** con una CA de desarrollo autofirmada (`certs/ca_cert.pem` / `ca_key.pem`),
  emisión/activación/revocación de certificados de usuario y verificación por
  **reto-respuesta** (challenge-response) firmada con RSA-PKCS#1 v1.5 + SHA-256.
- **WebAuthn / Passkeys** (librería `webauthn==2.3.0`) para registro/login sin contraseña y para
  firmar acciones críticas (`/action/passkey/*`), con derivación automática de un certificado
  X.509 a partir de la primera passkey registrada (arquitectura **N:1**: varias passkeys → un
  certificado por usuario).
- Protección **CSRF** global por sesión, *cookies* con `HttpOnly`/`Secure`/`SameSite`.
- **Bitácora de auditoría** (`logs`) con categorías (`operacion` / `seguridad`) para cada acción
  relevante.
- Flujo **ARCO multinivel** (Acceso, Rectificación, Cancelación, Oposición) para solicitudes de
  derechos de datos, con aprobación en cascada usuarios → operativos → coordinadores → (resuelto
  o reenviado a admin).
- **Respaldo cifrado** de la base de datos con Fernet (`tools/backup_db.py` / `restore_db.py`).

### Lo que el sistema NO incluye (a diferencia de borradores anteriores de este documento)

- No hay API JSON/REST: todas las rutas devuelven HTML renderizado por Jinja2 (`render_template`)
  o redirecciones; no existe `database.py`, ni endpoints como `GET /login` devolviendo JSON.
- No usa PostgreSQL, Docker, Gunicorn, Redis, `flask-talisman` ni pipelines de CI/CD: es una app
  **single-file** sobre **SQLite** pensada para ejecutarse con `python app.py` (servidor de
  desarrollo de Flask / WSGI simple).
- No hay segundo factor por SMS/correo; el refuerzo de identidad para roles críticos
  (`admin`, `coordinador`) es exclusivamente certificados X.509 + passkeys WebAuthn.
- No hay HSM ni custodia externa de llaves: el material criptográfico vive en archivos locales
  (`key.key`, `certs/`, `keys/`), todos excluidos de git vía `.gitignore`.

---

## Arquitectura del Sistema

### Vista de componentes

```
┌─────────────┐      HTTP (HTML/Jinja2)      ┌────────────────────────────────────┐
│  Navegador   │ ───────────────────────────▶ │              app.py                │
│ (cliente web)│ ◀─────────────────────────── │  (Flask, ~5 600 líneas, 40 rutas)  │
└─────────────┘                              │                                    │
                                              │  ┌──────────────┐  ┌────────────┐ │
                                              │  │ RBAC / CSRF  │  │  Auditoría │ │
                                              │  │ has_permission│  │ log() →    │ │
                                              │  │ require_role │  │  tabla logs│ │
                                              │  └──────────────┘  └────────────┘ │
                                              │  ┌──────────────┐  ┌────────────┐ │
                                              │  │  Cifrado     │  │  PKI X.509 │ │
                                              │  │  Fernet      │  │  CA local  │ │
                                              │  │  keyring     │  │  certs/    │ │
                                              │  └──────────────┘  └────────────┘ │
                                              │  ┌──────────────┐                 │
                                              │  │  WebAuthn /  │                 │
                                              │  │  Passkeys    │                 │
                                              │  └──────────────┘                 │
                                              └─────────────────┬──────────────────┘
                                                                │ sqlite3 (get_conn)
                                                       ┌────────▼────────┐
                                                       │  database.db     │
                                                       │  (SQLite, 11     │
                                                       │   tablas)        │
                                                       └──────────────────┘
                          ┌──────────────────────────────────────────────┐
                          │ tools/  (procesos auxiliares fuera del request)│
                          │  - backup_db.py / restore_db.py (Fernet)       │
                          │  - reencrypt_worker.py (consume reencrypt_jobs)│
                          └──────────────────────────────────────────────┘
```

### Archivo único, sin capa de modelos

A diferencia de un proyecto típico con `models.py`/`routes/`/`services/`, **todo** vive en
`app.py`: definición de rutas (`@app.route`), acceso a datos (consultas `sqlite3` crudas vía
`get_conn()`), helpers criptográficos, lógica de PKI/passkeys, reglas de negocio del flujo de
expedientes y de ARCO. La forma más rápida de orientarse es buscar `@app.route` y los `def`
de nivel superior. `config.py` centraliza la configuración (`DevelopmentConfig` /
`ProductionConfig` / `TestingConfig`, seleccionada vía `FLASK_ENV`).

### Inicialización (`init_db`, `app.py:~301-689`)

Al arrancar, `init_db()` crea las tablas si no existen y usa `ensure_column(conn, tabla, columna,
definición)` para añadir columnas nuevas de forma idempotente sobre bases de datos ya existentes
— el patrón establecido para evolucionar el esquema sin migraciones destructivas (usado
intensivamente para la migración a ARCO multinivel, cifrado con rotación, PKI y passkeys).
`create_default_accounts()` siembra cuentas por defecto (`admin_prod`, `admin_cont`,
`coord_admin`, `operativo_1`, `usuario_1`) y `bootstrap_dev_certificates()` genera la CA y
certificados de desarrollo si faltan.

---

## Stack Tecnológico

Tomado directamente de `requirements.txt`:

| Paquete | Versión | Uso |
|---|---|---|
| `Flask` | 2.3.3 | Framework web, enrutamiento, sesiones, `render_template` |
| `Werkzeug` | 2.3.7 | WSGI subyacente de Flask |
| `Jinja2` | 3.1.2 | Motor de plantillas HTML server-side |
| `cryptography` | `>=43.0.3,<46` | Fernet, X.509, RSA, padding PKCS1v15, hashes SHA-256 |
| `argon2-cffi` | 23.1.0 | Hashing de contraseñas Argon2id |
| `webauthn` | 2.3.0 | Ceremonias WebAuthn (registro/autenticación de passkeys) |
| `requests` | 2.31.0 | Llamadas HTTP salientes (auxiliar) |
| `pytest` / `pytest-cov` | 7.4.3 / 4.1.0 | Suite de pruebas |

Base de datos: **SQLite** (`database.db`, gitignored), accedida con el módulo estándar `sqlite3`
mediante `get_conn()` y `row_factory` para obtener filas tipo diccionario.

Requiere **Python 3.10+** (según `setup.sh`).

---

## Estructura del Proyecto

```
casa-monarca-app/
├── app.py                  # Backend completo: rutas, esquema DB, criptografía, reglas de negocio
├── config.py               # DevelopmentConfig / ProductionConfig / TestingConfig
├── generate_key.py         # Genera la llave Fernet maestra (key.key)
├── requirements.txt
├── setup.sh                # Script de instalación (crea .venv, .env, key.key, carpetas)
├── .env.example            # Plantilla de variables de entorno
├── .gitignore              # Excluye key.key, keys/, certs/*.pem, *.db, etc.
├── templates/              # 14 plantillas Jinja2 (HTML)
│   ├── login.html, dashboard.html, survey.html, admin.html
│   ├── admin_cifrado.html, admin_identidades.html, admin_pki.html
│   ├── arco.html, cert_setup.html, colaborador.html
│   ├── logs.html, password_update.html, profile.html, usuarios.html
├── static/                 # Activos estáticos (CSS/JS/imágenes)
├── tools/
│   ├── backup_db.py        # Respaldo cifrado de database.db con Fernet
│   ├── restore_db.py       # Restauración desde respaldo cifrado
│   └── reencrypt_worker.py # Procesa la cola reencrypt_jobs (rotación de llaves)
├── tests/                  # Suite pytest (fixtures app_module con DB/certs/llaves aislados)
├── certs/                  # CA local + certificados emitidos (gitignored salvo estructura)
├── keys/                   # Material de llaves rotadas (gitignored)
├── backups/                # Respaldos cifrados generados por tools/backup_db.py
├── logs/                   # Logs de ejecución
├── key.key                 # Llave Fernet activa (gitignored, generada por generate_key.py)
└── database.db             # Base de datos SQLite (gitignored, creada al primer arranque)
```

No existen `models.py`, `routes/`, `services/`, `Dockerfile`, `docker-compose.yml`,
`.github/workflows/`, ni archivos `.env.development` / `.env.staging` / `.env.production`: la app
usa un único `.env` (copiado de `.env.example` por `setup.sh`) y selecciona el comportamiento por
ambiente con la variable `FLASK_ENV` y las clases en `config.py`.

---

## Configuración del Entorno

`config.py` define una jerarquía `Config` → `DevelopmentConfig` / `ProductionConfig` /
`TestingConfig`, seleccionada en el diccionario `config` mediante `FLASK_ENV`
(`development` por defecto). Variables relevantes (con sus valores por defecto):

### Sesión y cookies
- `SECRET_KEY` (clave de firma de sesión Flask; *default* inseguro `"secreto_demo"` — debe
  sobreescribirse en producción)
- `SESSION_COOKIE_HTTPONLY = True`, `SESSION_COOKIE_SAMESITE` (`Lax` en dev, `Strict` forzado en
  producción), `SESSION_COOKIE_SECURE` (controlado por `ENABLE_SESSION_COOKIE_SECURE` en prod)
- `PERMANENT_SESSION_LIFETIME = timedelta(hours=8)`

### Cifrado de datos (Fernet / keyring)
- `ENCRYPTION_KEY_PATH` (default `"key.key"`)
- `ENCRYPTION_LEGACY_KEY_PATHS` (lista separada por comas — llaves "legadas" para descifrar datos
  antiguos durante una rotación)
- `ENCRYPTION_LATENCY_WARNING_SECONDS` (default `0.25`, umbral para registrar advertencias de
  latencia en `encryption_metrics`)

### PKI
- `CERT_CA_CERT_PATH` / `CERT_CA_KEY_PATH` (default `certs/ca_cert.pem` / `certs/ca_key.pem`)
- `CERT_VALIDITY_HOURS = 720` (30 días de validez para certificados de usuario)

### Rate limiting / bloqueo de cuentas
- `LOGIN_MAX_ATTEMPTS = 5`, `LOGIN_WINDOW_SECONDS = 300`, `LOGIN_LOCKOUT_SECONDS = 900`
  (5 intentos en 5 minutos → bloqueo de 15 minutos)
- En `TestingConfig`, `LOGIN_MAX_ATTEMPTS = 1000` para no interferir con las pruebas.

### Política de contraseñas y reto-respuesta
- `PASSWORD_MIN_LENGTH = 12`
- `SIGNATURE_CHALLENGE_TTL` (`SIGNATURE_CHALLENGE_TTL_SECONDS`, default `300`)

### Passkeys / WebAuthn
- `PASSKEY_ENABLED` (default activado), `PASSKEY_ENFORCE_CRITICAL` (si se exige passkey a
  `admin`/`coordinador`)
- `PASSKEY_RP_ID` (default `localhost`), `PASSKEY_RP_NAME` (`Casa Monarca`)
- `PASSKEY_ORIGIN` derivado de `PASSKEY_PORT` (default `http://localhost:5000`)
- `PASSKEY_TIMEOUT_MS = 60000`, `PASSKEY_MAX_CREDENTIALS_PER_USER = 5`

### Diferencias por entorno
- `DevelopmentConfig`: `DEBUG=True`, cookies no forzadas a `Secure`.
- `ProductionConfig`: `DEBUG=False`, `SESSION_COOKIE_SECURE` controlado por
  `ENABLE_SESSION_COOKIE_SECURE`, `SESSION_COOKIE_SAMESITE="Strict"`.
- `TestingConfig`: `TESTING=True`, rate-limiting prácticamente desactivado, cookies no
  forzadas a `Secure`.

`.env.example` documenta todas estas variables como plantilla; `setup.sh` copia
`.env.example` → `.env` si no existe.

---

## Instalación y Ejecución

```bash
# Configuración inicial (crea .venv, instala deps, copia .env, genera key.key, crea carpetas)
./setup.sh

# Ejecutar la app (sirve en http://127.0.0.1:5000; las tablas se crean en el primer arranque)
.venv/bin/python app.py

# Verificación de sintaxis
.venv/bin/python -m py_compile app.py

# Suite de pruebas completa
PYTHONPATH=. .venv/bin/pytest -q

# Una prueba puntual
PYTHONPATH=. .venv/bin/pytest tests/test_password_security.py::test_qa_a_rejects_weak_password_on_forced_update -q

# Generar/regenerar la llave Fernet de cifrado de datos
.venv/bin/python generate_key.py

# Respaldo / restauración cifrados de la base de datos
.venv/bin/python tools/backup_db.py
.venv/bin/python tools/restore_db.py
```

`setup.sh` realiza, en orden: creación de `.venv`, actualización de `pip`, instalación de
`requirements.txt`, copia de `.env.example` a `.env`, generación de `key.key` (si no existe) y
creación de los directorios `certs/`, `backups/`, `logs/`. No existe un comando de *lint* o
*format* dedicado: `py_compile` + `pytest` es la vía de verificación establecida.

Al primer arranque, `app.py` ejecuta `init_db()` (crea/migra el esquema),
`create_default_accounts()` (siembra usuarios por defecto con contraseñas distintas para
pruebas/producción) y `bootstrap_dev_certificates()` (genera la CA y certificados de
desarrollo si faltan), selecciona dinámicamente el puerto y arranca con
`app.run(host="0.0.0.0", port=port, debug=debug_mode)`.

---

## Base de Datos

SQLite (`database.db`), acceso vía `get_conn()` (envoltorio sobre `sqlite3.connect` con
`row_factory = sqlite3.Row`). Esquema de **11 tablas** creadas/migradas en `init_db()`:

### `usuarios`
Cuentas del sistema: `id`, `username`, `password_hash` (Argon2id, formato `$argon2id$...`),
`role`, `must_change_password`, `created_at`, más columnas añadidas vía `ensure_column` para el
flujo de certificados/passkeys (p. ej. estado de configuración de identidad reforzada).

### `encuestas`
Los expedientes/casos. Incluye `id`, `usuario_id` (autor), `estado` (uno de los cinco estados del
ciclo de vida), `datos` (**blob cifrado con Fernet**, prefijo `fp:<huella>\n<token>`),
`encryption_key_fingerprint`, timestamps de creación/actualización y metadatos de revisión por
nivel (operativo/coordinador).

### `logs`
Bitácora de auditoría: `usuario`, `accion`, `categoria` (`operacion` | `seguridad`), `detalle`,
`timestamp`, `ip_address`. Alimentada por la función `log()` (`app.py:707`) en cada operación
sensible (logins, cambios de estado, emisión/revocación de certificados, rotación de llaves,
resoluciones ARCO, etc.).

### `encryption_keys`
Ciclo de vida de las llaves Fernet de cifrado de datos: `key_fingerprint` (SHA-256 de la llave),
`source_path`, `state` (`activo` | `legada` | `retiring`), `notes`, timestamps de activación.

### `encryption_metrics`
Métricas de uso/latencia de cifrado y descifrado, usadas para detectar degradación de
rendimiento (umbral `ENCRYPTION_LATENCY_WARNING_SECONDS`).

### `reencrypt_jobs`
Cola de trabajos de re-cifrado masivo cuando se rota la llave activa: estado, progreso, huella
origen/destino. Consumida por `tools/reencrypt_worker.py` mediante `reencrypt_all_surveys`.

### `solicitudes_eliminacion`
Solicitudes internas de eliminación de un expediente (`/solicitar-eliminacion/<id>`), con su
flujo de aprobación/resolución (`/solicitud/<id>/resolver`).

### `login_lockouts`
Respaldo persistente del sistema de bloqueo de cuentas: identificador (usuario o IP),
`intentos`, `primer_intento_at` / ventana, `locked_until`. Trabaja junto con la caché en memoria
`failed_login_store` y las funciones `_is_locked` / `_record_failed` / `_clear_failed`
(`app.py:1027, 1052, 1084`).

### `certificados`
Certificados X.509 emitidos: `user_id`, `serial_number`, `certificate_pem`, `estado`
(`pendiente` | `activo` | `revocado` | `expirado`), `expires_at`, `algorithm`
(`CERT_PRODUCT_ALGORITHM = "X509/RSA-2048/AES-256-CBC"`), modo de custodia de la llave privada
(generada en servidor vs. importada vía CSR), motivo de revocación.

### `passkey_credentials`
Credenciales WebAuthn registradas: `user_id`, `credential_id`, `public_key` (COSE), `sign_count`
(contador anti-repetición), `cert_id` (vínculo N:1 al certificado derivado), `estado`,
`created_at`, `last_used_at`.

### `solicitudes_arco`
Solicitudes de derechos ARCO con columnas dedicadas de aprobación por nivel:
`aprobado_usuarios` / `_at` / `_por`, `aprobado_operativos` / `_at` / `_por`,
`aprobado_coordinadores` / `_at` / `_por`, `nivel_actual`
(`usuarios` → `operativos` → `coordinadores` → `admin`), `reenviado_por_coordinador`,
`resuelto`, y los datos de la solicitud (nombre, contacto, tipo de solicitud ARCO, descripción).

> El patrón `ensure_column(conn, tabla, columna, "TIPO ...")` es la forma establecida de añadir
> columnas sin romper bases de datos existentes — se usa intensivamente para la migración
> multinivel de ARCO y para añadir soporte de cifrado/PKI/passkeys de forma incremental. **No**
> se deben usar `ALTER TABLE` directos ni migraciones destructivas.

---

## Rutas HTTP (interfaz web)

La aplicación **no expone una API JSON/REST**: cada ruta renderiza una plantilla Jinja2
(`render_template`) o realiza una redirección (`redirect`/`url_for`) tras procesar un formulario
HTML. Las únicas respuestas JSON corresponden a los endpoints **WebAuthn** (que siguen el
protocolo `navigator.credentials.create/get` del lado del cliente) y a algunos endpoints
auxiliares de PKI/cifrado consumidos por `fetch()` desde las plantillas de administración.

### Autenticación e identidad

| Ruta | Métodos | Descripción |
|---|---|---|
| `/` | GET, POST | Login: verificación Argon2id, control de bloqueo (`login_lockouts`), `must_change_password`, disparo de reto-respuesta de certificado/passkey para roles críticos |
| `/auth/passkey/register/options` `/verify` | POST | Ceremonia WebAuthn de **registro** de passkey (genera opciones / verifica el atestado) |
| `/auth/check-passkey-required` | POST | Indica al cliente si la cuenta requiere autenticación con passkey |
| `/auth/passkey/login/options` `/verify` | POST | Ceremonia WebAuthn de **autenticación** (login sin contraseña con passkey) |
| `/action/passkey/options` `/verify` | POST | Firma de **acciones críticas** con passkey (rotación de llaves, revocaciones, etc.), gateado por `check_and_consume_passkey_action` |
| `/certificado/setup` | GET, POST | Alta de certificado X.509 propio (generación en servidor o importación vía CSR) |
| `/password/update` | GET, POST | Cambio de contraseña (incluye flujo forzado por `must_change_password`) |
| `/logout` | GET | Cierre de sesión |

### Expedientes y bandeja de trabajo

| Ruta | Métodos | Descripción |
|---|---|---|
| `/dashboard` | GET | Panel principal según rol |
| `/survey` | GET, POST | Formulario de levantamiento de un nuevo expediente (cifra `datos` con Fernet al guardar) |
| `/bandeja` | GET | Bandeja de expedientes pendientes de revisión por el rol en sesión |
| `/encuesta/<id>/avanzar` | POST | Avanza el estado del expediente según `next_status_for_role` |
| `/solicitar-eliminacion/<id>` | POST | Solicita eliminación de un expediente |
| `/solicitud/<id>/resolver` | POST | Resuelve una solicitud de eliminación |
| `/admin` | GET | Panel de administración general |

### Gestión de usuarios e identidades (PKI / passkeys)

| Ruta | Métodos | Descripción |
|---|---|---|
| `/usuarios` | GET, POST | Alta/edición de cuentas de usuario |
| `/eliminar-usuario/<id>` | POST | Elimina un usuario (limpia artefactos PKI huérfanos) |
| `/admin/identidades` | GET | Vista consolidada de identidades reforzadas (certificados + passkeys) |
| `/admin/pki` | GET | Panel de administración de PKI |
| `/admin/pki/passkey-certificate-status` | GET | Estado del vínculo passkey↔certificado por usuario |
| `/admin/pki/revoke-passkey` | POST | Revoca una passkey (y su certificado vinculado si corresponde) |
| `/admin/pki/revoke-certificate` | POST | Revoca un certificado (y las passkeys vinculadas) |
| `/certificado/<id>/descargar` | POST | Descarga el certificado emitido (PEM) |
| `/certificado/<id>/revocar` | POST | Revoca un certificado específico |

### Cifrado y rotación de llaves

| Ruta | Métodos | Descripción |
|---|---|---|
| `/admin/cifrado` | GET, POST | Panel de estado de cifrado (llave activa, llaves legadas, métricas) |
| `/admin/cifrado/metrics` | GET | Métricas de latencia/uso de cifrado (`encryption_metrics`) |
| `/admin/cifrado/jobs` | GET | Estado de los trabajos de re-cifrado (`reencrypt_jobs`) |
| `/admin/keys/configure` | POST | Configura una nueva llave candidata (requiere firma con passkey de acción) |
| `/admin/keys/<fp>/activate` | POST | Activa una llave por huella y encola el re-cifrado masivo |

### Auditoría y perfil

| Ruta | Métodos | Descripción |
|---|---|---|
| `/logs` | GET | Visualización de la bitácora de auditoría |
| `/logs/clear` | POST | Limpieza de la bitácora (acción crítica, sólo `admin`) |
| `/profile` | GET, POST | Perfil del usuario en sesión |

### ARCO (derechos de datos)

| Ruta | Métodos | Descripción |
|---|---|---|
| `/arco` | GET | Formulario público de solicitud ARCO |
| `/arco/solicitud` | POST | Registra una nueva solicitud (`nivel_actual = 'usuarios'`) |
| `/arco/<id>/aprobar` | POST | Aprobación en cascada por nivel (usuarios → operativos → coordinadores) |
| `/arco/<id>/resolver` | POST | Resolución de una solicitud en el nivel correspondiente |
| `/arco/<id>/resolver-coordinador` | POST | El coordinador marca como resuelta **o** la reenvía (`reenviado_por_coordinador`) a `nivel_actual = 'admin'` |

---

## Flujos y Lógica de Negocio

### 1. Inicio de sesión y refuerzo de identidad

1. El usuario envía usuario/contraseña a `/`.
2. Se valida el formato y se verifica contra `password_hash` con `verify_password_argon2id`
   (Argon2id, comparación de hash constante en tiempo vía la librería `argon2-cffi`).
3. Antes de comprobar la contraseña se consulta `_is_locked(identifier)`: si la cuenta/IP está
   bloqueada (`login_lockouts`), se rechaza sin revelar si el usuario existe.
4. Si la contraseña es incorrecta, `_record_failed(identifier)` incrementa el contador; al llegar
   a `LOGIN_MAX_ATTEMPTS` (5) dentro de `LOGIN_WINDOW_SECONDS` (300 s) se fija
   `locked_until = ahora + LOGIN_LOCKOUT_SECONDS` (900 s) y se registra en `logs` con
   `categoria="seguridad"`.
5. Si la contraseña es correcta, `_clear_failed(identifier)` limpia el contador.
6. `password_is_legacy_or_weak` detecta hashes heredados o contraseñas que ya no cumplen la
   política vigente y fuerza `must_change_password`.
7. Para roles críticos (`admin`, `coordinador`), `enforce_certificate_setup()`
   (`before_request`, `app.py:3155`) obliga a completar la configuración de certificado/passkey
   antes de permitir cualquier otra acción — se redirige a `/certificado/setup` o al flujo de
   registro de passkey según el estado de la cuenta.
8. Si la cuenta tiene passkeys activas, se exige (o se ofrece, según `PASSKEY_ENFORCE_CRITICAL`)
   una ceremonia WebAuthn de autenticación (`/auth/passkey/login/options` → `/verify`) o un reto
   firmado con el certificado, antes de abrir la sesión completa.

### 2. Ciclo de vida de un expediente (`encuestas`)

```
borrador ──(operativo revisa)──▶ en_revision_operativa
         ──(coordinador revisa)──▶ en_revision_coordinacion
         ──(coordinador valida)──▶ validado_coordinacion
         ──(admin cierra)──▶ cerrado
```

- `/survey` crea el expediente en estado `borrador`, cifrando el payload de datos sensibles con
  `encrypt_data()` antes de guardarlo en `encuestas.datos`.
- `/bandeja` filtra los expedientes visibles según el rol (cada rol ve los que le corresponde
  revisar, conforme a `PERMISSIONS` y al estado actual).
- `/encuesta/<id>/avanzar` consulta `next_status_for_role(role)` para determinar el estado
  esperado y el estado siguiente; si el expediente no está en el estado que el rol puede mover,
  la transición se rechaza. Cada cambio de estado se registra en `logs`.
- Al leer un expediente, `decrypt_data()` (con soporte de *keyring* para llaves legadas) descifra
  `datos` de forma transparente, registrando métricas de latencia.

### 3. Cifrado de datos y rotación de llaves (Fernet + keyring)

- `encrypt_data(payload, ...)` cifra con la llave **activa** y devuelve un blob con el formato
  `b"fp:" + <huella SHA-256 de la llave>.encode() + b"\n" + <token Fernet>`
  (`app.py:2999`). La huella permite identificar, sin descifrar, **con qué llave** se cifró
  cada registro.
- `decrypt_data(blob, ...)` (`app.py:2922`) reconoce el prefijo `fp:`, ubica la llave
  correspondiente en el *keyring* (`get_cipher_for_fingerprint`) — que incluye la llave activa
  más las legadas en `ENCRYPTION_LEGACY_KEY_PATHS` — y descifra. Esto permite **leer datos
  cifrados con llaves anteriores** mientras se completa una rotación.
- **Rotación**: un administrador configura una nueva llave candidata
  (`/admin/keys/configure`, requiere firma de acción con passkey vía
  `check_and_consume_passkey_action`), y al activarla (`/admin/keys/<fp>/activate`) se
  encola un trabajo en `reencrypt_jobs`. `tools/reencrypt_worker.py` procesa la cola en lotes,
  re-descifrando con la llave anterior y re-cifrando con la nueva (`reencrypt_all_surveys`),
  actualizando `encryption_keys.state` (`activo` → `legada` → eventualmente `retiring`).
- `record_encryption_metric()` / `get_encryption_metrics()` registran tiempos de cifrado/
  descifrado en `encryption_metrics`, comparándolos contra
  `ENCRYPTION_LATENCY_WARNING_SECONDS` para detectar degradación.

### 4. PKI X.509 y reto-respuesta

- `_load_or_create_certificate_authority()` genera (si no existe) una **CA local de
  desarrollo**: llave RSA de **3072 bits**, certificado autofirmado válido **10 años**
  (`days=3650`), firmado con **SHA-256**.
- `issue_user_certificate*` emite certificados de usuario: llave RSA de **2048 bits**, firmados
  por la CA con **SHA-256**, validez `CERT_VALIDITY_HOURS` = **720 horas (30 días)**. Pueden
  generarse en servidor o a partir de un **CSR** enviado por el cliente
  (`_build_signed_certificate_from_csr`).
- El **reto-respuesta** (`issue_signature_challenge` / `consume_signature_challenge`,
  `app.py:2182`) construye un *payload* determinista
  `f"CasaMonarca|{purpose}|{username}|{challenge}"` (`build_signature_payload`, `app.py:2243`),
  que el cliente firma con su llave privada y el servidor verifica con
  `verify_certificate_challenge_response` usando **`padding.PKCS1v15()` + `hashes.SHA256()`**
  contra la llave pública del certificado activo del usuario. Los retos tienen un TTL
  (`SIGNATURE_CHALLENGE_TTL`, 300 s) y se consumen una sola vez (anti-repetición).
- `revoke_certificate` / `revoke_certificate_and_passkeys` marcan el certificado como
  `revocado`, registran el motivo y desactivan las passkeys vinculadas.
- `check_certificate_expiration` detecta certificados vencidos y **desactiva automáticamente**
  las passkeys que dependían de ellos (vínculo N:1).

### 5. WebAuthn / Passkeys y vínculo con PKI

- Registro: `/auth/passkey/register/options` genera el reto de creación
  (`generate_registration_options`); `/verify` valida el atestado
  (`verify_registration_response`) y guarda la credencial (`save_passkey_credential`).
- **La primera passkey registrada deriva automáticamente un certificado X.509** para el usuario
  (`derive_certificate_from_first_passkey`, `app.py:1645` → `link_passkey_to_certificate`):
  arquitectura **N:1** — múltiples passkeys de un usuario pueden enlazarse al mismo certificado,
  de modo que revocar el certificado revoca/desactiva todas las passkeys vinculadas
  (`revoke_certificate_and_passkeys`) y viceversa (`revoke_passkey_and_cert`).
- Login: `/auth/passkey/login/options` → `/verify` ejecuta la ceremonia de autenticación
  (`generate_authentication_options` / `verify_authentication_response`), valida la firma
  contra la llave pública COSE almacenada y **comprueba que `sign_count` haya aumentado**
  respecto al valor guardado — la defensa estándar contra clonación de autenticadores.
- Firma de acciones críticas: `/action/passkey/options` → `/verify`, validadas por
  `check_and_consume_passkey_action(expected_action_label, max_age_seconds=60)`
  (`app.py:4143`), exigida antes de operaciones como rotar llaves de cifrado o revocar
  identidades — aporta **no repudio** operativo (la acción queda ligada criptográficamente a
  una credencial específica del usuario, auditada en `logs`).

### 6. Política de contraseñas

`validate_new_password_policy` combina:
- Longitud mínima `PASSWORD_MIN_LENGTH` (12).
- `password_has_minimum_entropy` (rechaza patrones triviales/`COMMON_WEAK_PASSWORDS`).
- `check_password_pwned` — consulta el **modelo de k-anonimato de Have I Been Pwned**: se
  calcula `SHA-1(password)`, se envían sólo los **primeros 5 caracteres hexadecimales** del hash
  a `https://api.pwnedpasswords.com/range/<prefijo>`, y se compara localmente el sufijo contra
  la lista de sufijos devueltos — el servicio externo nunca recibe la contraseña ni el hash
  completo (`app.py:1175-1193`).

`hash_password_argon2id` usa **Argon2id** (`Type.ID`) con
`memory_cost=65536` (64 MiB), `time_cost=3`, `parallelism=2`, `hash_len=32`, `salt_len=16`
(`ARGON2_*`, `app.py:60-64`), generando una sal aleatoria de 16 bytes por contraseña
(`generate_password_salt` → `os.urandom(ARGON2_SALT_LEN)`).

### 7. Solicitudes ARCO multinivel

```
/arco (formulario público)
  → INSERT en solicitudes_arco, nivel_actual = 'usuarios'
  → aprobado_usuarios       (nivel "usuarios")
  → aprobado_operativos     (nivel "operativos")
  → aprobado_coordinadores  (nivel "coordinadores")
        ├─ resuelto = 1                                    (fin del flujo)
        └─ reenviado_por_coordinador = 1, nivel_actual='admin'  (escalado a Admin)
```

Cada nivel registra su aprobación en columnas dedicadas (`aprobado_<nivel>`,
`_at`, `_por`), preservando una pista de auditoría completa de quién aprobó qué y cuándo,
adicional a la bitácora general `logs`. Documentación de diseño extendida en
`IMPLEMENTACION_ARCO_MULTINIVEL.md`.

---

## Seguridad: Cifrado, PKI y Passkeys en detalle

Esta sección resume, con nombres de funciones y constantes reales, los mecanismos
criptográficos del sistema — referencia directa para la sección de Q&A más abajo.

| Mecanismo | Algoritmo / parámetros | Función(es) clave |
|---|---|---|
| Hash de contraseñas | Argon2id, `memory_cost=65536`, `time_cost=3`, `parallelism=2`, sal de 16 B | `hash_password_argon2id`, `verify_password_argon2id` |
| Cifrado de campo | Fernet (AES-128-CBC + HMAC-SHA256 autenticado, con *token* versionado y marca de tiempo) | `encrypt_data`, `decrypt_data` |
| Identificación de llaves | SHA-256 de la llave Fernet → huella hexadecimal (`fingerprint`) | `_build_keyring`, `get_cipher_for_fingerprint` |
| CA local | RSA 3072 bits, autofirmada, SHA-256, validez 10 años | `_load_or_create_certificate_authority` |
| Certificados de usuario | RSA 2048 bits, firmados por la CA con SHA-256, validez 720 h | `issue_user_certificate*`, `_build_signed_certificate_from_csr` |
| Reto-respuesta | Payload determinista + firma RSA con `PKCS1v15` + `SHA-256` | `issue_signature_challenge`, `build_signature_payload`, `verify_certificate_challenge_response` |
| WebAuthn (passkeys) | Pares de llaves asimétricas por autenticador (COSE), reto-respuesta del navegador, `sign_count` anti-clonación | `save_passkey_credential`, `verify_authentication_response` (vía librería `webauthn`) |
| Verificación de breach | HIBP, k-anonimato sobre SHA-1 (prefijo de 5 hex) | `check_password_pwned` |
| Respaldo cifrado | Fernet sobre el archivo completo de la base de datos | `tools/backup_db.py` / `restore_db.py` |

`CERT_PRODUCT_ALGORITHM = "X509/RSA-2048/AES-256-CBC"` (`app.py:56`) es la cadena descriptiva
almacenada junto a cada certificado emitido — documenta tanto el algoritmo de firma del
certificado (RSA 2048) como el cifrado simétrico usado por `cryptography` para envolver la
llave privada en disco (`BestAvailableEncryption`, equivalente a AES-256-CBC vía OpenSSL).

---

## Auditoría, CSRF y Manejo de Errores

### Bitácora (`logs`)

`log(usuario, accion, categoria="operacion", detalle=None)` (`app.py:707`) inserta una fila en
`logs` con marca de tiempo e IP. Se invoca en cada operación sensible: intentos de login
(éxito/fallo/bloqueo), cambios de estado de expediente, emisión/activación/revocación de
certificados y passkeys, configuración/rotación de llaves de cifrado, resoluciones ARCO,
eliminación de usuarios, etc. La categoría `seguridad` distingue eventos de interés para
auditoría de seguridad (bloqueos, revocaciones, fallos de verificación) de las operaciones de
negocio normales (`operacion`). `/logs` permite visualizar la bitácora (acceso restringido por
rol) y `/logs/clear` su limpieza (acción crítica reservada a `admin`).

### CSRF

Protección global registrada como hook `before_request`:
- `ensure_csrf_token()` (`app.py:3087`) genera y guarda en sesión un token CSRF si no existe.
- `validate_csrf()` (`app.py:3093`) compara el token recibido (formulario/cabecera) contra el de
  sesión.
- `csrf_protect()` (`app.py:3103`) aplica la validación a todas las solicitudes que modifican
  estado (POST/PUT/DELETE), rechazando con error si no coincide o falta.

### Cookies de sesión

`enforce_cookie_flags(response)` (`app.py:3118`, hook `after_request`) añade los atributos
`HttpOnly`, `Secure` (según configuración del entorno) y `SameSite` a las cookies de sesión,
mitigando robo de sesión vía XSS y ataques CSRF/cross-site basados en cookies.

### Control de acceso y *gating* de identidad

- `require_role(*roles)` decorador para restringir rutas completas a ciertos roles.
- `has_permission(action)` valida acciones CRUD contra `PERMISSIONS` del rol en sesión.
- `enforce_certificate_setup()` (`before_request`) obliga a `admin`/`coordinador` a completar
  certificado y/o passkey antes de continuar — impide que cuentas críticas operen sin la
  identidad reforzada exigida por la política del sistema.

### Manejo de errores

No existe un *framework* de errores estructurado tipo JSON; los errores se comunican mediante
mensajes flash renderizados en las plantillas (`flash()` + `render_template`) y, para flujos
WebAuthn/AJAX, respuestas JSON con código de estado HTTP apropiado y un campo de error legible.
Los fallos de operaciones criptográficas (firma inválida, certificado expirado, reto vencido,
descifrado fallido por huella desconocida) se traducen en mensajes específicos al usuario y, en
paralelo, en entradas de auditoría con `categoria="seguridad"`.

---

## Pruebas

La suite vive en `tests/` y usa *fixtures* (`app_module`) que aplican `monkeypatch.chdir(tmp_path)`
para reconstruir, por cada prueba, una base de datos, un conjunto de certificados y llaves
**aislados** (ver `tests/test_password_security.py` como referencia del patrón). Cobertura
observada incluye:

- Seguridad de contraseñas: rechazo de contraseñas débiles en alta forzada, bloqueo de usuarios
  con hashes "legados"/débiles (`test_password_security.py`).
- Límite de intentos de login y bloqueo temporal (`login_lockouts`).
- Emisión, activación, revocación y flujo CSR de certificados X.509.
- Firma de acciones críticas con passkeys y verificación CSRF (`test_csrf_arco.py`).
- Ciclo completo de canalización de un expediente entre los cuatro roles.
- Flujo y escalamiento de solicitudes ARCO multinivel (incluye reenvío a `admin`).

Los archivos `test_arco_*.py`, `test_csrf_arco.py` y `test_final_verification.py` en la raíz del
repositorio son **scripts de verificación ad hoc**, no parte de la suite `pytest` formal en
`tests/`.

```bash
PYTHONPATH=. .venv/bin/pytest -q
PYTHONPATH=. .venv/bin/pytest tests/test_password_security.py -q
PYTHONPATH=. .venv/bin/pytest tests/test_password_security.py::test_qa_a_rejects_weak_password_on_forced_update -q
```

---

## Despliegue y Mantenimiento

Esta es una aplicación **single-file** sobre **SQLite**, pensada para una instalación sencilla
(no para una infraestructura distribuida). El despliegue real consiste en:

1. Ejecutar `setup.sh` en el servidor de destino (crea entorno virtual, instala dependencias,
   genera `.env` y `key.key`, crea `certs/`, `backups/`, `logs/`).
2. Ajustar `.env` para producción: `FLASK_ENV=production`, `SECRET_KEY` fuerte y única,
   `ENABLE_SESSION_COOKIE_SECURE=1` (fuerza cookies `Secure`/`Strict`), tiempos de bloqueo y
   política de contraseñas según las políticas de la organización.
3. Ejecutar la app (`python app.py`) detrás de un proxy reverso/terminador TLS si se expone a
   Internet — el código no incluye servidor WSGI de producción (Gunicorn/uWSGI) ni *reverse
   proxy* propios; eso queda fuera del alcance del repositorio.
4. Resguardar `key.key`, `certs/*.pem` y `database.db` con permisos restrictivos (todos están
   excluidos de git vía `.gitignore` precisamente porque son material sensible que nunca debe
   versionarse).
5. Programar respaldos periódicos cifrados con `tools/backup_db.py` (Fernet sobre el archivo
   completo de la base de datos) y validar la restauración con `tools/restore_db.py`.
6. Si se rota la llave de cifrado de datos, seguir el flujo `/admin/keys/configure` →
   `/admin/keys/<fp>/activate` y monitorear `/admin/cifrado/jobs` hasta que
   `tools/reencrypt_worker.py` complete el re-cifrado de todos los expedientes.

No existen Dockerfiles, *pipelines* de CI/CD, balanceadores ni colas externas (Redis/RabbitMQ):
la única "cola" es la tabla `reencrypt_jobs`, consumida por un *worker* de Python ejecutado
manualmente o vía *cron*. La política de ciclo de vida de llaves (basada en NIST SP 800-57) está
documentada al inicio de `Changelog-Backend.txt`, y el plan de migración de firma por certificado
hacia verificación de acciones basada en passkeys se describe también ahí.

---

## Preguntas Frecuentes (FAQ)

**P1. ¿Por qué la app usa SQLite y no PostgreSQL/MySQL?**
Por simplicidad de despliegue: es un sistema de un solo proceso, sin necesidad de un servidor de
base de datos separado. `get_conn()`/`init_db()`/`ensure_column()` encapsulan el acceso de modo
que una futura migración sería localizada, pero no existe planeada ni implementada.

**P2. ¿Dónde están las rutas de la API?**
No hay una "API" en el sentido JSON/REST; toda la interacción ocurre vía formularios HTML
renderizados con Jinja2 y *redirects*. Las únicas excepciones JSON son los *endpoints* WebAuthn
(`/auth/passkey/*`, `/action/passkey/*`) que siguen el protocolo del navegador, y algunos
*endpoints* de panel de administración consumidos por `fetch()`.

**P3. `python app.py` falla con `ModuleNotFoundError`.**
Asegúrate de activar el entorno virtual (`source .venv/bin/activate` o invocar
`.venv/bin/python`) y de haber corrido `pip install -r requirements.txt` (vía `setup.sh`).

**P4. Olvidé cómo regenerar la llave de cifrado.**
`generate_key.py` crea una nueva `key.key`. **Cuidado**: sustituir la llave activa sin pasar por
el flujo de rotación (`/admin/keys/configure` + `/admin/keys/<fp>/activate` +
`reencrypt_worker.py`) deja ilegibles los datos cifrados con la llave anterior.

**P5. Mi cuenta quedó bloqueada tras varios intentos fallidos.**
Espera `LOGIN_LOCKOUT_SECONDS` (15 minutos por defecto) o pide a un `admin` que reinicie el
registro en `login_lockouts`/`failed_login_store` desde el panel correspondiente.

**P6. ¿Cómo prueba el sistema que una acción crítica la autorizó realmente el titular de la
cuenta?**
Mediante reto-respuesta firmado: ya sea con la llave privada del certificado X.509
(`verify_certificate_challenge_response`, PKCS1v15+SHA-256) o con una passkey WebAuthn
(`check_and_consume_passkey_action`). Ambos mecanismos producen una firma criptográfica
verificable y quedan registrados en `logs`, dando trazabilidad y no repudio.

**P7. ¿Qué pasa si mi certificado expira?**
`check_certificate_expiration` lo detecta y desactiva automáticamente las passkeys que dependían
de él (vínculo N:1 passkey↔certificado); deberás re-emitir el certificado desde
`/certificado/setup`.

**P8. ¿Por qué Argon2id y no bcrypt o PBKDF2?**
Argon2id ganó la *Password Hashing Competition* y combina resistencia a ataques por GPU/ASIC
(función de derivación con costo de memoria configurable, `memory_cost=65536` ≈ 64 MiB) con
resistencia a ataques de canal lateral (variante híbrida `id`, a diferencia de `Argon2d`/`Argon2i`
puros). Ver más en la sección de Q&A.

---

## Q&A de Estudio — Criptografía y Ciberseguridad

> Guía de preguntas y respuestas tipo examen, **basada en la implementación real de este
> repositorio** (nombres de funciones, constantes y algoritmos verificables en `app.py` y
> `config.py`). Pensada para un curso de criptografía/ciberseguridad: cada respuesta enlaza el
> concepto teórico con la decisión concreta de diseño tomada en el código.

### Bloque A — Hashing de contraseñas (Argon2id)

**A1. ¿Por qué se usa Argon2id en lugar de un hash rápido como SHA-256 o MD5 para
contraseñas?**
Porque SHA-256/MD5 son funciones de hash *rápidas*, diseñadas para integridad de datos, no para
contraseñas: un atacante con hardware especializado (GPU/ASIC) puede probar miles de millones de
combinaciones por segundo. Argon2id es una **función de derivación de llaves con costo
configurable de memoria, tiempo y paralelismo** (`ARGON2_MEMORY_COST=65536` → 64 MiB,
`ARGON2_TIME_COST=3`, `ARGON2_PARALLELISM=2` en `app.py:60-63`), deliberadamente costosa de
calcular y, sobre todo, costosa de paralelizar en hardware dedicado por su requerimiento de
memoria ("memory-hard"). Esto hace que un ataque de fuerza bruta o de diccionario fuera de línea
sea órdenes de magnitud más lento y costoso.

**A2. ¿Cuál es la diferencia entre Argon2d, Argon2i y Argon2id, y por qué el código usa
`Type.ID`?**
- **Argon2d** maximiza la resistencia a ataques con GPU dependiendo de los datos de entrada para
  el acceso a memoria, pero es vulnerable a ataques de canal lateral (*side-channel*, p. ej.
  *cache-timing*).
- **Argon2i** usa accesos a memoria independientes de los datos (resistente a canal lateral) pero
  algo más débil contra ataques de fuerza bruta optimizados con GPU.
- **Argon2id** es un **híbrido**: combina ambos enfoques (usa Argon2i en las primeras
  iteraciones y Argon2d después), ofreciendo buena resistencia tanto a ataques de canal lateral
  como a ataques de fuerza bruta paralelizados — por eso es la variante recomendada por la RFC
  9106 para hashing de contraseñas, y la que `hash_password_argon2id` selecciona explícitamente
  (`Type.ID`).

**A3. ¿Para qué sirve la sal (`salt`) y por qué se genera con `os.urandom`?**
La sal es un valor aleatorio único por contraseña que se concatena/incorpora antes del hashing.
Su propósito es **evitar el uso de tablas precomputadas (rainbow tables)** y asegurar que dos
usuarios con la misma contraseña obtengan hashes distintos, de modo que comprometer una base de
datos no permita comparar hashes entre cuentas ni reutilizar trabajo de cómputo previo.
`generate_password_salt()` usa `os.urandom(ARGON2_SALT_LEN)` — un generador **criptográficamente
seguro** (CSPRNG basado en las primitivas del sistema operativo), produciendo 16 bytes (128 bits)
de entropía por sal, muy por encima del mínimo recomendado de 16 bytes para evitar colisiones.

**A4. ¿Qué aporta `parallelism=2` y por qué no se eligió un valor mucho mayor?**
El parámetro de paralelismo determina cuántos *lanes* (carriles) de cómputo independientes se
ejecutan al derivar el hash, lo que afecta tanto el tiempo de cálculo como la resistencia a
ataques con hardware masivamente paralelo. Un valor mayor incrementaría la resistencia contra
atacantes con GPU, pero también el costo de CPU/latencia en el servidor en cada login — el valor
`2` es un balance pragmático entre seguridad y experiencia/costo operativo del servidor (un
servidor que atiende muchos logins concurrentes no puede dedicar recursos ilimitados a cada uno).

**A5. ¿Qué información incluye el formato `$argon2id$...` almacenado en `password_hash`, y
por qué eso es relevante para la verificación?**
El formato PHC (*Password Hashing Competition string format*) embebe el algoritmo, la versión,
los parámetros (`m`, `t`, `p`), la sal y el hash resultante en una sola cadena autocontenida.
Esto permite que `verify_password_argon2id` reconstruya exactamente los mismos parámetros usados
al crear el hash (incluso si las constantes globales cambiaron después), garantizando
verificación correcta y facilitando una futura migración de parámetros sin invalidar hashes
existentes (se puede detectar un hash con parámetros "viejos" y forzar su renovación — ver
`password_is_legacy_or_weak`).

### Bloque B — Cifrado simétrico de datos (Fernet)

**B1. ¿Qué construcción criptográfica hay detrás de Fernet, y por qué se considera
"cifrado autenticado"?**
Fernet (de la librería `cryptography`) combina **AES-128 en modo CBC** para confidencialidad con
**HMAC-SHA256** para integridad/autenticidad, sobre un *token* versionado que incluye un IV
aleatorio y una marca de tiempo. Es "autenticado" porque, al descifrar, se verifica primero el
HMAC: si el *token* fue modificado (o la llave es incorrecta), la verificación falla **antes** de
intentar el descifrado, evitando ataques de oráculo de relleno (*padding oracle*) y garantizando
que el receptor detecta cualquier alteración del texto cifrado.

**B2. ¿Por qué el sistema cifra el campo `datos` de cada expediente en lugar de cifrar toda la
base de datos o el disco?**
Es **cifrado a nivel de campo** (*field-level encryption*): protege específicamente la
información sensible de cada expediente incluso si un atacante obtiene acceso de lectura a la
base de datos (p. ej. mediante una vulnerabilidad de inyección SQL u otra fuga), sin afectar
columnas no sensibles que se necesitan para indexar/filtrar (`estado`, `usuario_id`, etc.). Es
un control complementario, no sustituto, de otros (permisos del sistema de archivos, cifrado de
disco, respaldos cifrados).

**B3. ¿Qué es la "huella" (`fingerprint`) que precede a cada blob cifrado (`fp:<huella>\n...`),
y qué problema resuelve?**
Es el **SHA-256 de la llave Fernet** usada para cifrar ese registro en particular
(`hashlib.sha256(key_bytes).hexdigest()`, ver `_build_keyring`). Resuelve el problema de
**identificar, sin necesidad de probar varias llaves por fuerza bruta, con qué llave se cifró
cada dato** — esencial cuando conviven una llave activa y llaves "legadas" durante una rotación:
`decrypt_data` lee la huella, localiza la llave correspondiente en el *keyring*
(`get_cipher_for_fingerprint`) y descifra directamente con ella.

**B4. Explica el proceso de "rotación de llaves" implementado y por qué es necesario.**
La rotación reemplaza periódicamente la llave de cifrado activa (buena práctica recomendada por
NIST SP 800-57 para limitar la cantidad de datos expuestos si una llave se compromete, y para
cumplir políticas de criptoperiodo). En este sistema: (1) el administrador configura una nueva
llave candidata vía `/admin/keys/configure` (acción que exige firma con passkey); (2) al
activarla (`/admin/keys/<fp>/activate`), la llave anterior pasa a estado `legada` y se encola un
trabajo en `reencrypt_jobs`; (3) `tools/reencrypt_worker.py` recorre los expedientes en lotes,
**descifra con la llave legada y vuelve a cifrar con la llave nueva** (`reencrypt_all_surveys`),
de modo que con el tiempo todos los registros quedan bajo la llave activa y la legada puede
retirarse (`retiring`) sin perder acceso a datos antiguos durante la transición.

**B5. ¿Cómo se diferencia el cifrado simétrico (Fernet) usado aquí del cifrado asimétrico
(RSA) usado en la PKI, y por qué cada uno se aplica donde se aplica?**
El cifrado simétrico usa la **misma llave** para cifrar y descifrar — es mucho más eficiente
para grandes volúmenes de datos (como los campos de cada expediente), pero requiere que el
servidor posea la llave para ambas operaciones. El cifrado/firma asimétrico (RSA) usa un **par de
llaves** (privada/pública): la llave privada nunca debe salir del lado del usuario, y la pública
puede distribuirse libremente. Por eso la PKI no se usa para cifrar los datos del expediente
(sería costoso e innecesario), sino para **autenticar al usuario y verificar la autoría de
acciones críticas** mediante firmas digitales que sólo el titular de la llave privada puede
producir.

### Bloque C — PKI / Certificados X.509

**C1. ¿Qué función cumple la Autoridad Certificadora (CA) local, y por qué su llave es de
3072 bits mientras que los certificados de usuario usan 2048 bits?**
La CA es la raíz de confianza del sistema: emite y firma los certificados de usuario, de modo
que verificar la firma de la CA sobre un certificado equivale a confiar en la identidad que
declara. `_load_or_create_certificate_authority` genera una llave RSA de **3072 bits** —
mayor tamaño que los certificados de usuario (2048 bits) — porque la **seguridad de toda la
cadena de confianza depende de la robustez de la llave raíz**: comprometer la CA permitiría
forjar certificados para cualquier identidad, mientras que comprometer un certificado de usuario
sólo afecta a esa cuenta. Es una práctica estándar dimensionar la llave raíz con mayor margen de
seguridad (y, normalmente, mayor vida útil — aquí 10 años frente a 30 días).

**C2. ¿Por qué los certificados de usuario tienen una validez corta (720 horas = 30 días)
mientras que la CA dura 10 años?**
Una validez corta limita la ventana de exposición si una llave privada de usuario se compromete
sin que el usuario lo note: el certificado expira y deja de ser utilizable, forzando una
renovación periódica (que, de paso, revalida que el usuario sigue teniendo control de su llave
privada). La CA, en cambio, al ser la raíz de confianza, cambia con mucha menor frecuencia
porque rotarla implica reemitir *todos* los certificados subordinados — de ahí su vida útil
mucho más larga.

**C3. Describe el protocolo de reto-respuesta (`challenge-response`) implementado y qué
ataque previene frente a, por ejemplo, simplemente "enviar la contraseña otra vez".**
El servidor genera un reto aleatorio único (`issue_signature_challenge`) y construye un *payload*
determinista `f"CasaMonarca|{purpose}|{username}|{challenge}"`
(`build_signature_payload`). El cliente firma ese *payload* con su **llave privada** (RSA,
`PKCS1v15` + `SHA-256`) y el servidor verifica la firma con la **llave pública** del certificado
activo (`verify_certificate_challenge_response`). Como el reto es aleatorio, de un solo uso y
con un TTL (`SIGNATURE_CHALLENGE_TTL=300 s`), un atacante que intercepte una respuesta firmada
**no puede reutilizarla** (a diferencia de un secreto estático como una contraseña, cuya
intercepción permite reproducir la autenticación indefinidamente). Esto es la base de la
**autenticación por posesión de la llave privada**, sin que ésta viaje nunca por la red.

**C4. ¿Qué esquema de relleno (`padding`) y de hash se usan para firmar/verificar, y qué
garantizan?**
`padding.PKCS1v15()` junto con `hashes.SHA256()`. El esquema PKCS#1 v1.5 define cómo se da
formato al hash del mensaje antes de aplicar la operación RSA de firma, de forma estandarizada e
interoperable; SHA-256 produce un resumen criptográfico de 256 bits resistente a colisiones. En
conjunto garantizan que (a) cualquier alteración del mensaje firmado invalida la verificación
(integridad), y (b) sólo quien posea la llave privada correspondiente pudo producir esa firma
(autenticidad/no repudio), siempre que la llave privada permanezca secreta.

**C5. ¿Qué significa "revocar" un certificado en este sistema y por qué no basta con dejar
que expire?**
Revocar (`revoke_certificate` / `revoke_certificate_and_passkeys`) marca el certificado como
`revocado` de inmediato, registra el motivo en `logs` y desactiva las passkeys vinculadas — a
diferencia de la expiración natural, que ocurre en una fecha futura predefinida. La revocación es
necesaria cuando se sospecha que una llave privada fue comprometida, un usuario fue dado de baja,
o cambió de rol: **no se puede esperar a que el certificado expire por sí solo**, porque durante
ese tiempo seguiría siendo criptográficamente válido y utilizable por un atacante.

**C6. ¿Qué papel juega un CSR (Certificate Signing Request) en el flujo
`_build_signed_certificate_from_csr`, y qué garantiza sobre la llave privada del usuario?**
Un CSR permite que el **usuario genere su propio par de llaves localmente** y envíe al servidor
sólo la llave **pública** (junto con los datos de identidad), pidiendo que la CA la firme. Esto
garantiza que la **llave privada nunca sale del dispositivo del usuario ni transita por la red**
— el servidor jamás llega a conocerla — lo que reduce la superficie de exposición frente al
modelo alternativo (generación en servidor), donde el servidor genera el par y debe transmitir
o custodiar la llave privada de forma segura.

### Bloque D — WebAuthn / Passkeys (criptografía de llave pública aplicada)

**D1. ¿Por qué se considera que las passkeys son resistentes al *phishing*, a diferencia de
una contraseña o incluso de un código OTP por SMS/correo?**
Porque el protocolo WebAuthn ata cada credencial al **origen** (`PASSKEY_ORIGIN`/`PASSKEY_RP_ID`)
durante la ceremonia: el navegador firma el reto incluyendo el origen de la página que lo
solicitó, y el autenticador **se niega a operar para un origen distinto** al registrado. Un sitio
de *phishing* que imite la apariencia de Casa Monarca tendría un origen distinto, por lo que el
navegador/autenticador simplemente no completaría la ceremonia — a diferencia de una contraseña
u OTP, que un usuario engañado puede tipear manualmente en cualquier sitio.

**D2. ¿Qué es `sign_count` y qué ataque concreto mitiga su verificación en cada login?**
Es un contador que el autenticador incrementa con cada operación de firma y que se almacena en
`passkey_credentials.sign_count`. En cada autenticación (`verify_authentication_response`), el
servidor comprueba que el nuevo valor sea **mayor** que el almacenado. Esto mitiga la
**clonación de autenticadores**: si alguien copiara el material de una *passkey* (en
autenticadores que no son resistentes a la exportación) y lo usara en paralelo, los contadores
divergirían y una de las dos copias produciría un valor de `sign_count` menor o repetido,
delatando el uso de una credencial duplicada.

**D3. Compara la verificación de una passkey con la verificación de un certificado X.509 en
este sistema: ¿en qué se parecen y en qué difieren criptográficamente?**
Ambos son, en esencia, **pruebas de posesión de una llave privada mediante firma de un reto**:
el servidor envía un desafío, el cliente firma con su llave privada y el servidor verifica con
la llave pública correspondiente. La diferencia central es la **gestión de confianza**: un
certificado X.509 requiere una cadena de confianza hacia una CA (el servidor verifica que la
llave pública está avalada por una autoridad), mientras que una *passkey* WebAuthn se basa en un
**registro directo** (TOFU — *trust on first use* — de la llave pública asociada a la cuenta,
sin cadena de certificación), reforzado por las garantías del propio protocolo del navegador
(verificación de origen, posible verificación biométrica/PIN local).

**D4. ¿Por qué la primera *passkey* registrada deriva automáticamente un certificado X.509
(`derive_certificate_from_first_passkey`), y qué propiedad arquitectónica describe la
relación "N:1" entre passkeys y certificados?**
El sistema mantiene **dos mecanismos paralelos** de identidad reforzada (X.509 y WebAuthn) para
roles críticos; derivar el certificado automáticamente evita que el usuario tenga que pasar por
dos configuraciones independientes y asegura que ambos mecanismos queden **enlazados desde el
origen**. La relación "N:1" significa que **varias** credenciales *passkey* de un mismo usuario
(p. ej. registradas en distintos dispositivos) pueden enlazarse a **un mismo** certificado
(`link_passkey_to_certificate`), de modo que revocar el certificado revoca/desactiva todas las
passkeys asociadas (y viceversa, según el caso) — manteniendo una única fuente de verdad sobre
la identidad reforzada del usuario, sin importar cuántos dispositivos use.

**D5. ¿Qué se firma exactamente cuando un *admin* "autoriza una acción crítica" con su
*passkey* (`/action/passkey/verify`), y por qué eso aporta *no repudio*?**
Se firma un reto específico para esa acción (`expected_action_label`, validado con un margen de
antigüedad `max_age_seconds=60` en `check_and_consume_passkey_action`), atado a la sesión y al
propósito declarado (p. ej. "activar nueva llave de cifrado"). Como la firma sólo puede
producirla quien posee la llave privada del autenticador (protegida por hardware/biometría local
del dispositivo), el sistema obtiene una **prueba criptográfica verificable** de que *esa*
persona autorizó *esa* acción en *ese* momento — quedando además registrada en `logs`. Esto es
no repudio: el usuario no puede negar de forma creíble haber autorizado la acción, porque sólo su
credencial podía producir esa firma.

### Bloque E — Protecciones de aplicación web (CSRF, sesiones, cookies)

**E1. ¿Qué tipo de ataque previene la protección CSRF, y cómo está implementada aquí?**
CSRF (*Cross-Site Request Forgery*) consiste en inducir al navegador de una víctima ya
autenticada a enviar, sin su consentimiento, una solicitud que modifica estado en un sitio (p.
ej. cambiar su contraseña o aprobar una solicitud) aprovechando que el navegador adjunta
automáticamente las cookies de sesión. La mitigación aquí es el **patrón de token sincronizado**:
`ensure_csrf_token()` genera un token impredecible y lo guarda en la sesión del servidor; cada
formulario debe incluirlo, y `validate_csrf()`/`csrf_protect()` (hook `before_request`) rechazan
cualquier solicitud que modifique estado (POST/etc.) si el token no coincide — un sitio externo
no puede conocer ese token porque no tiene acceso a la sesión de la víctima.

**E2. ¿Para qué sirven los atributos `HttpOnly`, `Secure` y `SameSite` en las cookies de
sesión (`enforce_cookie_flags`), y qué amenaza mitiga cada uno?**
- **`HttpOnly`**: impide que JavaScript del lado del cliente lea la cookie — mitiga el robo de
  sesión mediante **XSS** (un script inyectado no podría exfiltrar la cookie).
- **`Secure`**: la cookie sólo se envía sobre **HTTPS** — mitiga la intercepción en tránsito
  (*sniffing*) sobre redes no cifradas.
- **`SameSite`** (`Lax` en desarrollo, `Strict` forzado en producción): controla si la cookie se
  envía en solicitudes iniciadas desde otros sitios — mitiga **CSRF** y fugas de sesión mediante
  navegación cruzada (en `Strict`, la cookie no se envía ni siquiera en navegaciones de nivel
  superior provenientes de otro sitio).

**E3. ¿Por qué `SECRET_KEY` tiene un valor por defecto inseguro (`"secreto_demo"`) en
`config.py`, y qué riesgo implica no sobreescribirlo en producción?**
Sirve como conveniencia para desarrollo local (la app debe poder arrancar sin configuración
adicional). El riesgo de no sobreescribirlo en producción es severo: `SECRET_KEY` es la llave con
la que Flask **firma criptográficamente las cookies de sesión**; si un atacante la conoce, puede
**forjar cookies de sesión válidas** para cualquier usuario (incluyendo administradores) sin
necesidad de conocer su contraseña — comprometiendo por completo el control de acceso del
sistema. Por eso `ProductionConfig` exige obtenerla de una variable de entorno.

### Bloque F — Mitigación de fuerza bruta y control de acceso

**F1. Describe el mecanismo de bloqueo de cuentas (`login_lockouts`) y explica por qué
combina una "ventana" y un "bloqueo" en lugar de bloquear permanentemente al primer error.**
Tras `LOGIN_MAX_ATTEMPTS` (5) intentos fallidos dentro de una **ventana** de
`LOGIN_WINDOW_SECONDS` (300 s = 5 min), la cuenta/IP queda **bloqueada** durante
`LOGIN_LOCKOUT_SECONDS` (900 s = 15 min) — `_is_locked`/`_record_failed`/`_clear_failed`. Este
diseño de **ventana deslizante + bloqueo temporal** equilibra dos riesgos: bloquear
permanentemente al primer error facilitaría un **ataque de denegación de servicio dirigido**
(un atacante podría bloquear cuentas legítimas a propósito sólo con teclear mal la contraseña),
mientras que no bloquear nunca permitiría ataques de fuerza bruta/diccionario en línea sin
fricción. Reiniciar el contador tras la ventana evita penalizar a usuarios que simplemente
cometen errores esporádicos de tecleo.

**F2. ¿Por qué `_is_locked` se evalúa *antes* de verificar la contraseña, y qué principio de
seguridad refleja eso?**
Porque revelar a través del tiempo de respuesta o del mensaje de error si una cuenta existe o
está bloqueada filtra información útil para un atacante (enumeración de usuarios). Evaluar el
bloqueo primero, con una respuesta uniforme, refleja el principio de **minimizar la superficie
de información expuesta** ante intentos de autenticación — el sistema no debería comportarse de
forma observablemente distinta según si el nombre de usuario existe o no.

**F3. Explica el modelo RBAC (`PERMISSIONS`/`has_permission`/`require_role`) y cómo aplica el
principio de mínimo privilegio en el flujo de expedientes.**
Cada rol tiene un conjunto fijo de permisos CRUD (`usuario`: sólo `create`; `operativo`:
`create`+`read`; `coordinador`: + `update`; `admin`: + `delete`). Además,
`next_status_for_role()` ata cada **transición de estado** del expediente a un rol específico, de
modo que ningún actor puede saltarse pasos del flujo de revisión (p. ej. un `usuario` no puede
"validar" su propio expediente). Esto encarna **mínimo privilegio** (cada rol puede hacer
exactamente lo necesario para su función, nada más) y **separación de funciones** (ningún rol
controla el ciclo completo en solitario, reduciendo el riesgo de fraude o error no detectado).

### Bloque G — Verificación de contraseñas filtradas (HIBP) y hashing no sensible

**G1. Explica paso a paso el modelo de "k-anonimato" usado por `check_password_pwned` para
consultar Have I Been Pwned sin revelar la contraseña al servicio externo.**
1. Se calcula `SHA-1(contraseña)` y se expresa en hexadecimal mayúsculas.
2. Se envían a la API **sólo los primeros 5 caracteres** del hash (el "prefijo"), nunca la
   contraseña ni el hash completo.
3. El servicio responde con **todos los sufijos** (el resto del hash) de contraseñas filtradas
   que comparten ese prefijo — potencialmente cientos o miles de candidatos.
4. La comparación final del **sufijo completo** ocurre **localmente**, en el servidor de Casa
   Monarca, sin que HIBP llegue a saber qué contraseña exacta se está consultando.
Este diseño (k-anonimato) permite aprovechar una base de datos externa de filtraciones masivas
**sin comprometer la confidencialidad** de la contraseña que se está validando — ni siquiera
ante el propio proveedor del servicio.

**G2. ¿Por qué se usa `SHA-1` aquí, si en el Bloque A se explicó que es inadecuado para
contraseñas?**
No hay contradicción: `SHA-1` no se usa aquí **como mecanismo de almacenamiento/protección** de
la contraseña (para eso se usa Argon2id), sino como **identificador de búsqueda** en un protocolo
de terceros (la API de HIBP fue diseñada y publicada usando SHA-1 por razones de compatibilidad
e interoperabilidad con su base de datos existente de filtraciones). El uso es efímero —sólo
para esa consulta puntual— y su "debilidad" frente a ataques de fuerza bruta es irrelevante en
este contexto, porque no protege ningún secreto a largo plazo: simplemente referencia un valor
que, por definición, **ya está filtrado públicamente**.

**G3. ¿Qué diferencia hay entre que el sistema rechace una contraseña por "filtrada" (HIBP) y
que la rechace por "entropía insuficiente" (`password_has_minimum_entropy`)?**
Son controles complementarios sobre amenazas distintas: la verificación de **entropía** evalúa
si la contraseña, *en abstracto*, es lo bastante impredecible (longitud, variedad de caracteres,
ausencia de patrones triviales o de `COMMON_WEAK_PASSWORDS`) para resistir un ataque de fuerza
bruta genérico; la verificación **HIBP** comprueba si esa contraseña concreta **ya apareció en
filtraciones reales conocidas** — es decir, si ya forma parte de los diccionarios que cualquier
atacante real usaría primero, sin importar cuán "aleatoria" parezca a simple vista (una
contraseña larga y compleja, pero reutilizada de un sitio ya filtrado, sigue siendo insegura).

### Bloque H — Preguntas de análisis / comparación (tipo "explica con tus palabras")

**H1. Si tuvieras que explicar en una frase por qué este sistema usa *tres* mecanismos
criptográficos distintos para "demostrar identidad" (contraseña+Argon2id, certificado X.509,
passkey WebAuthn), ¿cuál sería la justificación de diseño?**
Cada mecanismo cubre una capa distinta del modelo de amenazas: la contraseña (con Argon2id) es
el factor base de "algo que sabes", resistente a ataques de fuerza bruta fuera de línea; el
certificado X.509 añade "algo que tienes" verificable mediante criptografía asimétrica clásica e
interoperable (útil para automatización/firma de retos); la *passkey* WebAuthn añade un segundo
"algo que tienes" moderno, resistente a *phishing* por diseño y normalmente respaldado por
verificación local del dispositivo (biometría/PIN) — y sólo se exige a los roles cuyo
compromiso tendría mayor impacto (`admin`, `coordinador`).

**H2. ¿Qué tienen en común, criptográficamente, la verificación de una firma de certificado
(`PKCS1v15`+`SHA256`), la verificación de una *passkey* y la verificación del HMAC dentro de un
token Fernet? ¿Qué principio de seguridad subyace a los tres?**
Los tres son, en el fondo, **comprobaciones de un valor producido con un secreto que el
verificador no posee (o no necesita poseer)**: una firma RSA requiere la llave privada del
firmante; la verificación WebAuthn requiere la llave privada del autenticador; el HMAC de Fernet
requiere la llave simétrica compartida. En los tres casos, el verificador puede confirmar
**autenticidad/integridad sin poder, por sí solo, producir un valor válido falso** — el principio
subyacente es que la seguridad reside en el secreto (la llave), no en el secreto del algoritmo
(*Kerckhoffs's principle*): los algoritmos (RSA, ECDSA/COSE, HMAC-SHA256) son públicos y
estandarizados; lo que protege al sistema es exclusivamente el control de las llaves.

**H3. Un compañero argumenta: "si ya tenemos Argon2id para las contraseñas, ¿por qué
complicar el sistema con certificados X.509 y passkeys además?" ¿Cómo le responderías,
relacionándolo con el modelo de amenazas de Casa Monarca?**
Argon2id protege **un secreto compartido** (la contraseña): si ese secreto se filtra —por
*phishing*, reutilización en otro sitio comprometido, o malware en el dispositivo del usuario—
deja de ser una barrera, sin importar cuán robusto sea el hashing del lado del servidor (el
hashing protege la base de datos, no protege al usuario de revelar su contraseña). Los
certificados y *passkeys* añaden factores basados en **posesión de una llave privada que nunca
viaja por la red ni se revela al servidor**, eliminando esa clase de riesgo para las cuentas
(`admin`, `coordinador`) cuyo compromiso tendría el mayor impacto sobre la organización (acceso a
datos personales sensibles de personas migrantes, control de la rotación de llaves de cifrado,
etc.) — es defensa en profundidad dirigida específicamente a los activos de mayor criticidad.

**H4. Explica por qué la combinación "cifrado de campo (Fernet) + huellas SHA-256 + cola de
re-cifrado (`reencrypt_jobs`)" es preferible a simplemente "cambiar la llave y aceptar que los
datos viejos queden ilegibles".**
Cambiar la llave sin un mecanismo de transición provocaría **pérdida de disponibilidad de los
datos históricos** (todos los expedientes cifrados con la llave anterior quedarían
irrecuperables) — inaceptable para un sistema que custodia información sensible con valor legal y
operativo a largo plazo. El diseño con huellas + *keyring* + cola de trabajos permite una
transición **gradual y verificable**: los datos antiguos siguen siendo legibles (vía la llave
legada, identificada por su huella) mientras un proceso en segundo plano los migra
progresivamente a la llave nueva, sin tiempo de inactividad y sin arriesgar la integridad ni la
disponibilidad de la información durante la rotación — precisamente el objetivo de una política
de ciclo de vida de llaves bien diseñada (cf. NIST SP 800-57).

---

*Fin del documento.*
