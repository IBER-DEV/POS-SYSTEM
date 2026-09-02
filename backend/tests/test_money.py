"""Decision D1: shelf prices include tax, so tax is extracted, never added."""
from __future__ import annotations

from decimal import Decimal

import pytest

from apps.core.money import round_to_currency_unit, split_tax_from_gross


@pytest.mark.parametrize(
    "gross,rate,base,tax",
    [
        ("119000.00", 19, "100000.00", "19000.00"),
        ("459900.00", 19, "386470.59", "73429.41"),
        ("50000.00", 0, "50000.00", "0.00"),
        ("105000.00", 5, "100000.00", "5000.00"),
    ],
)
def test_tax_is_split_out_of_the_price(gross, rate, base, tax):
    assert split_tax_from_gross(gross, rate) == (Decimal(base), Decimal(tax))


def test_base_plus_tax_reconstructs_the_price():
    base, tax = split_tax_from_gross("459900.00", 19)
    assert base + tax == Decimal("459900.00")


def test_cop_totals_round_to_whole_pesos():
    assert round_to_currency_unit("386470.59", decimals=0) == Decimal("386471")
