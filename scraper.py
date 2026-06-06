"""
Web scraper module for PriceSentinel CLI.

Handles fetching and parsing HTML to extract product information and prices.
"""

import re
from typing import Optional, Tuple
import requests
from bs4 import BeautifulSoup
from rich.console import Console

console = Console()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT = 10


class PriceScraper:
    """Handles web scraping for product prices."""

    @staticmethod
    def fetch_page(url: str) -> Optional[str]:
        """
        Fetch HTML content from a URL.

        Args:
            url: The URL to fetch.

        Returns:
            HTML content as string, or None if fetch fails.
        """
        try:
            headers = {"User-Agent": USER_AGENT}
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.text
        except requests.exceptions.Timeout:
            console.print(f"[red]Timeout fetching {url}[/red]")
            return None
        except requests.exceptions.ConnectionError:
            console.print(f"[red]Connection error fetching {url}[/red]")
            return None
        except requests.exceptions.HTTPError as e:
            console.print(f"[red]HTTP error for {url}: {e.response.status_code}[/red]")
            return None
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Request failed for {url}: {e}[/red]")
            return None

    @staticmethod
    def parse_price_from_text(text: str) -> Optional[float]:
        """
        Extract price from text using regex patterns.

        Handles various price formats: $99.99, €49,99, 1999 INR, etc.

        Args:
            text: Text containing price information.

        Returns:
            Float price value, or None if no price found.
        """
        if not text:
            return None

        text = text.strip()

        pattern1 = r'[$€£¥₹]\s*(\d+(?:[.,]\d{1,2})?)'
        match = re.search(pattern1, text)
        if match:
            price_str = match.group(1).replace(',', '.')
            try:
                return float(price_str)
            except ValueError:
                pass

        pattern2 = r'(\d+(?:[.,]\d{1,2})?)\s*(?:USD|EUR|INR|GBP|JPY|CAD|AUD)'
        match = re.search(pattern2, text, re.IGNORECASE)
        if match:
            price_str = match.group(1).replace(',', '.')
            try:
                return float(price_str)
            except ValueError:
                pass

        pattern3 = r'(\d+(?:[.,]\d{1,2})?)'
        match = re.search(pattern3, text)
        if match:
            price_str = match.group(1).replace(',', '.')
            try:
                return float(price_str)
            except ValueError:
                pass

        return None

    @staticmethod
    def extract_product_info(url: str, html: str) -> Tuple[Optional[str], Optional[float]]:
        """
        Extract product title and price from HTML.

        Args:
            url: The product URL (for context).
            html: The HTML content to parse.

        Returns:
            Tuple of (title, price) or (None, None) if extraction fails.
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            title = PriceScraper._extract_title(soup)
            price = PriceScraper._extract_price(soup, html)
            return title, price
        except Exception as e:
            console.print(f"[red]Error parsing HTML: {e}[/red]")
            return None, None

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> Optional[str]:
        """Extract product title from HTML using multiple strategies."""
        title_tag = soup.find('title')
        if title_tag and title_tag.string:
            title = title_tag.string.strip()
            if title and len(title) > 2:
                return title

        h1_tag = soup.find('h1')
        if h1_tag and h1_tag.get_text():
            title = h1_tag.get_text().strip()
            if title and len(title) > 2:
                return title

        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content'].strip()
            if title and len(title) > 2:
                return title

        meta_desc = soup.find('meta', attrs={'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            content = meta_desc['content'].strip()
            if len(content) > 2:
                return content[:100]

        return "Unknown Product"

    @staticmethod
    def _extract_price(soup: BeautifulSoup, html: str) -> Optional[float]:
        """Extract price from HTML using multiple strategies."""
        price_selectors = [
            soup.find(class_=re.compile(r'price', re.I)),
            soup.find(id=re.compile(r'price', re.I)),
            soup.find(class_=re.compile(r'current-price', re.I)),
            soup.find(class_=re.compile(r'product-price', re.I)),
            soup.find(class_=re.compile(r'sale-price', re.I)),
        ]

        for element in price_selectors:
            if element:
                text = element.get_text()
                price = PriceScraper.parse_price_from_text(text)
                if price and price > 0:
                    return price

        for tag in soup.find_all(['span', 'div', 'p']):
            text = tag.get_text()
            if any(keyword in text.lower() for keyword in ['price:', '₹', '$', '€', 'cost']):
                price = PriceScraper.parse_price_from_text(text)
                if price and price > 0:
                    return price

        price = PriceScraper.parse_price_from_text(html)
        if price and price > 0:
            return price

        return None

    @staticmethod
    def fetch_product_info(url: str) -> Tuple[Optional[str], Optional[float], Optional[str]]:
        """
        Complete pipeline: fetch URL and extract product info.

        Args:
            url: Product URL to scrape.

        Returns:
            Tuple of (title, price, error_message).
        """
        html = PriceScraper.fetch_page(url)
        if not html:
            return None, None, "Failed to fetch webpage"

        title, price = PriceScraper.extract_product_info(url, html)

        if title is None or price is None:
            return None, None, "Parsing Error: Could not extract product info"

        return title, price, None
