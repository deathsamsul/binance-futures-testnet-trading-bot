from __future__ import annotations
import logging
import sys
import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from bot.client import BinanceClientError, BinanceFuturesClient, NetworkError
from bot.logging_config import get_logger, setup_logging
from bot.orders import OrderResult, place_order





"""
cli.py — Command-line entry point for the Binance Futures Trading Bot.
Lives at the PROJECT ROOT (trading_bot/cli.py), one level above the bot/
package, matching the task's suggested project structure exactly.
Sub-commands
------------
  place   — Place MARKET or LIMIT orders (core requirement).
  balance — Show futures account balances.
  price   — Show the current mark price for a symbol.
  ping    — Check connectivity to the testnet.
Global flags
------------
  --api-key    / env BINANCE_API_KEY
  --api-secret / env BINANCE_API_SECRET
  --base-url              (default: https://testnet.binancefuture.com)
  --log-level             DEBUG | INFO | WARNING | ERROR
Run from project root:
    python cli.py place --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001
"""

console = Console()
logger = get_logger(__name__)





# TODO: Add `cancel` sub-command (cancel an open order by orderId).
# TODO: Add `status` sub-command (query order status by orderId).
# TODO: Add `history` sub-command (read and pretty-print trade_history.log).
# TODO: Add interactive menu mode (rich Prompt / questionary) for bonus UX.
# TODO: Add `--config` flag pointing to a TOML/YAML config file.

# Helpers
def _make_client(ctx: click.Context) -> BinanceFuturesClient:
    """Construct an authenticated client from the shared Click context."""
    return BinanceFuturesClient(
        api_key=ctx.obj["api_key"],
        api_secret=ctx.obj["api_secret"],
        base_url=ctx.obj["base_url"],
    )


def _print_order_result(result: OrderResult, request_summary: dict) -> None:
    """Render the order request + API response as Rich tables."""

    # ── Request summary ──────────────────────────────────────────────────
    req_table = Table(
        title="[bold]Order Request[/bold]",
        box=box.ROUNDED,
        show_header=False,
        title_style="cyan",
    )
    req_table.add_column("Field", style="bold cyan", no_wrap=True)
    req_table.add_column("Value", style="white")
    for k, v in request_summary.items():
        req_table.add_row(k, str(v) if v is not None else "—")
    console.print(req_table)

    if result.success:
        # ── Response details ──────────────────────────────────────────────
        res_table = Table(
            title="[bold]Order Response[/bold]",
            box=box.ROUNDED,
            show_header=False,
            title_style="green",
        )
        res_table.add_column("Field", style="bold green", no_wrap=True)
        res_table.add_column("Value", style="white")
        for k, v in result.summary().items():
            if k == "success":
                continue
            res_table.add_row(k, str(v))
        console.print(res_table)

        console.print(
            Panel(
                f"[bold green]  Order placed successfully![/bold green]  "
                f"Order ID: [yellow]{result.order_id}[/yellow]   "
                f"Status: [cyan]{result.status}[/cyan]",
                border_style="green",
            )
        )
        logger.info("Order result displayed | orderId=%s status=%s", result.order_id, result.status)

    else:
        console.print(
            Panel(
                f"[bold red]  Order failed:[/bold red]  {result.error_message}",
                border_style="red",
            )
        )
        logger.error("Order failure displayed: %s", result.error_message)


# Root group---------------------------------
@click.group()
@click.option(
    "--api-key",
    envvar="BINANCE_API_KEY",
    required=True,
    help="Binance API key  (or set BINANCE_API_KEY env var).",
)
@click.option(
    "--api-secret",
    envvar="BINANCE_API_SECRET",
    required=True,
    help="Binance API secret  (or set BINANCE_API_SECRET env var).",
)
@click.option(
    "--base-url",
    envvar="BINANCE_BASE_URL",
    default="https://testnet.binancefuture.com",
    show_default=True,
    help="Binance Futures base URL.",
)
@click.option(
    "--log-level",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"], case_sensitive=False),
    default="INFO",
    show_default=True,
    envvar="LOG_LEVEL",
    help="Console log verbosity.",
)
@click.pass_context
def cli(
    ctx: click.Context,
    api_key: str,
    api_secret: str,
    base_url: str,
    log_level: str,
) -> None:
    """
    \b
    ╔══════════════════════════════════════════╗
    ║   Binance Futures Testnet Trading Bot    ║
    ║   USDT-M Futures — Testnet only          ║
    ╚══════════════════════════════════════════╝

    \b
    Quick examples:
      python cli.py place --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001
      python cli.py place --symbol ETHUSDT --side SELL --type LIMIT --quantity 0.01 --price 3500
      python cli.py balance
      python cli.py price --symbol BTCUSDT
      python cli.py ping
    """
    setup_logging(
        console_level=getattr(logging, log_level.upper()),
        file_level=logging.DEBUG,
    )
    ctx.ensure_object(dict)
    ctx.obj["api_key"] = api_key
    ctx.obj["api_secret"] = api_secret
    ctx.obj["base_url"] = base_url
    logger.debug("CLI started | base_url=%s log_level=%s", base_url, log_level)



# `place` — core requirement--------------------------------

@cli.command("place")
@click.option("--symbol",      required=True, help="Trading pair, e.g. BTCUSDT.")
@click.option(
    "--side", required=True,
    type=click.Choice(["BUY", "SELL"], case_sensitive=False),
    help="Order direction.",
)
@click.option(
    "--type", "order_type", required=True,
    type=click.Choice(["MARKET", "LIMIT"], case_sensitive=False),
    help="Order type.",
)
@click.option("--quantity", required=True, help="Contract quantity (e.g. 0.001).")
@click.option("--price",    default=None,  help="Limit price — required for LIMIT orders.")
@click.option(
    "--tif", default="GTC",
    type=click.Choice(["GTC", "IOC", "FOK"], case_sensitive=False),
    help="Time-in-force for LIMIT orders. Default: GTC.",
)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Validate inputs only; do NOT send to the API.",
)
@click.pass_context
def place(
    ctx: click.Context,
    symbol: str,
    side: str,
    order_type: str,
    quantity: str,
    price: str | None,
    tif: str,
    dry_run: bool,
) -> None:
    """Place a MARKET or LIMIT order on USDT-M Futures Testnet."""
    symbol     = symbol.upper()
    side       = side.upper()
    order_type = order_type.upper()

    price_display = (
        price if price
        else ("— (market price)" if order_type == "MARKET" else "[red]⚠ MISSING[/red]")
    )

    request_summary = {
        "Symbol":   symbol,
        "Side":     side,
        "Type":     order_type,
        "Quantity": quantity,
        "Price":    price_display,
        "TIF":      tif if order_type == "LIMIT" else "—",
        "Dry-run":  "Yes — order will NOT be sent" if dry_run else "No",
    }

    logger.info(
        "place command | symbol=%s side=%s type=%s qty=%s price=%s tif=%s dry_run=%s",
        symbol, side, order_type, quantity, price, tif, dry_run,
    )

    with _make_client(ctx) as client:
        result = place_order(
            client=client,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            time_in_force=tif,
            dry_run=dry_run,
        )

    _print_order_result(result, request_summary)
    sys.exit(0 if result.success else 1)


# `balance`----------------------------------------
@cli.command("balance")
@click.pass_context
def balance(ctx: click.Context) -> None:
    """Show futures account asset balances."""
    logger.info("balance command called.")
    with _make_client(ctx) as client:
        try:
            balances = client.get_account_balance()
        except (BinanceClientError, NetworkError) as exc:
            console.print(f"[red]Error fetching balance: {exc}[/red]")
            logger.error("Balance fetch failed: %s", exc)
            sys.exit(1)

    # Only show assets with a non-zero balance
    # TODO: add --all flag to show zero balances too
    nonzero = [b for b in balances if float(b.get("balance", 0)) != 0]

    if not nonzero:
        console.print("[yellow]No non-zero balances found on this testnet account.[/yellow]")
        return

    tbl = Table(title="Futures Account Balances", box=box.ROUNDED)
    tbl.add_column("Asset",         style="bold cyan")
    tbl.add_column("Balance",       justify="right")
    tbl.add_column("Available",     justify="right")
    tbl.add_column("Unrealised PnL", justify="right")

    for b in nonzero:
        upnl  = float(b.get("crossUnPnl", 0))
        color = "green" if upnl >= 0 else "red"
        tbl.add_row(
            b.get("asset", "?"),
            f"{float(b.get('balance', 0)):.4f}",
            f"{float(b.get('availableBalance', 0)):.4f}",
            f"[{color}]{upnl:.4f}[/{color}]",
        )

    console.print(tbl)


# `price`-----------------------
@cli.command("price")
@click.option("--symbol", required=True, help="Trading pair, e.g. BTCUSDT.")
@click.pass_context
def price(ctx: click.Context, symbol: str) -> None:
    """Show the latest mark price for a symbol."""
    symbol = symbol.upper()
    logger.info("price command | symbol=%s", symbol)
    with _make_client(ctx) as client:
        try:
            mark = client.get_symbol_price(symbol)
        except (BinanceClientError, NetworkError) as exc:
            console.print(f"[red]Error fetching price: {exc}[/red]")
            logger.error("Price fetch failed for %s: %s", symbol, exc)
            sys.exit(1)

    console.print(
        Panel(
            f"[bold cyan]{symbol}[/bold cyan]   →   "
            f"[bold yellow]{mark:,.4f} USDT[/bold yellow]",
            title="Mark Price",
            border_style="cyan",
        )
    )


# `ping`-------------------------------
@cli.command("ping")
@click.pass_context
def ping(ctx: click.Context) -> None:
    """Check connectivity to the Binance Futures Testnet."""
    logger.info("ping command called.")
    with _make_client(ctx) as client:
        ok = client.ping()

    if ok:
        console.print(Panel("[bold green]  Testnet is reachable![/bold green]", border_style="green"))
    else:
        console.print(Panel("[bold red]  Cannot reach testnet.[/bold red]", border_style="red"))
        sys.exit(1)


# Entry point-----------------------------

if __name__ == "__main__":
    cli()
