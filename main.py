"""
PriceSentinel CLI - Main entry point.

A terminal-based automation tool to track product prices from e-commerce websites
and alert users when prices drop.
"""

import time
import sys
from typing import Optional
import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.layout import Layout
import schedule

from database import PriceSentinelDatabase
from scraper import PriceScraper

console = Console()


class PriceSentinelCLI:
    """Main CLI application class."""

    def __init__(self, db_path: str = "pricesentinel.db"):
        """Initialize the CLI application."""
        self.db = PriceSentinelDatabase(db_path)

    def display_banner(self) -> None:
        """Display the PriceSentinel welcome banner."""
        banner = """
    ╔═══════════════════════════════════════╗
    ║        PRICESENTINEL CLI              ║
    ║  Price Tracking Made Simple           ║
    ╚═══════════════════════════════════════╝
        """
        console.print(banner, style="bold cyan")

    def add_product(self, url: str, target_price: float) -> None:
        """
        Add a product to track.

        Args:
            url: Product URL.
            target_price: Target price for alert.
        """
        if target_price < 0:
            console.print("[red]Error: Target price cannot be negative.[/red]")
            return

        if not url.startswith(("http://", "https://")):
            console.print("[red]Error: URL must start with http:// or https://[/red]")
            return

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task("[cyan]Fetching product information...", total=None)
            title, price, error = PriceScraper.fetch_product_info(url)

        if error:
            console.print(f"[red]Error: {error}[/red]")
            return

        try:
            product_id = self.db.add_product(title, url, price, target_price)
            console.print(
                f"[green]✓ Product added successfully![/green]\n"
                f"  ID: {product_id}\n"
                f"  Title: {title}\n"
                f"  Current Price: ₹{price:.2f}\n"
                f"  Target Price: ₹{target_price:.2f}"
            )
        except ValueError as e:
            console.print(f"[red]Error: {e}[/red]")

    def list_products(self) -> None:
        """Display all tracked products in a formatted table."""
        products = self.db.get_all_products()

        if not products:
            console.print("[yellow]No products being tracked yet.[/yellow]")
            return

        table = Table(title="[bold cyan]📊 Tracked Products[/bold cyan]", show_header=True)
        table.add_column("ID", style="cyan", width=5)
        table.add_column("Product Title", style="white", width=30)
        table.add_column("Current Price", style="magenta", width=15)
        table.add_column("Target Price", style="yellow", width=15)
        table.add_column("Status", style="green", width=20)
        table.add_column("Last Checked", style="blue", width=18)

        for product in products:
            product_id = product['id']
            title = product['title'][:27] + "..." if len(product['title']) > 30 else product['title']
            current_price = f"₹{product['current_price']:.2f}"
            target_price = f"₹{product['target_price']:.2f}"
            status = product['status']
            last_checked = product['last_checked'] or "Never"

            # Color code status
            if "PRICE DROP" in status:
                status_style = "[bold red]🚨 PRICE DROP![/bold red]"
            else:
                status_style = "[green]✓ Tracking[/green]"

            table.add_row(
                str(product_id),
                title,
                current_price,
                target_price,
                status_style,
                str(last_checked)[:16] if last_checked != "Never" else "Never"
            )

        console.print(table)

    def remove_product(self, product_id: int) -> None:
        """
        Remove a product from tracking.

        Args:
            product_id: ID of the product to remove.
        """
        product = self.db.get_product_by_id(product_id)
        if not product:
            console.print(f"[red]Error: Product with ID {product_id} not found.[/red]")
            return

        if self.db.remove_product(product_id):
            console.print(f"[green]✓ Product '{product['title']}' removed successfully![/green]")
        else:
            console.print("[red]Error: Failed to remove product.[/red]")

    def monitor_prices(self, interval_minutes: int = 5) -> None:
        """
        Continuously monitor and update product prices.

        Args:
            interval_minutes: Interval (in minutes) between price checks.
        """
        if interval_minutes < 1:
            console.print("[red]Error: Interval must be at least 1 minute.[/red]")
            return

        products = self.db.get_all_products()
        if not products:
            console.print("[yellow]No products to monitor. Please add products first.[/yellow]")
            return

        console.print(
            f"\n[bold cyan]🔄 Starting price monitor (interval: {interval_minutes} minute(s))[/bold cyan]\n"
            "[yellow]Press Ctrl+C to stop monitoring.[/yellow]\n"
        )

        def check_prices() -> None:
            """Check and update prices for all products."""
            products = self.db.get_all_products()

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task("[cyan]Checking prices...", total=None)

                for product in products:
                    product_id = product['id']
                    url = product['url']
                    target_price = product['target_price']

                    title, new_price, error = PriceScraper.fetch_product_info(url)

                    if error:
                        self.db.update_product_status(product_id, f"Error: {error}")
                    else:
                        old_price = product['current_price']
                        self.db.update_product_price(product_id, new_price)

                        # Determine status
                        if new_price <= target_price:
                            status = "🚨 PRICE DROP!"
                            self.db.update_product_status(product_id, status)

                            # Display alert
                            alert_panel = Panel(
                                f"[bold red]PRICE ALERT![/bold red]\n\n"
                                f"Product: {title}\n"
                                f"Previous: ₹{old_price:.2f} → Current: ₹{new_price:.2f}\n"
                                f"Target: ₹{target_price:.2f}\n"
                                f"[bold green]✓ Price target reached![/bold green]",
                                style="bold red",
                                title="🚨 ALERT"
                            )
                            console.print(alert_panel)
                        else:
                            status = "Tracking"
                            self.db.update_product_status(product_id, status)

            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            console.print(f"[blue]✓ Price check completed at {timestamp}[/blue]\n")

        # Schedule the job
        schedule.every(interval_minutes).minutes.do(check_prices)

        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]Monitoring stopped.[/yellow]")

    def close(self) -> None:
        """Close database connection."""
        self.db.close()


# Initialize CLI
cli_app = PriceSentinelCLI()


@click.group()
@click.version_option(version="1.0.0", prog_name="PriceSentinel")
def cli() -> None:
    """
    🔍 PriceSentinel - Price Tracking CLI

    Track product prices from e-commerce websites and get alerts when prices drop.
    """
    pass


@cli.command()
@click.option(
    '--url',
    prompt='Product URL',
    help='URL of the product to track',
    type=str
)
@click.option(
    '--target',
    prompt='Target price',
    help='Target price for price drop alert',
    type=float
)
def add(url: str, target: float) -> None:
    """Add a new product to track."""
    cli_app.add_product(url, target)


@cli.command()
def list() -> None:
    """List all tracked products."""
    cli_app.display_banner()
    cli_app.list_products()


@cli.command()
@click.option(
    '--id',
    prompt='Product ID',
    help='ID of the product to remove',
    type=int
)
def remove(id: int) -> None:
    """Remove a product from tracking."""
    cli_app.remove_product(id)


@cli.command()
@click.option(
    '--interval',
    default=5,
    help='Check interval in minutes (default: 5)',
    type=int,
    show_default=True
)
def monitor(interval: int) -> None:
    """Monitor prices continuously at specified intervals."""
    cli_app.display_banner()
    cli_app.monitor_prices(interval)


def main() -> None:
    """Entry point for the CLI application."""
    try:
        cli()
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        sys.exit(1)
    finally:
        cli_app.close()


if __name__ == '__main__':
    main()
