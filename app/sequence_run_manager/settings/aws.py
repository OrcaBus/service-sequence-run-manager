# -*- coding: utf-8 -*-
"""AWS Django settings

Usage:
- export DJANGO_SETTINGS_MODULE=sequence_run_manager.settings.aws
"""
import copy
import json
import logging
from types import SimpleNamespace

from environ import Env
from libumccr.aws import libsm

from .base import *  # noqa

logger = logging.getLogger(__name__)

DEBUG = False
PG_HOST = os.environ.get("PG_HOST")
PG_USER = os.environ.get("PG_USER")
PG_DB_NAME = os.environ.get("PG_DB_NAME")


DATABASES = {
    "default": {
        "HOST": PG_HOST,
        "USER": PG_USER,
        "NAME": PG_DB_NAME,
        "ENGINE": 'django_iam_dbauth.aws.postgresql',
        "OPTIONS": {
            "use_iam_auth": True,
            "sslmode": "require",
            "resolve_cname_enabled": False,
        }
    }
}

CORS_ORIGIN_ALLOW_ALL = False
CORS_ALLOW_CREDENTIALS = False

# FIXME: https://github.com/umccr/infrastructure/issues/272
CORS_ALLOWED_ORIGINS = [
    "https://portal.umccr.org",
    "https://portal.prod.umccr.org",
    "https://portal.stg.umccr.org",
    "https://portal.dev.umccr.org",
    "https://data.umccr.org",
    "https://data.prod.umccr.org",
    "https://data.dev.umccr.org",
    "https://data.stg.umccr.org",
]

CSRF_TRUSTED_ORIGINS = copy.deepcopy(CORS_ALLOWED_ORIGINS)
