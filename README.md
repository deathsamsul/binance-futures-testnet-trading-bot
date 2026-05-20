# Binance Futures Testnet Trading Bot

# Binance Futures Testnet Trading Bot

> **Language:** Python 3.11+  
> **Target:** Binance USDT-M Futures **Testnet** only  
> **Base URL:** `https://testnet.binancefuture.com`

---



## Project Structure

```
trading_bot/
├── bot/
│   ├── __init__.py          # Public package exports
│   ├── client.py            # Binance REST API wrapper (HMAC auth, signing, HTTP)
│   ├── orders.py            # Order placement logic + trade history logging
│   ├── validators.py        # Input validation (symbol, side, qty, price)
│   └── logging_config.py   # Console + rotating file logging setup
├── cli.py                   # CLI entry point (place / balance / price / ping)
├── logs/
│   ├── trading_bot.log      # Full debug log (auto-created on first run)
│   ├── trade_history.log    # One JSON line per placed order
│   ├── market_order.log     # Sample MARKET order log (submission artifact)
│   └── limit_order.log      # Sample LIMIT order log + error examples
├── README.md
└── requirements.txt
```



**Layer separation:**
- `bot/client.py` — only file that touches HTTP / Binance API
- `bot/validators.py` — runs before any API call; catches bad input instantly
- `bot/orders.py` — bridges validators → client; builds result objects
- `cli.py` — handles UX only; never calls HTTP directly

---

## Setup

### 1. Register on Binance Futures Testnet

1. Go to **https://testnet.binancefuture.com**
2. Click **Register** and create an account.
3. Navigate to **API Management** → generate a new key pair.
4. Save your **API Key** and **API Secret**.

### 2. Clone and install

```bash
git clone https://github.com/<your-username>/trading-bot.git
cd trading-bot
python -m venv .venv or python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Set credentials

**Recommended — environment variables:**
```bash
export BINANCE_API_KEY="your_api_key_here"
export BINANCE_API_SECRET="your_api_secret_here"
```

**Alternative — inline flags** (visible in shell history):
```bash
python cli.py --api-key YOUR_KEY --api-secret YOUR_SECRET <command>
```

---

## How to Run

```
python cli.py [GLOBAL OPTIONS] COMMAND [COMMAND OPTIONS]
```

### Global options

| Flag | Env var | Default | Description |
|---|---|---|---|
| `--api-key` | `BINANCE_API_KEY` | — | API key (required) |
| `--api-secret` | `BINANCE_API_SECRET` | — | API secret (required) |
| `--base-url` | `BINANCE_BASE_URL` | `https://testnet.binancefuture.com` | Base URL |
| `--log-level` | `LOG_LEVEL` | `INFO` | Console verbosity |

---

## Examples

### Place a MARKET BUY

```bash
python cli.py place --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001
```

Output:
```
╭─────────── Order Request ────────────╮
│ Symbol   │ BTCUSDT                   │
│ Side     │ BUY                       │
│ Type     │ MARKET                    │
│ Quantity │ 0.001                     │
│ Price    │ — (market price)          │
╰───────────────────────────────────────╯
╭─────────── Order Response ───────────╮
│ orderId     │ 3672910                │
│ status      │ FILLED                 │
│ executedQty │ 0.001                  │
│ avgPrice    │ 67432.10000            │
╰───────────────────────────────────────╯
 Order placed successfully!  Order ID: 3672910   Status: FILLED
```

### Place a LIMIT SELL

```bash
python cli.py place --symbol ETHUSDT --side SELL --type LIMIT --quantity 0.01 --price 3500
```

### LIMIT BUY with IOC time-in-force

```bash
python cli.py place --symbol BTCUSDT --side BUY --type LIMIT \
  --quantity 0.001 --price 60000 --tif IOC
```

### Dry-run (validate without sending to API)

```bash
python cli.py place --symbol BTCUSDT --side BUY --type MARKET \
  --quantity 0.001 --dry-run
```

### Check account balance

```bash
python cli.py balance
```

### Get mark price

```bash
python cli.py price --symbol BTCUSDT
```

### Ping testnet

```bash
python cli.py ping
```

---

## Error handling examples

### LIMIT order without price (caught before API call)

```bash
python cli.py place --symbol BTCUSDT --side BUY --type LIMIT --quantity 0.001
❌  Order failed: Price is required for LIMIT orders.
```

### Invalid quantity

```bash
python cli.py place --symbol BTCUSDT --side BUY --type MARKET --quantity abc
❌  Order failed: Quantity 'abc' is not a valid number.
```

### Negative quantity

```bash
python cli.py place --symbol BTCUSDT --side BUY --type MARKET --quantity -1
❌  Order failed: Quantity must be greater than zero.
```

---

## Logging

Two log files are created automatically in `./logs/`:

| File | Content | Level |
|---|---|---|
| `trading_bot.log` | All API calls, responses, validation, errors | DEBUG |
| `trade_history.log` | One JSON line per successfully placed order | INFO |

Example `trade_history.log` line:
```json
{"action": "PLACED", "success": true, "orderId": 3672910, "symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "status": "FILLED", "executedQty": "0.001", "avgPrice": "67432.10000"}
```

Files rotate at **10 MB**, keeping 5 backups. Console output is coloured when a TTY is detected.

---

## Assumptions

1. **Testnet only.** The default base URL is `https://testnet.binancefuture.com`. For mainnet, override with `--base-url` (use at your own risk).
2. **USDT-M futures.** COIN-M contracts are not tested.
3. **Quantity precision.** Binance's `LOT_SIZE` step-size filter is not enforced dynamically (marked `# TODO` in `validators.py`). Testnet is tolerant; mainnet orders may be rejected.
4. **No position management.** The bot places orders only; it does not track open positions or enforce `reduceOnly`.
5. **Credentials via env vars** to avoid shell-history leakage.

---

## Future Roadmap (`# TODO` in source)

- [ ] Stop-Limit / STOP_MARKET order type
- [ ] OCO (One-Cancels-the-Other) orders
- [ ] TWAP execution strategy
- [ ] Grid trading helper
- [ ] WebSocket live price streaming
- [ ] Dynamic LOT_SIZE / PRICE_FILTER validation from exchange info
- [ ] SQLite trade history persistence
- [ ] Interactive TUI menu (Rich Prompt / questionary)
- [ ] Docker image + docker-compose
- [ ] Pytest suite with mocked httpx responses
