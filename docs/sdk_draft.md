# SDK / Interfaz para Desarrolladores (Borrador)

## Objetivo

Describir componentes reutilizables y ejemplos para que un desarrollador integre o automatice tareas con Casa Monarca.

## Flujo de autenticación

### 1. Obtener desafío

**GET /login**

Retorna un formulario con campo `challenge` que es un UUID aleatorio generado por el servidor.

### 2. Firmar desafío

El cliente debe construir un payload y firmarlo con su clave privada:

```
Payload: CasaMonarca|<proposito>|<username>|<challenge>
```

Propósitos válidos:
- `login`: para iniciar sesión
- `creacion de usuario`: para crear usuario (solo admin)
- Otros: según operación administrativa

**Ejemplo:**

```python
import subprocess
import base64

def sign_payload(key_path, payload, passphrase=None):
    """Firma un payload con una clave privada."""
    cmd = ['openssl', 'dgst', '-sha256', '-sign', key_path]
    if passphrase:
        cmd.extend(['-passin', f'pass:{passphrase}'])
    
    result = subprocess.run(cmd, input=payload.encode(), capture_output=True)
    signature_b64 = base64.b64encode(result.stdout).decode().strip()
    return signature_b64
```

### 3. Enviar firma y certificado

**POST /login**

Datos:
- `username`: nombre de usuario
- `password`: contraseña
- `challenge`: valor original (para verificación)
- `signature_b64`: firma en Base64 (o binario)
- `certificate_file`: certificado X.509 (`.pem`)

## Endpoints principales (referencia)

### Gestión de expedientes

**GET /dashboard**
- Retorna panel con expedientes del usuario según su rol.
- Autenticado.

**POST /expediente/crear**
- Crea nuevo expediente.
- Requiere rol: usuario, operativo, coordinador, admin.
- Payload: `{titulo, descripcion}`

**GET /expediente/<id>**
- Obtiene detalles de expediente.
- Autenticado.

**POST /expediente/<id>/canalizar**
- Canaliza expediente al siguiente nivel.
- Requiere firma si es coordinador o admin (según configuración).

### Gestión de usuarios

**GET /admin/usuarios**
- Lista usuarios (solo admin).
- Autenticado, requiere admin.

**POST /admin/crear_usuario**
- Crea nuevo usuario (solo admin).
- Requiere firma con certificado admin.
- Payload: `{username, password, role, signature_b64, certificate_file}`

### Certificados

**GET /certificado/setup**
- Pantalla de setup de certificado.
- Autenticado.

**POST /certificado/generar**
- Genera o firma certificado (desde CSR o legacy).
- Payload: `{csr_pem, passphrase}` (según modo)

## Ejemplo de cliente Python (pseudo-código)

```python
import requests
import base64
from sign_payload import sign_payload  # función auxiliar

class CasaMonarcaClient:
    def __init__(self, base_url, username, key_path, passphrase=None):
        self.base_url = base_url
        self.username = username
        self.key_path = key_path
        self.passphrase = passphrase
        self.session = requests.Session()
    
    def login(self, password, certificate_path):
        """Autentica con password y certificado."""
        # Obtener desafío
        resp = self.session.get(f'{self.base_url}/login')
        challenge = resp.json().get('challenge')
        
        # Construir payload y firmar
        payload = f'CasaMonarca|login|{self.username}|{challenge}'
        signature = sign_payload(self.key_path, payload, self.passphrase)
        
        # Enviar login
        with open(certificate_path, 'rb') as f:
            files = {'certificate_file': f}
            data = {
                'username': self.username,
                'password': password,
                'challenge': challenge,
                'signature_b64': signature
            }
            resp = self.session.post(f'{self.base_url}/login', data=data, files=files)
        
        return resp.status_code == 200
    
    def get_dashboard(self):
        """Obtiene dashboard del usuario."""
        resp = self.session.get(f'{self.base_url}/dashboard')
        return resp.json()
    
    def crear_expediente(self, titulo, descripcion):
        """Crea expediente."""
        data = {'titulo': titulo, 'descripcion': descripcion}
        resp = self.session.post(f'{self.base_url}/expediente/crear', json=data)
        return resp.json()

# Uso
client = CasaMonarcaClient(
    'http://localhost:5000',
    'usuario_1',
    '/path/to/user.key',
    passphrase='mi_passphrase'
)

if client.login('Usuario_2026!X', '/path/to/user.pem'):
    dashboard = client.get_dashboard()
    print(dashboard)
```

---

**Nota:** completar con especificación OpenAPI/Swagger, ejemplos en otros lenguajes (JavaScript, cURL) y casos de uso antes de convertir a LaTeX.
