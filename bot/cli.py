from __future__ import annotations
import logging
import os
import sys
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from bot.client import BinanceFuturesClient, BinanceClientError, NetworkError
from bot.logging_config import setup_logging, get_logger
from bot.orders import place_order, OrderResult



console = Console()
logger = get_logger(__name__)



# TODO: Add `cancel` sub-command (cancel an open order by orderId).
# TODO: Add `status` sub-command (query order status by orderId).
# TODO: Add `history` sub-command (read and display trade_history.log).
# TODO: Add interactive menu mode (blessed / rich prompts) for bonus UX.
# TODO: Add `--config` flag pointing to a TOML/YAML config file.



# Shared context helpers

def _make_client(ctx: click.Context) -> BinanceFuturesClient:
    """Pull credentials from context and return an authenticated client."""
    return BinanceFuturesClient(
        api_key=ctx.obj["api_key"],
        api_secret=ctx.obj["api_secret"],
        base_url=ctx.obj["base_url"],
    )


def _print_order_result(result: OrderResult, request_summary: dict) -> None:
    """Pretty-print order request + response using Rich."""
    # --- Request table ---
    req_table = Table(title="  Order Request", box=box.ROUNDED, show_header=False)
    req_table.add_column("Field", style="bold cyan")
    req_table.add_column("Value", style="white")
    for k, v in request_summary.items():
        req_table.add_row(k, str(v) if v is not None else "—")
    console.print(req_table)

    if result.success:
        # --- Response table ---
        summary = result.summary()
        res_table = Table(title="  Order Response", box=box.ROUNDED, show_header=False)
        res_table.add_column("Field", style="bold green")
        res_table.add_column("Value", style="white")
        for k, v in summary.items():
            if k == "success":
                continue
            res_table.add_row(k, str(v))
        console.print(res_table)
        console.print(
            Panel(
                f"[bold green] Order placed successfully![/bold green]  "
                f"ID: [yellow]{result.order_id}[/yellow]  "
                f"Status: [cyan]{result.status}[/cyan]",
                border_style="green",
            )
        )
        logger.info("Order successfully displayed to user | orderId=%s", result.order_id)
    else:
        console.print(
            Panel(
                f"[bold red] Order failed:[/bold red] {result.error_message}",
                border_style="red",
            )
        )
        logger.error("Order failure displayed to user: %s", result.error_message)


# Root group
@click.group()
@click.option(
    "--api-key",
    envvar="BINANCE_API_KEY",
    required=True,
    help="Binance Futures API key (or set BINANCE_API_KEY env var).",
)
@click.option(
    "--api-secret",
    envvar="BINANCE_API_SECRET",
    required=True,
    help="Binance Futures API secret (or set BINANCE_API_SECRET env var).",
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
def cli(ctx: click.Context, api_key: str, api_secret: str, base_url: str, log_level: str):
    """
    \b
    ╔══════════════════════════════════════════╗
    ║  Binance Futures Testnet Trading Bot     ║
    ║  Author : Samsul Hoque Mondal            ║
    ║  Target : USDT-M Futures Testnet         ║
    ╚══════════════════════════════════════════╝

    \b
    Examples:
      # Place a MARKET BUY
      trading-bot place --symbol BTCUSDT --side BUY --type MARKET --quantity 0.001

      # Place a LIMIT SELL
      trading-bot place --symbol ETHUSDT --side SELL --type LIMIT --quantity 0.01 --price 3500

      # Check balance
      trading-bot balance

      # Show mark price
      trading-bot price --symbol BTCUSDT

      # Connectivity check
      trading-bot ping
    """
    setup_logging(
        console_level=getattr(logging, log_level.upper()),
        file_level=logging.DEBUG,
    )
    ctx.ensure_object(dict)
    ctx.obj["api_key"] = api_key
    ctx.obj["api_secret"] = api_secret
    ctx.obj["base_url"] = base_url
    logger.debug(
        "CLI started | base_url=%s log_level=%s", base_url, log_level
    )


# `place` sub-command
@cli.command("place")
@click.option("--symbol",   required=True, help="Trading pair, e.g. BTCUSDT.")
@click.option("--side",     required=True,
              type=click.Choice(["BUY", "SELL"], case_sensitive=False),
              help="Order direction.")
@click.option("--type",     "order_type", required=True,
              type=click.Choice(["MARKET", "LIMIT"], case_sensitive=False),
              help="Order type.")
@click.option("--quantity", required=True, help="Contract quantity.")
@click.option("--price",    default=None,  help="Limit price (required for LIMIT orders).")
@click.option("--tif",      default="GTC",
              type=click.Choice(["GTC", "IOC", "FOK"], case_sensitive=False),
              help="Time-in-force (LIMIT only). Default: GTC.")
@click.option("--dry-run",  is_flag=True, default=False,
              help="Validate inputs only; do NOT send to the API.")
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
):
    """Place a MARKET or LIMIT order on USDT-M Futures Testnet."""
    symbol = symbol.upper()
    side = side.upper()
    order_type = order_type.upper()

    request_summary = {
        "Symbol":     symbol,
        "Side":       side,
        "Type":       order_type,
        "Quantity":   quantity,
        "Price":      price or ("— (market)" if order_type == "MARKET" else "⚠️ MISSING"),
        "TIF":        tif if order_type == "LIMIT" else "—",
        "DryRun":     "Yes" if dry_run else "No",
    }

    logger.info(
        "User initiated 'place' | %s",
        " | ".join(f"{k}={v}" for k, v in request_summary.items()),
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


# `balance` sub-command
@cli.command("balance")
@click.pass_context
def balance(ctx: click.Context):
    """Show futures account asset balances."""
    logger.info("User requested account balance.")
    with _make_client(ctx) as client:
        try:
            balances = client.get_account_balance()
        except (BinanceClientError, NetworkError) as exc:
            console.print(f"[red]Error fetching balance: {exc}[/red]")
            logger.error("Balance fetch failed: %s", exc)
            sys.exit(1)

    # Filter non-zero balances for readability
    # TODO: add --all flag to show zero balances too
    nonzero = [b for b in balances if float(b.get("balance", 0)) != 0]

    if not nonzero:
        console.print("[yellow]No non-zero balances found.[/yellow]")
        return

    tbl = Table(title="  Futures Account Balances", box=box.ROUNDED)
    tbl.add_column("Asset", style="bold cyan")
    tbl.add_column("Balance", justify="right")
    tbl.add_column("Available", justify="right")
    tbl.add_column("Unrealised PnL", justify="right")

    for b in nonzero:
        upnl = float(b.get("crossUnPnl", 0))
        color = "green" if upnl >= 0 else "red"
        tbl.add_row(
            b.get("asset", "?"),
            f"{float(b.get('balance', 0)):.4f}",
            f"{float(b.get('availableBalance', 0)):.4f}",
            f"[{color}]{upnl:.4f}[/{color}]",
        )

    console.print(tbl)


# `price` sub-command
@cli.command("price")
@click.option("--symbol", required=True, help="Trading pair, e.g. BTCUSDT.")
@click.pass_context
def price(ctx: click.Context, symbol: str):
    """Show the latest mark price for a symbol."""
    symbol = symbol.upper()
    logger.info("User requested mark price for %s.", symbol)
    with _make_client(ctx) as client:
        try:
            mark = client.get_symbol_price(symbol)
        except (BinanceClientError, NetworkError) as exc:
            console.print(f"[red]Error fetching price: {exc}[/red]")
            logger.error("Price fetch failed for %s: %s", symbol, exc)
            sys.exit(1)

    console.print(
        Panel(
            f"[bold cyan]{symbol}[/bold cyan]  →  [bold yellow]{mark:,.8f} USDT[/bold yellow]",
            title="  Mark Price",
            border_style="cyan",
        )
    )


# `ping` sub-command
@cli.command("ping")
@click.pass_context
def ping(ctx: click.Context):
    """Check connectivity to the Binance Futures Testnet."""
    logger.info("User initiated ping.")
    with _make_client(ctx) as client:
        ok = client.ping()

    if ok:
        console.print(Panel("[bold green] Testnet is reachable![/bold green]", border_style="green"))
    else:
        console.print(Panel("[bold red] Cannot reach testnet.[/bold red]", border_style="red"))
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()
