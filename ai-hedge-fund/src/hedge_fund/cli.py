"""CLI entry point — quick data lookups from the terminal."""

from __future__ import annotations

import json
import sys

import click
from rich.console import Console
from rich.table import Table

from hedge_fund.data.service import get_data_service

console = Console()
ds = get_data_service()


@click.command()
@click.argument("ticker", required=False)
@click.option("--macro", help="FRED series ID (e.g., DFF, CPIAUCSL)")
@click.option("--technicals", is_flag=True, help="Show technical indicators")
@click.option("--json-output", "as_json", is_flag=True, help="Output as JSON")
def main(
    ticker: str | None,
    macro: str | None,
    technicals: bool,
    as_json: bool,
):
    """MJ Research — quick data lookup.

    Examples:
        uv run check-data AAPL
        uv run check-data THYAO.IS
        uv run check-data --macro DFF
    """
    if macro:
        _show_macro(macro, as_json)
    elif ticker:
        if technicals:
            _show_technicals(ticker, as_json)
        else:
            _show_ticker(ticker, as_json)
    else:
        click.echo("Usage: check-data TICKER | --macro SERIES")
        sys.exit(1)


def _show_ticker(ticker: str, as_json: bool):
    console.print(f"\n[bold]Fetching data for {ticker}...[/bold]\n")
    fundamentals = ds.get_fundamentals(ticker)

    if as_json:
        click.echo(json.dumps(fundamentals, indent=2, default=str))
        return

    table = Table(title=f"{ticker} — Fundamentals")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    for key, val in fundamentals.items():
        if key in ("ticker", "error"):
            continue
        table.add_row(key.replace("_", " ").title(), str(val))

    console.print(table)

    # Quick price
    df = ds.get_price_history(ticker, days=5)
    if not df.empty:
        last = df["close"].iloc[-1]
        prev = df["close"].iloc[-2] if len(df) > 1 else last
        change = last - prev
        pct = (change / prev) * 100
        color = "green" if change >= 0 else "red"
        console.print(
            f"\n  Price: [bold]{last:.2f}[/bold]  [{color}]{change:+.2f} ({pct:+.2f}%)[/{color}]\n"
        )


def _trend_label(data: dict) -> str:
    if "trend" in data and data["trend"]:
        return str(data["trend"])
    macd = data.get("macd") or {}
    if isinstance(macd, dict) and macd.get("trend"):
        return str(macd["trend"])
    a50 = data.get("above_sma50")
    a200 = data.get("above_sma200")
    if a50 is not None or a200 is not None:
        return f"above50={a50}, above200={a200}"
    return "N/A"


def _show_technicals(ticker: str, as_json: bool):
    console.print(f"\n[bold]Technical indicators for {ticker}...[/bold]\n")
    data = ds.get_technical_indicators(ticker)

    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
        return

    table = Table(title=f"{ticker} — Technicals")
    table.add_column("Indicator", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Price", f"{data.get('price', 'N/A'):.2f}")
    table.add_row("RSI (14)", str(data.get("rsi_14", "N/A")))
    macd = data.get("macd", {}) or {}
    table.add_row("MACD", f"{macd.get('line', 'N/A')} ({macd.get('trend', '')})")
    table.add_row("SMA 50", str(data.get("sma_50", "N/A")))
    table.add_row("SMA 200", str(data.get("sma_200", "N/A")))
    table.add_row("Trend", _trend_label(data))

    console.print(table)


def _show_macro(series_id: str, as_json: bool):
    console.print(f"\n[bold]FRED series: {series_id}[/bold]\n")
    df = ds.get_macro_data(series_id, days=365)

    if df.empty:
        console.print("[red]No data found.[/red]")
        return

    if as_json:
        click.echo(df.tail(10).to_json(orient="records", date_format="iso", indent=2))
        return

    table = Table(title=f"FRED: {series_id} (last 10)")
    table.add_column("Date", style="cyan")
    table.add_column("Value", style="green")

    for idx, row in df.tail(10).iterrows():
        val_cols = [c for c in row.index if c != "YEARWEEK"]
        val = row[val_cols[0]] if val_cols else "N/A"
        table.add_row(str(idx.date()) if hasattr(idx, "date") else str(idx), f"{val}")

    console.print(table)
