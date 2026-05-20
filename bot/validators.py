"""
validators.py — Input validation for trading bot CLI parameters.

Validates symbol names, sides, order types, quantities, and prices
*before* any API call is made, giving the user instant, clear feedback.

# TODO: Fetch live exchange info from Binance and validate LOT_SIZE /
#       PRICE_FILTER / MIN_NOTIONAL constraints dynamically per symbol.
# TODO: Add position-size guard (max % of account balance per trade).
# TODO: Cache symbol metadata so repeated validation doesn't hit the API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from bot.logging_config import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants — update as Binance adds new order types
# ---------------------------------------------------------------------------

VALID_SIDES: frozenset[str] = frozenset({"BUY", "SELL"})
VALID_ORDER_TYPES: frozenset[str] = frozenset({"MARKET", "LIMIT"})
VALID_TIME_IN_FORCE: frozenset[str] = frozenset({"GTC", "IOC", "FOK"})

# Binance futures symbols are all-caps alphanumeric (e.g. BTCUSDT, ETHUSDT)
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{3,20}$")

# Reasonable sanity bounds — NOT Binance's official filter limits
MIN_QUANTITY = 1e-8
MAX_QUANTITY = 1_000_000.0
MIN_PRICE = 1e-8
MAX_PRICE = 10_000_000.0


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class ValidationResult:
    valid: bool
    error: Optional[str] = None

    @classmethod
    def ok(cls) -> "ValidationResult":
        return cls(valid=True)

    @classmethod
    def fail(cls, reason: str) -> "ValidationResult":
        logger.warning("Validation failed: %s", reason)
        return cls(valid=False, error=reason)


# ---------------------------------------------------------------------------
# Individual validators
# ---------------------------------------------------------------------------

def validate_symbol(symbol: str) -> ValidationResult:
    """
    Ensure the symbol looks like a valid Binance futures pair.

    # TODO: Cross-check against /fapi/v1/exchangeInfo for exact symbol list.
    """
    if not symbol:
        return ValidationResult.fail("Symbol cannot be empty.")
    upper = symbol.upper()
    if not SYMBOL_PATTERN.match(upper):
        return ValidationResult.fail(
            f"Invalid symbol '{symbol}'. Must be 3–20 uppercase letters/digits "
            f"(e.g. BTCUSDT, ETHUSDT)."
        )
    logger.debug("Symbol '%s' passed validation.", upper)
    return ValidationResult.ok()


def validate_side(side: str) -> ValidationResult:
    """Ensure the side is BUY or SELL."""
    if not side:
        return ValidationResult.fail("Side cannot be empty.")
    upper = side.upper()
    if upper not in VALID_SIDES:
        return ValidationResult.fail(
            f"Invalid side '{side}'. Choose from: {', '.join(sorted(VALID_SIDES))}."
        )
    logger.debug("Side '%s' passed validation.", upper)
    return ValidationResult.ok()


def validate_order_type(order_type: str) -> ValidationResult:
    """Ensure the order type is one we support."""
    if not order_type:
        return ValidationResult.fail("Order type cannot be empty.")
    upper = order_type.upper()
    if upper not in VALID_ORDER_TYPES:
        return ValidationResult.fail(
            f"Invalid order type '{order_type}'. "
            f"Choose from: {', '.join(sorted(VALID_ORDER_TYPES))}."
        )
    logger.debug("Order type '%s' passed validation.", upper)
    return ValidationResult.ok()


def validate_quantity(quantity_str: str) -> ValidationResult:
    """Parse and range-check the quantity string."""
    if not quantity_str:
        return ValidationResult.fail("Quantity cannot be empty.")
    try:
        qty = float(quantity_str)
    except ValueError:
        return ValidationResult.fail(
            f"Quantity '{quantity_str}' is not a valid number."
        )
    if qty <= 0:
        return ValidationResult.fail("Quantity must be greater than zero.")
    if qty < MIN_QUANTITY:
        return ValidationResult.fail(
            f"Quantity {qty} is below the minimum allowed ({MIN_QUANTITY})."
        )
    if qty > MAX_QUANTITY:
        return ValidationResult.fail(
            f"Quantity {qty} exceeds the maximum allowed ({MAX_QUANTITY})."
        )
    logger.debug("Quantity %.8f passed validation.", qty)
    return ValidationResult.ok()


def validate_price(price_str: str | None, order_type: str) -> ValidationResult:
    """
    Validate price field.

    - MARKET orders must NOT provide a price (ignored / misleading).
    - LIMIT orders MUST provide a positive price.

    # TODO: Enforce PRICE_FILTER (tickSize) from exchange info.
    """
    upper_type = order_type.upper() if order_type else ""

    if upper_type == "MARKET":
        if price_str is not None and price_str != "":
            logger.warning(
                "Price '%s' supplied for MARKET order — it will be ignored.", price_str
            )
        return ValidationResult.ok()

    if upper_type == "LIMIT":
        if not price_str:
            return ValidationResult.fail("Price is required for LIMIT orders.")
        try:
            price = float(price_str)
        except ValueError:
            return ValidationResult.fail(
                f"Price '{price_str}' is not a valid number."
            )
        if price <= 0:
            return ValidationResult.fail("Price must be greater than zero.")
        if price < MIN_PRICE:
            return ValidationResult.fail(
                f"Price {price} is below the minimum allowed ({MIN_PRICE})."
            )
        if price > MAX_PRICE:
            return ValidationResult.fail(
                f"Price {price} exceeds the maximum sanity cap ({MAX_PRICE})."
            )
        logger.debug("Price %.8f passed validation.", price)
        return ValidationResult.ok()

    # Unknown order type — let validate_order_type handle reporting
    return ValidationResult.ok()


def validate_time_in_force(tif: str, order_type: str) -> ValidationResult:
    """Validate timeInForce; only relevant for LIMIT orders."""
    if order_type.upper() != "LIMIT":
        return ValidationResult.ok()
    upper = tif.upper()
    if upper not in VALID_TIME_IN_FORCE:
        return ValidationResult.fail(
            f"Invalid timeInForce '{tif}'. "
            f"Choose from: {', '.join(sorted(VALID_TIME_IN_FORCE))}."
        )
    return ValidationResult.ok()


# ---------------------------------------------------------------------------
# Composite validator — validates a full order spec at once
# ---------------------------------------------------------------------------

@dataclass
class OrderSpec:
    symbol: str
    side: str
    order_type: str
    quantity: str
    price: Optional[str] = None
    time_in_force: str = "GTC"


def validate_order_spec(spec: OrderSpec) -> list[str]:
    """
    Run all validators against a complete order specification.

    Returns a list of error messages (empty list → all valid).

    # TODO: Add cross-field checks, e.g. price vs current market price
    #       to warn user if a limit order is far outside the market.
    """
    errors: list[str] = []

    checks = [
        validate_symbol(spec.symbol),
        validate_side(spec.side),
        validate_order_type(spec.order_type),
        validate_quantity(spec.quantity),
        validate_price(spec.price, spec.order_type),
        validate_time_in_force(spec.time_in_force, spec.order_type),
    ]

    for result in checks:
        if not result.valid and result.error:
            errors.append(result.error)

    if errors:
        logger.warning("Order spec validation failed with %d error(s): %s", len(errors), errors)
    else:
        logger.info("Order spec validated successfully: %s", spec)

    return errors
