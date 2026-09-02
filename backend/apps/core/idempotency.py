"""Idempotency for critical writes.

Contract:
  * The client sends a stable key (HTTP `Idempotency-Key`, or `operation_id`
    for an operation queued offline).
  * Same key + same payload  -> the original response is replayed, the
    operation runs exactly once.
  * Same key + different payload -> 409, the key is not reusable.
  * Key still running -> 409, the caller retries later.

The reservation row is committed in its own transaction *before* the business
transaction, so a concurrent duplicate collides on the unique index instead of
running twice. If the operation fails, the reservation is released so a
legitimate retry can succeed.
"""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager

from django.db import IntegrityError, transaction
from django.utils import timezone

from .exceptions import IdempotencyConflict, OperationInProgress
from .json import to_jsonable
from .models import IdempotencyKey

IDEMPOTENCY_HEADER = "Idempotency-Key"


def hash_payload(payload) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class ReplayedResponse(Exception):
    """Signals that a stored response should be returned as-is."""

    def __init__(self, status_code: int, body):
        self.status_code = status_code
        self.body = body
        super().__init__("Idempotent replay")


@contextmanager
def idempotent(*, organization, key: str, endpoint: str, payload):
    """Guard a critical write. Yields a record the caller fills with the result.

    Usage:
        with idempotent(...) as record:
            result = do_the_work()
            record.set_response(201, serialized)
    """
    request_hash = hash_payload(payload)

    try:
        with transaction.atomic():
            entry = IdempotencyKey.objects.create(
                organization=organization,
                key=key,
                endpoint=endpoint,
                request_hash=request_hash,
            )
    except IntegrityError:
        existing = IdempotencyKey.objects.filter(organization=organization, key=key).first()
        if existing is None:  # pragma: no cover - only under a concurrent delete
            raise OperationInProgress() from None
        if existing.request_hash != request_hash:
            raise IdempotencyConflict(
                "Idempotency key already used with a different payload.",
                key=key,
            ) from None
        if existing.status == IdempotencyKey.Status.COMPLETED:
            raise ReplayedResponse(existing.response_status, existing.response_body) from None
        raise OperationInProgress() from None

    record = _Record(entry)
    try:
        yield record
    except Exception:
        # Release the key so the client can retry the operation legitimately.
        IdempotencyKey.objects.filter(pk=entry.pk).delete()
        raise

    entry.status = IdempotencyKey.Status.COMPLETED
    entry.response_status = record.response_status
    entry.response_body = record.response_body
    entry.completed_at = timezone.now()
    entry.save(update_fields=["status", "response_status", "response_body", "completed_at", "updated_at"])


class _Record:
    def __init__(self, entry: IdempotencyKey):
        self.entry = entry
        self.response_status = 200
        self.response_body = None

    def set_response(self, status_code: int, body) -> None:
        self.response_status = status_code
        self.response_body = to_jsonable(body)
