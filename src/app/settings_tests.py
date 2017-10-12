from settings import *


CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
    }
}

PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']

logging.disable(logging.CRITICAL)

# only test our apps
INSTALLED_APPS = POOLBOT_APPS
