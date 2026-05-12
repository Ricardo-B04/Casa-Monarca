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
- `operativo_1 / oper123`
- `usuario_1 / user123`

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

## Licencia de uso
Pendiente de definir (solo mencion).

## Contacto
Equipo del proyecto Casa Monarca.
Correo sugerido para mantenimiento: `soporte-proyecto@casamonarca.local` (reemplazar por correo real).
