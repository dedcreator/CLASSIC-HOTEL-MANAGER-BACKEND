# backend/hotel_project/settings.py

import os
from pathlib import Path
from decouple import config

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-your-secret-key-here')

DEBUG = config('DEBUG', default=True, cast=bool)

# ALLOWED_HOSTS for Render and local development
ALLOWED_HOSTS_CONFIG = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,.onrender.com,*')
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_CONFIG.split(',') if host.strip()]
RENDER_EXTERNAL_HOSTNAME = os.environ.get('RENDER_EXTERNAL_HOSTNAME')
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    
    # Third party apps
    'rest_framework',
    'corsheaders', 
    'rest_framework_simplejwt',
    'rest_framework.authtoken',
    
    # Created apps
    'accounts',
    'rooms',
    'bookings',
    'inventory',
    'sales',
    'reports',
    'consumables',
    'payments',
    'menu',
    'tables',
]

# MIDDLEWARE - CorsMiddleware and WhiteNoise
MIDDLEWARE = [
    'bookings.middleware.PublicBypassMiddleware', 
    'accounts.middleware.DisableCSRFForAPI',
    'corsheaders.middleware.CorsMiddleware', 
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'hotel_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'hotel_project.wsgi.application'

# Database - automatic PostgreSQL support on Render with SQLite local fallback
DATABASES = {
    'default': dj_database_url.config(
        default=f'sqlite:///{BASE_DIR / "db.sqlite3"}',
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
WHITENOISE_MANIFEST_STRICT = False

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom user model
AUTH_USER_MODEL = 'accounts.User'

FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:3000')

# JWT Settings
from datetime import timedelta


REST_FRAMEWORK = {
        'DEFAULT_RENDERER_CLASSES': (
        'rest_framework.renderers.JSONRenderer',
    ),

    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',  
        'rest_framework_simplejwt.authentication.JWTAuthentication', 
        'rest_framework.authentication.SessionAuthentication', 
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],

}

# JWT Settings - Increase token lifetimes
from datetime import timedelta

# backend/hotel_project/settings.py

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=30),  
    'REFRESH_TOKEN_LIFETIME': timedelta(days=60), 
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': False,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
}

# ====== CORS SETTINGS ======
CORS_ALLOWED_ORIGINS_CONFIG = config('CORS_ALLOWED_ORIGINS', default='').strip()
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:3003",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
    "http://127.0.0.1:3003",
]
if CORS_ALLOWED_ORIGINS_CONFIG:
    for origin in CORS_ALLOWED_ORIGINS_CONFIG.split(','):
        if origin.strip() and origin.strip() not in CORS_ALLOWED_ORIGINS:
            CORS_ALLOWED_ORIGINS.append(origin.strip())

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = config('CORS_ALLOW_ALL_ORIGINS', default=True, cast=bool)

CORS_ALLOW_METHODS = [
    'DELETE',
    'GET',
    'OPTIONS',
    'PATCH',
    'POST',
    'PUT',
]

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'x-korapay-signature',
]

# CSRF Trusted Origins
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:3003",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "http://127.0.0.1:3002",
    "http://127.0.0.1:3003",
    "https://*.onrender.com",
    "https://*.vercel.app",
]
if RENDER_EXTERNAL_HOSTNAME:
    CSRF_TRUSTED_ORIGINS.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

# Email settings (development)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'ClASSIC HOTEL <noreply@tsghotel.com.ng>'
SERVER_EMAIL = 'errors@tsghotel.com.ng'

# Payment Settings (Korapay)
KORAPAY_PUBLIC_KEY = config('KORAPAY_PUBLIC_KEY', default=os.environ.get('KORAPAY_PUBLIC_KEY', 'pk_test_korapay_public_key'))
KORAPAY_SECRET_KEY = config('KORAPAY_SECRET_KEY', default=os.environ.get('KORAPAY_SECRET_KEY', 'sk_test_korapay_secret_key'))
KORAPAY_SANDBOX = config('KORAPAY_SANDBOX', default=True, cast=bool)
KORAPAY_CALLBACK_URL = config('KORAPAY_CALLBACK_URL', default='http://localhost:3000/payment/verify')
KORAPAY_WEBHOOK_SECRET = config('KORAPAY_WEBHOOK_SECRET', default=os.environ.get('KORAPAY_WEBHOOK_SECRET', ''))

# Migration for payments
MIGRATION_MODULES = {
    'payments': 'payments.migrations',
}