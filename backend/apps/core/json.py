"""JSON normalisation for JSONField payloads.

DRF serializer output holds real Python objects (UUID, Decimal, datetime) which
psycopg cannot write into a jsonb column. Anything stored in a JSONField -
audit metadata, idempotent response snapshots, sync payloads - goes through
here first.
"""
from __future__ import annotations

import json

from django.core.serializers.json import DjangoJSONEncoder


def to_jsonable(value):
    if value is None:
        return None
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))
