import hashlib
import hmac
import time
from urllib.parse import urlencode
import httpx
from bot.logging_config import get_logger



"""
client.py — Binance Futures Testnet API client wrapper.
Handles authentication (HMAC-SHA256), signed/unsigned requests,
and base HTTP communication. All raw API interactions live here
so the rest of the codebase never touches requests directly.
"""

# TODO: Add WebSocket support for real-time price streaming
# TODO: Add connection pooling / session reuse for high-frequency trading
# TODO: Support Ed25519 API keys (newer Binance key type)
# TODO: Implement automatic rate-limit back-off based on response headers


logger = get_logger(__name__)

TESTNET_BASE_URL = "https://testnet.binancefuture.com"
RECV_WINDOW = 5000  # milliseconds; how long the server accepts the request


class BinanceClientError(Exception):
    """Raised when the Binance API returns an error payload."""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"Binance API error {code}: {message}")


class NetworkError(Exception):
    """Raised on connectivity / timeout problems."""


class BinanceFuturesClient:
    """
    Thin wrapper around the Binance USDT-M Futures Testnet REST API.
    Usage
    -----
    client = BinanceFuturesClient(api_key="...", api_secret="...")
    info   = client.get_exchange_info()
    order  = client.place_order(symbol="BTCUSDT", side="BUY",
                                order_type="MARKET", quantity=0.001)
    """

    def __init__(self, api_key: str, api_secret: str, base_url: str = TESTNET_BASE_URL):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        # TODO: make timeout configurable via env / config file
        self._http = httpx.Client(timeout=10.0)

    # Internal helpers
    def _timestamp(self) -> int:
        return int(time.time() * 1000)

    def _sign(self, params: dict) -> str:
        """Return HMAC-SHA256 signature for the given parameter dict."""
        query = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def _headers(self) -> dict:
        return {
            "X-MBX-APIKEY": self.api_key,
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def _get(self, endpoint: str, params: dict | None = None, signed: bool = False) -> dict:
        """Issue a GET request, optionally signing the payload."""
        params = params or {}
        if signed:
            params["timestamp"] = self._timestamp()
            params["recvWindow"] = RECV_WINDOW
            params["signature"] = self._sign(params)

        url = f"{self.base_url}{endpoint}"
        logger.debug("GET %s params=%s", url, params)
        try:
            resp = self._http.get(url, params=params, headers=self._headers())
        except httpx.RequestError as exc:
            logger.error("Network error on GET %s: %s", url, exc)
            raise NetworkError(str(exc)) from exc

        return self._handle_response(resp)

    def _post(self, endpoint: str, params: dict, signed: bool = True) -> dict:
        """Issue a POST request (always form-encoded, signed by default)."""
        if signed:
            params["timestamp"] = self._timestamp()
            params["recvWindow"] = RECV_WINDOW
            params["signature"] = self._sign(params)

        url = f"{self.base_url}{endpoint}"
        logger.info("POST %s body=%s", url, {k: v for k, v in params.items() if k != "signature"})
        try:
            resp = self._http.post(url, data=params, headers=self._headers())
        except httpx.RequestError as exc:
            logger.error("Network error on POST %s: %s", url, exc)
            raise NetworkError(str(exc)) from exc

        return self._handle_response(resp)

    @staticmethod
    def _handle_response(resp: httpx.Response) -> dict:
        """Parse the JSON response and raise on API-level errors."""
        logger.debug("Response status=%s body=%s", resp.status_code, resp.text[:500])
        try:
            data = resp.json()
        except Exception as exc:
            logger.error("Failed to parse JSON: %s | raw=%s", exc, resp.text[:200])
            raise NetworkError(f"Non-JSON response (HTTP {resp.status_code})") from exc

        if isinstance(data, dict) and "code" in data and data["code"] != 200:
            # Binance error payloads: {"code": -1121, "msg": "Invalid symbol."}
            raise BinanceClientError(code=data["code"], message=data.get("msg", "Unknown error"))

        return data

    # Public API methods
    def ping(self) -> bool:
        """Return True if the testnet is reachable."""
        try:
            self._get("/fapi/v1/ping")
            logger.info("Ping successful — testnet is reachable.")
            return True
        except (NetworkError, BinanceClientError) as exc:
            logger.error("Ping failed: %s", exc)
            return False

    def get_server_time(self) -> int:
        """Return server time in milliseconds."""
        data = self._get("/fapi/v1/time")
        return data["serverTime"]

    def get_exchange_info(self) -> dict:
        """
        Return exchange info including all tradeable symbols and their
        filters (LOT_SIZE, PRICE_FILTER, MIN_NOTIONAL, etc.).
        # TODO: Cache this response with a short TTL to reduce latency
        """
        return self._get("/fapi/v1/exchangeInfo")

    def get_symbol_price(self, symbol: str) -> float:
        """Return the latest mark price for *symbol*."""
        data = self._get("/fapi/v1/ticker/price", params={"symbol": symbol.upper()})
        return float(data["price"])

    def get_account_balance(self) -> list[dict]:
        """
        Return a list of asset balances for the futures account.
        # TODO: Add a helper that returns only non-zero balances
        """
        return self._get("/fapi/v2/balance", signed=True)


        # TODO: add stop_price for STOP_MARKET / STOP orders
        # TODO: add reduce_only flag for closing positions
        # TODO: add client_order_id for idempotent retries

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: float,
        price: float | None = None,
        time_in_force: str = "GTC",) -> dict:

        """
        Place a MARKET or LIMIT order on USDT-M Futures Testnet.
        Parameters
        ----------
        symbol        : e.g. "BTCUSDT"
        side          : "BUY" or "SELL"
        order_type    : "MARKET" or "LIMIT"
        quantity      : contract quantity
        price         : required for LIMIT orders
        time_in_force : "GTC" | "IOC" | "FOK"  (ignored for MARKET)
        """

        params: dict = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": str(quantity),
        }

        if order_type.upper() == "LIMIT":
            if price is None:
                raise ValueError("price is required for LIMIT orders")
            params["price"] = str(price)
            params["timeInForce"] = time_in_force

        logger.info(
            "Placing order | symbol=%s side=%s type=%s qty=%s price=%s",
            symbol, side, order_type, quantity, price,
        )
        response = self._post("/fapi/v1/order", params=params)
        logger.info("Order placed successfully | orderId=%s status=%s", response.get("orderId"), response.get("status"))
        return response

    def get_order(self, symbol: str, order_id: int) -> dict:
        """
        Fetch the current state of an existing order.
        # TODO: Add polling helper that waits until order is FILLED
        """
        return self._get(
            "/fapi/v1/order",
            params={"symbol": symbol.upper(), "orderId": order_id},
            signed=True,
        )

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """
        Cancel an open order.
        # TODO: Add cancel_all_orders(symbol) helper
        """
        params = {"symbol": symbol.upper(), "orderId": order_id}
        params["timestamp"] = self._timestamp()
        params["recvWindow"] = RECV_WINDOW
        params["signature"] = self._sign(params)
        url = f"{self.base_url}/fapi/v1/order"
        logger.info("Cancelling order %s for %s", order_id, symbol)
        try:
            resp = self._http.delete(url, params=params, headers=self._headers())
        except httpx.RequestError as exc:
            raise NetworkError(str(exc)) from exc
        return self._handle_response(resp)

    def close(self):
        """Release the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
