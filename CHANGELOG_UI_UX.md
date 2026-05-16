# CHANGELOG UI/UX - Casa Monarca

Registro de mejoras visuales, problemas identificados y enhancements pendientes en las interfaces de usuario.

---

## 📋 Sprint: Refactor Visual/UX

### ✅ Completado

#### Gestión de Usuarios (Usuarios.html)
- [x] Crear stylesheet centralizado con paleta profesional (`static/style.css`)
- [x] Convertir tabla monótona a layout card-based
- [x] Agregar summary cards con métricas (usuarios, admins, coordinadores, certs)
- [x] Simplificar formulario de creación: 8 campos → 3 campos básicos
- [x] Mover certificado + firma + contingencia a accordion colapsable
- [x] Implementar dinámica: mostrar campo "Área" solo si rol=coordinador
- [x] Implementar dinámica: mostrar certificado solo si rol=admin/coordinador
- [x] Badges coloreados por rol (admin=rojo, coordinador=naranja, operativo=azul, usuario=gris)
- [x] Indicadores visuales de estado en certificados (punto verde=activo)
- [x] Responsive design: 2-columnas → 1-columna en mobile

#### Bitácora (Logs.html)
- [x] Cambiar formato de timestamp de `2026-05-16 12:30:21.821975` a `HH:MM:SS`
- [x] Agrupar eventos por fecha (YYYY-MM-DD)
- [x] Mostrar solo fechas con eventos (sin días vacíos)
- [x] Agregar summary cards: total eventos, eventos hoy, usuarios únicos, tipos de acciones
- [x] Mover acción "Limpiar Bitácora" a accordion colapsable (no distrae)
- [x] Agregar filtros: usuario y acción
- [x] Unificar estilos con `static/style.css`

---

## ⚠️ Problemas Identificados (Pendientes de Resolver)

### Bitácora - Filtros (PRIORIDAD: MEDIA)
**Issue**: Los filtros en la bitácora tienen comportamientos inesperados

#### Problema 1: Filtro por acción
- **Descripción**: Al hacer clic en un filtro de acción del dropdown, todos los eventos desaparecen (no filtra correctamente)
- **Síntomas**: Seleccionar "Inicio de sesión" → muestra 0 eventos (cuando deberían mostrar ~30)
- **Causa probable**: Lógica de comparación en `filtrarLogs()` (JavaScript) puede estar usando case-sensitive o comparación exacta incorrecta
- **Solución propuesta**: 
  - Revisar que la comparación sea case-insensitive
  - Verificar que `dataset.accion` contenga el valor esperado
  - Posible bug en la iteración de elementos DOM

#### Problema 2: Filtro de usuario (UX pobre)
- **Descripción**: Campo de texto libre para usuarios, pero no hay autocomplete ni sugerencias
- **Síntomas**: Admin no sabe qué usuarios escribir; tiene que adivinar o mirar la lista
- **Causa probable**: Implementación rápida sin usabilidad refinada
- **Solución propuesta**:
  - Cambiar de input text a `<datalist>` o dropdown con opciones
  - Populated dinámicamente con usuarios que tienen eventos en bitácora
  - O agregar autocomplete con sugerencias en tiempo real
- **Impacto**: Mejora significativa en UX para admin operacional

#### Problema 3: Todos los eventos desaparecen
- **Descripción**: Ocasionalmente al filtrar, todos los eventos desaparecen (incluso si el filtro debe coincidir)
- **Síntomas**: Usuario filtra + todos los eventos hidden
- **Causa probable**: Posible conflicto entre filtro usuario + acción o error en lógica booleana
- **Solución propuesta**: Debug exhaustivo + test cases para cada combinación

---

## 🎯 Mejoras Pendientes (Próximas Fases)

### Bitácora - Acordeones por Fecha (PRIORIDAD: ALTA)
**Issue**: Sin acordeones, navegar bitácora con muchos eventos requiere mucho scroll

#### Mejora propuesta:
- [x] **Identificado**: Las tablas por día deberían colapsar/expandir
- [ ] **Implementar**: Headers de fecha (`2026-05-16`) clickeables como acordeones
- [ ] **Comportamiento**: 
  - Por defecto: expandir últimos 3 días, colapsar el resto
  - O: expandir solo HOY, colapsar todo lo demás
  - Click en header → toggle collapse/expand
- [ ] **UX**: Agregar icono de flecha (▼/▶) que rote según estado
- [ ] **Performance**: Mantener filtros funcionales incluso con acordeones colapsados

### Usuarios - Búsqueda/Filtro (PRIORIDAD: BAJA)
- [ ] Agregar campo de búsqueda para usuario en tabla
- [ ] Filtrar tabla en tiempo real mientras escribo
- [ ] Badges de rol como filtro (click para mostrar solo ese rol)

### Certificados - Detalles Expandibles (PRIORIDAD: MEDIA)
- [ ] Click en certificado → expandir detalles (fingerprint, serial, issuer, validity)
- [ ] Ver timeline de vida del certificado (creado → activo → revocado)
- [ ] Botón rápido para descargar o revocar sin ir a otra página

### Dashboard/Admin - Insights (PRIORIDAD: BAJA)
- [ ] Gráfica de logins por día (últimos 7 días)
- [ ] Usuarios más activos (ranking)
- [ ] Certificados expirando pronto (alertas visuales)
- [ ] Intentos de login fallidos (rate limiting status)

---

## 🐛 Bugs Reportados

### None yet

---

## 📝 Notas Técnicas

- **Stylesheet centralizado**: `static/style.css` con variables CSS, componentes reutilizables
- **Agrupación backend**: Datos pre-procesados en Python (app.py) para templates más simples
- **Filtrado frontend**: JavaScript puro sin reload (mejor UX)
- **Responsive**: Mobile-first, breakpoints en 768px y 480px
- **Colores**:
  - Primary: #161d2f (navy oscuro)
  - Secondary: #44506a (navy claro)
  - Accent: #8f3219 (marrón/naranja)
  - Roles: admin=rojo, coordinador=naranja, operativo=azul, usuario=gris

---

## 📅 Timeline

- **Sprint Actual**: Refactor Visual/UX usuarios + bitácora
- **Próximo**: Resolver problemas con filtros + acordeones por fecha
- **Después**: Enhancements de certificados, dashboard insights

---

## ✨ Versiones de Archivos

| Archivo | Última Versión | Commit | Estado |
|---------|---|---|---|
| `static/style.css` | 1.0 | `b67ed3b` | ✅ Stable |
| `templates/usuarios.html` | 2.0 | `b67ed3b` | ✅ Stable |
| `templates/logs.html` | 2.0 | `ff4d8f9` | ⚠️ Needs filter fixes |
| `app.py` | 3.2 | `ff4d8f9` | ✅ Stable |
