# Manual de Usuario (Borrador)

Este documento recoge los pasos operativos para usuarios finales: login, creación de cuentas administrativas, setup de certificados y uso básico.

## Uso básico

1. **Activar entorno:**
```bash
source .venv/bin/activate
```

2. **Ejecutar la aplicación:**
```bash
.venv/bin/python app.py
```

3. **Abrir en navegador:** `http://127.0.0.1:5000`

## Cuentas de prueba

- `admin_prod / AdminProdX2026!` (requiere certificado)
- `admin_cont / AdminContX2026!` (requiere certificado)
- `coord_admin / CoordAdminX2026!` (requiere certificado)
- `operativo_1 / Operativo_2026!`
- `usuario_1 / Usuario_2026!X`

## Login con challenge-response

**Para roles que requieren certificado (admin, coordinador):**

1. Abrir formulario de login y copiar el campo "Desafío a firmar".
2. Construir el payload: `CasaMonarca|login|<username>|<CHALLENGE>`.
3. Firmar con la clave privada local y enviar la firma (Base64 o binario) junto con el certificado `.pem`.

**Ejemplo (macOS/Linux):**

```bash
payload='CasaMonarca|login|admin_cont|<CHALLENGE>'
printf '%s' "$payload" | openssl dgst -sha256 -sign admin_cont_demo.key -passin pass:AdminContX2026! -out /tmp/cm_login.sig
base64 -i /tmp/cm_login.sig | tr -d '\n'
```

Copiar el resultado Base64 en el formulario, seleccionar el certificado y enviar.

## Crear usuario Admin/Coordinador (flujo completo)

**Paso 1: Login del admin existente**

Autenticarse como admin autorizado (ej: `admin_prod`) usando challenge-response.

**Paso 2: Navegar a Gestión de usuarios**

Haga clic en **Usuarios** → **Crear usuario**.

**Paso 3: Rellenar formulario**

- **Usuario:** nombre único (ej: `nuevo_admin`)
- **Contraseña:** contraseña fuerte (ej: `NuevoAdminX2026!`)
- **Rol:** seleccionar `Administrador (CRUD)` o `Coordinador (CRU)`
- **Certificado del admin para firmar:** cargar el `.pem` del admin actual (ej: `certs/admin_prod.pem`)
- **Firma del desafío:** generar con propósito `creacion de usuario`

**⚠️ DIFERENCIA CLAVE: Propósito de firma**

Para crear usuario, el propósito es `creacion de usuario` (diferente al login):

```bash
payload='CasaMonarca|creacion de usuario|admin_prod|<CHALLENGE>'
printf '%s' "$payload" | openssl dgst -sha256 -sign admin_prod_demo.key -passin pass:AdminProdX2026! | base64 | tr -d '\n'
```

**Paso 4: Crear usuario**

Haga clic en **Guardar usuario**. El sistema verifica la firma y crea el usuario con estado `must_change_password=1`.

**Paso 5: Primer login del nuevo usuario**

El nuevo usuario intenta loguear sin certificado (aún pendiente). El sistema lo redirige a **Actualizar contraseña** (cambio obligatorio).

**Paso 6: Cambio obligatorio de contraseña**

- Contraseña actual: `NuevoAdminX2026!`
- Nueva contraseña: `NuevoAdminX2026UpdatedV2!`
- Confirmar: `NuevoAdminX2026UpdatedV2!`

**Paso 7: Configuración de certificado**

Tras actualizar contraseña, redirige a **Configurar certificado** (`/certificado/setup`).

Opciones:
- **Modo legacy (passphrase):** ingrese una passphrase, confirme, y haga clic **Generar certificado**.
- **Modo moderno (CSR):** cargue una CSR generada localmente (recomendado).

## Setup de certificado por CSR (recomendado)

Esta es la forma más segura porque la clave privada se genera y queda solo en el equipo del usuario.

**Paso A: Generar clave privada local**

```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -aes-256-cbc -out coord_csr_demo.key.pem
```

Se pedirá una passphrase local para proteger la clave.

**Paso B: Generar CSR con esa clave**

```bash
openssl req -new -key coord_csr_demo.key.pem -out coord_csr_demo.csr.pem -sha256 \
  -subj "/C=MX/O=Casa Monarca/OU=coordinador/CN=coord_csr_demo"
```

Ejemplos:
- Para admin: `OU=admin`
- Para coordinador: `OU=coordinador`

**Paso C: Verificar CSR antes de subirla**

```bash
openssl req -in coord_csr_demo.csr.pem -noout -text
```

Validar:
- Subject contiene `CN=coord_csr_demo`
- Subject contiene `OU=coordinador`
- Algoritmo y clave son correctos

**Paso D: Cargar CSR en `/certificado/setup`**

- Opción 1: pegar el texto PEM en "CSR PEM o texto de la solicitud"
- Opción 2: subir archivo CSR

Presionar **Generar certificado**.

**Paso E: Login con el certificado emitido**

```bash
payload='CasaMonarca|login|coord_csr_demo|<CHALLENGE>'
printf '%s' "$payload" | openssl dgst -sha256 -sign coord_csr_demo.key.pem -out /tmp/coord_login.sig
base64 -i /tmp/coord_login.sig | tr -d '\n'
```

Si la clave privada está cifrada, OpenSSL pedirá la passphrase local.

## Propósitos de firma (tabla de referencia)

| Operación | Propósito | Ejemplo de payload |
|-----------|-----------|-------------------|
| Login | `login` | `CasaMonarca\|login\|nuevo_admin\|{CHALLENGE}` |
| Crear usuario | `creacion de usuario` | `CasaMonarca\|creacion de usuario\|admin_prod\|{CHALLENGE}` |
| Otras acciones admin | `{descripcion_accion}` | `CasaMonarca\|{descripcion}\|{username}\|{CHALLENGE}` |

## Backup y restore

**Crear respaldo cifrado:**

```bash
.venv/bin/python tools/backup_db.py
```

Genera un archivo `.enc` en `backups/`.

**Restaurar desde respaldo:**

```bash
.venv/bin/python tools/restore_db.py backups/db_backup_YYYYMMDDTHHMMSSZ.enc
```

Validar que `database.db` se restauró y que la app arranca normalmente.

## Checklist rápido para demostración

- [ ] Usuario nuevo creado por admin con firma de acción
- [ ] Usuario cambia contraseña obligatoria
- [ ] Usuario genera clave privada local
- [ ] Usuario genera CSR con `CN`/`OU` correctos
- [ ] Usuario carga CSR en `/certificado/setup`
- [ ] Certificado emitido y descargado
- [ ] Login exitoso con challenge-response y firma local
- [ ] Flujo completo de expediente (crear → revisar → validar → cerrar)

## Qué NO hacer

- No compartir la clave privada por chat/correo.
- No almacenar la privada en el servidor.
- No reutilizar passphrases débiles o compartidas.

---

**Nota:** este documento será completado con capturas de pantalla y ejemplos GUI para la versión final en Word.
