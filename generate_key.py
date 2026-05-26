from cryptography.fernet import Fernet
import os

key = Fernet.generate_key()

KEY_PATH = os.environ.get("ENCRYPTION_KEY_PATH", "key.key")

os.makedirs(os.path.dirname(KEY_PATH) or ".", exist_ok=True)

with open(KEY_PATH, "wb") as f:
    f.write(key)

print(f"Key generada en {KEY_PATH}")