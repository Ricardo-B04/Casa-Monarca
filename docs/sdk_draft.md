# SDK / Interfaz para Desarrolladores (Borrador)

## Descripción General

### Propósito del sistema

Casa Monarca es un **gestor centralizado de expedientes** que proporciona:

1. **Gestión de identidad y acceso:**
   - Autenticación con contraseña (hasheada y salada).
   - Autenticación reforzada (challenge-response + certificados X.509) para roles críticos (admin, coordinador).
   - Control de acceso basado en roles (RBAC): usuario, operativo, coordinador, admin.

2. **Gestión de expedientes:**
   - Ciclo de vida de expedientes: borrador → en revisión → validado → cerrado.
   - Trazabilidad: cada cambio de estado es auditado y registrado.
   - Permisos granulares: cada rol puede realizar acciones específicas en diferentes estados.

3. **Auditoría y cumplimiento:**
   - Bitácora completa de eventos (login, creaciones, canalizaciones, revocaciones).
   - Trazabilidad de acciones críticas con certificados digitales.
   - Backup/restore cifrado para recuperación ante desastres.

### Alcance

**¿Qué hace?**
- ✅ Gestión de usuarios con roles diferenciados.
- ✅ Flujo de expedientes con validaciones por nivel.
- ✅ Login seguro con challenge-response.
- ✅ Emisión, validación y revocación de certificados X.509.
- ✅ Auditoría completa mediante bitácora de eventos.
- ✅ Backup/restore cifrado (AES-256).
- ✅ API REST para integración (endpoints de expedientes, usuarios, certificados).

**¿Qué límites tiene?**
- ❌ No integra LDAP/AD (SSO). Usuarios creados localmente en base de datos.
- ❌ No tiene HSM (hardware security module). CA almacenada en filesystem.
- ❌ No soporta despliegue horizontal con sincronización de estado (SQL simplemente local).
- ❌ No tiene dashboard de reportes avanzados (bitácora básica solamente).
- ❌ No soporta delegación de firmas (solo admin/coordinador pueden firmar).
- ❌ No tiene 2FA por SMS/Email (solo certificados para roles críticos).

### Casos de uso principales

#### 1. **Flujo operativo básico: Usuario crea y canaliza expediente**

```
Usuario inicia sesión → Crea expediente (borrador) → Canaliza a Operativo
  ↓
Operativo revisa → Canaliza a Coordinador
  ↓
Coordinador valida (con certificado + firma) → Canaliza a Admin
  ↓
Admin cierra (con certificado + firma) → Expediente cerrado
```

#### 2. **Crear usuario Admin (requiere certificado)**

```
Admin existente autenticado (con certificado + firma)
  ↓
Navega a "Crear usuario" → Completa formulario + firma su acción
  ↓
Sistema verifica firma y crea nuevo usuario
  ↓
Nuevo usuario debe cambiar contraseña e generar su certificado
```

#### 3. **Setup de certificado (CSR recomendado)**

```
Usuario genera clave privada local (2048 RSA)
  ↓
Genera CSR (Certificate Signing Request) con su clave
  ↓
Carga CSR en /certificado/setup
  ↓
Servidor valida y firma el CSR
  ↓
Usuario descarga certificado y puede usar para login
```

#### 4. **Integración con sistemas externos (API)**

```
Sistema externo autentica con credenciales
  ↓
Obtiene token de sesión de Casa Monarca
  ↓
Consulta expedientes via GET /expediente/<id>
  ↓
Canaliza expediente si tiene permisos: POST /expediente/<id>/canalizar
  ↓
Acciones quedan auditadas en bitácora
```

---

## Arquitectura del Sistema

### Tipo de arquitectura

Casa Monarca utiliza una **arquitectura en capas (Layered Architecture)** con patrón **MVC (Model-View-Controller)** adaptado para Flask:

- **Capa de presentación:** templates HTML (Jinja2) + CSS estático.
- **Capa de lógica de negocio:** rutas Flask (app.py) con validación de roles y permisos.
- **Capa de persistencia:** SQLite con esquema en `database.py`.
- **Capa de seguridad:** módulo PKI interno para certificados, validación de firmas.

### Componentes principales

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENTE (Navegador)                       │
│                    templates/ (HTML + CSS)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP/HTTPS
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       SERVIDOR FLASK (app.py)                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Rutas y Controladores Flask                │   │
│  │  ├─ /login           → Autenticación                     │   │
│  │  ├─ /dashboard       → Panel de expedientes            │   │
│  │  ├─ /expediente/*    → Gestión de expedientes          │   │
│  │  ├─ /admin/*         → Gestión de usuarios (admin)     │   │
│  │  ├─ /certificado/*   → Setup y gestión de certs        │   │
│  │  └─ /bitacora        → Visualización de eventos        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                             │                                    │
│              ┌──────────────┼──────────────┐                    │
│              ▼              ▼              ▼                    │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │  Validación  │ │    RBAC      │ │  Verificación│            │
│  │  de entrada  │ │  (roles/      │ │   de firma  │            │
│  │              │ │   permisos)   │ │ (certificados)           │
│  └──────────────┘ └──────────────┘ └──────────────┘            │
│              │              │              │                    │
└──────────────┼──────────────┼──────────────┼────────────────────┘
               │              │              │
               ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 MÓDULO DE DATOS (database.py)                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Tablas SQLite:                                                  │
│  ├─ usuarios        (id, username, password_hash, role, ...)   │
│  ├─ expedientes     (id, user_id, titulo, estado, ...)         │
│  ├─ certificados    (id, user_id, cert_pem, huella, ...)       │
│  ├─ bitacora        (id, usuario, accion, timestamp, ...)      │
│  └─ login_attempts  (id, username, intentos, locked_until)     │
│                                                                   │
└────────┬────────────────────────────────────────────────────────┘
         │
         ▼
    database.db (SQLite local)
```

### Módulo PKI (Seguridad)

```
┌─────────────────────────────────────────────────────────────────┐
│                    MÓDULO PKI INTERNO (app.py)                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  CA Local                                                        │
│  ├─ ca_cert.pem   (certificado de la CA)                        │
│  └─ ca_key.pem    (clave privada de la CA)                      │
│                                                                   │
│  Flujo de emisión:                                              │
│  1. Usuario solicita certificado en /certificado/setup          │
│  2. Sistema recibe CSR o genera uno                             │
│  3. CA firma y genera certificado X.509                         │
│  4. Certificado se almacena en BD con huella                    │
│                                                                   │
│  Flujo de validación (login):                                   │
│  1. Usuario envía certificado + firma del challenge             │
│  2. Sistema verifica firma de CA                                │
│  3. Verifica vigencia y huella                                  │
│  4. Verifica que certificate.CN == username                     │
│  5. Comprueba que no esté revocado                              │
│  → Si todo OK: autenticación exitosa                            │
│                                                                   │
│  Flujo de revocación:                                           │
│  1. Admin revoca certificado con motivo obligatorio             │
│  2. Certificado marcado como revocado en BD                     │
│  3. Evento registrado en bitácora                               │
│  4. Usuario debe generar nuevo certificado                      │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Flujo general de solicitud autenticada

```
1. CLIENTE                          2. SERVIDOR
   ├─ GET /login                    └─ Genera UUID challenge
   │
   ├─ Copia challenge               
   ├─ Construye payload             
   │  CasaMonarca|login|usuario|{challenge}
   │
   ├─ Firma payload con clave privada
   │  openssl dgst -sha256 -sign private.key
   │
   ├─ POST /login                   3. SERVIDOR
   │  ├─ username                   ├─ Obtiene usuario de BD
   │  ├─ password                   ├─ Verifica hash de password
   │  ├─ challenge                  ├─ Verifica firma
   │  ├─ signature_b64              ├─ Verifica certificado
   │  └─ certificate.pem            ├─ Revisa si no está revocado
   │                                ├─ Crea sesión
   │                                └─ Retorna 200 OK
   │
   └─ Sesión activa                 4. Solicitudes posteriores
      └─ Cookies de sesión usadas  └─ RBAC verifica permisos
         para futuras requests        por rol en cada endpoint
```

---

## Stack Tecnológico

### Lenguajes

| Lenguaje | Propósito | Versión |
|----------|-----------|---------|
| **Python** | Backend, lógica de negocio, scripts | 3.10+ (recomendado 3.11) |
| **HTML5** | Templates de presentación (Jinja2) | HTML5 estándar |
| **CSS3** | Estilos y diseño responsive | CSS3 estándar |
| **JavaScript** | Interactividad en cliente (opcional) | ES6+ |
| **SQL** | Consultas a base de datos SQLite | SQLite dialect |
| **Bash/Shell** | Scripts de administración, backup | zsh/bash |
| **OpenSSL** | Generación y manejo de certificados | 1.1.1+ |

### Frameworks y librerías Python

#### Core

| Librería | Propósito | Versión |
|----------|-----------|---------|
| **Flask** | Framework web micro | 2.0+ |
| **Werkzeug** | Utilidades HTTP y hashing de contraseñas | 2.0+ (incluido en Flask) |
| **Jinja2** | Motor de templates HTML | 3.0+ (incluido en Flask) |

#### Seguridad y criptografía

| Librería | Propósito | Versión |
|----------|-----------|---------|
| **cryptography** | Cifrado AES-256, manejo de certificados X.509 | 3.0+ |
| **cryptography.hazmat.primitives.hashes** | Funciones hash (SHA-256) | (incluido en cryptography) |
| **cryptography.hazmat.primitives.asymmetric** | RSA, firma digital | (incluido en cryptography) |
| **cryptography.x509** | Generación y validación de certificados X.509 | (incluido en cryptography) |

#### Testing (opcional, para desarrollo)

| Librería | Propósito | Versión |
|----------|-----------|---------|
| **pytest** | Framework de testing | 7.0+ |
| **pytest-cov** | Cobertura de tests | 4.0+ |

#### Base de datos

| Librería | Propósito | Versión |
|----------|-----------|---------|
| **sqlite3** | Driver SQLite (librería estándar Python) | - |

### Arquitectura de herramientas

```
┌────────────────────────────────────────────────────────────────┐
│                    ENTORNO DE DESARROLLO                        │
├────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Sistema operativo: macOS, Linux, Windows                       │
│  Python 3.10+ (virtualenv recomendado)                          │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐      │
│  │ Dependencias principales (requirements)              │      │
│  ├──────────────────────────────────────────────────────┤      │
│  │ - Flask==2.3.x                                       │      │
│  │ - cryptography==41.x                                 │      │
│  │ - Werkzeug==2.3.x (auto con Flask)                   │      │
│  │ - pytest==7.x (desarrollo)                           │      │
│  └──────────────────────────────────────────────────────┘      │
│                                                                  │
│  ┌──────────────────────────────────────────────────────┐      │
│  │ Herramientas del sistema (no Python)                 │      │
│  ├──────────────────────────────────────────────────────┤      │
│  │ - OpenSSL 1.1.1+  (gestión de certs)                │      │
│  │ - SQLite 3.x      (base de datos)                   │      │
│  │ - Git             (control de versiones)            │      │
│  └──────────────────────────────────────────────────────┘      │
│                                                                  │
└────────────────────────────────────────────────────────────────┘
```

### Flujo de dependencias

```
CLIENTE (Navegador)
    ↓
    ├─ HTML5 (templates Jinja2)
    ├─ CSS3 (style.css)
    └─ JavaScript (opcional, interactividad)
    
         HTTP/HTTPS
            ↓
            
SERVIDOR FLASK (app.py)
    ↓
    ├─ Flask              ← Enrutamiento y sesiones
    ├─ Werkzeug           ← Hashing de contraseñas
    ├─ Jinja2             ← Rendering de templates
    ├─ cryptography       ← Cifrado AES-256
    │  ├─ cryptography.hazmat.primitives.hashes         ← SHA-256
    │  ├─ cryptography.hazmat.primitives.asymmetric    ← Firma digital
    │  └─ cryptography.x509                             ← Certificados X.509
    └─ database.py        ← Lógica de datos
         ↓
         sqlite3           ← Driver SQLite
         ↓
         database.db       ← Base de datos

HERRAMIENTAS EXTERNAS
    ├─ openssl            ← Generación/validación de certificados
    ├─ python generate_key.py    ← Script de generación de clave
    ├─ python tools/backup_db.py   ← Backup cifrado
    └─ python tools/restore_db.py  ← Restore
```

### Requisitos de instalación por entorno

**Desarrollo local:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask cryptography werkzeug pytest
```

**Producción (mínimo):**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install flask cryptography
```

**Con todas las herramientas (desarrollo + testing):**
```bash
pip install flask cryptography werkzeug pytest pytest-cov
```

### Versiones recomendadas (requirements.txt)

```
Flask==2.3.3
cryptography==41.0.7
Werkzeug==2.3.7
pytest==7.4.3
pytest-cov==4.1.0
```

---

## Configuración del Entorno

### Requisitos (versiones)

#### Sistema operativo

| SO | Versión | Estado |
|----|---------|--------|
| macOS | 10.14+ | ✅ Soportado |
| Linux (Ubuntu/Debian) | 18.04 LTS+ | ✅ Soportado |
| Linux (RHEL/CentOS) | 8+ | ✅ Soportado |
| Windows 10/11 | 21H2+ | ✅ Soportado (con WSL2 recomendado) |

#### Runtime y compiladores

| Componente | Versión mínima | Versión recomendada |
|------------|-----------------|-------------------|
| **Python** | 3.9 | 3.11 o 3.12 |
| **pip** | 21.0 | 24.0+ |
| **OpenSSL** | 1.1.1 | 3.x |
| **SQLite** | 3.25 | 3.40+ |

#### Dependencias Python (requirements.txt)

```
Flask==2.3.3
cryptography==41.0.7
Werkzeug==2.3.7
Jinja2==3.1.2
argon2-cffi==23.1.0
requests==2.31.0
pytest==7.4.3
pytest-cov==4.1.0
```

**Instalación:**
```bash
# Crear entorno virtual
python3 -m venv .venv

# Activar (macOS/Linux)
source .venv/bin/activate

# Activar (Windows)
.venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

**Verificación:**
```bash
# Verificar Python
python --version           # Debe ser 3.9+

# Verificar OpenSSL
openssl version            # Debe ser 1.1.1+

# Verificar SQLite
sqlite3 --version          # Debe ser 3.25+

# Verificar dependencias instaladas
pip list | grep -E "(Flask|cryptography|pytest)"
```

### Variables de entorno

#### Variables de desarrollo

Se definen en un archivo `.env` local (NO incluir en git):

```bash
# Seguridad de aplicación
SECRET_KEY=secreto_demo_muy_largo_y_aleatorio_para_desarrollo
APP_SECRET_KEY=app_secret_key_alternativo
ENABLE_SESSION_COOKIE_SECURE=0  # Desactivar HTTPS check en local

# Configuración de sesión
SESSION_COOKIE_SAMESITE=Lax      # Desarrollo: Lax; Producción: Strict
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SECURE=False      # HTTPS solo en producción

# Certificados (PKI local)
CERT_CA_CERT_PATH=certs/ca_cert.pem
CERT_CA_KEY_PATH=certs/ca_key.pem

# Rate limiting (login)
LOGIN_MAX_ATTEMPTS=5
LOGIN_WINDOW_SECONDS=300         # 5 minutos
LOGIN_LOCKOUT_SECONDS=900        # 15 minutos

# Validación de contraseña
PASSWORD_MIN_LENGTH=12

# Challenge-response
SIGNATURE_CHALLENGE_TTL_SECONDS=300  # 5 minutos

# Logging
FLASK_ENV=development
FLASK_DEBUG=1
LOG_LEVEL=DEBUG
```

#### Variables de producción

```bash
# Seguridad (CRÍTICO)
SECRET_KEY=<generar-con-secrets.token_hex(32)>
APP_SECRET_KEY=<generar-con-secrets.token_hex(32)>

# Cookies (HTTPS obligatorio)
SESSION_COOKIE_SECURE=1
SESSION_COOKIE_HTTPONLY=1
SESSION_COOKIE_SAMESITE=Strict

# Certificados (PKI en servidor)
CERT_CA_CERT_PATH=/etc/casa-monarca/certs/ca_cert.pem
CERT_CA_KEY_PATH=/etc/casa-monarca/certs/ca_key.pem

# Rate limiting más estricto
LOGIN_MAX_ATTEMPTS=3
LOGIN_WINDOW_SECONDS=300
LOGIN_LOCKOUT_SECONDS=1800       # 30 minutos

# Logging
FLASK_ENV=production
FLASK_DEBUG=0
LOG_LEVEL=INFO
```

#### Configuración por entorno

```bash
# Cargar variables desde .env (desarrollo)
export $(cat .env | xargs)
python app.py

# Con Flask CLI (desarrollo)
FLASK_ENV=development flask run

# Con Gunicorn (producción recomendado)
gunicorn --workers 4 --bind 0.0.0.0:5000 app:app
```

### Archivos de configuración

#### `.env.example` — Plantilla de variables

Crear archivo `.env.example` (sí incluir en git) con todas las variables documentadas:

```bash
# Casa Monarca Configuration Template
# Copy to .env and fill with appropriate values for your environment

# === SECURITY ===
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=your_secret_key_here_min_32_chars
APP_SECRET_KEY=your_app_secret_key_here

# === SESSION COOKIES ===
# Desarrollo: 0; Producción: 1
ENABLE_SESSION_COOKIE_SECURE=0
SESSION_COOKIE_SAMESITE=Lax
SESSION_COOKIE_HTTPONLY=True

# === PKI / CERTIFICATES ===
CERT_CA_CERT_PATH=certs/ca_cert.pem
CERT_CA_KEY_PATH=certs/ca_key.pem

# === RATE LIMITING ===
LOGIN_MAX_ATTEMPTS=5
LOGIN_WINDOW_SECONDS=300
LOGIN_LOCKOUT_SECONDS=900

# === PASSWORD POLICY ===
PASSWORD_MIN_LENGTH=12

# === AUTHENTICATION ===
SIGNATURE_CHALLENGE_TTL_SECONDS=300

# === ENVIRONMENT ===
FLASK_ENV=development
FLASK_DEBUG=1
LOG_LEVEL=DEBUG
```

**Uso:**
```bash
# Copiar plantilla
cp .env.example .env

# Editar con tus valores
nano .env

# Cargar variables
source .env
```

#### `config.py` — Configuración centralizada (alternativa)

Crear archivo `config.py` para gestión de configuración por entorno:

```python
import os
from datetime import timedelta

class Config:
    """Configuración base (desarrollo)"""
    SECRET_KEY = os.environ.get("SECRET_KEY") or "secreto_demo"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
    # PKI
    CERT_CA_CERT_PATH = os.environ.get("CERT_CA_CERT_PATH", "certs/ca_cert.pem")
    CERT_CA_KEY_PATH = os.environ.get("CERT_CA_KEY_PATH", "certs/ca_key.pem")
    CERT_VALIDITY_HOURS = 720
    
    # Rate limiting
    LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_WINDOW_SECONDS = int(os.environ.get("LOGIN_WINDOW_SECONDS", "300"))
    LOGIN_LOCKOUT_SECONDS = int(os.environ.get("LOGIN_LOCKOUT_SECONDS", "900"))
    
    # Password policy
    PASSWORD_MIN_LENGTH = int(os.environ.get("PASSWORD_MIN_LENGTH", "12"))
    
    # Challenge-response
    SIGNATURE_CHALLENGE_TTL = int(os.environ.get("SIGNATURE_CHALLENGE_TTL_SECONDS", "300"))


class DevelopmentConfig(Config):
    """Configuración para desarrollo"""
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    LOG_LEVEL = "DEBUG"


class ProductionConfig(Config):
    """Configuración para producción"""
    DEBUG = False
    SESSION_COOKIE_SECURE = os.environ.get("ENABLE_SESSION_COOKIE_SECURE", "1") == "1"
    SESSION_COOKIE_SAMESITE = "Strict"
    LOG_LEVEL = "INFO"


class TestingConfig(Config):
    """Configuración para testing"""
    TESTING = True
    SESSION_COOKIE_SECURE = False
    LOGIN_MAX_ATTEMPTS = 1000  # Desactivar rate-limiting en tests
    LOG_LEVEL = "DEBUG"


# Seleccionar configuración según entorno
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig
}
```

**Uso en `app.py`:**
```python
import os
from config import config

env = os.environ.get("FLASK_ENV", "development")
app.config.from_object(config[env])
```

#### `requirements.txt` — Dependencias Python

```
Flask==2.3.3
cryptography==41.0.7
Werkzeug==2.3.7
Jinja2==3.1.2
argon2-cffi==23.1.0
requests==2.31.0
pytest==7.4.3
pytest-cov==4.1.0
python-dotenv==1.0.0
```

**Instalación:**
```bash
pip install -r requirements.txt
```

#### `.gitignore` — Archivos a ignorar

```
# Entorno virtual
.venv/
venv/
ENV/

# Archivos de configuración sensibles
.env
.env.local
.env.*.local

# Archivos criptográficos
key.key
*.key
*.pem
admin_*_demo.*
coord_*_demo.*

# Base de datos
*.db
*.sqlite
*.sqlite3
database.db
usuarios.db
backups/

# Logs
*.log
flask.log
*.log.*

# Cache de Python
__pycache__/
*.py[cod]
*$py.class
.pytest_cache/
.coverage
htmlcov/

# IDE
.vscode/
.idea/
*.swp
*.swo
*.swn
*~
.DS_Store

# Sistema
.env.bak
dist/
build/
*.egg-info/
```

#### `setup.sh` — Script de inicialización (macOS/Linux)

```bash
#!/bin/bash
# Inicializar proyecto Casa Monarca

set -e

echo "=== Casa Monarca - Setup Inicial ==="

# 1. Crear entorno virtual
if [ ! -d ".venv" ]; then
    echo "Creando entorno virtual..."
    python3 -m venv .venv
else
    echo "Entorno virtual ya existe."
fi

# 2. Activar entorno virtual
source .venv/bin/activate

# 3. Actualizar pip
echo "Actualizando pip..."
pip install --upgrade pip setuptools wheel

# 4. Instalar dependencias
echo "Instalando dependencias..."
pip install -r requirements.txt

# 5. Crear .env si no existe
if [ ! -f ".env" ]; then
    echo "Creando .env desde .env.example..."
    cp .env.example .env
    echo "⚠️  Edita .env con tus valores antes de ejecutar la aplicación"
fi

# 6. Generar clave de cifrado
if [ ! -f "key.key" ]; then
    echo "Generando clave de cifrado..."
    python generate_key.py
fi

# 7. Crear estructura de carpetas
mkdir -p certs backups logs

# 8. Inicializar base de datos
echo "Inicializando base de datos..."
python app.py  # Ejecuta create_tables() al iniciar

echo ""
echo "✅ Setup completado."
echo ""
echo "Próximos pasos:"
echo "  1. Edita .env con tus valores"
echo "  2. Ejecuta: source .venv/bin/activate"
echo "  3. Ejecuta: python app.py"
```

**Uso:**
```bash
chmod +x setup.sh
./setup.sh
```

---

## Instalación y Ejecución

### Pasos para levantar el sistema

#### Opción 1: Setup rápido (macOS/Linux)

```bash
# 1. Clonar repositorio (si aplica)
git clone https://github.com/tu-org/casa-monarca.git
cd casa-monarca

# 2. Ejecutar script de setup
chmod +x setup.sh
./setup.sh

# 3. Editar configuración
nano .env

# 4. Ejecutar aplicación
source .venv/bin/activate
python app.py
```

**Resultado esperado:**
```
* Running on http://127.0.0.1:5000/
* WARNING in app.runWarning: This is a development server. 
  Do not use it in production. Use a production WSGI server instead.
```

Acceder a `http://localhost:5000` en el navegador.

#### Opción 2: Setup manual paso a paso

**Paso 1: Preparar entorno**
```bash
# Clonar o descargar proyecto
cd /ruta/al/proyecto

# Verificar Python 3.9+
python3 --version

# Crear entorno virtual
python3 -m venv .venv

# Activar (macOS/Linux)
source .venv/bin/activate

# O activar (Windows)
.venv\Scripts\activate
```

**Paso 2: Instalar dependencias**
```bash
# Actualizar pip
pip install --upgrade pip

# Instalar desde requirements.txt
pip install -r requirements.txt

# Verificar instalación
pip list
```

**Paso 3: Configurar seguridad**
```bash
# Generar clave de cifrado (si no existe)
python generate_key.py

# Copiar plantilla de configuración
cp .env.example .env

# Editar variables de entorno
# En .env, cambiar al menos:
#   - SECRET_KEY (32+ caracteres aleatorios)
#   - CERT_CA_CERT_PATH y CERT_CA_KEY_PATH (rutas correctas)
nano .env
```

**Paso 4: Preparar estructura de directorios**
```bash
# Crear carpetas necesarias
mkdir -p certs backups logs

# Crear certificados de CA (desarrollo)
openssl req -x509 -newkey rsa:2048 -keyout certs/ca_key.pem \
  -out certs/ca_cert.pem -days 3650 -nodes \
  -subj "/C=MX/ST=CDMX/L=Mexico/O=Casa Monarca/CN=Casa Monarca Development CA"
```

**Paso 5: Inicializar base de datos**
```bash
# Ejecutar app (crea database.db automáticamente)
python app.py

# Esperar ~5 segundos hasta ver "Running on http://..."
# Luego Ctrl+C para detener
```

**Paso 6: Verificar instalación**
```bash
# Abrir en navegador
# http://localhost:5000

# Probar login con cuenta demo (si está poblada)
# Username: usuario_demo
# Password: UserDemo123!
```

#### Opción 3: Setup en Docker (opcional)

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
```

**Construir e ejecutar:**
```bash
# Construir imagen
docker build -t casa-monarca:latest .

# Ejecutar contenedor
docker run -p 5000:5000 \
  -e SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')" \
  -v $(pwd)/certs:/app/certs \
  -v $(pwd)/database.db:/app/database.db \
  casa-monarca:latest
```

### Comandos principales

#### Ejecución

**Desarrollo (con auto-reload):**
```bash
source .venv/bin/activate
export FLASK_ENV=development
export FLASK_DEBUG=1
python app.py
```

**Producción (con Gunicorn recomendado):**
```bash
source .venv/bin/activate
gunicorn --workers 4 \
         --bind 0.0.0.0:5000 \
         --timeout 30 \
         --access-logfile - \
         --error-logfile - \
         app:app
```

**Con Flask CLI:**
```bash
source .venv/bin/activate
FLASK_ENV=development FLASK_DEBUG=1 flask run --host 0.0.0.0
```

#### Base de datos

**Inicializar (crear tablas):**
```bash
python -c "from app import app; from database import create_tables; create_tables()"
```

**Hacer backup cifrado:**
```bash
python tools/backup_db.py
# Crea: backups/db_backup_YYYYMMDDTHHMMSSZ.enc
```

**Restaurar desde backup:**
```bash
python tools/restore_db.py backups/db_backup_YYYYMMDDTHHMMSSZ.enc
```

**Acceder a SQLite directamente:**
```bash
sqlite3 database.db

# Comandos útiles:
sqlite> .tables                    # Listar tablas
sqlite> .schema usuarios           # Ver esquema de usuarios
sqlite> SELECT * FROM usuarios;    # Listar todos los usuarios
sqlite> .mode column               # Formato columnar
sqlite> .quit                      # Salir
```

#### Certificados y seguridad

**Generar/regenerar clave de cifrado:**
```bash
python generate_key.py
# Genera key.key (AES-256)
```

**Generar certificado de CA (desarrollo):**
```bash
openssl req -x509 -newkey rsa:2048 -keyout certs/ca_key.pem \
  -out certs/ca_cert.pem -days 3650 -nodes \
  -subj "/C=MX/ST=CDMX/L=Mexico/O=Casa Monarca/CN=Casa Monarca CA"
```

**Generar CSR (Certificate Signing Request) para usuario:**
```bash
# Generar clave privada
openssl genrsa -out usuario.key.pem 2048

# Generar CSR
openssl req -new -key usuario.key.pem -out usuario.csr.pem \
  -subj "/C=MX/ST=CDMX/L=Mexico/O=Casa Monarca/CN=nombre_usuario"

# Usuario carga usuario.csr.pem en /certificado/setup
```

**Verificar certificado:**
```bash
openssl x509 -in cert.pem -text -noout
openssl x509 -in cert.pem -dates -noout
```

**Verificar firma digital:**
```bash
# Verificar firma con clave pública
openssl dgst -sha256 -verify public_key.pem -signature sig.bin mensaje.txt

# Verificar firma con certificado
openssl x509 -in cert.pem -pubkey -noout | \
  openssl dgst -sha256 -verify /dev/stdin -signature sig.bin mensaje.txt
```

#### Testing y validación

**Ejecutar tests:**
```bash
# Todos los tests
PYTHONPATH=. pytest -v tests/

# Tests específicos
PYTHONPATH=. pytest -v tests/test_password_security.py

# Con cobertura
PYTHONPATH=. pytest --cov=. --cov-report=html tests/

# Ver reporte HTML
open htmlcov/index.html
```

**Validar contraseña (CLI):**
```bash
python -c "
from werkzeug.security import check_password_hash
from argon2.low_level import hash_secret, Type

# Hash de ejemplo
h = hash_secret(b'password123', b'salt1234' * 2, type=Type.ID, time_cost=3, memory_cost=65536)
print('Hash:', h)
"
```

#### Logs y diagnóstico

**Ver logs en tiempo real:**
```bash
tail -f flask.log
tail -f logs/*.log
```

**Activar debug mode:**
```bash
export FLASK_DEBUG=1
export FLASK_ENV=development
python app.py
```

**Limpiar caché y datos temporales:**
```bash
# Limpiar caché Python
find . -type d -name __pycache__ -exec rm -r {} +
find . -type f -name "*.pyc" -delete

# Limpiar .pytest_cache
rm -rf .pytest_cache

# Limpiar cobertura de tests
rm -rf htmlcov .coverage
```

#### Desarrollo y mantenimiento

**Crear nuevo usuario (CLI):**
```bash
python -c "
import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('database.db')
c = conn.cursor()

username = 'nuevo_usuario'
password = 'Password123!'
role = 'operativo'

hash_pwd = generate_password_hash(password)
c.execute('''INSERT INTO usuarios (username, password_hash, role, must_change_password)
             VALUES (?, ?, ?, 1)''', (username, hash_pwd, role))
conn.commit()
conn.close()

print(f'Usuario {username} creado. Debe cambiar contraseña al login.')
"
```

**Resetear contraseña (CLI):**
```bash
python -c "
import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('database.db')
c = conn.cursor()

username = 'usuario_a_resetear'
new_password = 'NewPassword123!'

hash_pwd = generate_password_hash(new_password)
c.execute('UPDATE usuarios SET password_hash = ?, must_change_password = 1 WHERE username = ?',
          (hash_pwd, username))
conn.commit()
conn.close()

print(f'Contraseña de {username} reseteada.')
"
```

**Listar todos los usuarios:**
```bash
sqlite3 -header -column database.db "SELECT id, username, role, created_at FROM usuarios;"
```

**Ver bitácora de eventos:**
```bash
sqlite3 -header -column database.db "SELECT username, accion, timestamp, ip_address FROM bitacora ORDER BY id DESC LIMIT 20;"
```

---

## Estructura del Proyecto

### Organización de carpetas

```
Intentoa2/                          # Raíz del proyecto
│
├── app.py                          # Aplicación principal Flask
│                                   # - Rutas (endpoints)
│                                   # - Lógica de negocio
│                                   # - Gestión de sesiones
│                                   # - Validación de roles (RBAC)
│                                   # - Verificación de firmas
│
├── database.py                     # Módulo de datos
│                                   # - Esquema SQLite
│                                   # - Funciones de ORM local
│                                   # - Inicialización de BD
│
├── generate_key.py                 # Script auxiliar
│                                   # - Genera/regenera key.key (cifrado)
│
├── database.db                     # Base de datos SQLite (generado al iniciar)
├── key.key                         # Clave de cifrado AES-256 (generado)
│
├── README.md                       # Documentación principal (resumida)
├── LICENSE                         # Licencia MIT
├── CONTRIBUTING.md                 # Guía de contribuciones
├── DEVELOPERS.md                   # Datos de desarrolladores
├── DOCUMENTATION_CHECKLIST.md      # Progreso de documentación
│
├── templates/                      # Vistas HTML (Jinja2)
│   ├── login.html                  # Formulario de login + desafío
│   ├── dashboard.html              # Panel principal de usuario
│   ├── survey.html                 # Creación/edición de expediente
│   ├── colaborador.html            # Panel para usuario operativo
│   ├── admin.html                  # Panel para administrador
│   ├── usuarios.html               # Gestión de usuarios (admin)
│   ├── logs.html                   # Bitácora de eventos
│   ├── password_update.html        # Cambio de contraseña
│   └── cert_setup.html             # Setup de certificado
│
├── static/                         # Recursos estáticos
│   └── style.css                   # Estilos CSS (diseño responsive)
│
├── certs/                          # Certificados X.509 (desarrollo)
│   ├── ca_cert.pem                 # Certificado de la CA local
│   ├── ca_key.pem                  # Clave privada de la CA
│   ├── admin_prod.pem              # Certificado demo para admin_prod
│   ├── admin_cont.pem              # Certificado demo para admin_cont
│   └── coord_admin.pem             # Certificado demo para coord_admin
│
├── tools/                          # Scripts auxiliares
│   ├── backup_db.py                # Genera backup cifrado de database.db
│   └── restore_db.py               # Restaura backup cifrado
│
├── tests/                          # Tests automatizados
│   └── test_password_security.py   # Tests de login lockout, hashing
│
├── docs/                           # Documentación de entrega (borradores)
│   ├── user_manual_draft.md        # Manual de usuario (Markdown)
│   ├── technical_report_draft.md   # Reporte técnico (Markdown)
│   ├── executive_report_draft.md   # Reporte ejecutivo (Markdown)
│   └── sdk_draft.md                # Este documento (SDK)
│
├── .venv/                          # Entorno virtual Python (no en git)
├── .gitignore                      # Patrones ignorados por git
├── __pycache__/                    # Cache de Python (no en git)
└── TODO.txt                        # Lista de tareas pendientes
```

### Descripción de módulos principales

#### `app.py` — Aplicación principal Flask

**Responsabilidades:**
- Inicializar aplicación Flask y configuración.
- Definir rutas (endpoints) para login, dashboard, expedientes, usuarios, certificados, bitácora.
- Implementar lógica de autenticación (password + challenge-response con certificados).
- Validar roles y permisos (RBAC) en cada endpoint.
- Gestionar sesiones de usuario.
- Manejar generación y validación de certificados X.509.

**Funciones clave:**
- `init_app()` — Inicializa la aplicación con configuración.
- `create_tables()` — Crea esquema de BD en primer arranque.
- `verify_certificate()` — Valida certificado X.509 del usuario.
- `verify_signature()` — Verifica firma digital (challenge-response).
- `require_login()` — Decorador para rutas autenticadas.
- `require_role(role)` — Decorador para validar rol requerido.
- `log_event()` — Registra evento en bitácora.

**Endpoints principales:**
- `GET /login` — Obtener desafío y formulario de login.
- `POST /login` — Autenticar con password + certificado + firma.
- `GET /dashboard` — Panel del usuario (expedientes según rol).
- `POST /expediente/crear` — Crear nuevo expediente.
- `POST /expediente/<id>/canalizar` — Cambiar estado de expediente.
- `GET /admin/usuarios` — Listar usuarios (admin only).
- `POST /admin/crear_usuario` — Crear usuario con firma (admin only).
- `GET /certificado/setup` — Pantalla de configuración de certificado.
- `POST /certificado/generar` — Generar/firmar certificado.
- `GET /bitacora` — Ver eventos auditados.
- `POST /logout` — Cerrar sesión.

#### `database.py` — Módulo de datos

**Responsabilidades:**
- Definir esquema SQLite (tablas, índices, constraints).
- Proporcionar funciones para CRUD (Create, Read, Update, Delete).
- Inicializar base de datos con datos de prueba.
- Manejar transacciones y integridad de datos.

**Tablas principales:**

| Tabla | Propósito | Campos clave |
|-------|-----------|--------------|
| `usuarios` | Almacenar cuentas | id, username, password_hash, role, must_change_password, created_at |
| `expedientes` | Gestionar expedientes | id, user_id, titulo, descripcion, estado, created_at, updated_at |
| `certificados` | Certificados X.509 emitidos | id, user_id, cert_pem, huella, estado, created_at, expires_at |
| `bitacora` | Auditoría de eventos | id, username, accion, descripcion, timestamp, ip_address |
| `login_attempts` | Rate-limiting | id, username, intentos, locked_until, ventana_inicio |

**Funciones clave:**
- `create_tables()` — Crea esquema al iniciar.
- `add_user(username, password, role)` — Inserta usuario.
- `get_user(username)` — Obtiene usuario por nombre.
- `verify_password(user_id, password)` — Valida contraseña hasheada.
- `create_expediente(user_id, titulo, descripcion)` — Crea expediente.
- `update_expediente_estado(expediente_id, nuevo_estado)` — Cambia estado.
- `add_certificate(user_id, cert_pem, huella)` — Almacena certificado.
- `revoke_certificate(cert_id, razon)` — Revoca certificado.
- `log_event(username, accion, descripcion)` — Registra evento.
- `check_login_attempts(username)` — Verifica si usuario está bloqueado.

#### `generate_key.py` — Generador de clave de cifrado

**Responsabilidades:**
- Generar clave AES-256 aleatoria para cifrado de backups.
- Almacenar clave en `key.key` (solo lectura).
- Permitir regeneración segura de clave.

**Uso:**
```bash
python generate_key.py          # Genera key.key si no existe
python generate_key.py --force  # Regenera (cuidado: invalida backups antiguos)
```

#### `tools/backup_db.py` — Backup cifrado

**Responsabilidades:**
- Crear respaldo cifrado de `database.db` usando `key.key`.
- Usar AES-256 en modo CBC con IV aleatorio.
- Generar archivo `.enc` con timestamp.
- Almacenar en directorio `backups/`.

**Uso:**
```bash
python tools/backup_db.py       # Genera backups/db_backup_YYYYMMDDTHHMMSSZ.enc
```

#### `tools/restore_db.py` — Restore de backup

**Responsabilidades:**
- Desencriptar backup `.enc` usando `key.key`.
- Validar integridad de datos desencriptados.
- Restaurar `database.db` (con opción de backup previo).
- Permitir restauración selectiva si es necesario.

**Uso:**
```bash
python tools/restore_db.py backups/db_backup_YYYYMMDDTHHMMSSZ.enc
```

#### `templates/` — Vistas HTML

**Características comunes:**
- Usa Jinja2 para renderizado dinámico.
- Incluye token CSRF en formularios POST.
- Responsive design (CSS Bootstrap o custom).
- Validación cliente-lado + server-side.

**Flujo de templates:**
1. `login.html` → Usuario ingresa credenciales + firma desafío.
2. `dashboard.html` → Panel con expedientes filtrados por rol.
3. `survey.html` → Crear/editar expediente.
4. `colaborador.html` → Vista específica para operativo.
5. `admin.html` → Panel administrativo.
6. `usuarios.html` → Gestión de usuarios (crear, eliminar, cambiar rol).
7. `cert_setup.html` → Setup de certificado (CSR o legacy).
8. `logs.html` → Bitácora de eventos (read-only).
9. `password_update.html` → Cambio de contraseña obligatorio.

#### `static/style.css` — Estilos

**Características:**
- Diseño responsive (mobile, tablet, desktop).
- Colores y tipografía consistentes.
- Validación visual de formularios.
- Animaciones suaves (transiciones).
- Accesibilidad (contraste, tamaños legibles).

#### `tests/test_password_security.py` — Tests

**Cobertura:**
- Validación de hash de contraseña.
- Login lockout (intentos fallidos).
- Rate-limiting.
- Expiración de bloqueo temporal.

**Ejecución:**
```bash
PYTHONPATH=. pytest -v tests/
```

---

## Base de Datos

### Modelo de datos

Casa Monarca utiliza **SQLite 3.x** como base de datos local. El modelo sigue un diseño **normalizado** (3NF) con 5 tablas principales que cubren:
- **Gestión de usuarios:** autenticación, roles, passwords
- **Gestión de expedientes:** ciclo de vida y auditoría
- **Seguridad:** certificados X.509 e intentos de login
- **Auditoría:** bitácora de eventos

#### Diagrama Entidad-Relación (E-R)

```
┌─────────────────────────────────────────────────────────────────┐
│                         MODELO CONCEPTUAL                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│                                                                   │
│    ┌──────────────────┐                                          │
│    │    USUARIOS      │                                          │
│    ├──────────────────┤                                          │
│    │ id (PK)          │                                          │
│    │ username (UQ)    │                                          │
│    │ password_hash    │                                          │
│    │ role             │────────┐                                 │
│    │ created_at       │        │ 1:N                            │
│    │ must_change_pwd  │        │                                │
│    └──────────────────┘        │                                │
│           │ 1:N                │                                │
│           │                    ▼                                │
│           │            ┌──────────────────────────┐             │
│           │            │    EXPEDIENTES           │             │
│           │            ├──────────────────────────┤             │
│           │            │ id (PK)                  │             │
│           │            │ user_id (FK → USUARIOS)  │             │
│           │            │ titulo                   │             │
│           │            │ descripcion              │             │
│           │            │ estado                   │             │
│           │            │ created_at               │             │
│           │            │ updated_at               │             │
│           │            └──────────────────────────┘             │
│           │                                                      │
│           │ 1:N                                                  │
│           │                                                      │
│           ▼                                                      │
│    ┌──────────────────┐                                          │
│    │  CERTIFICADOS    │                                          │
│    ├──────────────────┤                                          │
│    │ id (PK)          │                                          │
│    │ user_id (FK)     │                                          │
│    │ cert_pem         │                                          │
│    │ huella (UQ)      │                                          │
│    │ estado           │                                          │
│    │ created_at       │                                          │
│    │ expires_at       │                                          │
│    └──────────────────┘                                          │
│                                                                   │
│    ┌──────────────────────────┐                                  │
│    │      BITACORA            │                                  │
│    ├──────────────────────────┤                                  │
│    │ id (PK)                  │                                  │
│    │ username (FK → USUARIOS) │                                  │
│    │ accion                   │                                  │
│    │ descripcion              │                                  │
│    │ timestamp                │                                  │
│    │ ip_address               │                                  │
│    └──────────────────────────┘                                  │
│                                                                   │
│    ┌──────────────────────────┐                                  │
│    │    LOGIN_ATTEMPTS        │                                  │
│    ├──────────────────────────┤                                  │
│    │ id (PK)                  │                                  │
│    │ username (FK)            │                                  │
│    │ intentos                 │                                  │
│    │ locked_until             │                                  │
│    │ ventana_inicio           │                                  │
│    └──────────────────────────┘                                  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘

Leyenda:
  PK = Primary Key (clave primaria)
  FK = Foreign Key (clave foránea)
  UQ = Unique (único)
  1:N = Relación uno-a-muchos
```

### Tablas principales

#### 1. `usuarios` — Gestión de cuentas y autenticación

**Propósito:** Almacenar información de usuarios, roles y credenciales.

**Esquema:**

| Campo | Tipo | Restricciones | Descripción |
|-------|------|----------------|------------|
| `id` | INTEGER | PRIMARY KEY, AUTO INCREMENT | Identificador único |
| `username` | TEXT | NOT NULL, UNIQUE | Nombre de usuario (login único) |
| `password_hash` | TEXT | NOT NULL | Hash Argon2 de contraseña |
| `role` | TEXT | NOT NULL DEFAULT 'usuario' | Rol RBAC: usuario, operativo, coordinador, admin |
| `must_change_password` | INTEGER | DEFAULT 1 | Flag: 1 = debe cambiar al login |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Fecha de creación |

**Índices:**
```sql
CREATE UNIQUE INDEX idx_usuarios_username ON usuarios(username);
CREATE INDEX idx_usuarios_role ON usuarios(role);
```

**Ejemplo de datos:**
```
id | username    | password_hash              | role        | must_change_password | created_at
1  | usuario_pru | $argon2id$v=19$m=65536... | usuario     | 0                    | 2026-05-01 10:00:00
2  | operativo_1 | $argon2id$v=19$m=65536... | operativo   | 1                    | 2026-05-05 14:30:00
3  | coord_admin | $argon2id$v=19$m=65536... | coordinador | 0                    | 2026-05-02 09:15:00
4  | admin_prod  | $argon2id$v=19$m=65536... | admin       | 0                    | 2026-05-01 08:00:00
```

#### 2. `expedientes` — Gestión del ciclo de vida

**Propósito:** Almacenar expedientes y su estado en el flujo de procesamiento.

**Esquema:**

| Campo | Tipo | Restricciones | Descripción |
|-------|------|----------------|------------|
| `id` | INTEGER | PRIMARY KEY, AUTO INCREMENT | Identificador único |
| `user_id` | INTEGER | NOT NULL, FK → usuarios(id) | Usuario creador (propietario) |
| `titulo` | TEXT | NOT NULL | Título del expediente |
| `descripcion` | TEXT | | Descripción detallada |
| `estado` | TEXT | DEFAULT 'borrador' | Estado: borrador, en_revision, validado, cerrado |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Fecha de creación |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Última actualización |

**Índices:**
```sql
CREATE INDEX idx_expedientes_user_id ON expedientes(user_id);
CREATE INDEX idx_expedientes_estado ON expedientes(estado);
CREATE INDEX idx_expedientes_created_at ON expedientes(created_at DESC);
```

**Estados y transiciones permitidas:**
```
borrador → en_revision → validado → cerrado
   ↑         (solo si     ↓        (solo
  (solo      validado)    └─→ borrador (admin)
  propietario)                (revisar)
```

**Permisos por rol:**
- `usuario`: Crea (borrador), ve propios, puede cancelar
- `operativo`: Ve asignados, canaliza a coordinador
- `coordinador`: Revisa, canaliza a admin (con firma)
- `admin`: Valida finales, cierra

**Ejemplo de datos:**
```
id | user_id | titulo              | estado      | created_at         | updated_at
1  | 1       | Caso #001 - Refugio | borrador    | 2026-05-10 11:30   | 2026-05-10 11:30
2  | 1       | Caso #002 - Legal   | en_revision | 2026-05-12 09:45   | 2026-05-15 14:20
3  | 2       | Caso #003 - Medico  | validado    | 2026-05-14 16:00   | 2026-05-16 10:10
```

#### 3. `certificados` — Gestión de certificados X.509

**Propósito:** Almacenar certificados digitales emitidos por la CA local.

**Esquema:**

| Campo | Tipo | Restricciones | Descripción |
|-------|------|----------------|------------|
| `id` | INTEGER | PRIMARY KEY, AUTO INCREMENT | Identificador único |
| `user_id` | INTEGER | NOT NULL, FK → usuarios(id) | Usuario propietario del certificado |
| `cert_pem` | TEXT | NOT NULL | Certificado en formato PEM (X.509) |
| `huella` | TEXT | NOT NULL, UNIQUE | SHA-256 del certificado (fingerprint) |
| `estado` | TEXT | DEFAULT 'activo' | Estado: activo, revocado, expirado |
| `razon_revocacion` | TEXT | | Motivo de revocación (si aplica) |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Fecha de emisión |
| `expires_at` | TIMESTAMP | NOT NULL | Fecha de expiración (validez 720 horas = 30 días) |

**Índices:**
```sql
CREATE INDEX idx_certificados_user_id ON certificados(user_id);
CREATE UNIQUE INDEX idx_certificados_huella ON certificados(huella);
CREATE INDEX idx_certificados_estado ON certificados(estado);
CREATE INDEX idx_certificados_expires_at ON certificados(expires_at);
```

**Estados de ciclo de vida:**
- `activo`: Certificado válido y usable para autenticación
- `revocado`: Revocado por el usuario o admin (no puede usarse)
- `expirado`: Pasó la fecha de expiración

**Validación en login:**
```python
if estado != 'activo':
    raise AuthenticationError("Certificado no está activo")
if expires_at < NOW():
    raise AuthenticationError("Certificado expirado")
if not verify_ca_signature(cert_pem):
    raise AuthenticationError("Firma de CA inválida")
if certificate.CN != username:
    raise AuthenticationError("CN no coincide con usuario")
```

**Ejemplo de datos:**
```
id | user_id | huella (SHA-256)          | estado   | expires_at         | created_at
1  | 4       | a1b2c3d4e5f6...           | activo   | 2026-06-15 08:00   | 2026-05-16 08:00
2  | 3       | f6e5d4c3b2a1...           | activo   | 2026-06-14 10:30   | 2026-05-15 10:30
3  | 3       | 9z8y7x6w5v4u...           | revocado | 2026-06-10 14:00   | 2026-05-10 14:00
```

#### 4. `bitacora` — Auditoría de eventos

**Propósito:** Registro inmutable de eventos (audit log) para trazabilidad y compliance.

**Esquema:**

| Campo | Tipo | Restricciones | Descripción |
|-------|------|----------------|------------|
| `id` | INTEGER | PRIMARY KEY, AUTO INCREMENT | Identificador único |
| `username` | TEXT | NOT NULL, FK → usuarios(username) | Usuario que ejecutó la acción |
| `accion` | TEXT | NOT NULL | Tipo de acción: login, logout, crear_expediente, cambiar_estado, crear_usuario, revocar_certificado, etc. |
| `descripcion` | TEXT | | Detalles adicionales de la acción |
| `timestamp` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Fecha/hora exacta del evento |
| `ip_address` | TEXT | | Dirección IP del cliente (para auditoría de seguridad) |

**Índices:**
```sql
CREATE INDEX idx_bitacora_username ON bitacora(username);
CREATE INDEX idx_bitacora_accion ON bitacora(accion);
CREATE INDEX idx_bitacora_timestamp ON bitacora(timestamp DESC);
```

**Eventos auditados:**

| Acción | Descripción |
|--------|------------|
| `login_exitoso` | Usuario inició sesión correctamente |
| `login_fallido` | Intento de login fallido (contraseña incorrecta) |
| `login_bloqueado` | Usuario bloqueado por intentos excesivos |
| `logout` | Usuario cerró sesión |
| `cambiar_contrasena` | Usuario cambió su contraseña |
| `crear_expediente` | Nuevo expediente creado |
| `cambiar_estado_expediente` | Cambio de estado en expediente |
| `crear_usuario` | Nuevo usuario creado por admin |
| `eliminar_usuario` | Usuario eliminado |
| `cambiar_rol_usuario` | Rol de usuario modificado |
| `generar_certificado` | Certificado X.509 emitido |
| `revocar_certificado` | Certificado revocado |
| `backup_realizado` | Backup cifrado realizado |
| `backup_restaurado` | Base de datos restaurada desde backup |

**Ejemplo de datos:**
```
id | username    | accion                  | descripcion                    | timestamp           | ip_address
1  | admin_prod  | crear_usuario           | Nuevo usuario: operativo_1     | 2026-05-05 14:30:00 | 192.168.1.100
2  | usuario_pru | login_exitoso           | Login con certificado exitoso  | 2026-05-10 11:20:00 | 192.168.1.150
3  | operativo_1 | crear_expediente        | ID: 1, Título: Caso #001      | 2026-05-10 11:30:00 | 192.168.1.155
4  | operativo_1 | cambiar_estado_exped    | ID: 1, borrador → en_revision | 2026-05-12 09:45:00 | 192.168.1.155
5  | coord_admin | revocar_certificado     | User: operativo_1, huella: ...| 2026-05-16 15:00:00 | 192.168.1.120
```

#### 5. `login_attempts` — Rate-limiting y protección

**Propósito:** Rastrear intentos de login fallidos para implementar lockout temporal (rate-limiting).

**Esquema:**

| Campo | Tipo | Restricciones | Descripción |
|-------|------|----------------|------------|
| `id` | INTEGER | PRIMARY KEY, AUTO INCREMENT | Identificador único |
| `username` | TEXT | NOT NULL, UNIQUE | Usuario intentando login (UNIQUE para evitar duplicados) |
| `intentos` | INTEGER | DEFAULT 0 | Número de intentos fallidos en la ventana actual |
| `locked_until` | TIMESTAMP | | Fecha/hora hasta la que el usuario está bloqueado (NULL = no bloqueado) |
| `ventana_inicio` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Inicio de la ventana de conteo |

**Índices:**
```sql
CREATE UNIQUE INDEX idx_login_attempts_username ON login_attempts(username);
CREATE INDEX idx_login_attempts_locked_until ON login_attempts(locked_until);
```

**Lógica de rate-limiting:**

```
Configuración:
  - LOGIN_MAX_ATTEMPTS = 5
  - LOGIN_WINDOW_SECONDS = 300 (5 minutos)
  - LOGIN_LOCKOUT_SECONDS = 900 (15 minutos)

Flujo:
1. Usuario intenta login
2. Si password es incorrecto:
   - intentos += 1
   - Si intentos >= 5:
       locked_until = NOW + 900 segundos
   - Registrar en bitácora "login_fallido"
3. Si password es correcto:
   - Resetear intentos = 0
   - Registrar en bitácora "login_exitoso"
4. Si locked_until > NOW:
   - Rechazar login inmediatamente
   - Registrar en bitácora "login_bloqueado"
5. Si locked_until < NOW:
   - Desbloquear: locked_until = NULL, intentos = 0
```

**Ejemplo de datos:**
```
id | username    | intentos | locked_until        | ventana_inicio
1  | usuario_pru | 0        | NULL                | 2026-05-10 11:00:00
2  | operativo_1 | 3        | NULL                | 2026-05-12 09:30:00
3  | admin_temp  | 5        | 2026-05-16 15:15:00 | 2026-05-16 15:00:00
```

### Relaciones

#### Relación: USUARIOS ← 1:N → EXPEDIENTES

```
Un usuario puede crear múltiples expedientes.
Un expediente pertenece a exactamente un usuario.

ON DELETE: CASCADE (si se elimina usuario, se eliminan sus expedientes)
ON UPDATE: CASCADE (si cambia user_id, se propaga a expedientes)
```

**SQL:**
```sql
ALTER TABLE expedientes 
ADD CONSTRAINT fk_expedientes_user_id 
FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE;
```

#### Relación: USUARIOS ← 1:N → CERTIFICADOS

```
Un usuario puede tener múltiples certificados (activos, revocados, expirados).
Un certificado pertenece a exactamente un usuario.

ON DELETE: CASCADE (si se elimina usuario, se eliminan sus certs)
ON UPDATE: CASCADE
```

**SQL:**
```sql
ALTER TABLE certificados 
ADD CONSTRAINT fk_certificados_user_id 
FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE;
```

#### Relación: USUARIOS ← 1:N → BITACORA

```
Un usuario puede generar múltiples eventos auditados.
Un evento en bitácora se asocia a un usuario específico.

ON DELETE: SET NULL (el evento permanece pero usuario se desconoce)
ON UPDATE: CASCADE
```

**SQL:**
```sql
ALTER TABLE bitacora 
ADD CONSTRAINT fk_bitacora_username 
FOREIGN KEY (username) REFERENCES usuarios(username) ON UPDATE CASCADE;
```

#### Relación: USUARIOS ← 1:1 → LOGIN_ATTEMPTS

```
Un usuario tiene exactamente un registro de intentos de login (por ventana).
Un registro de intentos pertenece a un usuario.

ON DELETE: CASCADE
ON UPDATE: CASCADE
```

**SQL:**
```sql
ALTER TABLE login_attempts 
ADD CONSTRAINT fk_login_attempts_username 
FOREIGN KEY (username) REFERENCES usuarios(username) ON DELETE CASCADE;
```

### Script de inicialización (DDL)

```sql
-- Table: usuarios
CREATE TABLE usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'usuario',
    must_change_password INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Table: expedientes
CREATE TABLE expedientes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    titulo TEXT NOT NULL,
    descripcion TEXT,
    estado TEXT DEFAULT 'borrador',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

-- Table: certificados
CREATE TABLE certificados (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    cert_pem TEXT NOT NULL,
    huella TEXT NOT NULL UNIQUE,
    estado TEXT DEFAULT 'activo',
    razon_revocacion TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

-- Table: bitacora
CREATE TABLE bitacora (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    accion TEXT NOT NULL,
    descripcion TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address TEXT,
    FOREIGN KEY (username) REFERENCES usuarios(username) ON UPDATE CASCADE
);

-- Table: login_attempts
CREATE TABLE login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    intentos INTEGER DEFAULT 0,
    locked_until TIMESTAMP,
    ventana_inicio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (username) REFERENCES usuarios(username) ON DELETE CASCADE
);

-- Índices para optimización
CREATE UNIQUE INDEX idx_usuarios_username ON usuarios(username);
CREATE INDEX idx_usuarios_role ON usuarios(role);

CREATE INDEX idx_expedientes_user_id ON expedientes(user_id);
CREATE INDEX idx_expedientes_estado ON expedientes(estado);
CREATE INDEX idx_expedientes_created_at ON expedientes(created_at DESC);

CREATE INDEX idx_certificados_user_id ON certificados(user_id);
CREATE UNIQUE INDEX idx_certificados_huella ON certificados(huella);
CREATE INDEX idx_certificados_estado ON certificados(estado);
CREATE INDEX idx_certificados_expires_at ON certificados(expires_at);

CREATE INDEX idx_bitacora_username ON bitacora(username);
CREATE INDEX idx_bitacora_accion ON bitacora(accion);
CREATE INDEX idx_bitacora_timestamp ON bitacora(timestamp DESC);

CREATE UNIQUE INDEX idx_login_attempts_username ON login_attempts(username);
CREATE INDEX idx_login_attempts_locked_until ON login_attempts(locked_until);
```

### Consultas principales (ejemplos)

**Obtener todos los expedientes de un usuario:**
```sql
SELECT e.id, e.titulo, e.estado, e.created_at 
FROM expedientes e
WHERE e.user_id = ? 
ORDER BY e.created_at DESC;
```

**Listar certificados activos próximos a expirar:**
```sql
SELECT c.id, c.huella, c.expires_at, u.username
FROM certificados c
JOIN usuarios u ON c.user_id = u.id
WHERE c.estado = 'activo' 
  AND c.expires_at < datetime('now', '+7 days')
ORDER BY c.expires_at ASC;
```

**Historial de eventos de un usuario:**
```sql
SELECT accion, descripcion, timestamp, ip_address
FROM bitacora
WHERE username = ?
ORDER BY timestamp DESC
LIMIT 50;
```

**Verificar si usuario está bloqueado:**
```sql
SELECT locked_until, intentos
FROM login_attempts
WHERE username = ?
  AND locked_until > datetime('now');
```

**Contar expedientes por estado:**
```sql
SELECT estado, COUNT(*) as cantidad
FROM expedientes
GROUP BY estado
ORDER BY cantidad DESC;
```

---

## API / Interfaces

Casa Monarca expone una **API REST** basada en Flask para operaciones HTTP. Los endpoints están protegidos con **autenticación por sesión** (cookies) y **validación de roles (RBAC)**.

### Convenciones generales

**Protocolo:** HTTP/HTTPS (HTTPS obligatorio en producción)

**Base URL:** `http://localhost:5000` (desarrollo) o `https://casa-monarca.ejemplo.com` (producción)

**Autenticación:** 
- Método 1: Sesión con cookie (POST /login)
- Método 2: Challenge-response con certificado (para admin/coordinador)

**Formato de respuestas:** JSON (excepto descargas de archivos)

**Códigos HTTP utilizados:**
| Código | Significado |
|--------|------------|
| 200 | OK - Solicitud exitosa |
| 201 | Created - Recurso creado |
| 400 | Bad Request - Parámetro inválido |
| 401 | Unauthorized - No autenticado |
| 403 | Forbidden - Sin permisos para esta acción |
| 404 | Not Found - Recurso no existe |
| 422 | Unprocessable Entity - Datos inválidos |
| 500 | Internal Server Error - Error del servidor |

### Endpoints de autenticación

#### 1. GET /login — Obtener formulario y desafío

**Descripción:** Obtiene el formulario de login y genera un desafío para firmar (challenge).

**Método:** `GET`

**Autenticación requerida:** No

**Parámetros:** Ninguno

**Respuesta (200 OK):**
```json
{
  "challenge": "a1b2c3d4-e5f6-4789-abcd-ef1234567890",
  "form": "<html>...</html>"
}
```

**Ejemplo (curl):**
```bash
curl -X GET http://localhost:5000/login
```

---

#### 2. POST /login — Autenticarse con credenciales

**Descripción:** Autentica usuario con contraseña y, opcionalmente, certificado + firma.

**Método:** `POST`

**Autenticación requerida:** No

**Parámetros (form-data o JSON):**

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|------------|
| `username` | string | Sí | Nombre de usuario |
| `password` | string | Sí | Contraseña |
| `challenge` | string | No | UUID del desafío (para login con cert) |
| `signature_b64` | string | No | Firma Base64 del desafío (para admin/coordinador) |
| `certificate_pem` | string | No | Certificado PEM (para login reforzado) |

**Respuesta (200 OK - login exitoso):**
```json
{
  "status": "success",
  "message": "Login exitoso",
  "user": {
    "id": 1,
    "username": "usuario_pru",
    "role": "usuario",
    "must_change_password": false
  }
}
```

**Respuesta (401 Unauthorized - credenciales inválidas):**
```json
{
  "status": "error",
  "message": "Contraseña incorrecta",
  "remaining_attempts": 4
}
```

**Respuesta (423 Locked - usuario bloqueado):**
```json
{
  "status": "locked",
  "message": "Usuario bloqueado por intentos excesivos",
  "locked_until": "2026-05-16T15:15:00Z"
}
```

**Ejemplo (curl - login básico):**
```bash
curl -X POST http://localhost:5000/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=usuario_pru&password=UserDemo123!" \
  -c cookies.txt
```

**Ejemplo (curl - login con certificado):**
```bash
curl -X POST http://localhost:5000/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin_prod&password=AdminProdX2026!&challenge=a1b2c3d4-e5f6-4789-abcd-ef1234567890&signature_b64=ABC123==&certificate_pem=$(cat admin_prod.pem | base64)" \
  -c cookies.txt
```

**Ejemplo (Python):**
```python
import requests

session = requests.Session()
response = session.post(
    "http://localhost:5000/login",
    data={
        "username": "usuario_pru",
        "password": "UserDemo123!"
    }
)
print(response.json())
# {'status': 'success', 'user': {...}}
```

---

#### 3. POST /logout — Cerrar sesión

**Descripción:** Cierra la sesión del usuario autenticado.

**Método:** `POST`

**Autenticación requerida:** Sí (sesión activa)

**Parámetros:** Ninguno

**Respuesta (200 OK):**
```json
{
  "status": "success",
  "message": "Sesión cerrada"
}
```

**Ejemplo (curl):**
```bash
curl -X POST http://localhost:5000/logout \
  -b cookies.txt
```

---

### Endpoints de gestión de expedientes

#### 4. GET /dashboard — Obtener panel del usuario

**Descripción:** Retorna expedientes según el rol del usuario.

**Método:** `GET`

**Autenticación requerida:** Sí

**Parámetros:** Ninguno

**Respuesta (200 OK):**
```json
{
  "user": {
    "id": 1,
    "username": "usuario_pru",
    "role": "usuario"
  },
  "expedientes": [
    {
      "id": 1,
      "titulo": "Caso #001 - Refugio",
      "estado": "borrador",
      "created_at": "2026-05-10T11:30:00Z",
      "updated_at": "2026-05-10T11:30:00Z"
    },
    {
      "id": 2,
      "titulo": "Caso #002 - Legal",
      "estado": "en_revision",
      "created_at": "2026-05-12T09:45:00Z",
      "updated_at": "2026-05-15T14:20:00Z"
    }
  ]
}
```

**Ejemplo (curl):**
```bash
curl -X GET http://localhost:5000/dashboard \
  -b cookies.txt
```

**Ejemplo (Python):**
```python
response = session.get("http://localhost:5000/dashboard")
dashboard = response.json()
print(f"Usuario: {dashboard['user']['username']}")
print(f"Expedientes: {len(dashboard['expedientes'])}")
```

---

#### 5. POST /expediente/crear — Crear nuevo expediente

**Descripción:** Crea un nuevo expediente en estado "borrador".

**Método:** `POST`

**Autenticación requerida:** Sí

**Parámetros (JSON):**

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|------------|
| `titulo` | string | Sí | Título del expediente |
| `descripcion` | string | No | Descripción detallada |

**Respuesta (201 Created):**
```json
{
  "status": "success",
  "message": "Expediente creado",
  "expediente": {
    "id": 3,
    "titulo": "Caso #003 - Medico",
    "descripcion": "Necesita asistencia médica urgente",
    "estado": "borrador",
    "user_id": 1,
    "created_at": "2026-05-16T10:30:00Z"
  }
}
```

**Ejemplo (curl):**
```bash
curl -X POST http://localhost:5000/expediente/crear \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "titulo": "Caso #003 - Medico",
    "descripcion": "Necesita asistencia médica urgente"
  }'
```

**Ejemplo (Python):**
```python
response = session.post(
    "http://localhost:5000/expediente/crear",
    json={
        "titulo": "Caso #003 - Medico",
        "descripcion": "Necesita asistencia médica urgente"
    }
)
expediente = response.json()["expediente"]
print(f"Expediente creado: ID {expediente['id']}")
```

---

#### 6. GET /expediente/<id> — Obtener detalle de expediente

**Descripción:** Retorna detalles de un expediente específico (con validación de permisos).

**Método:** `GET`

**Autenticación requerida:** Sí

**Parámetros (path):**

| Parámetro | Tipo | Descripción |
|-----------|------|------------|
| `id` | integer | ID del expediente |

**Respuesta (200 OK):**
```json
{
  "expediente": {
    "id": 1,
    "titulo": "Caso #001 - Refugio",
    "descripcion": "Solicitud de refugio",
    "estado": "borrador",
    "user_id": 1,
    "created_at": "2026-05-10T11:30:00Z",
    "updated_at": "2026-05-10T11:30:00Z"
  }
}
```

**Ejemplo (curl):**
```bash
curl -X GET http://localhost:5000/expediente/1 \
  -b cookies.txt
```

---

#### 7. POST /expediente/<id>/canalizar — Cambiar estado de expediente

**Descripción:** Canaliza (cambia de estado) un expediente. Requiere validación de firma para ciertos roles.

**Método:** `POST`

**Autenticación requerida:** Sí

**Parámetros (path + JSON):**

| Parámetro | Tipo | Ubicación | Descripción |
|-----------|------|-----------|------------|
| `id` | integer | path | ID del expediente |
| `nuevo_estado` | string | body | Nuevo estado: en_revision, validado, cerrado |
| `signature_b64` | string | body | Firma del cambio (requerida para coordinador/admin) |
| `challenge` | string | body | Challenge para validar firma |

**Estados permitidos por rol:**
- `usuario` → puede canalizar a operativo
- `operativo` → puede canalizar a coordinador
- `coordinador` → puede canalizar a admin (con firma)
- `admin` → puede cerrar o volver a borrador

**Respuesta (200 OK):**
```json
{
  "status": "success",
  "message": "Expediente canalizado",
  "expediente": {
    "id": 1,
    "estado": "en_revision",
    "updated_at": "2026-05-12T14:00:00Z"
  }
}
```

**Ejemplo (curl):**
```bash
curl -X POST http://localhost:5000/expediente/1/canalizar \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "nuevo_estado": "en_revision",
    "signature_b64": "ABC123==",
    "challenge": "a1b2c3d4-e5f6-4789-abcd-ef1234567890"
  }'
```

---

### Endpoints de gestión de certificados

#### 8. GET /certificado/setup — Obtener página de setup de certificado

**Descripción:** Retorna formulario HTML para setup de certificado (CSR).

**Método:** `GET`

**Autenticación requerida:** Sí

**Respuesta:** HTML del formulario

**Ejemplo (curl):**
```bash
curl -X GET http://localhost:5000/certificado/setup \
  -b cookies.txt
```

---

#### 9. POST /certificado/generar — Generar/firmar certificado

**Descripción:** Genera o firma un certificado X.509 para el usuario.

**Método:** `POST`

**Autenticación requerida:** Sí

**Parámetros (form-data):**

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|------------|
| `csr_pem` | string | Sí | Certificate Signing Request (PEM) o vacío para generar |
| `days_valid` | integer | No | Días de validez (default: 30) |

**Respuesta (200 OK):**
```json
{
  "status": "success",
  "message": "Certificado generado",
  "certificate_pem": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
  "fingerprint_sha256": "a1b2c3d4e5f6...",
  "expires_at": "2026-06-15T08:00:00Z"
}
```

**Ejemplo (curl - generar sin CSR):**
```bash
curl -X POST http://localhost:5000/certificado/generar \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -b cookies.txt \
  -d "csr_pem=&days_valid=30"
```

**Ejemplo (curl - firmar CSR):**
```bash
curl -X POST http://localhost:5000/certificado/generar \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -b cookies.txt \
  -d "csr_pem=$(cat usuario.csr.pem | base64)&days_valid=30"
```

---

#### 10. POST /certificado/<id>/revocar — Revocar certificado

**Descripción:** Revoca un certificado (marca como revocado en BD).

**Método:** `POST`

**Autenticación requerida:** Sí (admin o propietario del cert)

**Parámetros (path + JSON):**

| Parámetro | Tipo | Ubicación | Descripción |
|-----------|------|-----------|------------|
| `id` | integer | path | ID del certificado |
| `razon` | string | body | Motivo de revocación |

**Respuesta (200 OK):**
```json
{
  "status": "success",
  "message": "Certificado revocado",
  "certificate_id": 1,
  "razon": "Compromiso de seguridad"
}
```

**Ejemplo (curl):**
```bash
curl -X POST http://localhost:5000/certificado/1/revocar \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"razon": "Compromiso de seguridad"}'
```

---

### Endpoints de administración

#### 11. GET /admin/usuarios — Listar usuarios (admin only)

**Descripción:** Lista todos los usuarios del sistema.

**Método:** `GET`

**Autenticación requerida:** Sí (role = admin)

**Parámetros:** Ninguno

**Respuesta (200 OK):**
```json
{
  "usuarios": [
    {
      "id": 1,
      "username": "usuario_pru",
      "role": "usuario",
      "created_at": "2026-05-01T10:00:00Z"
    },
    {
      "id": 4,
      "username": "admin_prod",
      "role": "admin",
      "created_at": "2026-05-01T08:00:00Z"
    }
  ]
}
```

**Ejemplo (curl):**
```bash
curl -X GET http://localhost:5000/admin/usuarios \
  -b cookies.txt
```

---

#### 12. POST /admin/crear_usuario — Crear usuario (admin only)

**Descripción:** Crea nuevo usuario (requiere firma del admin).

**Método:** `POST`

**Autenticación requerida:** Sí (role = admin con certificado)

**Parámetros (JSON):**

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|------------|
| `username` | string | Sí | Nombre de usuario |
| `role` | string | Sí | Rol: usuario, operativo, coordinador, admin |
| `challenge` | string | Sí | Challenge para validar firma del admin |
| `signature_b64` | string | Sí | Firma de admin |

**Respuesta (201 Created):**
```json
{
  "status": "success",
  "message": "Usuario creado",
  "usuario": {
    "id": 5,
    "username": "nuevo_operativo",
    "role": "operativo",
    "created_at": "2026-05-16T15:30:00Z"
  }
}
```

**Ejemplo (curl):**
```bash
curl -X POST http://localhost:5000/admin/crear_usuario \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "username": "nuevo_operativo",
    "role": "operativo",
    "challenge": "a1b2c3d4-e5f6-4789-abcd-ef1234567890",
    "signature_b64": "ABC123=="
  }'
```

---

#### 13. POST /admin/eliminar_usuario/<id> — Eliminar usuario (admin only)

**Descripción:** Elimina un usuario del sistema.

**Método:** `POST`

**Autenticación requerida:** Sí (role = admin)

**Parámetros (path):**

| Parámetro | Tipo | Descripción |
|-----------|------|------------|
| `id` | integer | ID del usuario a eliminar |

**Respuesta (200 OK):**
```json
{
  "status": "success",
  "message": "Usuario eliminado",
  "user_id": 5
}
```

**Ejemplo (curl):**
```bash
curl -X POST http://localhost:5000/admin/eliminar_usuario/5 \
  -b cookies.txt
```

---

#### 14. POST /admin/cambiar_rol/<id> — Cambiar rol de usuario (admin only)

**Descripción:** Modifica el rol de un usuario.

**Método:** `POST`

**Autenticación requerida:** Sí (role = admin)

**Parámetros (path + JSON):**

| Parámetro | Tipo | Ubicación | Descripción |
|-----------|------|-----------|------------|
| `id` | integer | path | ID del usuario |
| `nuevo_rol` | string | body | Nuevo rol: usuario, operativo, coordinador, admin |

**Respuesta (200 OK):**
```json
{
  "status": "success",
  "message": "Rol modificado",
  "user_id": 5,
  "nuevo_rol": "coordinador"
}
```

**Ejemplo (curl):**
```bash
curl -X POST http://localhost:5000/admin/cambiar_rol/5 \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"nuevo_rol": "coordinador"}'
```

---

### Endpoints de perfil y seguridad

#### 15. GET /perfil — Obtener perfil del usuario autenticado

**Descripción:** Retorna información del perfil del usuario actual.

**Método:** `GET`

**Autenticación requerida:** Sí

**Respuesta (200 OK):**
```json
{
  "usuario": {
    "id": 1,
    "username": "usuario_pru",
    "role": "usuario",
    "created_at": "2026-05-01T10:00:00Z",
    "must_change_password": false
  }
}
```

**Ejemplo (curl):**
```bash
curl -X GET http://localhost:5000/perfil \
  -b cookies.txt
```

---

#### 16. POST /cambiar_contrasena — Cambiar contraseña

**Descripción:** Cambia la contraseña del usuario autenticado.

**Método:** `POST`

**Autenticación requerida:** Sí

**Parámetros (JSON):**

| Parámetro | Tipo | Requerido | Descripción |
|-----------|------|----------|------------|
| `password_actual` | string | Sí | Contraseña actual |
| `password_nueva` | string | Sí | Nueva contraseña (mín. 12 caracteres) |
| `password_confirmacion` | string | Sí | Confirmación de nueva contraseña |

**Respuesta (200 OK):**
```json
{
  "status": "success",
  "message": "Contraseña cambiada exitosamente"
}
```

**Respuesta (422 Unprocessable Entity - contraseña débil):**
```json
{
  "status": "error",
  "message": "Contraseña no cumple requisitos de seguridad",
  "requirements": {
    "min_length": 12,
    "must_have_uppercase": true,
    "must_have_lowercase": true,
    "must_have_number": true,
    "must_have_special": true
  }
}
```

**Ejemplo (curl):**
```bash
curl -X POST http://localhost:5000/cambiar_contrasena \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "password_actual": "UserDemo123!",
    "password_nueva": "NewPassword456!",
    "password_confirmacion": "NewPassword456!"
  }'
```

---

### Endpoints de auditoría

#### 17. GET /bitacora — Ver bitácora de eventos

**Descripción:** Lista eventos auditados (acceso según rol).

**Método:** `GET`

**Autenticación requerida:** Sí (admin y coordinador ven todos, otros ven propios)

**Parámetros (query - opcionales):**

| Parámetro | Tipo | Descripción |
|-----------|------|------------|
| `username` | string | Filtrar por usuario (admin only) |
| `accion` | string | Filtrar por tipo de acción |
| `limit` | integer | Número de registros (default: 50) |
| `offset` | integer | Desplazamiento para paginación (default: 0) |

**Respuesta (200 OK):**
```json
{
  "eventos": [
    {
      "id": 1,
      "username": "admin_prod",
      "accion": "crear_usuario",
      "descripcion": "Nuevo usuario: operativo_1",
      "timestamp": "2026-05-05T14:30:00Z",
      "ip_address": "192.168.1.100"
    },
    {
      "id": 2,
      "username": "usuario_pru",
      "accion": "login_exitoso",
      "descripcion": "Login con certificado",
      "timestamp": "2026-05-10T11:20:00Z",
      "ip_address": "192.168.1.150"
    }
  ],
  "total": 250,
  "limit": 50,
  "offset": 0
}
```

**Ejemplo (curl):**
```bash
curl -X GET "http://localhost:5000/bitacora?limit=20&accion=login_exitoso" \
  -b cookies.txt
```

**Ejemplo (curl - filtrar por usuario, admin only):**
```bash
curl -X GET "http://localhost:5000/bitacora?username=usuario_pru&limit=30" \
  -b cookies.txt
```

---

### Resumen de endpoints por rol

| Endpoint | GET | POST | PUT | DELETE | Admin | Coord | Oper | Usuario |
|----------|-----|------|-----|--------|-------|-------|------|---------|
| /login | ✓ | ✓ |  |  | ✓ | ✓ | ✓ | ✓ |
| /logout |  | ✓ |  |  | ✓ | ✓ | ✓ | ✓ |
| /dashboard | ✓ |  |  |  | ✓ | ✓ | ✓ | ✓ |
| /perfil | ✓ |  |  |  | ✓ | ✓ | ✓ | ✓ |
| /cambiar_contrasena |  | ✓ |  |  | ✓ | ✓ | ✓ | ✓ |
| /expediente/crear |  | ✓ |  |  | ✓ | ✓ | ✓ | ✓ |
| /expediente/<id> | ✓ |  |  |  | ✓ | ✓ | ✓ | (propio) |
| /expediente/<id>/canalizar |  | ✓ |  |  | ✓ | ✓ | ✓ | ✓ |
| /certificado/setup | ✓ |  |  |  | ✓ | ✓ | ✓ | ✓ |
| /certificado/generar |  | ✓ |  |  | ✓ | ✓ | ✓ | ✓ |
| /certificado/<id>/revocar |  | ✓ |  |  | ✓ | ✓ | ✓ | (propio) |
| /admin/usuarios | ✓ |  |  |  | ✓ |  |  |  |
| /admin/crear_usuario |  | ✓ |  |  | ✓ |  |  |  |
| /admin/eliminar_usuario |  | ✓ |  |  | ✓ |  |  |  |
| /admin/cambiar_rol |  | ✓ |  |  | ✓ |  |  |  |
| /bitacora | ✓ |  |  |  | ✓ | ✓ |  |  |

---

### Manejo de errores

Todos los endpoints retornan errores en formato JSON:

**Formato de error:**
```json
{
  "status": "error",
  "message": "Descripción del error",
  "code": "ERROR_CODE",
  "details": {}
}
```

**Errores comunes:**

```json
// 400 Bad Request
{
  "status": "error",
  "message": "Parámetro 'titulo' es requerido",
  "code": "MISSING_PARAMETER"
}

// 401 Unauthorized
{
  "status": "error",
  "message": "No autenticado",
  "code": "NOT_AUTHENTICATED"
}

// 403 Forbidden
{
  "status": "error",
  "message": "No tienes permisos para esta acción",
  "code": "FORBIDDEN",
  "details": {"required_role": "admin", "current_role": "usuario"}
}

// 404 Not Found
{
  "status": "error",
  "message": "Expediente no encontrado",
  "code": "NOT_FOUND"
}

// 422 Unprocessable Entity
{
  "status": "error",
  "message": "Validación fallida",
  "code": "VALIDATION_ERROR",
  "details": {
    "username": "Longitud mínima: 3 caracteres",
    "password": "Debe contener mayúscula, minúscula, número y símbolo"
  }
}
```

---

### Ejemplo de flujo completo (Python)

```python
import requests
import json

BASE_URL = "http://localhost:5000"
session = requests.Session()

# 1. Login
print("=== 1. Login ===")
login_response = session.post(
    f"{BASE_URL}/login",
    data={"username": "usuario_pru", "password": "UserDemo123!"}
)
print(f"Status: {login_response.status_code}")
print(f"Response: {login_response.json()}\n")

# 2. Ver dashboard
print("=== 2. Dashboard ===")
dashboard = session.get(f"{BASE_URL}/dashboard").json()
print(f"Usuario: {dashboard['user']['username']} ({dashboard['user']['role']})")
print(f"Expedientes: {len(dashboard['expedientes'])}\n")

# 3. Crear expediente
print("=== 3. Crear expediente ===")
new_exp = session.post(
    f"{BASE_URL}/expediente/crear",
    json={
        "titulo": "Nuevo caso",
        "descripcion": "Descripción del caso"
    }
).json()
exp_id = new_exp["expediente"]["id"]
print(f"Expediente creado: ID {exp_id}\n")

# 4. Ver detalles
print("=== 4. Ver detalles ===")
exp_detail = session.get(f"{BASE_URL}/expediente/{exp_id}").json()
print(f"Estado: {exp_detail['expediente']['estado']}\n")

# 5. Canalizar expediente
print("=== 5. Canalizar ===")
canal_response = session.post(
    f"{BASE_URL}/expediente/{exp_id}/canalizar",
    json={"nuevo_estado": "en_revision"}
).json()
print(f"Nuevo estado: {canal_response['expediente']['estado']}\n")

# 6. Ver bitácora
print("=== 6. Bitácora ===")
bitacora = session.get(f"{BASE_URL}/bitacora?limit=5").json()
for evento in bitacora["eventos"][-3:]:
    print(f"- {evento['timestamp']}: {evento['accion']}")

# 7. Logout
print("\n=== 7. Logout ===")
session.post(f"{BASE_URL}/logout")
print("Sesión cerrada")
```

**Output esperado:**
```
=== 1. Login ===
Status: 200
Response: {'status': 'success', 'user': {'id': 1, 'username': 'usuario_pru', ...}}

=== 2. Dashboard ===
Usuario: usuario_pru (usuario)
Expedientes: 2

=== 3. Crear expediente ===
Expediente creado: ID 3

=== 4. Ver detalles ===
Estado: borrador

=== 5. Canalizar ===
Nuevo estado: en_revision

=== 6. Bitácora ===
- 2026-05-16T15:30:00Z: crear_expediente
- 2026-05-16T15:30:15Z: cambiar_estado_expediente
- 2026-05-16T15:30:20Z: ver_bitacora

=== 7. Logout ===
Sesión cerrada
```

---

## Flujos y Lógica de Negocio

### Procesos clave del sistema

#### 1. Autenticación y Control de Acceso

**Flujo de autenticación básica (usuario):**

```
┌─────────────────────────────────────────────────────────────────┐
│                   AUTENTICACIÓN BÁSICA                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. USUARIO ACCEDE A /login                                     │
│     └─→ Servidor genera UUID challenge                         │
│     └─→ Retorna formulario HTML                                │
│                                                                   │
│  2. USUARIO INGRESA CREDENCIALES                               │
│     ├─ username                                                 │
│     └─ password                                                 │
│                                                                   │
│  3. CLIENTE ENVÍA POST /login                                  │
│                                                                   │
│  4. SERVIDOR VALIDA                                            │
│     ├─ ¿Usuario existe?                                        │
│     │  └─→ NO: Retorna 401 "Usuario no existe"               │
│     ├─ ¿Está bloqueado por intentos?                          │
│     │  └─→ SÍ: Retorna 423 "Usuario bloqueado"               │
│     ├─ ¿Contraseña es correcta?                               │
│     │  ├─→ NO: login_attempts++                               │
│     │  │   └─ Si intentos >= 5:                              │
│     │  │      └─ locked_until = NOW + 900 seg                │
│     │  │   └─→ Retorna 401 "Contraseña incorrecta"           │
│     │  └─→ SÍ: Continuar                                      │
│     └─ Resetear login_attempts a 0                            │
│                                                                   │
│  5. CREAR SESIÓN                                               │
│     ├─ Generar session_id                                      │
│     ├─ Almacenar en Flask session                              │
│     ├─ Configurar cookie HttpOnly + SameSite                   │
│     └─ Registrar evento "login_exitoso" en bitácora            │
│                                                                   │
│  6. RETORNAR RESPUESTA 200                                     │
│     └─ {"status": "success", "user": {...}}                   │
│                                                                   │
│  7. CLIENTE RECIBE COOKIE DE SESIÓN                            │
│     └─ Se almacena en cliente de forma segura                  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Flujo de autenticación reforzada (admin/coordinador con certificado):**

```
┌─────────────────────────────────────────────────────────────────┐
│            AUTENTICACIÓN CON CERTIFICADO + FIRMA                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  1. USUARIO ACCEDE A /login                                     │
│     └─→ Servidor genera UUID challenge                         │
│                                                                   │
│  2. USUARIO CONSTRUYE PAYLOAD PARA FIRMAR                       │
│     Formato: CasaMonarca|<proposito>|<username>|<challenge>    │
│     Ejemplo: CasaMonarca|login|admin_prod|a1b2c3d4-...        │
│                                                                   │
│  3. USUARIO FIRMA CON CLAVE PRIVADA                            │
│     Command: openssl dgst -sha256 -sign private.key             │
│     Resultado: signature_b64 (Base64)                           │
│                                                                   │
│  4. USUARIO ENVÍA POST /login                                  │
│     ├─ username                                                 │
│     ├─ password                                                 │
│     ├─ challenge                                                │
│     ├─ signature_b64                                            │
│     └─ certificate_pem                                          │
│                                                                   │
│  5. SERVIDOR VALIDA CONTRASEÑA (igual que arriba)              │
│                                                                   │
│  6. SERVIDOR VALIDA CERTIFICADO                                │
│     ├─ ¿Certificado tiene firma válida de CA?                 │
│     │  └─→ NO: Retorna 401 "Certificado inválido"             │
│     ├─ ¿Certificado está expirado?                            │
│     │  └─→ SÍ: Retorna 401 "Certificado expirado"             │
│     ├─ ¿CN del certificado == username?                       │
│     │  └─→ NO: Retorna 401 "CN no coincide"                   │
│     ├─ ¿Certificado está revocado?                            │
│     │  └─→ SÍ: Retorna 401 "Certificado revocado"             │
│     └─→ VÁLIDO: Continuar                                      │
│                                                                   │
│  7. SERVIDOR VALIDA FIRMA                                      │
│     ├─ Extraer clave pública del certificado                   │
│     ├─ Verificar: signature_b64 = RSA-SHA256(payload)          │
│     │  └─→ NO: Retorna 401 "Firma inválida"                   │
│     └─→ VÁLIDA: Continuar                                      │
│                                                                   │
│  8. CREAR SESIÓN (igual que autenticación básica)              │
│     └─ Sesión ahora tiene "certificado_validado: true"        │
│                                                                   │
│  9. REGISTRAR EN BITÁCORA                                      │
│     └─ "login_exitoso" + "Con certificado + firma"            │
│                                                                   │
│  10. RETORNAR RESPUESTA 200                                    │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

#### 2. Ciclo de vida de expedientes

**Estados y transiciones:**

```
                ┌──────────────┐
                │   BORRADOR   │ ◄──────┐ Usuario crea
                └──────┬───────┘        │ expediente
                       │
                       │ canalizar (usuario)
                       ▼
                ┌──────────────┐
                │ EN_REVISIÓN  │
                └──────┬───────┘
                       │
                       │ canalizar (operativo)
                       ▼
                ┌──────────────┐
                │  VALIDADO    │
                └──────┬───────┘
                       │
                       │ canalizar (coordinador + firma)
                       ▼
                ┌──────────────┐
                │   CERRADO    │
                └──────────────┘
                       ▲
                       │
                       └─ Cualquier estado → borrador (admin, para revisar)
```

**Reglas de transición:**

| De → A | Rol requerido | Autenticación | Condiciones adicionales |
|--------|---------------|--------------|----------------------|
| BORRADOR → EN_REVISIÓN | usuario | Contraseña | Solo propietario |
| EN_REVISIÓN → VALIDADO | operativo | Contraseña | Solo asignado |
| VALIDADO → CERRADO | coordinador | Cert + Firma | Debe registrarse en bitácora |
| * → BORRADOR | admin | Cert + Firma | Para revisar/editar |
| * → CERRADO | admin | Cert + Firma | Cierre de emergencia |

**Permisos por rol en cada estado:**

| Estado | Usuario | Operativo | Coordinador | Admin |
|--------|---------|-----------|-------------|-------|
| BORRADOR | Ver, Canalizar | - | - | Ver, Canalizar, Editar |
| EN_REVISIÓN | Ver (propio) | Ver, Canalizar | Ver | Ver, Canalizar |
| VALIDADO | Ver (propio) | Ver | Ver, Canalizar | Ver, Canalizar |
| CERRADO | Ver (propio) | Ver | Ver | Ver, Reabrir |

#### 3. Gestión de certificados

**Ciclo de vida de certificados:**

```
┌─────────────────────────────────────────────────────────────────┐
│                  CICLO DE VIDA DE CERTIFICADOS                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  USUARIO SOLICITA CERTIFICADO EN /certificado/setup             │
│  ├─ Opción A: Generar localmente (sin CSR)                     │
│  │  └─ CA genera clave privada + CSR + certificado             │
│  │  └─ Usuario descarga (.pem)                                 │
│  └─ Opción B: Cargar CSR existente                             │
│     └─ Usuario previamente generó CSR con clave privada        │
│     └─ CA firma el CSR                                         │
│     └─ Usuario descarga certificado firmado                    │
│                                                                   │
│  CERTIFICADO EMITIDO (estado: ACTIVO)                           │
│  ├─ Stored en BD (huella SHA-256, PEM)                         │
│  ├─ Válido por 30 días (720 horas)                             │
│  └─ Puede usar para:                                           │
│     ├─ Autenticación reforzada (login)                         │
│     └─ Firmar acciones críticas                                │
│                                                                   │
│  ANTES DE EXPIRACIÓN                                            │
│  └─ Usuario recibe notificación (7 días antes)                 │
│     └─ Puede renovar en /certificado/setup                     │
│                                                                   │
│  USUARIO REVOCA (acción crítica)                               │
│  ├─ POST /certificado/<id>/revocar con motivo                  │
│  ├─ Motivo obligatorio: "Compromiso", "Pérdida", "Rotación"    │
│  ├─ Certificado marcado como REVOCADO                          │
│  ├─ Evento registrado en bitácora                              │
│  └─ No puede volver a usar (incluso si había tiempo)           │
│                                                                   │
│  CERTIFICADO EXPIRA                                            │
│  └─ Después de 30 días                                         │
│  └─ Estado automático: EXPIRADO                                │
│  └─ No puede usar para autenticación                           │
│  └─ Debe generar nuevo                                         │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Validaciones de certificado en login:**

```python
def validate_certificate_for_login(cert_pem, username):
    # 1. Parsear certificado
    cert = load_pem_x509_certificate(cert_pem)
    
    # 2. Validar firma de CA
    if not verify_ca_signature(cert):
        raise InvalidCertificate("CA signature invalid")
    
    # 3. Validar CN
    cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    if cn != username:
        raise InvalidCertificate("CN mismatch")
    
    # 4. Validar vigencia
    if cert.not_valid_after < datetime.now():
        raise CertificateExpired()
    
    # 5. Consultar BD
    db_cert = get_certificate_by_fingerprint(certificate_fingerprint(cert))
    
    # 6. Validar estado en BD
    if db_cert.estado != 'activo':
        raise CertificateRevoked()
    
    return True
```

#### 4. Rate-limiting y protección

**Lógica de bloqueo por intentos fallidos:**

```
┌─────────────────────────────────────────────────────────────────┐
│                   RATE-LIMITING DE LOGIN                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Configuración:                                                 │
│  ├─ MAX_ATTEMPTS = 5 intentos                                   │
│  ├─ WINDOW = 300 segundos (5 minutos)                           │
│  └─ LOCKOUT = 900 segundos (15 minutos)                         │
│                                                                   │
│  USUARIO INTENTA LOGIN                                          │
│  ├─ ¿Existe registro en login_attempts?                         │
│  │  └─ NO: Crear registro nuevo (intentos=0)                   │
│  │  └─ SÍ: Continuar                                           │
│  │                                                               │
│  ├─ ¿locked_until > NOW?                                       │
│  │  └─ SÍ: RECHAZAR "Usuario bloqueado hasta ..."             │
│  │  └─ NO: Continuar                                           │
│  │                                                               │
│  ├─ ¿ ventana_inicio + 300 < NOW?                             │
│  │  └─ SÍ: RESETEAR (intentos=0, ventana_inicio=NOW)          │
│  │  └─ NO: Continuar con ventana actual                        │
│  │                                                               │
│  ├─ VALIDAR CREDENCIALES                                       │
│  │  └─ ¿Correctas?                                             │
│  │     ├─ SÍ: intentos=0, locked_until=NULL → LOGIN OK       │
│  │     └─ NO: intentos++ → Continuar                           │
│  │                                                               │
│  ├─ ¿intentos >= MAX_ATTEMPTS (5)?                            │
│  │  └─ SÍ:                                                      │
│  │     ├─ locked_until = NOW + 900 seg                         │
│  │     ├─ Registrar "login_bloqueado" en bitácora              │
│  │     └─ RECHAZAR "Usuario bloqueado 15 minutos"             │
│  │  └─ NO:                                                      │
│  │     ├─ remaining = 5 - intentos                             │
│  │     └─ RECHAZAR "Contraseña incorrecta. Intenta: X/5"      │
│  │                                                               │
│  ├─ DESPUÉS DE 15 MINUTOS                                      │
│  │  └─ locked_until < NOW                                      │
│  │  └─ Siguiente intento: resetea automáticamente              │
│  │  └─ Vuelve a contar desde 0                                 │
│  │                                                               │
└─────────────────────────────────────────────────────────────────┘
```

### Reglas importantes

#### 1. Reglas de seguridad

**Contraseña:**
- Mínimo 12 caracteres
- Debe contener: mayúscula, minúscula, número, símbolo especial
- No puede ser contraseña débil común (lista negra)
- Hashing: Argon2id con:
  - `memory_cost` = 65536 KB (64 MB)
  - `time_cost` = 3 iteraciones
  - `parallelism` = 2
  - `hash_len` = 32 bytes

**Certificados X.509:**
- Generados por CA local
- Válidos por 30 días (720 horas)
- Utilizan RSA-2048 para claves
- SHA-256 para firma
- CN debe coincidir con username

**Sesiones:**
- Cookie HttpOnly: No accesible por JavaScript
- Cookie SameSite: Strict (producción) / Lax (desarrollo)
- Cookie Secure: Requiere HTTPS en producción
- Tiempo de vida: 8 horas (configurable)

#### 2. Reglas de integridad de datos

**Expedientes:**
- Solo el propietario puede editar en estado "BORRADOR"
- Una vez canalizados, no pueden volver a "BORRADOR" excepto admin
- Cambios de estado se registran en bitácora con timestamp
- Auditoría completa: quién, cuándo, qué acción

**Certificados:**
- Una vez revocado, no se puede reactivar (debe generar nuevo)
- Huella SHA-256 es única (no puede haber dos certificados con misma huella)
- Expiración es automática en BD (chequeo al login)

**Usuarios:**
- username es único (constraint UNIQUE)
- No se puede cambiar username después de creación
- Eliminar usuario es operación crítica (cascada a expedientes)

#### 3. Reglas de auditoría

**Eventos auditados (14 tipos):**
1. `login_exitoso` — Login correcto
2. `login_fallido` — Credenciales incorrectas
3. `login_bloqueado` — Usuario bloqueado por intentos
4. `logout` — Cierre de sesión
5. `cambiar_contrasena` — Cambio de contraseña
6. `crear_expediente` — Nuevo expediente
7. `cambiar_estado_expediente` — Canalización
8. `crear_usuario` — Creación por admin (requiere firma)
9. `eliminar_usuario` — Eliminación por admin
10. `cambiar_rol_usuario` — Cambio de rol por admin
11. `generar_certificado` — Emisión de certificado
12. `revocar_certificado` — Revocación de certificado
13. `backup_realizado` — Backup cifrado
14. `backup_restaurado` — Restauración de backup

**Registro obligatorio:**
- username: usuario que realizó la acción
- accion: tipo de evento
- descripcion: detalles (ej: "User: operativo_1, Estado: borrador → en_revision")
- timestamp: fecha/hora exacta (UTC)
- ip_address: IP del cliente (para auditoría de seguridad)

#### 4. Reglas de acceso RBAC

**Roles y permisos:**

| Rol | Crear Expediente | Canalizar | Ver Bitácora | Crear Usuario | Revocar Cert |
|-----|-----------------|-----------|--------------|---------------|-------------|
| usuario | ✓ (propio) | ✓ | - | - | ✓ (propio) |
| operativo | - | ✓ | - | - | ✓ (propio) |
| coordinador | - | ✓ (con firma) | ✓ (todo) | - | ✓ (todo) |
| admin | ✓ | ✓ | ✓ (todo) | ✓ (con firma) | ✓ (todo) |

**Validación en cada request:**
```python
@require_login
@require_role("admin")  # Solo admin
def admin_crear_usuario():
    # Si no es admin → 403 Forbidden
    # Si no está autenticado → 401 Unauthorized
    pass
```

### Casos críticos

#### 1. Usuario bloqueado por intentos

**Escenario:** Usuario ingresa contraseña incorrecta 5 veces en 5 minutos.

**Lógica:**
1. Intento 1-4: Rechaza con "Credenciales incorrectas. Intentos restantes: X"
2. Intento 5: locked_until = NOW + 900 segundos (15 minutos)
3. Login rechazado: "Usuario bloqueado hasta 2026-05-16T15:15:00Z"
4. Evento registrado: `login_bloqueado`
5. Después de 15 min: Usuario puede intentar de nuevo (contador resetea)

**Código:**
```python
def check_login_attempts(username):
    record = db.query(LoginAttempts).filter_by(username=username).first()
    
    # Si no existe, crear
    if not record:
        record = LoginAttempts(username=username, intentos=0)
        db.add(record)
        db.commit()
        return True
    
    # Si está bloqueado y aún vigente
    if record.locked_until and record.locked_until > datetime.now():
        log_event(username, "login_bloqueado", f"Bloqueado hasta {record.locked_until}")
        return False
    
    # Si pasó la ventana de bloqueo, resetear
    if record.ventana_inicio and (datetime.now() - record.ventana_inicio).total_seconds() > 300:
        record.intentos = 0
        record.ventana_inicio = datetime.now()
        db.commit()
    
    return True

def handle_failed_login(username):
    record = db.query(LoginAttempts).filter_by(username=username).first()
    record.intentos += 1
    
    if record.intentos >= 5:
        record.locked_until = datetime.now() + timedelta(seconds=900)
        log_event(username, "login_bloqueado", "Por intentos excesivos")
    else:
        log_event(username, "login_fallido", f"Intento {record.intentos}/5")
    
    db.commit()
```

#### 2. Certificado próximo a expirar

**Escenario:** Certificado expira en 7 días.

**Lógica:**
1. Sistema detecta: expires_at < NOW + 7 días
2. En siguiente login: Mostrar banner amarillo "Tu certificado expira el X"
3. Usuario navega a /certificado/setup
4. Si intenta usar certificado expirado:
   - Rechaza login con "Certificado expirado"
   - Debe generar nuevo certificado

**Consulta de detección:**
```sql
SELECT * FROM certificados
WHERE user_id = ? 
  AND estado = 'activo'
  AND expires_at < datetime('now', '+7 days')
ORDER BY expires_at ASC;
```

#### 3. Expediente en transición de estado bloqueado

**Escenario:** Coordinador intenta canalizar expediente que está en revisión pero sin firma.

**Lógica:**
1. POST /expediente/<id>/canalizar
2. Servidor valida:
   - ¿Usuario es coordinador? ✓
   - ¿Expediente está en VALIDADO? ✓
   - ¿Tiene firma? ✗ (signature_b64 vacío)
3. Rechaza: "Firma requerida para canalizar"
4. Usuario debe firmar con certificado privado

**Validación:**
```python
def canalizar_expediente(exp_id, nuevo_estado, signature_b64=None):
    exp = get_expediente(exp_id)
    user = get_current_user()
    
    # Validar transición
    if not es_transicion_valida(exp.estado, nuevo_estado, user.role):
        raise PermissionError(f"Transición no permitida para {user.role}")
    
    # Si es coordinador/admin, requiere firma
    if user.role in ["coordinador", "admin"]:
        if not signature_b64:
            raise ValueError("Firma requerida")
        
        if not verify_signature(signature_b64, user.certificate_pem):
            raise ValueError("Firma inválida")
    
    # Actualizar y auditar
    exp.estado = nuevo_estado
    exp.updated_at = datetime.now()
    db.commit()
    
    log_event(user.username, "cambiar_estado_expediente",
              f"ID: {exp_id}, {exp.estado} → {nuevo_estado}")
```

#### 4. Admin resetea contraseña de usuario bloqueado

**Escenario:** User "operativo_1" está bloqueado por intentos. Admin lo resetea.

**Lógica:**
1. Admin accede (autenticado)
2. Admin navega a /admin/usuarios
3. Localiza "operativo_1"
4. Opción: "Resetear contraseña"
5. Sistema:
   - Genera nueva contraseña temporal
   - Establece `must_change_password = 1`
   - Resetea `login_attempts.locked_until = NULL`
   - Resetea `login_attempts.intentos = 0`
   - Registra evento: "cambiar_contrasena_forzado"
6. Admin comparte password temporal con usuario
7. Usuario en siguiente login debe cambiar contraseña

#### 5. Backup fallido durante operación crítica

**Escenario:** Proceso de backup interrumpido mientras se escribía archivo .enc

**Lógica:**
1. `tools/backup_db.py` inicia
2. Genera IV aleatorio
3. Cifra database.db con AES-256
4. Escribe backup a `backups/db_backup_YYYYMMDDTHHMMSSZ.enc`
5. Si falla a mitad:
   - Archivo .enc queda incompleto/corrupto
   - Siguiente intento crea nuevo archivo
   - No intenta completar anterior

**Protección:**
```python
def backup_database():
    try:
        # Leer BD
        with open("database.db", "rb") as f:
            db_data = f.read()
        
        # Generar IV aleatorio
        iv = os.urandom(16)
        
        # Cifrar
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(iv),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(db_data) + encryptor.finalize()
        
        # Escribir a archivo temporal primero
        timestamp = datetime.now().isoformat().replace(":", "").replace(".", "")
        temp_path = f"backups/db_backup_{timestamp}.tmp"
        final_path = f"backups/db_backup_{timestamp}.enc"
        
        with open(temp_path, "wb") as f:
            f.write(iv + encrypted)
        
        # Renombrar solo si todo fue bien
        os.rename(temp_path, final_path)
        
        log_event("system", "backup_realizado", f"File: {final_path}")
        
    except Exception as e:
        log_event("system", "backup_fallido", f"Error: {str(e)}")
        raise
```

#### 6. Validación de CSR cargado por usuario

**Escenario:** Usuario carga CSR generado con su clave privada en /certificado/setup

**Lógica:**
1. Usuario navega a /certificado/setup
2. Selecciona "Usar CSR existente"
3. Carga archivo: `usuario.csr.pem`
4. Servidor valida:
   - ¿Es formato PEM válido?
   - ¿CSR está bien formado?
   - ¿CN en CSR == username del usuario?
   - ¿Clave pública en CSR es válida?
5. Si todo OK:
   - CA firma el CSR
   - Emite certificado X.509
   - Almacena en BD
6. Si error: Rechaza con mensaje claro

**Validación:**
```python
def validar_csr(csr_pem, username):
    try:
        # Parsear CSR
        csr = load_pem_x509_csr(csr_pem.encode())
        
        # Validar CN
        cn = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
        if cn != username:
            raise ValueError(f"CSR CN ({cn}) no coincide con usuario ({username})")
        
        # Validar clave pública
        public_key = csr.public_key()
        if not isinstance(public_key, RSAPublicKey):
            raise ValueError("CSR debe usar RSA")
        
        if public_key.key_size < 2048:
            raise ValueError("CSR debe usar RSA-2048 o mayor")
        
        return True
        
    except Exception as e:
        raise ValueError(f"CSR inválido: {str(e)}")
```

---

## Ejemplos de Uso

### 1. Caso típico: Usuario crea y canaliza expediente

**Escenario:** Usuario operativo crea un expediente, lo revisa y lo canaliza a coordinador.

```bash
# 1. Login
curl -X POST http://localhost:5000/login \
  -d "username=operativo_1&password=Operativo123!" \
  -c cookies.txt

# 2. Ver dashboard
curl http://localhost:5000/dashboard -b cookies.txt

# 3. Crear expediente
curl -X POST http://localhost:5000/expediente/crear \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"titulo":"Caso refugio","descripcion":"Solicitud urgente"}'
# Response: {"expediente": {"id": 10, ...}}

# 4. Canalizar a coordinador
curl -X POST http://localhost:5000/expediente/10/canalizar \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"nuevo_estado":"en_revision"}'

# 5. Logout
curl -X POST http://localhost:5000/logout -b cookies.txt
```

### 2. Caso típico: Admin crea usuario con certificado

**Escenario:** Admin crea nuevo usuario operativo mediante certificado.

```bash
# 1. Admin obtiene challenge
CHALLENGE=$(curl http://localhost:5000/login | jq -r '.challenge')

# 2. Admin construye y firma payload
PAYLOAD="CasaMonarca|creacion de usuario|admin_prod|$CHALLENGE"
echo -n "$PAYLOAD" | openssl dgst -sha256 -sign admin_prod.key | base64 > sig.b64
SIGNATURE=$(cat sig.b64 | tr -d '\n')

# 3. Admin login con certificado
curl -X POST http://localhost:5000/login \
  -d "username=admin_prod&password=AdminProdX2026!&challenge=$CHALLENGE&signature_b64=$SIGNATURE&certificate_pem=$(cat admin_prod.pem | base64)" \
  -c cookies.txt

# 4. Admin crea usuario (requiere firma)
curl -X POST http://localhost:5000/admin/crear_usuario \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{"username":"nuevo_operativo","role":"operativo","challenge":"...","signature_b64":"..."}'
```

### 3. Integración básica: Cliente Python

**Cliente reutilizable para integración:**

```python
import requests
import json

class CasaMonarcaClient:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.session = requests.Session()
    
    def login(self, username, password):
        """Autentica usuario con contraseña."""
        resp = self.session.post(
            f"{self.base_url}/login",
            data={"username": username, "password": password}
        )
        return resp.json()
    
    def crear_expediente(self, titulo, descripcion=""):
        """Crea nuevo expediente."""
        return self.session.post(
            f"{self.base_url}/expediente/crear",
            json={"titulo": titulo, "descripcion": descripcion}
        ).json()
    
    def canalizar_expediente(self, exp_id, nuevo_estado):
        """Canaliza expediente a nuevo estado."""
        return self.session.post(
            f"{self.base_url}/expediente/{exp_id}/canalizar",
            json={"nuevo_estado": nuevo_estado}
        ).json()
    
    def obtener_bitacora(self, limit=20):
        """Obtiene últimos eventos auditados."""
        return self.session.get(
            f"{self.base_url}/bitacora",
            params={"limit": limit}
        ).json()
    
    def logout(self):
        """Cierra sesión."""
        return self.session.post(f"{self.base_url}/logout").json()

# Uso
client = CasaMonarcaClient()
client.login("usuario_pru", "UserDemo123!")
exp = client.crear_expediente("Mi caso", "Descripción")
print(f"Expediente creado: {exp['expediente']['id']}")
client.canalizar_expediente(exp['expediente']['id'], "en_revision")
client.logout()
```

### 4. Ejecución de funciones clave desde Python

**Operaciones comunes directas:**

```python
# Login básico
import requests
session = requests.Session()
r = session.post("http://localhost:5000/login",
                 data={"username": "usuario_pru", "password": "UserDemo123!"})
print(r.json())

# Crear expediente
r = session.post("http://localhost:5000/expediente/crear",
                 json={"titulo": "Nuevo caso", "descripcion": "Detalles"})
expediente_id = r.json()["expediente"]["id"]

# Obtener dashboard
r = session.get("http://localhost:5000/dashboard")
print(f"Expedientes: {len(r.json()['expedientes'])}")

# Canalizar
r = session.post(f"http://localhost:5000/expediente/{expediente_id}/canalizar",
                 json={"nuevo_estado": "en_revision"})
print(r.json()["message"])

# Ver bitácora
r = session.get("http://localhost:5000/bitacora?limit=5")
for evt in r.json()["eventos"]:
    print(f"{evt['timestamp']}: {evt['accion']}")

# Logout
session.post("http://localhost:5000/logout")
```

### 5. Script de administración (backup y restore)

```bash
# Hacer backup cifrado
python tools/backup_db.py
# Salida: Backup guardado en backups/db_backup_20260516T153000Z.enc

# Restaurar desde backup
python tools/restore_db.py backups/db_backup_20260516T153000Z.enc
# Salida: Base de datos restaurada exitosamente

# Ver usuarios en BD
sqlite3 database.db "SELECT id, username, role FROM usuarios;"

# Crear usuario vía CLI
python -c "
import sqlite3
from werkzeug.security import generate_password_hash
conn = sqlite3.connect('database.db')
c = conn.cursor()
c.execute('INSERT INTO usuarios (username, password_hash, role) VALUES (?, ?, ?)',
          ('nuevo_user', generate_password_hash('Pass123!'), 'usuario'))
conn.commit()
"
```

### 6. Testing rápido de endpoints

```bash
# Setup: guardar BASE_URL
BASE_URL="http://localhost:5000"

# 1. Login
curl -s -X POST "$BASE_URL/login" \
  -d "username=usuario_pru&password=UserDemo123!" \
  -c /tmp/cookies.txt | jq .

# 2. Dashboard
curl -s "$BASE_URL/dashboard" -b /tmp/cookies.txt | jq '.expedientes | length'

# 3. Crear expediente
curl -s -X POST "$BASE_URL/expediente/crear" \
  -H "Content-Type: application/json" \
  -b /tmp/cookies.txt \
  -d '{"titulo":"Test","descripcion":"Quick test"}' | jq '.expediente.id'

# 4. Bitácora
curl -s "$BASE_URL/bitacora?limit=3" -b /tmp/cookies.txt | jq '.eventos[-1]'

# 5. Logout
curl -s -X POST "$BASE_URL/logout" -b /tmp/cookies.txt | jq .
```

---

## Manejo de Errores

### Estrategia de errores

Casa Monarca implementa una **estrategia consistente de manejo de errores** con:

1. **Validación en capas:**
   - Capa 1: Validación HTTP (parámetros, headers)
   - Capa 2: Validación de negocio (roles, estados)
   - Capa 3: Validación de seguridad (certs, firmas)

2. **Respuestas de error normalizadas:**
```json
{
  "status": "error",
  "message": "Descripción legible para el usuario",
  "code": "ERROR_CODE",
  "details": {"field": "error_specific"}
}
```

3. **Códigos HTTP apropriados:**
   - `400` — Parámetro inválido (culpa del cliente)
   - `401` — No autenticado (sesión expirada)
   - `403` — Sin permisos (RBAC denied)
   - `404` — Recurso no existe
   - `422` — Validación fallida (datos inválidos)
   - `423` — Recurso bloqueado (usuario locked, expediente en transición)
   - `500` — Error del servidor (excepción no manejada)

4. **Manejo de excepciones:**
   - Captura de excepciones en decoradores de rutas
   - Logging de stack trace en servidor
   - Respuesta genérica al cliente (nunca exponer detalles internos)

### Mensajes comunes

#### Autenticación

| Error | Código HTTP | Mensaje | Causa |
|-------|------------|---------|-------|
| Credenciales inválidas | 401 | `Credenciales inválidas` | Usuario/password incorrecto |
| Usuario no existe | 401 | `Usuario no encontrado` | username no existe en BD |
| Usuario bloqueado | 423 | `Usuario bloqueado hasta {timestamp}` | 5 intentos fallidos |
| Certificado inválido | 401 | `Certificado no válido` | Firma CA falló |
| Certificado expirado | 401 | `Certificado expirado` | Fecha de expiración pasada |
| CN mismatch | 401 | `CN del certificado no coincide con usuario` | Cert CN ≠ username |
| Certificado revocado | 401 | `Certificado ha sido revocado` | Estado = revocado en BD |
| Firma inválida | 401 | `Firma digital inválida` | Verificación RSA-SHA256 falló |
| No autenticado | 401 | `No autenticado. Inicia sesión` | Sin sesión activa |
| Sesión expirada | 401 | `Tu sesión ha expirado` | Cookie > 8 horas |

#### Autorización

| Error | Código HTTP | Mensaje | Causa |
|-------|------------|---------|-------|
| Rol insuficiente | 403 | `No tienes permisos. Rol requerido: {role}` | User role < required |
| Acceso denegado | 403 | `No puedes acceder a este recurso` | RBAC validation failed |
| Sin firma requerida | 422 | `Firma requerida para esta acción` | Certificado + firma no provided |

#### Validación de datos

| Error | Código HTTP | Mensaje | Detalles |
|-------|------------|---------|----------|
| Parámetro faltante | 400 | `Parámetro '{field}' es requerido` | `{"field": "titulo"}` |
| Formato inválido | 422 | `'{field}' tiene formato inválido` | `{"field": "email", "expected": "email"}` |
| Longitud mínima | 422 | `'{field}' debe tener ≥ {min} caracteres` | `{"field": "password", "min": 12}` |
| Contraseña débil | 422 | `Contraseña no cumple requisitos` | `{"requirements": [...]}` |
| Username duplicado | 422 | `Username ya existe` | `{"field": "username"}` |
| Expediente no existe | 404 | `Expediente no encontrado` | `{"id": 999}` |
| Transición inválida | 422 | `No puedes cambiar de {from} a {to}` | `{"from": "borrador", "to": "cerrado"}` |

#### Certificados

| Error | Código HTTP | Mensaje | Causa |
|-------|------------|---------|-------|
| CSR inválido | 422 | `CSR tiene formato inválido` | PEM parse error |
| CN en CSR inválido | 422 | `CN del CSR no coincide con usuario` | CSR CN ≠ username |
| Clave débil | 422 | `CSR debe usar RSA-2048 o mayor` | Key size < 2048 |
| Certificado no encontrado | 404 | `Certificado no existe` | cert_id invalid |
| Ya tiene certificado activo | 422 | `Ya tienes un certificado activo` | User already has active cert |

#### Sistema

| Error | Código HTTP | Mensaje | Causa |
|-------|------------|---------|-------|
| Error interno | 500 | `Error interno del servidor` | Excepción no manejada |
| BD indisponible | 503 | `Base de datos no disponible` | SQLite locked/missing |
| Backup fallido | 500 | `No se pudo crear backup` | Escritura a disco falló |

### Ejemplos de respuestas de error

**Formato estándar de error:**
```json
{
  "status": "error",
  "message": "Contraseña incorrecta",
  "code": "INVALID_CREDENTIALS",
  "remaining_attempts": 4
}
```

**Error de validación (422):**
```json
{
  "status": "error",
  "message": "Validación fallida",
  "code": "VALIDATION_ERROR",
  "details": {
    "titulo": "Mínimo 5 caracteres",
    "descripcion": "Campo opcional"
  }
}
```

**Error de permisos (403):**
```json
{
  "status": "error",
  "message": "No tienes permisos para esta acción",
  "code": "FORBIDDEN",
  "details": {
    "required_role": "admin",
    "current_role": "usuario"
  }
}
```

**Error de bloqueo (423):**
```json
{
  "status": "locked",
  "message": "Usuario bloqueado por intentos excesivos",
  "code": "USER_LOCKED",
  "locked_until": "2026-05-16T15:15:00Z"
}
```

### Registro (logs)

#### Niveles de log

| Nivel | Propósito | Ejemplo |
|-------|-----------|---------|
| DEBUG | Desarrollo, variables internas | "Iniciando validación de cert..." |
| INFO | Eventos normales significativos | "Usuario login_exitoso", "Backup completado" |
| WARNING | Situaciones anormales | "Usuario bloqueado", "Certificado próximo a expirar" |
| ERROR | Errores que requieren atención | "Login fallido x5", "Backup fallido" |
| CRITICAL | Fallos de sistema | "BD indisponible", "Clave CA corrupta" |

#### Ubicación de logs

```
proyecto/
├── logs/
│   ├── app.log              # Logs principales de aplicación
│   ├── security.log         # Eventos de seguridad
│   ├── audit.log            # Auditoría (duplica bitácora)
│   └── error.log            # Solo errores
├── flask.log                # Log Flask por defecto
└── database.db              # Bitácora en BD (inmutable)
```

#### Configuración de logging

```python
import logging
import logging.handlers

# Logger principal
logger = logging.getLogger('casa_monarca')
logger.setLevel(logging.DEBUG)

# Handler para archivo (rotación)
fh = logging.handlers.RotatingFileHandler(
    'logs/app.log',
    maxBytes=10*1024*1024,  # 10 MB
    backupCount=5           # Mantener 5 backups
)
fh.setLevel(logging.DEBUG)

# Handler para errores solo
error_handler = logging.handlers.RotatingFileHandler(
    'logs/error.log',
    maxBytes=5*1024*1024,
    backupCount=3
)
error_handler.setLevel(logging.ERROR)

# Formato
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
fh.setFormatter(formatter)
error_handler.setFormatter(formatter)

logger.addHandler(fh)
logger.addHandler(error_handler)
```

#### Eventos de seguridad (security.log)

```
2026-05-16 15:30:00 - INFO - [LOGIN_EXITOSO] usuario_pru (192.168.1.150)
2026-05-16 15:31:15 - WARNING - [LOGIN_FALLIDO] operativo_1 intento 1/5 (192.168.1.155)
2026-05-16 15:31:42 - WARNING - [LOGIN_FALLIDO] operativo_1 intento 2/5 (192.168.1.155)
2026-05-16 15:32:30 - WARNING - [LOGIN_FALLIDO] operativo_1 intento 3/5 (192.168.1.155)
2026-05-16 15:33:15 - WARNING - [LOGIN_FALLIDO] operativo_1 intento 4/5 (192.168.1.155)
2026-05-16 15:34:00 - ERROR - [LOGIN_BLOQUEADO] operativo_1 (192.168.1.155) hasta 2026-05-16T15:49:00Z
2026-05-16 15:40:20 - INFO - [CERTIFICADO_GENERADO] admin_prod (huella: a1b2c3d4...)
2026-05-16 15:41:10 - WARNING - [CERTIFICADO_PROXIMO_EXPIRAR] coord_admin expira en 7 días
```

#### Auditoría en código

```python
def log_event(username, accion, descripcion="", ip_address=""):
    """Registra evento en BD y log de auditoría."""
    try:
        # Registrar en BD (bitácora)
        evento = Bitacora(
            username=username,
            accion=accion,
            descripcion=descripcion,
            timestamp=datetime.now(timezone.utc),
            ip_address=ip_address
        )
        db.session.add(evento)
        db.commit()
        
        # Registrar en archivo de auditoría
        logger.info(f"[{accion}] {username} - {descripcion} ({ip_address})")
        
    except Exception as e:
        logger.error(f"Error logging event: {str(e)}")

# Uso en rutas
@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    ip = request.remote_addr
    
    user = get_user(username)
    if not user:
        log_event(username, "login_fallido", "Usuario no existe", ip)
        return {"status": "error", "message": "Usuario no encontrado"}, 401
    
    if not verify_password(user, password):
        log_event(username, "login_fallido", "Contraseña incorrecta", ip)
        return {"status": "error", "message": "Credenciales inválidas"}, 401
    
    # Login exitoso
    session['user_id'] = user.id
    log_event(username, "login_exitoso", "Autenticación correcta", ip)
    return {"status": "success", "user": user.to_dict()}, 200
```

#### Consultar logs

```bash
# Ver últimos 50 eventos de app.log
tail -50 logs/app.log

# Monitorear en tiempo real
tail -f logs/app.log

# Buscar logins fallidos
grep "login_fallido" logs/security.log

# Contar eventos por tipo
grep "INFO\|WARNING\|ERROR" logs/app.log | cut -d'-' -f4 | sort | uniq -c

# Ver solo errores de las últimas 24 horas
find logs/ -name "*.log" -mtime -1 -exec grep -h "ERROR\|CRITICAL" {} \;

# Limpiar logs antiguos (> 30 días)
find logs/ -name "*.log" -mtime +30 -delete
```

#### Monitoreo y alertas

**Problemas a monitorear:**

```bash
# 1. Múltiples intentos fallidos (potencial ataque)
grep -c "login_fallido" logs/security.log
# Si > 50 en última hora → ALERTA

# 2. Certificados a punto de expirar
sqlite3 database.db \
  "SELECT username FROM certificados 
   WHERE expires_at < datetime('now', '+7 days') 
   AND estado='activo';"

# 3. Tamaño de logs
du -sh logs/
# Si > 1GB → Considerar rotación manual

# 4. Errores de sistema
grep "CRITICAL\|500" logs/error.log
```

---

## Pruebas

### Tipos de tests

#### 1. Tests unitarios (Unit Tests)

**Propósito:** Validar funciones individuales en aislamiento.

**Cobertura:**
- Hashing de contraseñas (Argon2)
- Validación de emails
- Cálculo de huellas SHA-256
- Generación de desafíos UUID
- Lógica de rate-limiting

**Ejemplo:**
```python
# tests/test_password_security.py
import pytest
from werkzeug.security import generate_password_hash, check_password_hash
from argon2.low_level import hash_secret, Type

def test_password_hashing():
    """Test que hash de contraseña es verificable."""
    password = "SecurePass123!"
    hash_pwd = generate_password_hash(password, method='pbkdf2')
    assert check_password_hash(hash_pwd, password)

def test_weak_password_rejected():
    """Test que contraseña débil es rechazada."""
    weak_passwords = ["123456", "password", "admin123"]
    for pwd in weak_passwords:
        assert is_weak_password(pwd)

def test_login_attempts_reset():
    """Test que intentos de login se resetean."""
    record = LoginAttempts(username="test", intentos=3)
    reset_login_attempts(record)
    assert record.intentos == 0
    assert record.locked_until is None
```

**Ejecución:**
```bash
PYTHONPATH=. pytest tests/test_password_security.py -v
```

#### 2. Tests de integración (Integration Tests)

**Propósito:** Validar flujos completos entre módulos (autenticación, BD, lógica).

**Cobertura:**
- Flujo de login (usuario + contraseña)
- Flujo de login con certificado + firma
- Creación y canalización de expedientes
- Generación y revocación de certificados
- Operaciones de backup/restore

**Ejemplo:**
```python
# tests/test_integration.py
import pytest
from app import app, db
from database import create_tables, add_user, get_user

@pytest.fixture
def client():
    """Fixture para cliente de prueba."""
    app.config['TESTING'] = True
    with app.test_client() as client:
        with app.app_context():
            create_tables()
            yield client

def test_login_flow(client):
    """Test flujo completo de login."""
    # 1. Crear usuario
    add_user("test_user", "TestPass123!", "usuario")
    
    # 2. Login exitoso
    response = client.post('/login',
        data={"username": "test_user", "password": "TestPass123!"})
    assert response.status_code == 200
    assert response.json['status'] == 'success'
    
    # 3. Acceder a dashboard (requiere sesión)
    response = client.get('/dashboard')
    assert response.status_code == 200

def test_crear_expediente_unauthorized(client):
    """Test que usuario no autenticado no puede crear."""
    response = client.post('/expediente/crear',
        json={"titulo": "Test"})
    assert response.status_code == 401
```

**Ejecución:**
```bash
PYTHONPATH=. pytest tests/test_integration.py -v
```

#### 3. Tests de seguridad (Security Tests)

**Propósito:** Validar controles de seguridad (RBAC, SSL, CSRF, rate-limiting).

**Cobertura:**
- Autenticación obligatoria en endpoints protegidos
- Validación de roles (admin, coordinador, operativo, usuario)
- CSRF token en formularios
- Rate-limiting en login
- Validación de certificados (CA, expiración, revocación)
- Hashing de contraseñas con salt

**Ejemplo:**
```python
# tests/test_security.py
import pytest

def test_rbac_admin_only(client, auth_user):
    """Test que solo admin accede a /admin/usuarios."""
    # 1. Usuario normal intenta acceder
    client.post('/login', data={"username": "user", "password": "Pass123!"})
    response = client.get('/admin/usuarios')
    assert response.status_code == 403
    
    # 2. Admin accede exitosamente
    client.post('/login', data={"username": "admin", "password": "Pass123!"})
    response = client.get('/admin/usuarios')
    assert response.status_code == 200

def test_rate_limiting(client):
    """Test que usuario se bloquea tras 5 intentos fallidos."""
    for i in range(5):
        response = client.post('/login',
            data={"username": "test", "password": "wrong"})
        assert response.status_code == 401
    
    # 6to intento debe estar bloqueado
    response = client.post('/login',
        data={"username": "test", "password": "correct"})
    assert response.status_code == 423  # Locked

def test_certificate_validation(client):
    """Test que certificado expirado es rechazado."""
    # Crear certificado con expiración pasada
    old_cert = create_expired_certificate("test_user")
    
    response = client.post('/login',
        data={"username": "test_user", "password": "Pass123!",
              "certificate_pem": old_cert})
    assert response.status_code == 401
    assert "expirado" in response.json['message'].lower()
```

**Ejecución:**
```bash
PYTHONPATH=. pytest tests/test_security.py -v
```

#### 4. Tests de carga (Load Tests - opcional)

**Propósito:** Validar rendimiento bajo carga.

**Herramienta:** `locust` (opcional, instalar con `pip install locust`)

**Ejemplo:**
```python
# tests/locustfile.py
from locust import HttpUser, task, between

class CasaMonarcaUser(HttpUser):
    wait_time = between(1, 3)
    
    @task(3)
    def login(self):
        self.client.post("/login",
            data={"username": "user", "password": "Pass123!"})
    
    @task(1)
    def dashboard(self):
        self.client.get("/dashboard")

# Ejecutar: locust -f tests/locustfile.py --host=http://localhost:5000
```

### Cómo ejecutarlos

#### Setup inicial

```bash
# 1. Activar entorno virtual
source .venv/bin/activate

# 2. Instalar pytest
pip install pytest pytest-cov

# 3. Crear directorio de tests (si no existe)
mkdir -p tests
```

#### Ejecutar todos los tests

```bash
# Ejecutar todos los tests
PYTHONPATH=. pytest -v

# Con reporte de cobertura
PYTHONPATH=. pytest --cov=. --cov-report=html

# Ver reporte HTML
open htmlcov/index.html
```

#### Ejecutar tests específicos

```bash
# Solo tests de password
PYTHONPATH=. pytest tests/test_password_security.py -v

# Solo tests de integración
PYTHONPATH=. pytest tests/test_integration.py -v

# Solo tests de seguridad
PYTHONPATH=. pytest tests/test_security.py -v

# Un test específico
PYTHONPATH=. pytest tests/test_password_security.py::test_weak_password_rejected -v

# Tests que coincidan con patrón
PYTHONPATH=. pytest -k "login" -v
```

#### Opciones útiles de pytest

```bash
# Mostrar salida (print statements)
PYTHONPATH=. pytest -v -s

# Parar en primer error
PYTHONPATH=. pytest -x

# Parar después de N errores
PYTHONPATH=. pytest --maxfail=3

# Ejecutar en paralelo (instalar pytest-xdist)
PYTHONPATH=. pytest -n auto

# Listar tests sin ejecutarlos
PYTHONPATH=. pytest --collect-only

# Ejecutar con markers (tests lentos, rápidos)
PYTHONPATH=. pytest -m "not slow"
```

#### Cobertura de código

```bash
# Generar reporte HTML de cobertura
PYTHONPATH=. pytest --cov=. --cov-report=html tests/

# Ver cobertura por módulo
PYTHONPATH=. pytest --cov=. --cov-report=term-missing

# Excluir archivos de cobertura
PYTHONPATH=. pytest --cov=. --cov-report=html \
  --cov-config=.coveragerc
```

#### Archivo .coveragerc (excluir archivos)

```ini
[run]
omit =
    .venv/*
    tests/*
    setup.py
    */__pycache__/*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
```

#### Ejemplo: Ejecutar tests con Jenkins/CI

```bash
#!/bin/bash
# .gitlab-ci.yml o similar

test:
  stage: test
  script:
    - python -m venv venv
    - source venv/bin/activate
    - pip install -r requirements.txt pytest pytest-cov
    - PYTHONPATH=. pytest --cov=. --cov-report=xml --cov-report=html
  artifacts:
    paths:
      - htmlcov/
    reports:
      coverage_report:
        coverage_format: cobertura
        path: coverage.xml
```

#### Checklist de tests antes de desplegar

```bash
#!/bin/bash
# tests/pre_deploy.sh

set -e

echo "=== Tests de Seguridad ==="
PYTHONPATH=. pytest tests/test_security.py -v

echo "=== Tests de Integración ==="
PYTHONPATH=. pytest tests/test_integration.py -v

echo "=== Tests Unitarios ==="
PYTHONPATH=. pytest tests/test_password_security.py -v

echo "=== Cobertura ==="
PYTHONPATH=. pytest --cov=. --cov-report=term-missing \
  --cov-fail-under=80  # Fallar si cobertura < 80%

echo "✅ Todos los tests pasaron"
```

**Ejecutar:**
```bash
chmod +x tests/pre_deploy.sh
./tests/pre_deploy.sh
```

---

## Despliegue

### Cómo hacerlo

#### 1. Pre-despliegue (Checklist)

```bash
#!/bin/bash
# scripts/pre_deploy.sh

set -e

echo "🔍 Pre-despliegue checklist"

# 1. Verificar rama
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ] && [ "$BRANCH" != "release" ]; then
    echo "❌ No estás en main o release"
    exit 1
fi

# 2. Verificar cambios sin commit
if [ -n "$(git status --porcelain)" ]; then
    echo "❌ Cambios sin commit"
    git status
    exit 1
fi

# 3. Ejecutar tests
echo "▶️  Ejecutando tests..."
PYTHONPATH=. pytest --cov=. --cov-fail-under=80 -q

# 4. Verificar variables de entorno
echo "▶️  Verificando .env..."
for var in SECRET_KEY DATABASE_URL AES_KEY; do
    if [ -z "${!var}" ]; then
        echo "❌ Variable $var no configurada en .env"
        exit 1
    fi
done

# 5. Verificar certificados
if [ ! -f "ca.key" ] || [ ! -f "ca.crt" ]; then
    echo "❌ Certificados CA no encontrados"
    exit 1
fi

# 6. Verificar clave de encriptación
if [ ! -f "key.key" ]; then
    echo "❌ key.key no encontrada"
    exit 1
fi

# 7. Generar backup pre-despliegue
echo "▶️  Creando backup..."
python tools/backup_db.py

echo "✅ Pre-despliegue OK. Listo para desplegar."
```

**Ejecutar:**
```bash
chmod +x scripts/pre_deploy.sh
./scripts/pre_deploy.sh
```

#### 2. Despliegue manual (Local/Servidor)

**Opción A: Despliegue directo en servidor**

```bash
# 1. Conectar a servidor
ssh user@server.com

# 2. Navegar a carpeta del proyecto
cd /opt/casa_monarca

# 3. Descargar cambios
git pull origin main

# 4. Instalar dependencias
pip install -r requirements.txt

# 5. Ejecutar migraciones BD (si aplica)
python -c "from database import create_tables; create_tables()"

# 6. Recopilar archivos estáticos (si aplica)
# flask collect-static

# 7. Detener servicio antiguo
systemctl stop casa_monarca

# 8. Iniciar servicio nuevo
systemctl start casa_monarca

# 9. Verificar estado
systemctl status casa_monarca

# 10. Ver logs
journalctl -u casa_monarca -f
```

**Opción B: Despliegue con zero-downtime (Blue-Green)**

```bash
#!/bin/bash
# scripts/deploy_blue_green.sh

set -e

BLUE_PORT=5000
GREEN_PORT=5001
NGINX_CONF="/etc/nginx/sites-available/casa_monarca"

echo "🚀 Blue-Green Deployment"

# 1. Detectar versión actual (BLUE o GREEN)
CURRENT_PORT=$(grep "proxy_pass" $NGINX_CONF | grep -oP 'localhost:\K\d+')
if [ "$CURRENT_PORT" = "$BLUE_PORT" ]; then
    DEPLOY_PORT=$GREEN_PORT
    NEXT_ENV="GREEN"
else
    DEPLOY_PORT=$BLUE_PORT
    NEXT_ENV="BLUE"
fi

echo "▶️  Versión actual: puerto $CURRENT_PORT"
echo "▶️  Desplegando en $NEXT_ENV (puerto $DEPLOY_PORT)"

# 2. Preparar entorno en puerto nuevo
cd /opt/casa_monarca

# 3. Actualizar código
git pull origin main

# 4. Instalar dependencias
pip install -r requirements.txt

# 5. Ejecutar tests en nuevo entorno
PYTHONPATH=. pytest -q

# 6. Iniciar aplicación en puerto nuevo
PORT=$DEPLOY_PORT python app.py &
DEPLOY_PID=$!

sleep 2

# 7. Verificar que nueva versión está online
if ! curl -f http://localhost:$DEPLOY_PORT/health; then
    echo "❌ Nueva versión no respondió"
    kill $DEPLOY_PID
    exit 1
fi

# 8. Cambiar nginx a nuevo puerto
sed -i "s/proxy_pass http:\/\/localhost:\d\+/proxy_pass http:\/\/localhost:$DEPLOY_PORT/" $NGINX_CONF
nginx -s reload

echo "✅ Tráfico movido a $NEXT_ENV (puerto $DEPLOY_PORT)"

# 9. Mantener versión antigua como rollback
echo "▶️  Versión anterior en puerto $CURRENT_PORT (disponible para rollback)"
```

**Ejecutar:**
```bash
chmod +x scripts/deploy_blue_green.sh
./scripts/deploy_blue_green.sh
```

#### 3. Despliegue con Docker

```bash
# 1. Construir imagen
docker build -t casa_monarca:latest .

# 2. Etiquetar para registro
docker tag casa_monarca:latest registry.example.com/casa_monarca:latest

# 3. Subir a registro
docker push registry.example.com/casa_monarca:latest

# 4. En servidor de despliegue, actualizar compose
docker compose pull
docker compose up -d

# 5. Ejecutar migraciones si aplica
docker compose exec web python -c "from database import create_tables; create_tables()"

# 6. Ver logs
docker compose logs -f web
```

**Dockerfile:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    openssl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Crear carpetas necesarias
RUN mkdir -p logs backups certs

# Usuario no-root por seguridad
RUN useradd -m -u 1000 casa_user
RUN chown -R casa_user:casa_user /app
USER casa_user

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/health')"

# Comando de inicio
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--worker-class", "sync", "--timeout", "30", "app:app"]
```

**docker-compose.yml:**
```yaml
version: '3.8'

services:
  web:
    image: casa_monarca:latest
    container_name: casa_monarca_web
    ports:
      - "5000:5000"
    environment:
      - FLASK_ENV=production
      - SECRET_KEY=${SECRET_KEY}
      - DATABASE_URL=sqlite:////app/data/database.db
      - LOG_LEVEL=INFO
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./certs:/app/certs
      - ./backups:/app/backups
    networks:
      - casa_monarca
    restart: unless-stopped
    depends_on:
      - db_backup

  nginx:
    image: nginx:alpine
    container_name: casa_monarca_nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs/ssl:/etc/nginx/certs:ro
    networks:
      - casa_monarca
    depends_on:
      - web
    restart: unless-stopped

  db_backup:
    image: casa_monarca:latest
    container_name: casa_monarca_backup
    command: python -c "from tools.backup_db import backup_database; backup_database()"
    environment:
      - DATABASE_URL=sqlite:////app/data/database.db
      - AES_KEY=${AES_KEY}
    volumes:
      - ./data:/app/data
      - ./backups:/app/backups
    networks:
      - casa_monarca
    restart: unless-stopped

networks:
  casa_monarca:
    driver: bridge
```

### Entornos

#### Desarrollo (Local)

**Archivo: `.env.development`**
```bash
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=dev-key-1234567890abcdefghijklmnopqrstuv
DATABASE_URL=sqlite:///database.db
LOG_LEVEL=DEBUG
TESTING=False

# Certificados (auto-generados)
CA_KEY=ca_dev.key
CA_CRT=ca_dev.crt
CA_PASSPHRASE=DevPass123!

# Encriptación
AES_KEY=dev-key-32-bytes-for-aes256enc
```

**Setup:**
```bash
# 1. Crear venv
python3 -m venv .venv
source .venv/bin/activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Generar certificados
python scripts/generate_certs.py --env dev

# 4. Generar clave AES
python generate_key.py

# 5. Inicializar BD
python -c "from database import create_tables; create_tables()"

# 6. Crear usuario admin
python -c "
from database import add_user
add_user('admin', 'AdminDev123!', 'admin')
print('Usuario admin creado')
"

# 7. Ejecutar aplicación
python app.py
```

**URL:** `http://localhost:5000`

**Credenciales de prueba:**
- Usuario: `admin`
- Contraseña: `AdminDev123!`

#### Staging (Pre-producción)

**Archivo: `.env.staging`**
```bash
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=staging-key-${RANDOM_256_BITS}
DATABASE_URL=sqlite:///data/database.db
LOG_LEVEL=INFO
TESTING=False

# Certificados (certificados reales o auto-firmados con validez extendida)
CA_KEY=ca_staging.key
CA_CRT=ca_staging.crt
CA_PASSPHRASE=${STAGING_CA_PASSPHRASE}

# Encriptación
AES_KEY=${STAGING_AES_KEY}

# HTTPS
HTTPS=True
SSL_CERT=/etc/ssl/certs/staging.crt
SSL_KEY=/etc/ssl/private/staging.key
```

**Servidor: staging.casa_monarca.local**

**Verificación:**
```bash
# Health check
curl -k https://staging.casa_monarca.local/health

# Acceso a login
curl -k https://staging.casa_monarca.local/login

# Tests contra staging
PYTHONPATH=. pytest tests/test_integration.py \
  --base-url=https://staging.casa_monarca.local \
  -v
```

#### Producción (Operacional)

**Archivo: `.env.production`** (NO commitear a git)
```bash
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=${PROD_SECRET_KEY}  # 256 bits random, mínimo
DATABASE_URL=sqlite:///data/database.db
LOG_LEVEL=WARNING
TESTING=False

# Certificados (certificados válidos emitidos por CA)
CA_KEY=${PROD_CA_KEY}
CA_CRT=${PROD_CA_CRT}
CA_PASSPHRASE=${PROD_CA_PASSPHRASE}

# Encriptación (debe ser igual al usado en backups anteriores)
AES_KEY=${PROD_AES_KEY}

# HTTPS obligatorio
HTTPS=True
SSL_CERT=/etc/ssl/certs/casa_monarca.crt
SSL_KEY=/etc/ssl/private/casa_monarca.key
HSTS_MAX_AGE=31536000  # 1 año

# Rate-limiting más estricto
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_DURATION=900  # 15 minutos
```

**Servidor: casa_monarca.institucion.mx**

**Requisitos:**
- ✅ HTTPS obligatorio (certificado válido de CA)
- ✅ Firewall restrictivo (solo puertos 80, 443)
- ✅ Servidor actualizado con parches de seguridad
- ✅ Contraseñas fuertes para .env (almacenar en secrets manager)
- ✅ Backups diarios encriptados
- ✅ Monitoreo 24/7

### Consideraciones

#### Seguridad

**1. Certificados HTTPS**
```bash
# Generar certificado auto-firmado (solo para testing)
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365

# Usar Let's Encrypt en producción
certbot certonly --standalone -d casa_monarca.institucion.mx
```

**2. Credenciales y secretos**
```bash
# NUNCA commitear .env a git
echo ".env*" >> .gitignore
echo "*.key" >> .gitignore
echo "*.pem" >> .gitignore

# Usar secrets manager
# AWS Secrets Manager, HashiCorp Vault, Azure Key Vault

# En GitHub Actions:
- name: Deploy
  env:
    SECRET_KEY: ${{ secrets.SECRET_KEY }}
    AES_KEY: ${{ secrets.AES_KEY }}
```

**3. Permisos de archivos**
```bash
# Proteger archivos sensibles en servidor
chmod 600 .env
chmod 600 ca.key
chmod 600 key.key
chown app:app .env ca.key key.key
```

**4. HTTPS + HSTS + Redirección**
```python
# app.py
from flask_talisman import Talisman

Talisman(app, 
    force_https=True,
    strict_transport_security=True,
    strict_transport_security_max_age=31536000)  # 1 año
```

#### Escalabilidad

**1. Base de datos SQLite (Limitación)**
- SQLite es single-writer (una transacción a la vez)
- Máx ~100-1000 conexiones simultáneas
- Ideal para: equipos pequeños, <50 usuarios concurrentes

**Plan para Etapa 2 (PostgreSQL):**
```bash
# Cambiar DATABASE_URL en producción
DATABASE_URL=postgresql://user:pass@db.server/casa_monarca

# Instalar adaptador
pip install psycopg2-binary

# Migrar datos
python scripts/migrate_sqlite_to_postgres.py
```

**2. Aplicación multi-worker**
```bash
# Usar Gunicorn con múltiples workers
gunicorn --bind 0.0.0.0:5000 --workers 4 --worker-class sync app:app

# En docker-compose:
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4"]
```

**3. Caché (Redis)**
```bash
# Opcional para Etapa 2
# Cachear sesiones, certificados, expedientes

pip install flask-caching redis

CACHE_TYPE=redis
CACHE_REDIS_URL=redis://localhost:6379/0
```

#### Disponibilidad

**1. Health check**
```python
# app.py
@app.route('/health')
def health():
    return {
        'status': 'ok',
        'version': '1.0.0',
        'timestamp': datetime.utcnow().isoformat()
    }, 200
```

**Verificación:**
```bash
curl http://localhost:5000/health
```

**2. Alertas y monitoreo**
```bash
# Monitorear logs en tiempo real
tail -f logs/error.log | grep -E "ERROR|CRITICAL"

# Contar errores por hora
grep "ERROR" logs/error.log | cut -d' ' -f1-2 | sort | uniq -c

# Alertar si >10 errores en 5 minutos
watch -n 60 'tail -300 logs/error.log | grep "ERROR" | wc -l'
```

**3. Rollback rápido**
```bash
# Mantener versión anterior
git tag -a v1.0.0-prod -m "Versión 1.0.0 en producción"
git push origin v1.0.0-prod

# Si hay problema, volver a versión anterior
git checkout v1.0.0-prod
python app.py  # Reiniciar
```

#### Mantenimiento

**1. Backups diarios**
```bash
# Programar con cron
0 2 * * * cd /opt/casa_monarca && python tools/backup_db.py

# Verificar que backup se crea
ls -lh backups/ | tail -1

# Listar backups
ls -1 backups/ | head -10
```

**2. Rotación de logs**
```bash
# Configurar en app.py (ya incluido)
# Logs rotan cada 10MB, máx 5 archivos

# Limpiar logs viejos (>30 días)
find logs/ -name "*.log.*" -mtime +30 -delete
```

**3. Verificación de integridad**
```bash
# Verificar que BD está OK
python -c "
import sqlite3
conn = sqlite3.connect('database.db')
conn.integrity_check()
print('✅ BD OK')
"

# Ejecutar tests en producción
PYTHONPATH=. pytest tests/test_security.py -v --tb=short
```

**4. Actualización de dependencias**
```bash
# Revisar si hay vulnerabilidades
pip install safety
safety check

# Actualizar dependencias menores
pip install --upgrade -r requirements.txt

# Generar nuevo requirements.txt
pip freeze > requirements.txt
```

#### Monitoreo y logging

**1. Agregar monitoreo en producción**
```python
# app.py - Agregar antes de run()

import logging
from logging.handlers import RotatingFileHandler

if not app.debug:
    if not os.path.exists('logs'):
        os.mkdir('logs')
    
    file_handler = RotatingFileHandler(
        'logs/casa_monarca.log',
        maxBytes=10240000,  # 10MB
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    
    app.logger.setLevel(logging.INFO)
    app.logger.info('Casa Monarca iniciado')
```

**2. Alertas automáticas**
```bash
# Enviar alerta si error rate > 5%
# Implementar en Etapa 2 con Datadog, New Relic, etc.

# Por ahora, revisar logs manualmente
tail -100 logs/error.log | grep -c ERROR
```

**3. Métricas clave**
- Tiempo de respuesta promedio
- Errores por hora
- Usuarios activos
- Expedientes procesados por día
- Certificados próximos a expirar

#### Desastre y recuperación

**1. Backup y restore**
```bash
# Crear backup manual
python tools/backup_db.py

# Restaurar desde backup
python tools/restore_db.py backups/db_backup_20260517T143022Z.enc

# Verificar restauración
python -c "
from database import get_all_users
users = get_all_users()
print(f'✅ Restaurados {len(users)} usuarios')
"
```

**2. Plan de recuperación ante desastre (DRP)**

| Escenario | RTO* | RPO** | Acción |
|-----------|------|-------|--------|
| BD corrupta | 1 hora | 24 horas | Restaurar último backup |
| Servidor caído | 30 min | 5 min | Failover a réplica (Etapa 2) |
| Ataque de seguridad | 2 horas | 1 hora | Restore + cambiar credenciales |
| Pérdida total de datos | 24 horas | 7 días | Restaurar de backup en cloud |

*RTO = Recovery Time Objective (tiempo para recuperar)
**RPO = Recovery Point Objective (datos máx que se pierden)

---

## Seguridad

### Autenticación

#### 1. Flujo de autenticación básica (Usuario + Contraseña)

**Paso a paso:**
```
Usuario                    Servidor
   |                            |
   |--- POST /login ---------->|
   |    {username, password}    |
   |                            |
   |                    [Validate password]
   |                    [Check rate-limit]
   |                    [Create session]
   |<--- 200 + Set-Cookie ------|
   |    (HttpOnly, SameSite, Secure)
   |                            |
   |--- GET /dashboard ------->|
   |    (Cookie enviada)        |
   |                    [Verify session]
   |<--- 200 + HTML ------------|
```

**Código en app.py:**
```python
@app.route('/login', methods=['POST'])
def login():
    """Autenticación básica: usuario + contraseña"""
    username = request.form.get('username')
    password = request.form.get('password')
    
    # 1. Validar entrada
    if not username or not password:
        return {'error': 'Usuario y contraseña requeridos'}, 400
    
    # 2. Verificar rate-limiting
    if check_login_attempts(username):
        return {'error': 'Usuario bloqueado por 15 minutos'}, 423
    
    # 3. Obtener usuario
    user = get_user(username)
    if not user:
        record_failed_attempt(username)
        return {'error': 'Usuario o contraseña incorrectos'}, 401
    
    # 4. Verificar contraseña (Argon2id)
    if not check_password_hash(user['password_hash'], password):
        record_failed_attempt(username)
        return {'error': 'Usuario o contraseña incorrectos'}, 401
    
    # 5. Limpiar intentos fallidos
    reset_login_attempts(username)
    
    # 6. Crear sesión
    session['user_id'] = user['id']
    session['username'] = username
    session['role'] = user['role']
    session['login_time'] = datetime.utcnow()
    
    # 7. Registrar en auditoría
    log_event('LOGIN', username, 'success')
    
    return {
        'status': 'success',
        'message': f'Bienvenido {username}',
        'role': user['role']
    }, 200
```

**Configuración de cookies (segura):**
```python
# app.py
app.config.update(
    SESSION_COOKIE_SECURE=True,        # Solo HTTPS
    SESSION_COOKIE_HTTPONLY=True,      # No accesible desde JS
    SESSION_COOKIE_SAMESITE='Strict',  # Previene CSRF
    PERMANENT_SESSION_LIFETIME=3600,   # 1 hora
)

@app.before_request
def make_session_permanent():
    """Hacer sesión permanente con tiempo de vida limitado"""
    session.permanent = True
```

#### 2. Flujo de autenticación reforzada (Challenge-Response con Certificados)

**Paso a paso:**
```
Usuario (con certificado)    Servidor
           |                     |
           |--- GET /challenge ->|
           |                     |
           |<-- challenge_uuid --|
           |                     |
           |[Sign con private key]
           |--- POST /login-cert --->|
           |    {username, cert_pem,  |
           |     challenge_uuid,      |
           |     signature}           |
           |                     |
           |            [Validate cert]
           |            [Verify signature]
           |            [Check expiration]
           |            [Verify challenge]
           |<--- 200 + session ---|
           |    (Certificado registrado)
```

**Código en app.py:**
```python
import uuid
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding

# 1. Generar desafío
@app.route('/challenge', methods=['GET'])
def get_challenge():
    """Generar desafío UUID para login reforzado"""
    challenge = str(uuid.uuid4())
    session['challenge'] = challenge
    session['challenge_time'] = datetime.utcnow()
    
    log_event('CHALLENGE_REQUESTED', session.get('username', 'unknown'), 'generated')
    
    return {
        'challenge': challenge,
        'purpose': 'login',
        'ttl': 300  # 5 minutos
    }, 200

# 2. Verificar certificado y firma
@app.route('/login-cert', methods=['POST'])
def login_certificate():
    """Autenticación reforzada con certificado y firma"""
    data = request.json
    username = data.get('username')
    cert_pem = data.get('certificate_pem')
    signature_b64 = data.get('signature')
    challenge = data.get('challenge')
    
    # 1. Validar desafío
    stored_challenge = session.get('challenge')
    challenge_time = session.get('challenge_time')
    
    if not stored_challenge or stored_challenge != challenge:
        return {'error': 'Desafío inválido'}, 401
    
    # 2. Validar TTL del desafío (5 minutos)
    if (datetime.utcnow() - challenge_time).seconds > 300:
        return {'error': 'Desafío expirado'}, 401
    
    # 3. Cargar certificado
    try:
        cert = x509.load_pem_x509_certificate(cert_pem.encode())
    except Exception as e:
        log_event('LOGIN_CERT', username, f'invalid_cert: {str(e)}')
        return {'error': 'Certificado inválido'}, 401
    
    # 4. Validar que certificado pertenece al usuario
    cert_subject = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
    if not cert_subject or cert_subject[0].value != username:
        log_event('LOGIN_CERT', username, 'cert_subject_mismatch')
        return {'error': 'Certificado no pertenece al usuario'}, 401
    
    # 5. Validar que certificado no está expirado
    if datetime.utcnow() > cert.not_valid_after_utc:
        log_event('LOGIN_CERT', username, 'cert_expired')
        return {'error': 'Certificado expirado'}, 401
    
    # 6. Validar que certificado está firmado por CA
    if not verify_ca_signature(cert):
        log_event('LOGIN_CERT', username, 'invalid_ca_signature')
        return {'error': 'Certificado no firmado por CA válida'}, 401
    
    # 7. Verificar firma del desafío
    payload = f"CasaMonarca|login|{username}|{challenge}".encode()
    signature = base64.b64decode(signature_b64)
    
    try:
        public_key = cert.public_key()
        public_key.verify(
            signature,
            payload,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
    except InvalidSignature:
        log_event('LOGIN_CERT', username, 'invalid_signature')
        return {'error': 'Firma inválida'}, 401
    
    # 8. Crear sesión
    user = get_user(username)
    session['user_id'] = user['id']
    session['username'] = username
    session['role'] = user['role']
    session['auth_method'] = 'certificate'
    session['cert_fingerprint'] = cert.fingerprint(hashes.SHA256()).hex()
    
    log_event('LOGIN_CERT', username, 'success')
    
    return {
        'status': 'success',
        'message': f'Autenticado con certificado: {username}',
        'role': user['role'],
        'cert_expiry': cert.not_valid_after_utc.isoformat()
    }, 200
```

#### 3. Rate-limiting y bloqueo de cuenta

**Implementación:**
```python
# database.py
def check_login_attempts(username, max_attempts=5, lockout_minutes=15):
    """
    Verificar si usuario está bloqueado por demasiados intentos fallidos.
    
    Args:
        username: Nombre de usuario
        max_attempts: Máximo de intentos permitidos (default: 5)
        lockout_minutes: Minutos de bloqueo (default: 15)
    
    Returns:
        bool: True si usuario está bloqueado, False si puede intentar
    """
    record = db.session.query(LoginAttempts).filter_by(username=username).first()
    
    if not record:
        return False
    
    # Si hay bloqueo y no ha expirado
    if record.locked_until:
        if datetime.utcnow() < record.locked_until:
            return True
        else:
            # Bloqueo expiró, resetear
            record.locked_until = None
            record.intentos = 0
            db.session.commit()
            return False
    
    # Si intentos >= max_attempts, bloquear
    if record.intentos >= max_attempts:
        record.locked_until = datetime.utcnow() + timedelta(minutes=lockout_minutes)
        db.session.commit()
        return True
    
    return False

def record_failed_attempt(username):
    """Registrar intento fallido de login"""
    record = db.session.query(LoginAttempts).filter_by(username=username).first()
    
    if not record:
        record = LoginAttempts(username=username, intentos=1)
    else:
        record.intentos += 1
    
    record.last_attempt = datetime.utcnow()
    db.session.add(record)
    db.session.commit()
    
    log_event('LOGIN_ATTEMPT_FAILED', username, f'intento {record.intentos}')

def reset_login_attempts(username):
    """Resetear intentos fallidos (login exitoso)"""
    record = db.session.query(LoginAttempts).filter_by(username=username).first()
    
    if record:
        record.intentos = 0
        record.locked_until = None
        db.session.commit()
```

### Manejo de datos sensibles

#### 1. Hashing de contraseñas (Argon2id)

**Configuración en app.py:**
```python
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError

# Configuración recomendada para Casa Monarca
ph = PasswordHasher(
    time_cost=3,           # Iteraciones
    memory_cost=65536,     # 64 MB
    parallelism=2,         # Threads
    hash_len=32,           # Bytes
    salt_len=16,           # Bytes
    type=Type.ID           # Argon2id (hybrid)
)

def hash_password(password):
    """
    Hashear contraseña con Argon2id.
    
    Argon2id es resistente a:
    - GPU attacks (memory-hard)
    - Side-channel attacks (Argon2id hybrid)
    - Rainbow tables (salt aleatorio)
    """
    if not password or len(password) < 8:
        raise ValueError("Contraseña debe tener mínimo 8 caracteres")
    
    return ph.hash(password)

def verify_password(hashed, password):
    """Verificar contraseña contra hash"""
    try:
        ph.verify(hashed, password)
        return True
    except (InvalidHash, VerifyMismatchError):
        return False
```

**Ejemplo de hash generado:**
```
$argon2id$v=19$m=65536,t=3,p=2$AbCdEfGhIjKlMnOp$1234567890abcdefghijklmnopqrstuv
 ^^^^^^    ^^^^^^    ^^^^ hash params         ^^^ salt (base64)    ^^ hash (base64)
```

#### 2. Encriptación de datos en tránsito (HTTPS + TLS 1.3)

**Configuración en app.py:**
```python
from flask_talisman import Talisman

# Forzar HTTPS en producción
Talisman(
    app,
    force_https=True,
    strict_transport_security=True,
    strict_transport_security_max_age=31536000,  # 1 año
    strict_transport_security_include_subdomains=True,
    content_security_policy={
        'default-src': "'self'",
        'script-src': "'self' 'unsafe-inline'",  # Revisar en producción
        'style-src': "'self' 'unsafe-inline'",
    }
)

# Redireccionar HTTP → HTTPS
@app.before_request
def redirect_to_https():
    if not request.is_secure and os.getenv('FLASK_ENV') == 'production':
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)
```

**Verificar TLS en cliente:**
```bash
# Verificar que servidor usa TLS 1.2+
openssl s_client -connect localhost:443 -tls1_2 << EOF
Q
EOF

# Verificar certificado
openssl x509 -in cert.pem -text -noout

# Verificar que es auto-firmado o de CA
openssl verify -CAfile ca.crt cert.pem
```

#### 3. Encriptación en reposo (AES-256-CBC)

**Para backups:**
```python
# tools/backup_db.py
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import os

def backup_database_encrypted():
    """Crear backup encriptado de la base de datos"""
    
    # 1. Leer BD
    with open('database.db', 'rb') as f:
        db_data = f.read()
    
    # 2. Cargar clave AES-256
    with open('key.key', 'rb') as f:
        key = f.read()  # 32 bytes para AES-256
    
    # 3. Generar IV aleatorio
    iv = os.urandom(16)
    
    # 4. Encriptar con AES-256-CBC
    cipher = Cipher(
        algorithms.AES(key),
        modes.CBC(iv),
        backend=default_backend()
    )
    encryptor = cipher.encryptor()
    
    # Padding PKCS7
    from cryptography.hazmat.primitives import padding as crypto_padding
    padder = crypto_padding.PKCS7(128).padder()
    padded_data = padder.update(db_data) + padder.finalize()
    
    encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
    
    # 5. Guardar: IV (16 bytes) + datos encriptados
    timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    backup_file = f'backups/db_backup_{timestamp}.enc'
    
    with open(backup_file, 'wb') as f:
        f.write(iv)
        f.write(encrypted_data)
    
    print(f"✅ Backup encriptado: {backup_file}")
    return backup_file

def restore_database_encrypted(backup_file):
    """Restaurar BD desde backup encriptado"""
    
    # 1. Cargar clave
    with open('key.key', 'rb') as f:
        key = f.read()
    
    # 2. Leer backup: IV + datos encriptados
    with open(backup_file, 'rb') as f:
        iv = f.read(16)
        encrypted_data = f.read()
    
    # 3. Desencriptar
    cipher = Cipher(
        algorithms.AES(key),
        modes.CBC(iv),
        backend=default_backend()
    )
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(encrypted_data) + decryptor.finalize()
    
    # Remover padding PKCS7
    unpadder = crypto_padding.PKCS7(128).unpadder()
    db_data = unpadder.update(padded_data) + unpadder.finalize()
    
    # 4. Restaurar BD
    with open('database.db', 'wb') as f:
        f.write(db_data)
    
    print(f"✅ BD restaurada desde {backup_file}")
```

#### 4. Gestión de claves y certificados

**Generar clave AES-256:**
```bash
# generate_key.py
python generate_key.py
# Genera key.key (32 bytes aleatorios en base64)
```

**Almacenamiento seguro:**
```bash
# Proteger archivos de claves
chmod 600 key.key
chmod 600 ca.key
chown app:app key.key ca.key

# Usar variables de entorno en producción
export AES_KEY=$(cat key.key)
export CA_PASSPHRASE="contraseña-fuerte"
```

**Rotación de claves (Etapa 2):**
```python
# scripts/rotate_aes_key.py
"""
Rotación de claves AES:
1. Generar nueva clave
2. Re-encriptar todos los backups con nueva clave
3. Actualizar clave en producción
4. Archivar clave anterior por 30 días
"""
```

#### 5. Certificados X.509

**Generación de CA:**
```bash
# scripts/generate_ca.py
openssl req -new -x509 -days 3650 -nodes \
  -out ca.crt -keyout ca.key \
  -subj "/CN=Casa Monarca CA/O=Institution/C=MX"

chmod 600 ca.key
```

**Generación de certificado de usuario:**
```bash
# scripts/generate_user_cert.py
openssl req -new -key user.key -out user.csr \
  -subj "/CN=username/O=Institution/C=MX"

openssl x509 -req -days 365 -in user.csr \
  -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out user.crt \
  -sha256

# Combinar en PEM
cat user.key user.crt > user.pem
```

### Buenas prácticas

#### 1. OWASP Top 10 - Mitigaciones

| Vulnerabilidad | Mitigación en Casa Monarca |
|----------------|---------------------------|
| **1. Injection** | Prepared statements (SQLAlchemy ORM), validación entrada |
| **2. Broken Authentication** | Argon2id, 2FA (certificados), rate-limiting |
| **3. Sensitive Data Exposure** | HTTPS + TLS 1.3, AES-256 en reposo, logs sin PII |
| **4. XML External Entities** | No procesar XML, usar JSON |
| **5. Broken Access Control** | RBAC decorators (@require_role), validación en cada endpoint |
| **6. Security Misconfiguration** | .env por ambiente, headers seguridad, logging centralizador |
| **7. XSS** | Jinja2 escapa HTML por defecto, CSP headers, sanitización input |
| **8. Insecure Deserialization** | No usar pickle, usar JSON, validar esquemas |
| **9. Using Components with Known Vulnerabilities** | Auditar requirements.txt, `pip audit`, updates |
| **10. Insufficient Logging** | Audit log para eventos críticos, alertas en errores |

#### 2. Inyección SQL - Prevención

**❌ VULNERABLE:**
```python
# NO HACER ESTO
query = f"SELECT * FROM usuarios WHERE username = '{username}'"
conn.execute(query)  # ¡SQL Injection!
```

**✅ SEGURO:**
```python
# HACER ESTO (SQLAlchemy ORM)
from database import Usuario

user = Usuario.query.filter_by(username=username).first()

# O con prepared statements
query = "SELECT * FROM usuarios WHERE username = ?"
user = conn.execute(query, (username,)).fetchone()
```

#### 3. CSRF Protection

**Implementación en Flask:**
```python
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect(app)

# En template HTML
<form method="POST" action="/expediente/crear">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
    <input type="text" name="titulo">
    <button type="submit">Crear</button>
</form>

# En Python (AJAX)
headers = {
    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
}
```

#### 4. XSS Prevention

**Jinja2 escapa por defecto:**
```html
<!-- Template: template.html -->
<h1>Usuario: {{ username }}</h1>  <!-- Automáticamente escapado -->

<!-- Si username = "<script>alert('XSS')</script>" -->
<!-- Se renderiza como: <h1>Usuario: &lt;script&gt;alert(&#39;XSS&#39;)&lt;/script&gt;</h1> -->
```

**CSP Headers:**
```python
@app.after_request
def set_security_headers(response):
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'"
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response
```

#### 5. Validación de entrada

```python
from wtforms import StringField, PasswordField
from wtforms.validators import Length, Email, Regexp

# Definir validadores
class CreateUserForm(FlaskForm):
    username = StringField('Username', [
        Length(min=3, max=20),
        Regexp(r'^[a-zA-Z0-9_]+$', message='Solo letras, números y _')
    ])
    
    email = StringField('Email', [
        Email()
    ])
    
    password = PasswordField('Password', [
        Length(min=8, max=128),
        Regexp(r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[@$!%*?&]).*$',
               message='Debe incluir mayúscula, minúscula, número y símbolo')
    ])

# En route
@app.route('/admin/crear-usuario', methods=['POST'])
@require_role('admin')
def crear_usuario():
    form = CreateUserForm()
    if not form.validate():
        return {'errors': form.errors}, 400
    
    # ... crear usuario ...
```

#### 6. Auditoría y logging

**Función de auditoría (app.py):**
```python
def log_event(event_type, username, details, severity='INFO'):
    """
    Registrar evento de seguridad para auditoría.
    
    Args:
        event_type: LOGIN, LOGIN_CERT, CREATE_USER, CERT_REVOKED, etc.
        username: Usuario que realizó la acción
        details: Detalles adicionales
        severity: INFO, WARNING, CRITICAL
    """
    
    timestamp = datetime.utcnow().isoformat()
    
    # Registrar en BD (tabla bitacora)
    event = AuditLog(
        timestamp=timestamp,
        event_type=event_type,
        username=username,
        details=details,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
        severity=severity
    )
    db.session.add(event)
    db.session.commit()
    
    # Registrar en archivo (rotated)
    logger.log(
        getattr(logging, severity),
        f"[{timestamp}] {event_type} | {username} | {details}"
    )
    
    # Alerta si CRITICAL
    if severity == 'CRITICAL':
        send_alert_email(
            subject=f"ALERTA SEGURIDAD: {event_type}",
            message=f"{username}: {details}"
        )
```

**Eventos críticos a auditar:**
```python
log_event('LOGIN', username, 'success')
log_event('LOGIN_FAILED', username, f'intento {count}', 'WARNING')
log_event('LOGIN_BLOCKED', username, f'bloqueado 15min', 'WARNING')

log_event('USER_CREATED', admin, f'creó usuario: {new_user}', 'INFO')
log_event('ROLE_CHANGED', admin, f'{user}: {old_role} → {new_role}', 'INFO')

log_event('CERT_ISSUED', username, f'CN={username}, exp={expiry}', 'INFO')
log_event('CERT_REVOKED', admin, f'revocó certificado de {username}', 'INFO')

log_event('EXPEDIENTE_CREATED', username, f'id={exp_id}', 'INFO')
log_event('EXPEDIENTE_SIGNED', admin, f'firmó id={exp_id}', 'INFO')

log_event('DB_BACKUP', 'system', f'archivo={backup_file}', 'INFO')
log_event('UNAUTHORIZED_ACCESS', username, f'intentó acceder a {endpoint}', 'CRITICAL')
```

#### 7. Secretos en variables de entorno

**❌ VULNERABLE (NO HACER):**
```python
SECRET_KEY = "my-super-secret-key-12345"  # En código fuente
AES_KEY = "abcdef123456789..."            # En código fuente
```

**✅ SEGURO:**
```bash
# .env (no commitear a git)
SECRET_KEY=<generar con 256 bits aleatorios>
AES_KEY=<cargar desde key.key>
CA_PASSPHRASE=<contraseña fuerte>
DATABASE_URL=sqlite:///data/database.db

# En .gitignore
.env
.env.*
*.key
*.pem
key.key
```

**Cargar en app.py:**
```python
import os
from dotenv import load_dotenv

load_dotenv()

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
AES_KEY = os.getenv('AES_KEY')
CA_PASSPHRASE = os.getenv('CA_PASSPHRASE')

# Validar que existen
for var in ['SECRET_KEY', 'AES_KEY', 'CA_PASSPHRASE']:
    if not os.getenv(var):
        raise ValueError(f"Variable de entorno {var} no configurada")
```

#### 8. Testing de seguridad

```bash
# Instalar herramientas
pip install bandit safety semgrep

# Análisis estático con Bandit
bandit -r . -ll  # Low level issues

# Chequear dependencias vulnerables
safety check

# Análisis de código con Semgrep
semgrep --config=p/security-audit .

# Test específico: verificar no hay secrets en código
git log -p | grep -i "secret\|password\|key" | head -5
```

**Test de penetración manual:**
```bash
#!/bin/bash
# tests/security_test.sh

echo "🔐 Security Test Suite"

# 1. Verificar HTTPS
echo "▶️  HTTPS enforcement..."
curl -I http://localhost:5000/dashboard | grep -q "301\|403" && echo "✅ HTTPS OK" || echo "❌ FAIL"

# 2. Verificar HSTS
echo "▶️  HSTS headers..."
curl -I https://localhost:5000/dashboard | grep -q "Strict-Transport-Security" && echo "✅ HSTS OK" || echo "❌ FAIL"

# 3. Verificar CSP
echo "▶️  CSP headers..."
curl -I https://localhost:5000/dashboard | grep -q "Content-Security-Policy" && echo "✅ CSP OK" || echo "❌ FAIL"

# 4. Verificar no hay información sensible en respuestas
echo "▶️  No version disclosure..."
curl -I https://localhost:5000/dashboard | grep -q "Server:" && echo "❌ Server header visible" || echo "✅ OK"

# 5. Verificar rate-limiting
echo "▶️  Rate-limiting on /login..."
for i in {1..6}; do
    curl -X POST https://localhost:5000/login \
        -d "username=test&password=wrong" -s -o /dev/null -w "%{http_code}\n"
done
```

#### 9. Deshabilitar features inseguras

```python
# app.py
app.config.update(
    DEBUG=False,                          # No debug en producción
    TESTING=False,                        # No modo testing
    PROPAGATE_EXCEPTIONS=False,           # No exponer stack traces
    PRESERVE_CONTEXT_ON_EXCEPTION=False,  # No logs detallados de excepciones
    JSON_SORT_KEYS=False,                 # No ordenar claves (timing attack)
)

# Deshabilitar endpoint de debug
@app.route('/debug')
def debug_info():
    if not app.debug:
        abort(404)
    return {...}
```

#### 10. Validación de certificados en cliente

```python
# tests/test_certificate_validation.py
import pytest
from datetime import datetime, timedelta
from cryptography import x509

def test_expired_certificate_rejected():
    """Test que certificado expirado es rechazado"""
    # Crear certificado con expiración pasada
    old_cert = create_cert_with_expiry(
        datetime.utcnow() - timedelta(days=1)
    )
    
    response = client.post('/login-cert', json={
        'username': 'user',
        'certificate_pem': old_cert,
        'challenge': 'test-challenge',
        'signature': 'fake-signature'
    })
    
    assert response.status_code == 401
    assert 'expirado' in response.json['error'].lower()

def test_certificate_wrong_ca_rejected():
    """Test que certificado de CA diferente es rechazado"""
    # Crear certificado firmado por CA diferente
    wrong_ca_cert = create_cert_from_different_ca('user')
    
    response = client.post('/login-cert', json={
        'username': 'user',
        'certificate_pem': wrong_ca_cert,
        'challenge': 'test-challenge',
        'signature': 'fake-signature'
    })
    
    assert response.status_code == 401
    assert 'CA' in response.json['error']

def test_signature_tampered_rejected():
    """Test que firma tamper es rechazada"""
    response = client.post('/login-cert', json={
        'username': 'user',
        'certificate_pem': valid_cert_pem,
        'challenge': 'valid-challenge',
        'signature': 'TAMPERED_SIGNATURE_BASE64'
    })
    
    assert response.status_code == 401
    assert 'Firma inválida' in response.json['error']
```

---

## Guía de Contribución

### Convenciones de código

**Python (PEP 8)**
```python
# ✅ Nombres descriptivos
def verify_certificate_signature(cert_pem, signature):
    """Verificar que firma de certificado es válida."""
    pass

# ✅ Máximo 79 caracteres por línea
long_variable_name = some_function(
    parameter1, parameter2, parameter3
)

# ✅ Docstrings en todas las funciones
def add_user(username, password, role):
    """
    Crear nuevo usuario en la BD.
    
    Args:
        username: Nombre único de usuario (3-20 caracteres)
        password: Contraseña sin hashear (mínimo 8 caracteres)
        role: usuario, operativo, coordinador, admin
    
    Returns:
        dict: {'id': int, 'username': str, 'created_at': str}
    
    Raises:
        ValueError: Si usuario ya existe o parámetros inválidos
        DatabaseError: Si falla inserción en BD
    """
    pass

# ✅ Type hints (Python 3.10+)
def get_user(user_id: int) -> dict | None:
    """Obtener usuario por ID"""
    pass

# ❌ Evitar
x = some_func(a, b)  # Nombres no descriptivos
def f():  # Sin docstring
    return 1
```

**JavaScript/HTML**
```html
<!-- ✅ IDs descriptivos, clases en snake_case -->
<input id="login_username" class="form_field" type="text">

<!-- ✅ Comentarios en secciones importantes -->
<!-- Formulario de autenticación reforzada -->
<form id="login_cert_form">
    <input type="text" name="username">
</form>
```

**SQL**
```sql
-- ✅ Keywords en MAYÚSCULA, tablas/columnas en snake_case
SELECT id, username, created_at 
FROM usuarios 
WHERE role = 'admin' AND is_active = true
ORDER BY created_at DESC;

-- ❌ Evitar
select * from usuarios where username='test'
```

### Flujo de trabajo (Git)

**1. Crear rama para feature**
```bash
git checkout -b feature/agregar-2fa
# O bugfix
git checkout -b bugfix/corregir-rate-limiting
```

**2. Hacer cambios y commits atómicos**
```bash
# Cambio 1: agregar función de verificación
git add app.py
git commit -m "feat: add 2fa verification function"

# Cambio 2: agregar tests
git add tests/
git commit -m "test: add tests for 2fa verification"

# Formato de commit: type(scope): short description
# Types: feat, fix, test, docs, refactor, security
# Scope: app, database, auth, api, etc.
```

**3. Push y crear Pull Request**
```bash
git push origin feature/agregar-2fa

# En GitHub: crear PR con descripción:
# - Qué se agregó
# - Por qué
# - Testing realizado
```

**4. Code Review y merge**
```bash
# Después de aprobación:
git checkout main
git pull origin main
git merge --no-ff feature/agregar-2fa
git push origin main

# Eliminar rama
git branch -d feature/agregar-2fa
git push origin -d feature/agregar-2fa
```

**Convenciones de commit:**
```
feat: agregar soporte para 2FA
fix: corregir bug en rate-limiting
test: agregar tests para login
docs: actualizar README
refactor: simplificar lógica de autenticación
security: mejorar validación de entrada
chore: actualizar dependencias
```

### Cómo agregar funcionalidades

**Ejemplo: Agregar endpoint para cambiar contraseña**

**Paso 1: Planificar**
```
Requirement:
- Endpoint: POST /profile/change-password
- Input: usuario + contraseña actual + contraseña nueva
- Output: 200 OK o 401/400 error
- Seguridad: HTTPS, validar sesión, rate-limiting
- Testing: test login antiguo falla, test login nuevo funciona
```

**Paso 2: Implementar BD**
```python
# database.py - agregar función
def update_user_password(user_id: int, new_password: str) -> bool:
    """Actualizar contraseña del usuario"""
    from argon2 import PasswordHasher
    
    user = Usuario.query.get(user_id)
    if not user:
        raise ValueError(f"Usuario {user_id} no existe")
    
    # Hash nueva contraseña
    ph = PasswordHasher()
    user.password_hash = ph.hash(new_password)
    user.password_updated = datetime.utcnow()
    
    db.session.commit()
    log_event('PASSWORD_CHANGED', user.username, 'success')
    
    return True
```

**Paso 3: Implementar endpoint**
```python
# app.py
@app.route('/profile/change-password', methods=['POST'])
@require_login
def change_password():
    """Cambiar contraseña del usuario autenticado"""
    data = request.json
    
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    
    # Validar entrada
    if not old_password or not new_password:
        return {'error': 'Contraseña actual y nueva requeridas'}, 400
    
    if len(new_password) < 8:
        return {'error': 'Contraseña debe tener mínimo 8 caracteres'}, 400
    
    # Obtener usuario
    user = get_user(session['username'])
    
    # Verificar contraseña actual
    if not verify_password(user['password_hash'], old_password):
        log_event('PASSWORD_CHANGE_FAILED', session['username'], 'wrong_old_password')
        return {'error': 'Contraseña actual incorrecta'}, 401
    
    # Actualizar contraseña
    try:
        update_user_password(user['id'], new_password)
        return {'status': 'success', 'message': 'Contraseña actualizada'}, 200
    except Exception as e:
        log_event('PASSWORD_CHANGE_ERROR', session['username'], str(e), 'CRITICAL')
        return {'error': 'Error al actualizar contraseña'}, 500
```

**Paso 4: Agregar tests**
```python
# tests/test_change_password.py
import pytest

def test_change_password_success(client, auth_session):
    """Test cambio de contraseña exitoso"""
    response = client.post('/profile/change-password', json={
        'old_password': 'OldPass123!',
        'new_password': 'NewPass456!'
    })
    
    assert response.status_code == 200
    assert response.json['status'] == 'success'
    
    # Verificar que login antiguo ya no funciona
    logout_response = client.get('/logout')
    assert logout_response.status_code == 200
    
    login_old = client.post('/login', data={
        'username': 'testuser',
        'password': 'OldPass123!'
    })
    assert login_old.status_code == 401
    
    # Verificar que login nuevo funciona
    login_new = client.post('/login', data={
        'username': 'testuser',
        'password': 'NewPass456!'
    })
    assert login_new.status_code == 200

def test_change_password_wrong_old(client, auth_session):
    """Test cambio con contraseña anterior incorrecta"""
    response = client.post('/profile/change-password', json={
        'old_password': 'WrongPass123!',
        'new_password': 'NewPass456!'
    })
    
    assert response.status_code == 401
    assert 'incorrecta' in response.json['error'].lower()

def test_change_password_weak_new(client, auth_session):
    """Test rechazo de contraseña nueva débil"""
    response = client.post('/profile/change-password', json={
        'old_password': 'OldPass123!',
        'new_password': '123456'
    })
    
    assert response.status_code == 400
    assert 'mínimo' in response.json['error'].lower()

def test_change_password_unauthenticated(client):
    """Test que usuario no autenticado no puede cambiar"""
    response = client.post('/profile/change-password', json={
        'old_password': 'Pass123!',
        'new_password': 'NewPass456!'
    })
    
    assert response.status_code == 401
```

**Paso 5: Agregar en frontend (si aplica)**
```html
<!-- templates/profile.html -->
<h2>Cambiar Contraseña</h2>
<form id="change_password_form">
    <input type="password" name="old_password" placeholder="Contraseña actual" required>
    <input type="password" name="new_password" placeholder="Contraseña nueva" required>
    <button type="submit">Cambiar</button>
</form>

<script>
document.getElementById('change_password_form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const data = {
        old_password: e.target.old_password.value,
        new_password: e.target.new_password.value
    };
    
    const response = await fetch('/profile/change-password', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });
    
    const result = await response.json();
    
    if (response.ok) {
        alert(result.message);
        e.target.reset();
    } else {
        alert('Error: ' + result.error);
    }
});
</script>
```

**Paso 6: Commit y PR**
```bash
git checkout -b feature/change-password

git add database.py app.py tests/test_change_password.py templates/profile.html
git commit -m "feat: add endpoint to change user password"

git push origin feature/change-password

# Crear PR en GitHub con descripción:
# - Permite a usuarios cambiar su contraseña
# - Validación: contraseña actual correcta, nueva >= 8 caracteres
# - Tests: 4 cases (success, wrong old, weak new, unauthenticated)
# - Security: Argon2id hash, auditoría de cambios
```

**Checklist antes de hacer PR:**
- ✅ Tests nuevos pasan: `PYTHONPATH=. pytest tests/test_change_password.py -v`
- ✅ Tests existentes no fallan: `PYTHONPATH=. pytest -v`
- ✅ Código sigue PEP 8: `pylint app.py` o `black --check app.py`
- ✅ Sin hardcoded secrets
- ✅ Docstrings completos
- ✅ Commits atómicos con mensajes claros
- ✅ Rama actualizada con main: `git pull origin main`

---

## Problemas Conocidos

### Bugs actuales
❌ N/A — Primera versión (1.0.0), sin bugs reportados en testing.

### Limitaciones

#### 1. Base de datos SQLite (HostGator)
- ❌ Single-writer: máx 1 transacción simultánea
- ❌ No soporta >100-1000 conexiones concurrentes
- ❌ No escalable horizontalmente
- ✅ Solución Etapa 2: Migrar a PostgreSQL

#### 2. Almacenamiento en HostGator
- ❌ Límite de espacio en disco (revisar plan)
- ❌ Backups manuales en carpeta (backups/)
- ✅ Solución: Implementar backup automático a S3 (Etapa 2)

#### 3. Certificados auto-firmados
- ❌ Navegadores muestran advertencia de seguridad
- ❌ No válidos para producción real
- ✅ Solución: Usar Let's Encrypt o CA institucional en Etapa 2

#### 4. Sin caché distribuida
- ❌ Cada servidor tiene caché local
- ❌ No hay sesiones compartidas en multi-servidor
- ✅ Solución: Implementar Redis (Etapa 2)

#### 5. Sin autoscaling
- ❌ HostGator no permite load balancing automático
- ❌ Escalabilidad manual (cambiar plan)
- ✅ Solución: Considerar migración a cloud (Etapa 2)

#### 6. Logs locales
- ❌ Logs solo en servidor (sin centralización)
- ❌ Difícil monitoreo multi-servidor
- ✅ Solución: ELK Stack o Datadog (Etapa 2)

#### 7. Sin 2FA (aún)
- ❌ Autenticación solo básica + certificados
- ✅ Solución: Agregar TOTP (Etapa 2)

---

## FAQ Técnica

### Q1: ¿Cómo levantar el proyecto en local?

**A:** 
```bash
# 1. Clonar
git clone <repo>
cd Intentoa2

# 2. Crear venv
python3 -m venv .venv
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Generar claves
python generate_key.py

# 5. Crear BD
python -c "from database import create_tables; create_tables()"

# 6. Crear usuario admin
python -c "from database import add_user; add_user('admin', 'AdminDev123!', 'admin')"

# 7. Ejecutar
python app.py
```

### Q2: Error "ModuleNotFoundError: No module named 'database'"

**A:** Falta PYTHONPATH
```bash
# Antes de ejecutar tests:
export PYTHONPATH=.
pytest tests/ -v

# O en un comando:
PYTHONPATH=. python app.py
```

### Q3: Error "database.db no existe"

**A:** Crear tablas
```bash
python -c "from database import create_tables; create_tables()"
```

### Q4: Error en certificados "ca.key o ca.crt no encontrados"

**A:** Generar certificados
```bash
python scripts/generate_certs.py --env dev
```

### Q5: ¿Cómo resetear la contraseña de un usuario?

**A:** 
```python
# En terminal Python
from database import update_user_password
update_user_password(user_id=1, new_password='NewPass123!')
```

### Q6: Tests fallan con "sqlite3.OperationalError: database is locked"

**A:** Cerrar todas las instancias de app
```bash
# Matar procesos Python
pkill -f "python app.py"
pkill -f "pytest"

# Luego ejecutar tests
PYTHONPATH=. pytest -v
```

### Q7: ¿Cómo ver logs en tiempo real?

**A:**
```bash
# Error logs
tail -f logs/error.log

# Info logs
tail -f logs/app.log | grep INFO

# Ver últimas 50 líneas
tail -50 logs/error.log

# Buscar errores específicos
grep "ERROR\|CRITICAL" logs/error.log
```

### Q8: Error "key.key not found" en backups

**A:** Generar clave AES
```bash
python generate_key.py
```

### Q9: ¿Cómo ejecutar un test específico?

**A:**
```bash
# Test específico
PYTHONPATH=. pytest tests/test_password_security.py::test_weak_password_rejected -v

# Tests que coincidan con patrón
PYTHONPATH=. pytest -k "login" -v

# Tests lentos (si tienen marker @pytest.mark.slow)
PYTHONPATH=. pytest -m "slow" -v
```

### Q10: ¿Cómo cambiar puerto (no es 5000)?

**A:** En `app.py`, última línea:
```python
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
```

O en terminal:
```bash
python -c "import app; app.app.run(port=8080)"
```

### Q11: Error "Address already in use" en puerto 5000

**A:** Encontrar y matar proceso
```bash
# Encontrar PID usando puerto 5000
lsof -i :5000

# Matar proceso
kill -9 <PID>

# O usar otro puerto
python app.py --port 8080
```

### Q12: ¿Cómo cambiar la BD a otro nombre?

**A:** En `app.py` o `.env`:
```python
DATABASE_URL = 'sqlite:///mi_base_datos.db'

# Luego crear tablas
python -c "from database import create_tables; create_tables()"
```

### Q13: Error "certificate verify failed" en HTTPS local

**A:** Certificado auto-firmado en desarrollo, es normal. Para ignorar:
```bash
# Python requests
import requests
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
response = requests.get('https://localhost:5000', verify=False)

# curl
curl -k https://localhost:5000/health
```

### Q14: ¿Cómo hacer backup de la BD?

**A:**
```bash
# Backup encriptado
python tools/backup_db.py

# Ver backups creados
ls -lh backups/

# Restaurar desde backup
python tools/restore_db.py backups/db_backup_20260517T143022Z.enc
```

### Q15: Tests de cobertura muy bajos

**A:** Generar reporte HTML
```bash
PYTHONPATH=. pytest --cov=. --cov-report=html

# Abrir reporte
open htmlcov/index.html
```

---
