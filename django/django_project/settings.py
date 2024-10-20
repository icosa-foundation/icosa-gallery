"""
Django settings for icosa project.

Generated by 'django-admin startproject' using Django 4.2.11.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/4.2/ref/settings/
"""

import os
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
if os.environ.get("DJANGO_DISABLE_CACHE"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.dummy.DummyCache",
        }
    }

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/4.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
JWT_KEY = os.environ.get("JWT_SECRET_KEY")


# SECURITY WARNING: don't run with debug turned on in production!
DEPLOYMENT_ENV = os.environ.get("DEPLOYMENT_ENV")
DEPLOYMENT_HOST_WEB = os.environ.get("DEPLOYMENT_HOST_WEB")
DEPLOYMENT_HOST_API = os.environ.get("DEPLOYMENT_HOST_API")
DEBUG = False
if DEPLOYMENT_ENV in [
    "development",
    "local",
]:
    DEBUG = True

SITE_ID = 1

ALLOWED_HOSTS = [
    "localhost",
    f"{DEPLOYMENT_HOST_WEB}",
]
if DEPLOYMENT_HOST_API:
    ALLOWED_HOSTS.append(f"{DEPLOYMENT_HOST_API}")

CSRF_TRUSTED_ORIGINS = [
    "https://*.127.0.0.1",
    f"https://{DEPLOYMENT_HOST_WEB}",
]
if DEPLOYMENT_HOST_API:
    CSRF_TRUSTED_ORIGINS.append(f"https://{DEPLOYMENT_HOST_API}")

DJANGO_DEFAULT_FILE_STORAGE = os.environ.get("DJANGO_DEFAULT_FILE_STORAGE")
DJANGO_STORAGE_URL = os.environ.get("DJANGO_STORAGE_URL")
DJANGO_STORAGE_BUCKET_NAME = os.environ.get("DJANGO_STORAGE_BUCKET_NAME")
DJANGO_STORAGE_REGION_NAME = os.environ.get("DJANGO_STORAGE_REGION_NAME")
DJANGO_STORAGE_ACCESS_KEY = os.environ.get("DJANGO_STORAGE_ACCESS_KEY")
DJANGO_STORAGE_SECRET_KEY = os.environ.get("DJANGO_STORAGE_SECRET_KEY")

if (
    DJANGO_STORAGE_URL
    and DJANGO_STORAGE_BUCKET_NAME
    and DJANGO_STORAGE_REGION_NAME
    and DJANGO_STORAGE_ACCESS_KEY
    and DJANGO_STORAGE_SECRET_KEY
):

    # Not using the STORAGES dict here as there is a bug in django-storages
    # that means we must set these separately.
    DEFAULT_FILE_STORAGE = DJANGO_DEFAULT_FILE_STORAGE
    AWS_DEFAULT_ACL = "public-read"
    AWS_ACCESS_KEY_ID = DJANGO_STORAGE_ACCESS_KEY
    AWS_SECRET_ACCESS_KEY = DJANGO_STORAGE_SECRET_KEY
    AWS_STORAGE_BUCKET_NAME = DJANGO_STORAGE_BUCKET_NAME
    AWS_S3_REGION_NAME = DJANGO_STORAGE_REGION_NAME
    AWS_S3_ENDPOINT_URL = DJANGO_STORAGE_URL
else:
    DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"


# Application definition

APPEND_SLASH = False

INSTALLED_APPS = [
    "icosa",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.staticfiles",
    "django.contrib.messages",
    "compressor",
    "corsheaders",
    "huey.contrib.djhuey",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.cache.UpdateCacheMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.cache.FetchFromCacheMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "icosa.middleware.redirect.RemoveSlashMiddleware",
]

ROOT_URLCONF = "django_project.urls"
LOGIN_URL = "/login"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "icosa.context_processors.owner_processor",
            ],
            "loaders": [
                "django.template.loaders.app_directories.Loader",
            ],
        },
    },
]

EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "localhost")
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_PORT = 587
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "")

WSGI_APPLICATION = "django_project.wsgi.application"

PAGINATION_PER_PAGE = 40

ACCESS_TOKEN_EXPIRE_MINUTES = 20_160  # 2 weeks

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB"),
        "USER": os.environ.get("POSTGRES_USER"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD"),
        "HOST": "db",
        "PORT": 5432,
    }
}


# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = os.path.join(BASE_DIR, "static")
STATICFILES_FINDERS = (
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    "compressor.finders.CompressorFinder",
)

# Media files
# TODO make this configurable based on file storage. We should have an absolute
# path for local storage and a root-relative path for storages such as s3.
MEDIA_ROOT = "icosa"
# MEDIA_URL = "..."  # unused with django-storages

# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Cors settings


CORS_ALLOW_ALL_ORIGINS = bool(
    os.environ.get("DJANGO_CORS_ALLOW_ALL_ORIGINS", False)
)

if os.environ.get("DJANGO_CORS_ALLOWED_ORIGINS", None) is not None:
    CORS_ALLOWED_ORIGINS = [
        x
        for x in os.environ.get(
            "DJANGO_CORS_ALLOWED_ORIGINS",
            "",
        ).split(",")
        if x
    ]

# Compressor settings

COMPRESS_PRECOMPILERS = (("text/x-scss", "django_libsass.SassCompiler"),)

# Huey settings

HUEY = {
    "huey_class": "huey.SqliteHuey",  # Huey implementation to use.
    "results": True,  # Store return values of tasks.
    "store_none": False,  # If a task returns None, do not save to results.
    "immediate": False,  # If DEBUG=True, run synchronously.
    "utc": True,  # Use UTC for all times internally.
    "consumer": {
        "workers": 1,
        "worker_type": "thread",
        "initial_delay": 0.1,  # Smallest polling interval, same as -d.
        "backoff": 1.15,  # Exponential backoff using this rate, -b.
        "max_delay": 10.0,  # Max possible polling interval, -m.
        "scheduler_interval": 1,  # Check schedule every second, -s.
        "periodic": True,  # Enable crontab feature.
        "check_worker_health": True,  # Enable worker health checks.
        "health_check_interval": 1,  # Check worker health every second.
    },
}

# Ninja settings

NINJA_PAGINATION_PER_PAGE = 20

# Registration settings

ALLOWED_REGISTRATION_EMAILS = [
    x
    for x in os.environ.get(
        "DJANGO_ALLOWED_REGISTRATION_EMAILS",
        "",
    ).split(",")
    if x
]


# Category settings
#
# Google Poly originally came with a set of categories that were not
# user-editable. The official install of Icosa Gallery respects these, but
# allows user installations to override them in settings. To avoid hard-coding
# the categories, which would result in a migration and source code changes to
# amend them, we are instead mapping from an int to a string here.
ASSET_CATEGORIES_MAP = {
    1: ("Art", "art"),
    2: ("Animals & Pets", "animals"),
    3: ("Architecture", "architecture"),
    4: ("Places & Scenes", "places"),
    5: ("Unused", "unused"),
    6: ("Food & Drink", "food"),
    7: ("Nature", "nature"),
    8: ("People & Characters", "people"),
    9: ("Tools & Technology", "tech"),
    10: ("Transport", "transport"),
    11: ("Miscellaneous", "miscellaneous"),
    12: ("Objects", "objects"),
    13: ("Culture & Humanity", "culture"),
    14: ("Current Events", "current_events"),
    15: ("Furniture & Home", "home"),
    16: ("History", "history"),
    17: ("Science", "science"),
    18: ("Sports & Fitness", "sport"),
    19: ("Travel & Leisure", "travel"),
}
# TODO(james): move this to somewhere else so that categories can be overridden
# in local settings and still be reverse mapped correctly.
ASSET_CATEGORIES_REVERSE_MAP = {
    v[1]: k for k, v in ASSET_CATEGORIES_MAP.items()
}
ASSET_CATEGORY_LABEL_MAP = {
    v[1]: v[0] for k, v in ASSET_CATEGORIES_MAP.items()
}
