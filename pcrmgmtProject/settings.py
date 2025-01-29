# pcrmgmtProject/settings.py

import os
from pathlib import Path
from dotenv import load_dotenv
from django.db.utils import OperationalError
from django.db import connections

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET_KEY', 'fallback-secret-key')
DEBUG = os.getenv('DEBUG', 'True') == 'True'
ALLOWED_HOSTS = ['0.0.0.0', '127.0.0.1', 'pcrsrvisl', '192.168.31.205', 'localhost']
SECURE_CROSS_ORIGIN_OPENER_POLICY = None
CKEDITOR_UPLOAD_PATH = "uploads/"

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'pcrmgmtAPP',
    'ckeditor',
    'ckeditor_uploader',
]

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    # ... possibly other backends ...
]


MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'pcrmgmtProject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'pcrmgmtAPP/templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'pcrmgmtAPP.context_processors.current_theme',
            ],
        },
    },
]

WSGI_APPLICATION = 'pcrmgmtProject.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'mssql',
        'NAME': os.getenv('DB_NAME', ''),
        'USER': os.getenv('DB_USER', ''),
        'PASSWORD': os.getenv('DB_PASSWORD', ''),
        'HOST': os.getenv('DB_HOST', ''),
        'PORT': os.getenv('DB_PORT', ''),
        'OPTIONS': {'driver': 'ODBC Driver 17 for SQL Server'},
    },
    'isllogs': {
        'ENGINE': 'mssql',
        'NAME': 'isllogs',
        'USER': os.getenv('ISL_DB_USER', ''),
        'PASSWORD': os.getenv('ISL_DB_PASSWORD', ''),
        'HOST': os.getenv('ISL_DB_HOST', ''),
        'PORT': os.getenv('ISL_DB_PORT', ''),
        'OPTIONS': {'driver': 'ODBC Driver 17 for SQL Server'},
    },
    'address_db': {
        'ENGINE': 'mssql',
        'NAME': os.getenv('ADDRESS_DB_NAME', ''),
        'USER': os.getenv('ADDRESS_DB_USER', ''),
        'PASSWORD': os.getenv('ADDRESS_DB_PASSWORD', ''),
        'HOST': os.getenv('ADDRESS_DB_HOST', ''),
        'PORT': os.getenv('ADDRESS_DB_PORT', ''),
        'OPTIONS': {
            'driver': 'ODBC Driver 17 for SQL Server',
            'TrustServerCertificate': os.getenv('ADDRESS_TRUST_SERVER_CERTIFICATE', 'no') == 'yes',
        },
    },
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / "pcrmgmtAPP/static",  # Ensure this matches your directory structure
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
        'pcrmgmtAPP': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
