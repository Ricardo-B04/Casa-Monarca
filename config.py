import os
from datetime import timedelta

class Config:
    """Configuración base (desarrollo)"""
    SECRET_KEY = os.environ.get("SECRET_KEY") or "secreto_demo"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    
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
