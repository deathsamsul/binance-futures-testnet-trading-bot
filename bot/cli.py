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

# ---------------------------------------------------------------------------
# Shared context helpers
# ---------------------------------------------------------------------------

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
    req_table = Table(title=" Order Request", box=box.ROUNDED, show_header=False)
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


