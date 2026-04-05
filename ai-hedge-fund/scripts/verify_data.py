#!/usr/bin/env python3
"""Quick verification script — checks all data sources."""

from rich.console import Console
from rich.table import Table

from hedge_fund.data.service import DataService

console = Console()
ds = DataService()

TICKERS = ["AAPL", "THYAO.IS", "NOVO-B.CO", "NESTE.HE"]


def main():
    console.print("\n[bold]Data Platform Verification[/bold]\n")

    table = Table(title="Price Data Check")
    table.add_column("Ticker", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Last Close")
    table.add_column("Points")

    for ticker in TICKERS:
        try:
            df = ds.get_price_history(ticker, days=30)
            if not df.empty:
                last = df["close"].iloc[-1]
                table.add_row(ticker, "OK", f"{last:.2f}", str(len(df)))
            else:
                table.add_row(ticker, "[red]EMPTY[/red]", "-", "0")
        except Exception as e:
            table.add_row(ticker, f"[red]ERR: {e}[/red]", "-", "-")

    console.print(table)

    # Fundamentals
    console.print("\n[bold]Fundamentals Check[/bold]")
    for ticker in ["AAPL", "THYAO.IS"]:
        f = ds.get_fundamentals(ticker)
        status = "OK" if "error" not in f else f"ERR: {f['error']}"
        console.print(f"  {ticker}: {status}")

    # Technicals
    console.print("\n[bold]Technicals Check[/bold]")
    t = ds.get_technical_indicators("AAPL")
    console.print(f"  AAPL RSI: {t.get('rsi_14', 'N/A')}, Trend: {t.get('trend', 'N/A')}")

    console.print("\n[bold green]Verification complete.[/bold green]\n")


if __name__ == "__main__":
    main()
