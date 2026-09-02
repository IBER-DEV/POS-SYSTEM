"""Gap-free document numbering."""
from __future__ import annotations

from django.db import transaction

from .models import DocumentSequence

DEFAULT_PREFIXES = {
    DocumentSequence.DocumentType.SALE: "V-",
    DocumentSequence.DocumentType.PURCHASE: "C-",
    DocumentSequence.DocumentType.REFUND: "D-",
}


def next_document_number(*, organization, location, document_type: str) -> str:
    """Reserve the next number for this (location, document type).

    Must be called inside the transaction that creates the document: if that
    transaction rolls back, the number is released with it and no gap appears.
    Call it as late as possible, since the row stays locked until commit.
    """
    sequence, _ = DocumentSequence.objects.get_or_create(
        organization=organization,
        location=location,
        document_type=document_type,
        defaults={"prefix": DEFAULT_PREFIXES.get(document_type, "")},
    )

    with transaction.atomic():
        locked = DocumentSequence.objects.select_for_update().get(pk=sequence.pk)
        locked.last_number += 1
        locked.save(update_fields=["last_number", "updated_at"])
        return f"{locked.prefix}{locked.last_number:06d}"
