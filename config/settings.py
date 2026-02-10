from pathlib import Path
import os
from dotenv import load_dotenv # Asegúrate de que esto está aquí

# 1. Cargar el archivo .env
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# 2. Leer claves. Si no existen, lanzará error (mejor que fallar en silencio)
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-clave-por-defecto-para-desarrollo')

# Debug debe ser True para ver errores en pantalla
DEBUG = os.getenv('DEBUG') == 'True'

ALLOWED_HOSTS = ['*']

# 3. Aplicaciones Instaladas
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Tus apps
    'games',
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

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [], # Django busca automáticamente en carpetas 'templates' dentro de las apps
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'games.context_processors.notifications_count',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# 4. Base de Datos (SQLite por defecto)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# 5. Validadores de Contraseña
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

# 6. Internacionalización
LANGUAGE_CODE = 'es-es'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# 7. Archivos Estáticos (CSS, JS, Imágenes)
STATIC_URL = 'static/'

# IMPORTANTE: Configuración de Media (Avatares y Banners)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# 8. Configuración de Login/Logout
LOGIN_REDIRECT_URL = 'index'
LOGOUT_REDIRECT_URL = 'login'
LOGIN_URL = 'login'

# 9. CLAVES DE LA API IGDB (Leídas del .env)
IGDB_CLIENT_ID = os.getenv('IGDB_CLIENT_ID')
IGDB_CLIENT_SECRET = os.getenv('IGDB_CLIENT_SECRET')

# Tipo de campo para ID automáticos
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'