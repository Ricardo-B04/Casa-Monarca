# TODO — Pendientes

Lista de lo que falta por hacer antes y durante el lanzamiento a producción.
Marcar `[x]` conforme se completen.

## Documentación / entregables
- [ ] Reemplazar el correo placeholder de mantenimiento en `README.md`
      (`soporte-proyecto@casamonarca.local`) por uno real.
- [ ] Revisar que los correos de contacto en `DEVELOPERS.md` estén actualizados.

## Código y pruebas
- [ ] Completar comentarios en el código fuente (`app.py`) según la rúbrica.
- [ ] Ejecutar y documentar la suite de pruebas: `PYTHONPATH=. .venv/bin/pytest -q`.
- [ ] Cubrir con pruebas los flujos críticos faltantes (PKI, passkeys, ARCO).

## Configuración para producción
- [ ] Definir `FLASK_ENV=production` y `SECRET_KEY` fuerte en el `.env` del servidor.
- [ ] Servir detrás de HTTPS y configurar `PASSKEY_RP_ID` / `PASSKEY_ORIGIN` al dominio real.
- [ ] Verificar flags de cookies seguras (`enforce_cookie_flags`) en el entorno de producción.
- [ ] Desplegar con un servidor WSGI (p. ej. gunicorn/uWSGI) detrás de un reverse proxy, no con `app.py` directo.
- [ ] Configurar respaldos periódicos cifrados (`tools/backup_db.py`) y probar el restore (`tools/restore_db.py`).
- [ ] Definir política y rotación de llaves de cifrado (`key.key` / `keys/`) y custodia segura.
- [ ] Revisar y rotar credenciales/certificados de desarrollo antes de producción.

## Mantenimiento
- [ ] Mantener actualizados `CHANGELOG.txt`, `Changelog-Backend.txt` y `Changelog-Frontend.txt`
      con cada cambio (nuevas características, modificaciones y correcciones de bugs).
