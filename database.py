"""
Database module for PriceSentinel CLI.

Handles all SQLite database operations for tracking products, prices, and history.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from rich.console import Console

console = Console()


class PriceSentinelDatabase:
    """Manages SQLite database operations for PriceSentinel."""

    def __init__(self, db_path: str = "pricesentinel.db"):
        """
        Initialize the database connection.

        Args:
            db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        self.connection = None
        self.cursor = None
        self._initialize_db()

    def _initialize_db(self) -> None:
        """Create database connection and initialize tables if needed."""
        try:
            self.connection = sqlite3.connect(self.db_path)
            self.connection.row_factory = sqlite3.Row
            self.cursor = self.connection.cursor()
            self._create_tables()
        except sqlite3.Error as e:
            console.print(f"[red]Database connection error: {e}[/red]")
            raise

    def _create_tables(self) -> None:
        """Create necessary tables if they don't exist."""
        create_products_table = """
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            initial_price REAL NOT NULL,
            current_price REAL NOT NULL,
            target_price REAL NOT NULL,
            status TEXT DEFAULT 'Tracking',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_checked TIMESTAMP,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """

        create_price_history_table = """
        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            price REAL NOT NULL,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
        )
        """

        try:
            self.cursor.execute(create_products_table)
            self.cursor.execute(create_price_history_table)
            self.connection.commit()
        except sqlite3.Error as e:
            console.print(f"[red]Error creating tables: {e}[/red]")
            raise

    def add_product(
        self,
        title: str,
        url: str,
        initial_price: float,
        target_price: float
    ) -> int:
        """
        Add a new product to track.

        Args:
            title: Product title/name.
            url: Product URL.
            initial_price: Initial price fetched from the website.
            target_price: Target price for alert.

        Returns:
            The product ID (row id).

        Raises:
            ValueError: If URL already exists or inputs are invalid.
            sqlite3.Error: If database operation fails.
        """
        if target_price < 0:
            raise ValueError("Target price cannot be negative.")

        if not url.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")

        try:
            self.cursor.execute(
                """
                INSERT INTO products
                (title, url, initial_price, current_price, target_price)
                VALUES (?, ?, ?, ?, ?)
                """,
                (title, url, initial_price, initial_price, target_price)
            )
            self.connection.commit()
            product_id = self.cursor.lastrowid

            self.cursor.execute(
                """
                INSERT INTO price_history (product_id, price)
                VALUES (?, ?)
                """,
                (product_id, initial_price)
            )
            self.connection.commit()

            return product_id
        except sqlite3.IntegrityError:
            raise ValueError(f"Product with URL '{url}' already exists in database.")
        except sqlite3.Error as e:
            console.print(f"[red]Error adding product: {e}[/red]")
            raise

    def get_all_products(self) -> List[Dict]:
        """
        Retrieve all tracked products.

        Returns:
            List of dictionaries containing product information.
        """
        try:
            self.cursor.execute("SELECT * FROM products ORDER BY id DESC")
            rows = self.cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            console.print(f"[red]Error fetching products: {e}[/red]")
            return []

    def get_product_by_id(self, product_id: int) -> Optional[Dict]:
        """
        Retrieve a specific product by ID.

        Args:
            product_id: The product ID.

        Returns:
            Dictionary with product data or None if not found.
        """
        try:
            self.cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
            row = self.cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            console.print(f"[red]Error fetching product: {e}[/red]")
            return None

    def update_product_price(self, product_id: int, new_price: float) -> bool:
        """
        Update the current price of a product and log to history.

        Args:
            product_id: The product ID.
            new_price: The new price.

        Returns:
            True if update was successful, False otherwise.
        """
        try:
            self.cursor.execute(
                """
                UPDATE products
                SET current_price = ?, last_checked = CURRENT_TIMESTAMP,
                    last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (new_price, product_id)
            )

            self.cursor.execute(
                """
                INSERT INTO price_history (product_id, price)
                VALUES (?, ?)
                """,
                (product_id, new_price)
            )

            self.connection.commit()
            return True
        except sqlite3.Error as e:
            console.print(f"[red]Error updating product price: {e}[/red]")
            return False

    def update_product_status(self, product_id: int, status: str) -> bool:
        """
        Update the status of a product.

        Args:
            product_id: The product ID.
            status: New status (e.g., "Tracking", "🚨 PRICE DROP!").

        Returns:
            True if update was successful, False otherwise.
        """
        try:
            self.cursor.execute(
                """
                UPDATE products
                SET status = ?, last_updated = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (status, product_id)
            )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            console.print(f"[red]Error updating product status: {e}[/red]")
            return False

    def remove_product(self, product_id: int) -> bool:
        """
        Remove a product and its price history from tracking.

        Args:
            product_id: The product ID.

        Returns:
            True if removal was successful, False otherwise.
        """
        try:
            self.cursor.execute("DELETE FROM price_history WHERE product_id = ?", (product_id,))
            self.cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            console.print(f"[red]Error removing product: {e}[/red]")
            return False

    def get_price_history(self, product_id: int, limit: int = 10) -> List[Tuple]:
        """
        Retrieve price history for a product.

        Args:
            product_id: The product ID.
            limit: Number of historical entries to retrieve.

        Returns:
            List of (price, checked_at) tuples.
        """
        try:
            self.cursor.execute(
                """
                SELECT price, checked_at FROM price_history
                WHERE product_id = ?
                ORDER BY checked_at DESC
                LIMIT ?
                """,
                (product_id, limit)
            )
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            console.print(f"[red]Error fetching price history: {e}[/red]")
            return []

    def close(self) -> None:
        """Close the database connection."""
        if self.connection:
            try:
                self.connection.close()
            except sqlite3.Error as e:
                console.print(f"[red]Error closing database: {e}[/red]")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
