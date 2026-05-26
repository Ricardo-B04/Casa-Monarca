#!/usr/bin/env python3
import os
import datetime
from cryptography.fernet import Fernet

KEY_PATH = os.environ.get(
    'ENCRYPTION_KEY_PATH',
    os.path.join(os.path.dirname(__file__), '..', 'key.key')
)
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database.db')
BACKUP_DIR = os.path.join(os.path.dirname(__file__), '..', 'backups')


def load_key():
    with open(KEY_PATH, 'rb') as f:
        return f.read()


def make_backup(dest_path=None):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    key = load_key()
    f = Fernet(key)
    ts = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    dest = dest_path or os.path.join(BACKUP_DIR, f'db_backup_{ts}.enc')

    if not os.path.exists(DB_PATH):
        raise FileNotFoundError('database.db not found')

    with open(DB_PATH, 'rb') as dbf:
        data = dbf.read()

    token = f.encrypt(data)
    with open(dest, 'wb') as out:
        out.write(token)

    return dest


if __name__ == '__main__':
    path = make_backup()
    print('Backup creado en', path)
