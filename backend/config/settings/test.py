import tempfile

from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ["*"]

# Uploaded test files (product photos) go to a throwaway directory, never
# into the real media/ tree the dev server serves from.
MEDIA_ROOT = tempfile.mkdtemp(prefix="pos-test-media-")

# Fast, deterministic hashing keeps the business-rule suite quick.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
AUTH_PASSWORD_VALIDATORS = []

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Static file serving is irrelevant to the API tests and whitenoise warns
# on every request when collectstatic has not run.
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]

# Throttling would make test outcomes depend on execution order.
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []  # noqa: F405
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {}  # noqa: F405

DATABASES["default"]["NAME"] = env("DB_NAME", default="pos")  # noqa: F405
