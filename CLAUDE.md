# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Casa Monarca is a Flask web app (single-file backend in `app.py`, ~5600 lines) for managing case files (`expedientes`/`encuestas`) that are routed through operational levels (Usuario → Operativo → Coordinador → Admin). It layers on a fairly elaborate security stack: Argon2id password hashing, account lockout, X.509 PKI with challenge-response signing for critical roles, WebAuthn/passkeys, Fernet field-level encryption with key rotation, and an audit log (`logs` table). UI strings, templates, and most documentation are in Spanish.

## Common commands

Run everything through the project's virtualenv (`.venv`).

```bash
# Setup (creates .venv, installs deps, copies .env, generates key.key, makes certs/backups/logs)
./setup.sh

# Run the app (serves on http://127.0.0.1:5000; DB tables are created on first run)
.venv/bin/python app.py

# Syntax check
.venv/bin/python -m py_compile app.py

# Run the full test suite
PYTHONPATH=. .venv/bin/pytest -q

# Run a single test file / test function
PYTHONPATH=. .venv/bin/pytest tests/test_password_security.py -q
PYTHONPATH=. .venv/bin/pytest tests/test_password_security.py::test_qa_a_rejects_weak_password_on_forced_update -q

# Generate/regenerate the Fernet data-encryption key (key.key)
.venv/bin/python generate_key.py

# Encrypted DB backup / restore
.venv/bin/python tools/backup_db.py
.venv/bin/python tools/restore_db.py
```

There is no separate lint/format command configured — `py_compile` plus pytest is the existing verification path.

## Architecture

### Single-file Flask app
Almost all backend logic — routes, DB schema/migrations, crypto helpers, PKI/passkey logic, and business rules — lives in `app.py`. When orienting yourself, search for `@app.route` and the top-level `def`s rather than expecting a package layout. `config.py` defines `DevelopmentConfig`/`ProductionConfig`/`TestingConfig`, selected via `FLASK_ENV` (default `development`).

### Database
SQLite (`database.db`, gitignored), accessed via `get_conn()` (raw `sqlite3`, row factory). `init_db()` creates tables and uses `ensure_column()` to add columns idempotently to existing DBs (used heavily for the multilevel ARCO migration — see below). Key tables: `encuestas` (case files, encrypted payload in `datos`), `usuarios`, `logs` (audit trail), `certificados`, `passkey_credentials`, `encryption_keys` / `encryption_metrics` / `reencrypt_jobs`, `solicitudes_arco`, `solicitudes_eliminacion`, `login_lockouts`.

### Roles and permissions
Four roles in `ROLE_LABELS`/`PERMISSIONS`: `admin`, `coordinador`, `operativo`, `usuario`, each mapped to a CRUD-like permission set checked via `has_permission()`/`require_role()`. `next_status_for_role()` and `enforce_certificate_setup()` gate the case-file workflow (`borrador → en_revision → validado → cerrado`) and force critical roles (`admin`, `coordinador`) through certificate/passkey setup before they can act.

### Encryption (Fernet, field-level)
Sensitive payloads (e.g. `encuestas.datos`) are encrypted/decrypted with Fernet via `encrypt_data()`/`decrypt_data()`. Key material loading goes through `_load_key_bytes()` → `_build_keyring()` → `get_cipher_for_fingerprint()`, supporting an active key plus legacy keys (`ENCRYPTION_LEGACY_KEY_PATHS`) for rotation/decryption-during-migration. Key lifecycle (generate/activate/retire) is tracked in `encryption_keys`, latency/usage in `encryption_metrics`, and bulk re-encryption is queued in `reencrypt_jobs` and executed by `tools/reencrypt_worker.py` (see `enqueue_reencrypt_job`, `reencrypt_all_surveys`, and the `/admin/cifrado*` and `/admin/keys/*` routes). The NIST SP 800-57–based key-lifecycle policy is documented at the top of `Changelog-Backend.txt`.

### PKI / certificates / passkeys
Two parallel auth-strengthening mechanisms exist for critical roles (`admin`, `coordinador`):
- **X.509 challenge-response**: a dev CA is bootstrapped in `certs/` (`_load_or_create_certificate_authority`, `bootstrap_dev_certificates`); user certs are issued/activated/revoked through `issue_user_certificate*`, `activate_pending_certificate*`, `revoke_certificate*`, and verified via `verify_certificate_challenge_response`/`verify_action_certificate`. Routes live under `/certificado/*` and `/admin/pki/*`.
- **WebAuthn/passkeys**: registration and login flows under `/auth/passkey/*`, plus per-action verification under `/action/passkey/*` (`action_passkey_options`/`action_passkey_verify`, gated by `check_and_consume_passkey_action`). Passkeys can be linked to certificates (`derive_certificate_from_first_passkey`, `link_passkey_to_certificate`) and revoked together (`revoke_passkey_and_cert`, `revoke_certificate_and_passkeys`). Controlled by the `PASSKEY_*` settings in `config.py` (`PASSKEY_ENABLED`, `PASSKEY_ENFORCE_CRITICAL`, `PASSKEY_RP_ID`/`PASSKEY_ORIGIN`, etc.). The migration plan from legacy certificate signing to passkey-based action verification is tracked in `Changelog-Backend.txt`.

### ARCO requests (data-rights workflow)
`solicitudes_arco` implements a multilevel approval pipeline for ARCO (Acceso, Rectificación, Cancelación, Oposición) data-rights requests, replacing an earlier admin-only flow:
```
/arco (public form) → nivel_actual='usuarios' → operativos → coordinadores
  → coordinador either marks resuelto OR forwards (reenviado_por_coordinador) to nivel_actual='admin'
```
Routes: `/arco`, `/arco/solicitud`, `/arco/<id>/aprobar`, `/arco/<id>/resolver`, `/arco/<id>/resolver-coordinador`. Each level's approval flag/timestamp/actor is tracked in dedicated columns (`aprobado_usuarios[_at|_por]`, etc.). Full design notes are in `IMPLEMENTACION_ARCO_MULTINIVEL.md`.

### Auth, sessions, and CSRF
Login (`/`) does Argon2id verification (`hash_password_argon2id`/`verify_password_argon2id`) with rate limiting/lockout backed by `login_lockouts` (`_is_locked`, `_record_failed`, `_clear_failed`). Password policy is enforced in `validate_new_password_policy`/`password_has_minimum_entropy`/`check_password_pwned` (HIBP lookup). CSRF protection is global via `csrf_protect()`/`validate_csrf()`/`ensure_csrf_token()` (registered as a `before_request` hook), and `enforce_cookie_flags()` sets cookie security attributes per environment.

## Notable conventions

- Spanish is used throughout: route names, template names, log messages, DB column names, commit messages, and most docs/changelogs (`Changelog-Backend.txt`, `Changelog-Frontend.txt`, `CHANGELOG.txt`).
- `key.key` (Fernet key), `certs/*.pem` (CA + user certs), `keys/` (rotated key material), and `*.db` files are runtime-generated/secret and gitignored — never commit them or print their contents.
- `ensure_column()` is the established pattern for evolving the schema without breaking existing databases; follow it (rather than `ALTER TABLE` directly or destructive migrations) when adding columns.
- Tests under `tests/` use `app_module` fixtures that `monkeypatch.chdir(tmp_path)` and rebuild an isolated DB/cert/key set per test (see `tests/test_password_security.py`); the standalone `test_arco_*.py` / `test_csrf_arco.py` / `test_final_verification.py` files at the repo root are ad hoc verification scripts rather than pytest suites proper.
