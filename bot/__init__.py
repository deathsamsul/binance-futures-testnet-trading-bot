from bot.client import BinanceFuturesClient, BinanceClientError, NetworkError
from bot.orders import place_order, place_market_order, place_limit_order, OrderResult
from bot.validators import validate_order_spec, OrderSpec


"""
trading_bot/bot/__init__.py
Exposes the public API of the bot package so callers can do:
    from bot import BinanceFuturesClient, place_order
"""
# TODO: add __version__ from importlib.metadata once package is published.



__all__ = [
    "BinanceFuturesClient",
    "BinanceClientError",
    "NetworkError",
    "place_order",
    "place_market_order",
    "place_limit_order",
    "OrderResult",
    "validate_order_spec",
    "OrderSpec",
]
