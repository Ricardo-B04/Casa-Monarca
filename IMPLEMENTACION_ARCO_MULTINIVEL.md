# Implementación: Flujo Multinivel de Solicitudes ARCO

## 📋 Resumen de Cambios

Se ha implementado con éxito un flujo multinivel de solicitudes ARCO que reemplaza el sistema anterior donde solo los admins tenían acceso directo. El nuevo flujo es:

```
Solicitud Pública (/arco)
    ↓ nivel_actual = 'usuarios'
Usuarios (bandeja) - APRUEBA
    ↓ nivel_actual = 'operativos'
Operativos (bandeja) - APRUEBA
    ↓ nivel_actual = 'coordinadores'
Coordinadores (bandeja)
    ├─ Opción A: Marca RESUELTA → Estado: 'resuelto'
    └─ Opción B: Envía a Admin → nivel_actual = 'admin'
        ↓
Administrador (panel /admin)
    ├─ Sección "ARCO Prioritarias" (con badge rojo)
    └─ Sección "ARCO Directas" (flujo antiguo)
```

---

## 🔧 Cambios en Base de Datos

### Nuevas Columnas en `solicitudes_arco`

Se agregaron 14 columnas para rastrear el flujo multinivel:

| Columna | Tipo | Propósito |
|---------|------|----------|
| `nivel_actual` | TEXT | Nivel actual: usuarios, operativos, coordinadores, admin, resuelto |
| `aprobado_usuarios` | INTEGER | Flag si fue aprobado por usuarios (0/1) |
| `aprobado_usuarios_at` | DATETIME | Timestamp de aprobación |
| `aprobado_usuarios_por` | TEXT | Usuario que aprobó |
| `aprobado_operativos` | INTEGER | Flag si fue aprobado por operativos |
| `aprobado_operativos_at` | DATETIME | Timestamp de aprobación |
| `aprobado_operativos_por` | TEXT | Usuario que aprobó |
| `aprobado_coordinadores` | INTEGER | Flag si fue aprobado por coordinadores |
| `aprobado_coordinadores_at` | DATETIME | Timestamp de aprobación |
| `aprobado_coordinadores_por` | TEXT | Usuario que aprobó |
| `reenviado_por_coordinador` | INTEGER | Flag si coordinador reenviló a admin |
| `reenviado_por_coordinador_at` | DATETIME | Timestamp de reenvío |
| `resuelto_coordinador` | INTEGER | Flag si coordinador marcó como resuelta |
| `resuelto_coordinador_at` | DATETIME | Timestamp de resolución |

**Nota**: Las columnas `atendida_por` y `atendida_at` se conservan para la resolución final del admin (flujo secundario).

---

## 🔀 Cambios en Backend (app.py)

### 1. Inicialización de BD (init_db)

Se agregaron las columnas nuevas mediante `ensure_column()` para compatibilidad con BDs existentes.

**Ubicación**: [app.py - línea ~460](app.py#L460)

### 2. Nuevos Endpoints

#### POST `/arco/<id>/aprobar`

**Funcionalidad**: Endpoint para usuarios, operativos y coordinadores para aprobar solicitudes.

**Flujo**:
- Valida que el usuario tiene un rol permitido (usuario, operativo, coordinador)
- Verifica que la solicitud está en el `nivel_actual` esperado para ese rol
- Actualiza:
  - Flag de aprobación (`aprobado_X`)
  - Timestamp de aprobación
  - Usuario que aprobó
  - Avanza al siguiente nivel automáticamente
- Registra en logs
- Redirige a `/bandeja`

**Validaciones**:
- ✓ Solo roles permitidos pueden acceder
- ✓ Solicitud debe estar en el nivel correcto
- ✓ Manejo de excepciones y rollback en BD

#### POST `/arco/<id>/resolver-coordinador`

**Funcionalidad**: Endpoint exclusivo para coordinadores con 2 opciones.

**Opción 1 - Marcar Resuelta**:
- Estado: `resuelto`
- nivel_actual: `resuelto`
- estado: `atendida`
- Se registra timestamp y coordinador

**Opción 2 - Enviar a Admin**:
- Reenviado como "PRIORITARIA"
- nivel_actual: `admin`
- reenviado_por_coordinador: 1
- Visible en sección especial en /admin

**Ubicación**: [app.py - línea ~4260](app.py#L4260)

### 3. Modificaciones a Endpoints Existentes

#### GET `/bandeja` (modificado)

**Cambios**:
- Carga `solicitudes_arco` filtrando por `nivel_actual` según el rol:
  - Usuario: `nivel_actual = 'usuarios'`
  - Operativo: `nivel_actual = 'operativos'`
  - Coordinador: `nivel_actual = 'coordinadores'`
- Pasa solicitudes al template como `solicitudes_arco`

**Ubicación**: [app.py - línea ~3435](app.py#L3435)

#### GET `/admin` (modificado)

**Cambios**:
- Separa solicitudes ARCO en 2 listas:
  - `solicitudes_arco_prioritarias`: Reenviadas por coordinadores (reenviado_por_coordinador=1)
  - `solicitudes_arco_directas`: Flujo antiguo o en proceso
- El endpoint `/arco/<id>/resolver` sigue disponible para ambas

**Ubicación**: [app.py - línea ~3393](app.py#L3393)

---

## 🎨 Cambios en Templates

### 1. colaborador.html (Nueva Sección ARCO)

**Ubicación**: Después de la sección de expedientes

**Características**:
- Muestra solicitudes ARCO pendientes según el rol del usuario
- Botones de acción:
  - **Usuarios/Operativos**: "✓ Aprobar" → Avanza automáticamente
  - **Coordinadores**: 
    - "✓ Marcar Resuelta" → Cierra la solicitud
    - "→ Enviar a Admin" → Marca como prioritaria

**Estilos**:
- Borde izquierdo amarillo (`#f59e0b`)
- Información clara del solicitante y motivo

**Ubicación**: [colaborador.html - línea ~86](templates/colaborador.html#L86)

### 2. admin.html (Secciones Separadas ARCO)

**Ubicación**: Reemplaza la sección antigua de "Solicitudes ARCO"

#### Sección "ARCO Prioritarias"

- **Badge**: Rojo con etiqueta "PRIORITARIA"
- **Borde**: Rojo (#dc2626)
- **Información adicional**: Muestra quién y cuándo fue reenviada
- **Ordenamiento**: Por fecha de reenvío más reciente
- **Acciones**: "✓ Marcar atendida", "✗ Rechazar"

#### Sección "ARCO Directas"

- **Badge**: Amarillo "Pendiente"
- **Información de flujo**: Muestra checkmarks de aprobaciones previas
- **Estado**: Muestra el `nivel_actual`
- **Acciones**: Mismo que antes

**Contador actualizado**: Suma ambas listas para el resumen

**Ubicación**: [admin.html - línea ~511](templates/admin.html#L511)

---

## 🧪 Verificaciones Realizadas

### ✓ Prueba 1: Columnas de Base de Datos
- 14 columnas nuevas verificadas
- Compatibles con BD existentes
- **Estado**: PASÓ

### ✓ Prueba 2: Estructura de Tabla
- 36 columnas totales (22 originales + 14 nuevas)
- Tipos de datos correctos
- **Estado**: PASÓ

### ✓ Prueba 3: Datos Existentes
- BDs existentes mantienen sus datos
- Campo `nivel_actual` con valor por defecto 'usuarios'
- **Estado**: PASÓ

### ✓ Prueba 4: Flujo de Aprobación
- Simulación completa: usuario → operativo → coordinador
- Transiciones correctas entre niveles
- Registro de aprobadores y timestamps
- **Estado**: PASÓ

### ✓ Prueba 5: Endpoints Registrados
- 5 endpoints ARCO verificados
- Métodos HTTP correctos (GET, POST)
- Handlers implementados
- **Estado**: PASÓ

### ✓ Prueba 6: Permisos por Rol
- RBAC funcionando correctamente
- Restricciones de acceso validadas
- **Estado**: PASÓ

---

## 📊 Flujo de Estados

```
           ┌──────────────────────────────────┐
           │  Solicitud pública (sin autenticación)
           │  POST /arco/solicitud
           │  nivel_actual = 'usuarios'
           └──────────────────┬───────────────┘
                              │
        ┌─────────────────────▼─────────────────────┐
        │  Bandeja Usuarios                         │
        │  GET /bandeja (rol=usuario)              │
        │  POST /arco/<id>/aprobar                 │
        │  ✓ Aprueba → nivel='operativos'          │
        └─────────────────────┬─────────────────────┘
                              │
        ┌─────────────────────▼─────────────────────┐
        │  Bandeja Operativos                       │
        │  GET /bandeja (rol=operativo)            │
        │  POST /arco/<id>/aprobar                 │
        │  ✓ Aprueba → nivel='coordinadores'       │
        └─────────────────────┬─────────────────────┘
                              │
        ┌─────────────────────▼──────────────────────────┐
        │  Bandeja Coordinadores                        │
        │  GET /bandeja (rol=coordinador)              │
        │  POST /arco/<id>/resolver-coordinador        │
        │  Dos opciones:                                │
        │  ├─ ✓ Resuelta → estado='resuelto'          │
        │  └─ → Admin → nivel='admin', prioritaria=1   │
        └────────┬──────────────────────┬──────────────┘
                 │ (resuelta)           │ (enviada a admin)
                 │                      │
        ┌────────▼────┐     ┌───────────▼──────────────┐
        │  Cerrada    │     │  Panel Admin             │
        │  por        │     │  GET /admin             │
        │  coordinador│     │  ARCO Prioritarias ⭐  │
        │             │     │  POST /arco/<id>/resolver
        └─────────────┘     │  ✓ Atendida / ✗ Rechazar
                            └────────────────────────────┘
```

---

## 🔐 Seguridad

- ✓ CSRF tokens en formularios admin
- ✓ RBAC validado en cada endpoint
- ✓ Logging de todas las acciones
- ✓ Validaciones de datos de entrada
- ✓ Manejo de excepciones con rollback

---

## 📝 Notas de Implementación

1. **Backward Compatibility**: El flujo antiguo (admin directo) sigue funcionando como fallback. Las solicitudes directas aparecen en la sección "ARCO Directas".

2. **Auto-forward**: Los usuarios, operativos simplemente aprueban. El sistema automáticamente avanza al siguiente nivel. No requieren confirmación de paso.

3. **Decisión Binaria en Coordinadores**: Los coordinadores deben elegir:
   - Resolver localmente (no pasa a admin)
   - O enviar a admin como prioritaria

4. **Visible para Admin**: El admin siempre ve todas las solicitudes, pero las prioritarias están en una sección destacada con badge rojo.

5. **Auditoría Completa**: Cada aprobación queda registrada con:
   - Usuario que aprobó
   - Timestamp exacto
   - Nivel en que ocurrió

---

## 📁 Archivos Modificados

1. **app.py**
   - Agregadas columnas en `init_db()`
   - Nuevos endpoints: `/arco/<id>/aprobar`, `/arco/<id>/resolver-coordinador`
   - Modificados: `/bandeja`, `/admin`

2. **templates/colaborador.html**
   - Nueva sección "Solicitudes ARCO Pendientes" con botones contextuales

3. **templates/admin.html**
   - Reemplazada sección "Solicitudes ARCO" por dos subsecciones:
     - "ARCO Prioritarias" (destacadas en rojo)
     - "ARCO Directas" (flujo antiguo)

---

## ✅ Checklist de Validación

- [x] BD actualizada con nuevas columnas
- [x] Nuevos endpoints implementados
- [x] RBAC verificado en cada endpoint
- [x] Templates actualizados
- [x] Flujo completo probado (usuario → operativo → coordinador)
- [x] Logging implementado
- [x] Manejo de errores con rollback
- [x] Backward compatibility mantenida
- [x] Todas las pruebas automatizadas pasadas
- [x] Endpoints verificados y registrados correctamente

---

**Implementación completada y verificada.**
