#!/usr/bin/env python3
import os
from cryptography.fernet import Fernet

KEY_PATH = os.environ.get(
    'ENCRYPTION_KEY_PATH',
    os.path.join(os.path.dirname(__file__), '..', 'key.key')
)
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'database.db')


def load_key():
    with open(KEY_PATH, 'rb') as f:
        return f.read()


def restore_backup(backup_path):
    key = load_key()
    f = Fernet(key)

    if not os.path.exists(backup_path):
        raise FileNotFoundError('Backup file not found: ' + backup_path)

    with open(backup_path, 'rb') as bf:
        token = bf.read()

    data = f.decrypt(token)

    with open(DB_PATH, 'wb') as out:
        out.write(data)

    return DB_PATH


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print('Usage: restore_db.py <backup_file.enc>')
        sys.exit(2)
    path = restore_backup(sys.argv[1])
    print('Restaurado en', path)
