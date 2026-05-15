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
- Se generan/actualizan certificados X.509 de desarrollo para `admin_prod`, `admin_cont` y `coord_admin` en la carpeta [certs](certs), y se limpian los artefactos legacy.
- Las llaves demo para firmar challenges quedan en `admin_prod_demo.key`, `admin_cont_demo.key` y `coord_admin_demo.key`.

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

## Mejoras de PKI aplicadas (Sprint 2)
Se incorporo una CA interna del proyecto para emitir certificados X.509 de los roles criticos.

- Emision: `admin` y `coordinador` generan un certificado X.509 firmado por la CA local y empaquetado junto con la llave privada cifrada en el mismo archivo `.pem`.
- Validacion: al iniciar sesion y al ejecutar acciones criticas, la app verifica firma de CA, vigencia, huella del certificado, correspondencia con el usuario y estado activo.
- Revocacion: el panel de usuarios permite revocar certificados activos con un motivo obligatorio; la revocacion queda auditada en la tabla `certificados` y en la bitacora.
- Custodia: la CA del proyecto se crea automaticamente en `certs/ca_cert.pem` y `certs/ca_key.pem` la primera vez que se emite un certificado.
- Flujo operativo: si un certificado se revoca o expira, el usuario debe reemitirlo desde `certificado/setup`.

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
- `admin_prod / AdminProdX2026!` (requiere [certs/admin_prod.pem](certs/admin_prod.pem))
- `admin_cont / AdminContX2026!` (requiere [certs/admin_cont.pem](certs/admin_cont.pem))
- `coord_admin / CoordAdminX2026!` (requiere [certs/coord_admin.pem](certs/coord_admin.pem))
- `operativo_1 / Operativo_2026!`
 - `usuario_1 / Usuario_2026!X`

4. Login de cuentas sensibles con challenge-response:
- El formulario de acceso pedira usuario, contrasena, certificado X.509 y firma del desafio.
- Primero abre el login y copia el valor del campo `Desafio a firmar`.
- Firma ese valor con la llave privada local asociada a la cuenta.
- Enviar la firma en Base64 o como archivo binario y luego seleccionar el certificado X.509 correspondiente.
- En macOS, la firma puede generarse con este flujo:

```bash
payload='CasaMonarca|login|admin_cont|<CHALLENGE>'
printf '%s' "$payload" > /tmp/cm_login_payload.txt
openssl dgst -sha256 -sign admin_cont_demo.key -passin pass:AdminContX2026! -out /tmp/cm_login.sig /tmp/cm_login_payload.txt
base64 -i /tmp/cm_login.sig | tr -d '\n'
```

- Sustituye `admin_cont` y `admin_cont_demo.key` por `admin_prod` o `coord_admin` cuando corresponda.
- La contraseña que debe ingresarse en el login es la de la cuenta semilla, no la passphrase de la llave demo.

### Creación de nuevo usuario Admin con certificado (flujo completo)

Para crear un nuevo usuario con rol Admin o Coordinador, debe hacerlo un admin existente autorizado con su certificado y firma. El proceso es:

**Paso 1: Login del admin existente**
Acceda como admin autorizado (ej: `admin_prod`) usando el flujo de challenge-response descrito arriba.

**Paso 2: Navegar a Gestion de usuarios**
Una vez logueado, haga clic en **Usuarios** → **Crear usuario**.

**Paso 3: Rellenar formulario y firmar**
El formulario requiere:
- **Usuario**: nombre único (ej: `nuevo_admin`)
- **Contraseña**: contraseña fuerte (ej: `NuevoAdminX2026!`)
- **Rol**: seleccionar `Administrador (CRUD)` o `Coordinador (CRU)`
- **Certificado del admin para firmar**: cargar el `.pem` del admin actual (ej: `certs/admin_prod.pem`)
- **Firma del desafío**: **IMPORTANTE** – aquí cambia respecto al login

**⚠️ DIFERENCIA CLAVE EN LA FIRMA**

A diferencia del login, la firma para crear un usuario debe usar el propósito `"creacion de usuario"` en lugar de `"login"`.

**Comando incorrecto (para login):**
```bash
payload='CasaMonarca|login|admin_prod|<CHALLENGE>'
```

**Comando correcto (para crear usuario):**
```bash
payload='CasaMonarca|creacion de usuario|admin_prod|<CHALLENGE>'
printf '%s' "$payload" | openssl dgst -sha256 -sign admin_prod_demo.key -passin pass:AdminProdX2026! | base64 | tr -d '\n'
```

Note que:
- El propósito cambió de `login` a `creacion de usuario`
- La contraseña de la llave demo es `AdminProdX2026!` (para `admin_prod`), `AdminContX2026!` (para `admin_cont`), etc.
- Copie el resultado Base64 en el campo **Firma Base64** del formulario

**Paso 4: Crear usuario**
Haga clic en **Guardar usuario**. El sistema:
- Verifica la firma del certificado admin
- Crea el nuevo usuario con estado `must_change_password=1`
- Crea un certificado **pendiente** asociado

**Paso 5: Primer login del nuevo usuario**
El nuevo usuario intenta loguear:
- Usuario: `nuevo_admin`
- Contraseña: `NuevoAdminX2026!` (la que seleccionó en Paso 3)
- **Sin certificado** (aún pendiente)

El sistema detecta que es admin sin certificado activo y redirige a **Actualizar contraseña** (porque es nuevo).

**Paso 6: Cambio obligatorio de contraseña**
El nuevo usuario debe actualizar su contraseña (mismo formato fuerte). Ejemplo:
- Contraseña actual: `NuevoAdminX2026!`
- Nueva contraseña: `NuevoAdminX2026UpdatedV2!`
- Confirmar: `NuevoAdminX2026UpdatedV2!`

**Paso 7: Configuración de certificado**
Tras actualizar contraseña, redirige a **Configurar certificado** (`/certificado/setup`).
Elija modo:
- **Modo legacy (passphrase)**: ingrese una passphrase (ej: `CertSetupPass2026!`), confirme, y haga clic **Generar certificado**.
- **Modo moderno (CSR)**: si tiene una CSR generada localmente, péguala o cargue el archivo.

El sistema genera/firma el certificado y redirige al dashboard.

### Setup de certificado por CSR (flujo recomendado y detallado)

Esta es la forma recomendada para cuentas nuevas (`admin`/`coordinador`) porque la clave privada se genera y queda solo en el equipo del usuario.

**Objetivo de seguridad**
- El servidor recibe solo la CSR (clave publica + metadatos firmados).
- La clave privada **no** viaja al servidor.
- Se evita exponer la privada en archivos del sistema, backups o logs del servidor.

**Campos esperados por el backend**
- `CN` (Common Name): debe ser exactamente el `username`.
- `OU` (Organizational Unit): debe coincidir con el rol interno:
	- `admin`
	- `coordinador`

Si no coinciden, la app rechazara la CSR.

**Paso A: Generar clave privada local (usuario final)**

```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -aes-256-cbc -out coord_csr_demo.key.pem
```

- Este comando pedira una passphrase local para proteger la clave privada.
- Esa passphrase la conoce solo el usuario.

**Paso B: Generar CSR con esa clave**

```bash
openssl req -new -key coord_csr_demo.key.pem -out coord_csr_demo.csr.pem -sha256 -subj "/C=MX/O=Casa Monarca/OU=coordinador/CN=coord_csr_demo"
```

Ejemplos:
- Para admin: `OU=admin`
- Para coordinador: `OU=coordinador`

**Paso C: Verificar CSR antes de subirla**

```bash
openssl req -in coord_csr_demo.csr.pem -noout -text
```

Validar visualmente:
- Subject contiene `CN=coord_csr_demo`
- Subject contiene `OU=coordinador`
- Algoritmo y clave son correctos

**Paso D: Cargar CSR en la pantalla de setup**

En `/certificado/setup`:
- Opción 1: pegar el texto PEM en **"CSR PEM o texto de la solicitud"**
- Opción 2: subir **Archivo CSR** (`.csr` o `.pem`)

Luego presionar **Generar certificado**.

**Resultado esperado**
- El servidor firma la clave publica de la CSR.
- El usuario recibe el certificado emitido (`.crt`/`.pem`).
- La clave privada sigue local en `coord_csr_demo.key.pem`.

**Paso E: Login challenge-response usando la clave local**

En login:
1. Copiar `Desafio a firmar`
2. Firmar con la clave privada local
3. Enviar firma (Base64 o binaria) + certificado emitido

Ejemplo (macOS/Linux):

```bash
payload='CasaMonarca|login|coord_csr_demo|<CHALLENGE>'
printf '%s' "$payload" | openssl dgst -sha256 -sign coord_csr_demo.key.pem -out /tmp/coord_login.sig
base64 -i /tmp/coord_login.sig | tr -d '\n'
```

Notas:
- Si la clave privada fue cifrada, OpenSSL pedira la passphrase local.
- Puedes subir `/tmp/coord_login.sig` como archivo binario en lugar de pegar Base64.

**Checklist rapido para presentaciones/demo**
- [ ] Usuario nuevo creado por admin con firma de accion
- [ ] Usuario cambia contraseña obligatoria
- [ ] Usuario genera clave privada local
- [ ] Usuario genera CSR con `CN`/`OU` correctos
- [ ] Usuario carga CSR en `/certificado/setup`
- [ ] Certificado emitido y descargado
- [ ] Login exitoso con challenge-response y firma local

**Qué NO hacer**
- No compartir la clave privada por chat/correo.
- No almacenar la privada en el servidor.
- No reutilizar passphrases débiles o compartidas.

**Paso 8: Login con certificado (challenge-response)**
El nuevo usuario accede con el flujo completo:
- Usuario: `nuevo_admin`
- Contraseña: `NuevoAdminX2026UpdatedV2!` (la nueva)
- Certificado: `certs/nuevo_admin.pem` (recién generado)
- Firma del desafío: **aquí es `login` de nuevo**

```bash
# COMANDO PARA LOGIN (propósito: login)
payload='CasaMonarca|login|nuevo_admin|<CHALLENGE>'
printf '%s' "$payload" | openssl dgst -sha256 -sign nuevo_admin.key.pem | base64 | tr -d '\n'
```

Si usas una clave demo legacy cifrada, agrega `-passin pass:<PASSPHRASE>` al comando de firma.

**Resumen de propósitos por operación**

| Operación | Propósito | Ejemplo de payload |
|-----------|-----------|-------------------|
| Login | `login` | `CasaMonarca\|login\|nuevo_admin\|{CHALLENGE}` |
| Crear usuario | `creacion de usuario` | `CasaMonarca\|creacion de usuario\|admin_prod\|{CHALLENGE}` |
| Otras acciones admin | `{descripcion_accion}` | `CasaMonarca\|{descripcion}\|{username}\|{CHALLENGE}` |

5. Ejemplo breve de flujo completo:
- Abrir el login, copiar el desafio, firmarlo, seleccionar el certificado X.509 y entrar.
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
