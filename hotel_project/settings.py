# backend/hotel_project/settings.py

import os
from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-your-secret-key-here')

DEBUG = config('DEBUG', default=True, cast=bool)

# This is fine - keeps your existing ALLOWED_HOSTS
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party apps
    'rest_framework',
    'corsheaders', 
    'rest_framework_simplejwt',
    'rest_framework.authtoken',
    'anymail',
    
    # Created apps
    'accounts',
    'rooms',
    'bookings',
    'inventory',
    'sales',
    'reports',
    'consumables',
    'payments',
]

# MIDDLEWARE - CorsMiddleware MUST be at the very top
MIDDLEWARE = [
    'bookings.middleware.PublicBypassMiddleware', 
    'accounts.middleware.DisableCSRFForAPI',
    'corsheaders.middleware.CorsMiddleware', 
    'django.middleware.security.SecurityMiddleware',
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

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
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
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Custom user model
AUTH_USER_MODEL = 'accounts.User'

FRONTEND_URL = config('FRONTEND_URL', default='http://localhost:3000')

# JWT Settings
from datetime import timedelta


REST_FRAMEWORK = {
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

# ====== CORS SETTINGS - ADD THESE AT THE BOTTOM ======
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://172.20.10.4:3000",
]

CORS_ALLOW_CREDENTIALS = True

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
]

# For development only - you can temporarily enable this
# CORS_ALLOW_ALL_ORIGINS = True

# Disable authentication for these specific paths
import re
class DisableAuthForPublicPaths:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/api/bookings/public/'):
            # Mock authentication
            from django.contrib.auth.models import AnonymousUser
            request.user = AnonymousUser()
        return self.get_response(request)

MIDDLEWARE.append('hotel_project.settings.DisableAuthForPublicPaths')

# CSRF Trusted Origins (sometimes needed)
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://172.20.10.4:3000",
]

# ====== EMAIL CONFIGURATION (BREVO) ======

# Brevo/Anymail Configuration
ANYMAIL = {
    'BREVO_API_KEY': 'your-brevo-api-key-here',  # Replace with your actual key
}

# Use Brevo as the email backend
EMAIL_BACKEND = 'anymail.backends.brevo.EmailBackend'

# Default from address (use your verified domain if you set one up)
DEFAULT_FROM_EMAIL = 'TSG HOTEL <noreply@tsghotel.com.ng>'

# For error reports
SERVER_EMAIL = 'errors@tsghotel.com.ng'

# Optional but recommended - store API key in environment variable
import os
BREVO_API_KEY = os.environ.get('BREVO_API_KEY', 'your-api-key-here')

# Email settings (development)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# For production, use:
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = 'smtp.gmail.com'
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
# EMAIL_HOST_USER = 'your-email@gmail.com'
# EMAIL_HOST_PASSWORD = 'your-app-password'
# DEFAULT_FROM_EMAIL = 'Hotel Manager <noreply@hotelmanager.com>'


# Payment Settings
KORAPAY_PUBLIC_KEY = os.environ.get('KORAPAY_PUBLIC_KEY', '')
KORAPAY_SECRET_KEY = os.environ.get('KORAPAY_SECRET_KEY', '')
KORAPAY_SANDBOX = os.environ.get('KORAPAY_SANDBOX', True)
KORAPAY_CALLBACK_URL = os.environ.get('KORAPAY_CALLBACK_URL', 'https://yourdomain.com/payments/verify')
KORAPAY_WEBHOOK_SECRET = os.environ.get('KORAPAY_WEBHOOK_SECRET', '')


# Migration for payments
MIGRATION_MODULES = {
    'payments': 'payments.migrations',
}