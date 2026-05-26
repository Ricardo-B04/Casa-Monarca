import os
from datetime import timedelta

class Config:
    """Configuración base (desarrollo)"""
    SECRET_KEY = os.environ.get("SECRET_KEY") or "secreto_demo"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # Cifrado de datos sensibles
    ENCRYPTION_KEY_PATH = os.environ.get("ENCRYPTION_KEY_PATH", "key.key")
    ENCRYPTION_LEGACY_KEY_PATHS = [
        path.strip()
        for path in os.environ.get("ENCRYPTION_LEGACY_KEY_PATHS", "").split(",")
        if path.strip()
    ]
    ENCRYPTION_LATENCY_WARNING_SECONDS = float(
        os.environ.get("ENCRYPTION_LATENCY_WARNING_SECONDS", "0.25")
    )
    
    # PKI
    CERT_CA_CERT_PATH = os.environ.get("CERT_CA_CERT_PATH", "certs/ca_cert.pem")
    CERT_CA_KEY_PATH = os.environ.get("CERT_CA_KEY_PATH", "certs/ca_key.pem")
    CERT_VALIDITY_HOURS = 720
    
    # Rate limiting
    LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
    LOGIN_WINDOW_SECONDS = int(os.environ.get("LOGIN_WINDOW_SECONDS", "300"))
    LOGIN_LOCKOUT_SECONDS = int(os.environ.get("LOGIN_LOCKOUT_SECONDS", "900"))
    
    # Password policy
    PASSWORD_MIN_LENGTH = int(os.environ.get("PASSWORD_MIN_LENGTH", "12"))
    
    # Challenge-response
    SIGNATURE_CHALLENGE_TTL = int(os.environ.get("SIGNATURE_CHALLENGE_TTL_SECONDS", "300"))

    # Passkeys/WebAuthn
    PASSKEY_ENABLED = os.environ.get("PASSKEY_ENABLED", "1") == "1"
    PASSKEY_ENFORCE_CRITICAL = os.environ.get("PASSKEY_ENFORCE_CRITICAL", "0") == "1"
    PASSKEY_RP_ID = os.environ.get("PASSKEY_RP_ID", "localhost")
    PASSKEY_RP_NAME = os.environ.get("PASSKEY_RP_NAME", "Casa Monarca")
    _passkey_port = os.environ.get("PASSKEY_PORT", "5000")
    PASSKEY_ORIGIN = os.environ.get("PASSKEY_ORIGIN", f"http://localhost:{_passkey_port}")
    PASSKEY_TIMEOUT_MS = int(os.environ.get("PASSKEY_TIMEOUT_MS", "60000"))
    PASSKEY_MAX_CREDENTIALS_PER_USER = int(os.environ.get("PASSKEY_MAX_CREDENTIALS_PER_USER", "5"))


class DevelopmentConfig(Config):
    """Configuración para desarrollo"""
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    LOG_LEVEL = "DEBUG"


class ProductionConfig(Config):
    """Configuración para producción"""
    DEBUG = False
    SESSION_COOKIE_SECURE = os.environ.get("ENABLE_SESSION_COOKIE_SECURE", "1") == "1"
    SESSION_COOKIE_SAMESITE = "Strict"
    LOG_LEVEL = "INFO"


class TestingConfig(Config):
    """Configuración para testing"""
    TESTING = True
    SESSION_COOKIE_SECURE = False
    LOGIN_MAX_ATTEMPTS = 1000  # Desactivar rate-limiting en tests
    LOG_LEVEL = "DEBUG"


# Seleccionar configuración según entorno
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig
}
