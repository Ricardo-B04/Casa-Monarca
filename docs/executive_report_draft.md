# Reporte Ejecutivo (Borrador)

## Resumen ejecutivo

Casa Monarca es una plataforma web para gestión de expedientes con control de acceso por roles. Diseñada para organizaciones que requieren trazabilidad, auditoría y seguridad en procesos de canalización multi-nivel.

**Estado:** Primera etapa completada. Sistema funcional con autenticación reforzada y fundamentos de PKI.

## Problema resuelto

Necesidad de un sistema centralizado para:
- Gestionar expedientes a través de múltiples niveles operativos.
- Controlar acceso según roles (usuario, operativo, coordinador, admin).
- Mantener auditoría completa de acciones.
- Asegurar que solo usuarios autorizados ejecuten acciones críticas (administración, validación).

## Solución entregada

**Plataforma web escalable** con:
- Gestión flexible de usuarios y roles.
- Flujo de estados para expedientes con validaciones.
- **Autenticación reforzada:** contraseñas hasheadas + challenge-response con certificados X.509 para roles críticos.
- **Auditoría completa:** bitácora de eventos (login, creaciones, cambios de estado).
- **Seguridad:** backups cifrados, protección CSRF, cookies seguras, rate-limiting de login.

## Logros clave (Sprint 1 y 2)

### Sprint 1: Fundamentos y seguridad
- [x] Sistema de usuarios con roles diferenciados.
- [x] Autenticación con contraseñas hasheadas.
- [x] Flujo de expedientes (borrador → revisión → validación → cierre).
- [x] Protección CSRF y cookies seguras.
- [x] Rate-limiting y bloqueo temporal de login.
- [x] Backups cifrados y restauración.
- [x] Bitácora de eventos.

### Sprint 2: PKI y acciones críticas
- [x] CA interna del proyecto.
- [x] Emisión de certificados X.509 para admin/coordinador.
- [x] Challenge-response para login seguro.
- [x] Revocación de certificados con auditoría.
- [x] Soporte para CSR (claves privadas generadas localmente).

## Funcionalidades operativas

| Funcionalidad | Estado | Notas |
|---------------|--------|-------|
| Gestión de usuarios | ✓ Completo | CRUD con validaciones |
| Flujo de expedientes | ✓ Completo | 5 estados, transiciones controladas |
| Autenticación | ✓ Completo | Password + challenge-response |
| Certificados X.509 | ✓ Completo | Emisión, validación, revocación |
| Bitácora | ✓ Completo | Evento por acción crítica |
| Backup/Restore | ✓ Completo | AES-256 con key.key |
| Rate-limiting | ✓ Completo | 5 intentos, 15 min bloqueo |
| Tests | ✓ Completo | Cobertura de seguridad básica |

## Beneficios

1. **Seguridad:** autenticación reforzada (2FA via certificados), auditoría completa.
2. **Trazabilidad:** cada acción queda registrada con usuario, rol, timestamp.
3. **Control:** permisos granulares por rol, flujos controlados.
4. **Resilencia:** backups cifrados, validación de integridad.

## Recomendaciones para producción

- **HTTPS:** servir detrás de proxy HTTPS (Nginx, Caddy).
- **Secretos:** exportar `SECRET_KEY` desde gestor (no hardcodear).
- **Escalado:** migrar CA a HSM, contadores de login a Redis.
- **Auditoría externa:** integrar con SIEM/Log aggregator.
- **Backups:** estrategia de retención, almacenamiento externo.

## Próximos pasos (Etapa 2)

- Migración de CA a HSM o secret manager.
- Integración LDAP/AD para SSO.
- Escalado horizontal (Redis, load balancing).
- Dashboard de reportes y analytics.
- Despliegue en Kubernetes/Docker.

## Inversión y ROI

| Aspecto | Estimado |
|--------|----------|
| Desarrollo | ~200 horas (2 sprints) |
| Testing | ~50 horas |
| Documentación | ~30 horas |
| **Total** | **~280 horas** |

Beneficio: plataforma de gestión centralizada lista para producción, con seguridad baseline y auditoría.

## Conclusión

Casa Monarca es una solución viables para organizaciones que requieren gestión de procesos con trazabilidad y control de acceso. La primera etapa proporciona fundamentos sólidos de seguridad y escalabilidad.

---

Este reporte será refinado y formateado para PDF (LaTeX) según rúbrica de entrega.
