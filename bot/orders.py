from __future__ import annotations
import json
import logging
from typing import Optional
from bot.client import BinanceClientError, BinanceFuturesClient, NetworkError
from bot.logging_config import get_logger
from bot.validators import OrderSpec, validate_order_spec




"""
orders.py — High-level order placement logic.
Sits between the CLI and the raw API client.  Responsibilities:
  • Assemble the order payload from validated inputs.
  • Call the client.
  • Format and return a human-readable summary dict.
  • Log the full trade record to the trade_history logger.

"""

# TODO: Add STOP_LIMIT order type (stopPrice param).
# TODO: Add OCO (One-Cancels-the-Other) order support.
# TODO: Add TWAP execution strategy (split qty into time-sliced chunks).
# TODO: Add Grid trading helper (place laddered limit orders).
# TODO: Persist each trade to a SQLite / PostgreSQL DB for history queries.
# TODO: Add position-size calculator (risk % of balance → quantity).



logger = get_logger(__name__)

# Dedicated trade-history logger (writes to logs/trade_history.log)
trade_logger = get_logger("trade_history")


# Result dataclass--------------------------------
class OrderResult:
    """Encapsulates the outcome of an order attempt."""

    def __init__(
        self,
        success: bool,
        raw_response: dict | None = None,
        error_message: str | None = None,
    ):
        self.success = success
        self.raw = raw_response or {}
        self.error_message = error_message

    # Convenience accessors for the most-needed fields
    @property
    def order_id(self) -> int | None:
        return self.raw.get("orderId")

    @property
    def status(self) -> str:
        return self.raw.get("status", "N/A")

    @property
    def executed_qty(self) -> str:
        return self.raw.get("executedQty", "0")

    @property
    def avg_price(self) -> str:
        return self.raw.get("avgPrice", self.raw.get("price", "N/A"))

    @property
    def symbol(self) -> str:
        return self.raw.get("symbol", "N/A")

    @property
    def side(self) -> str:
        return self.raw.get("side", "N/A")

    @property
    def order_type(self) -> str:
        return self.raw.get("type", "N/A")

    def summary(self) -> dict:
        """Return a clean dict suitable for CLI display."""
        if not self.success:
            return {"success": False, "error": self.error_message}
        return {
            "success": True,
            "orderId": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "type": self.order_type,
            "status": self.status,
            "executedQty": self.executed_qty,
            "avgPrice": self.avg_price,
            "clientOrderId": self.raw.get("clientOrderId", "N/A"),
            "updateTime": self.raw.get("updateTime", "N/A"),
        }



# Core order function -----------------------------
def place_order(client: BinanceFuturesClient,symbol: str,side: str,order_type: str,quantity: str,
                price: Optional[str] = None,time_in_force: str = "GTC",dry_run: bool = False,) -> OrderResult:
    
    """
    Validate inputs, optionally preview (dry_run), then place the order.
    Parameters
    ----------
    client        : authenticated BinanceFuturesClient
    symbol        : e.g. "BTCUSDT"
    side          : "BUY" or "SELL"
    order_type    : "MARKET" or "LIMIT"
    quantity      : string quantity (validated here)
    price         : string price (required for LIMIT)
    time_in_force : "GTC" | "IOC" | "FOK"
    dry_run       : if True, validate only — do NOT send to the API
    """
    # TODO: wire --dry-run flag through CLI


    # 1. Validate
    spec = OrderSpec(symbol=symbol,side=side,order_type=order_type,
                     quantity=quantity,price=price,time_in_force=time_in_force,)
    
    errors = validate_order_spec(spec)
    if errors:
        msg = " | ".join(errors)
        logger.error("Order rejected at validation: %s", msg)
        return OrderResult(success=False, error_message=msg)

    # 2. Dry-run gate
    if dry_run:
        logger.info("DRY RUN — order NOT sent to API. Spec: %s", spec)
        return OrderResult(
            success=True,
            raw_response={
                "orderId": "DRY_RUN",
                "symbol": symbol.upper(),
                "side": side.upper(),
                "type": order_type.upper(),
                "status": "DRY_RUN",
                "executedQty": "0",
                "avgPrice": price or "MARKET",
            },
        )

    # 3. Place via client
    try:
        qty_float = float(quantity)
        price_float = float(price) if price else None

        raw = client.place_order(symbol=symbol, side=side,order_type=order_type,
                                 quantity=qty_float,price=price_float, time_in_force=time_in_force,)
        
        result = OrderResult(success=True, raw_response=raw)
        _log_trade(result, "PLACED")
        return result

    except BinanceClientError as exc:
        logger.error(
            "API error placing order: code=%s msg=%s", exc.code, exc.message)
        return OrderResult( success=False,error_message=f"[API {exc.code}] {exc.message}", )
    
    except NetworkError as exc:
        logger.error("Network error placing order: %s", exc)
        return OrderResult(success=False, error_message=f"[NETWORK] {exc}",)
    
    except Exception as exc:
        logger.exception("Unexpected error placing order: %s", exc)
        return OrderResult(success=False, error_message=f"[UNEXPECTED] {exc}",)


# Trade history logger----------------------------
def _log_trade(result: OrderResult, action: str) -> None:
    """
    Write a single-line JSON record to the trade_history logger.
    Each line is a self-contained trade event parseable by tools like jq.
    """
   # TODO: Extend with PnL, fees, and position impact fields.

    record = {"action": action,**result.summary(),}
    trade_logger.info(json.dumps(record, default=str))


# Convenience wrappers-------------------------------
def place_market_order(
    client: BinanceFuturesClient,
    symbol: str,
    side: str,
    quantity: str,
) -> OrderResult:
    """Shortcut for MARKET orders."""
    return place_order(client=client, symbol=symbol, side=side,
                        order_type="MARKET", quantity=quantity, price=None, )


def place_limit_order(client: BinanceFuturesClient,symbol: str,side: str,
                      quantity: str,price: str,time_in_force: str = "GTC",) -> OrderResult:
    
    """Shortcut for LIMIT orders."""
    return place_order( client=client,symbol=symbol,side=side, order_type="LIMIT",quantity=quantity,
                        price=price,time_in_force=time_in_force, )
