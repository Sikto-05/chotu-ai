"""
web_intel.py - Web Intelligence Skill for CHOTU AI Assistant
=============================================================
Provides web search, weather, news, URL fetching, definitions,
time information, math evaluation, and stock price lookups.
"""

import json
import logging
import math
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# Optional imports with graceful fallback
try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    logger.warning("beautifulsoup4 not installed. fetch_url will return raw text.")

try:
    import pytz
    PYTZ_AVAILABLE = True
except ImportError:
    PYTZ_AVAILABLE = False
    logger.warning("pytz not installed. Timezone support will be limited.")

try:
    from googlesearch import search as google_search
    GOOGLE_SEARCH_AVAILABLE = True
except ImportError:
    GOOGLE_SEARCH_AVAILABLE = False
    logger.warning("googlesearch-python not installed. Will use DuckDuckGo fallback.")

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not installed. Stock price lookups will be unavailable.")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
REQUEST_TIMEOUT: int = 10          # seconds
RATE_LIMIT_DELAY: float = 1.0      # seconds between outbound requests
FREE_DICT_API = "https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
WTTR_API = "https://wttr.in/{city}?format=j1"
DDG_API = "https://api.duckduckgo.com/"
NEWSAPI_URL = "https://newsapi.org/v2/everything"
BBC_RSS = "https://feeds.bbci.co.uk/news/rss.xml"


class WebIntel:
    """
    Web Intelligence skill that provides real-time information retrieval
    including web search, weather, news, URL parsing, definitions, time,
    math evaluation, and stock price lookups.
    """

    def __init__(self, newsapi_key: str = "") -> None:
        """
        Initialise the WebIntel skill.

        Args:
            newsapi_key: Optional NewsAPI.org API key for richer news results.
        """
        self.newsapi_key: str = newsapi_key
        self._last_request_time: float = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
        )
        logger.info("WebIntel skill initialised.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rate_limit(self) -> None:
        """Enforce a 1-second gap between outbound requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def _get(self, url: str, **kwargs: Any) -> Optional[requests.Response]:
        """
        Perform a rate-limited GET request.

        Args:
            url:    Target URL.
            **kwargs: Extra keyword arguments forwarded to ``requests.get``.

        Returns:
            ``requests.Response`` on success, ``None`` on any error.
        """
        self._rate_limit()
        try:
            response = self.session.get(url, timeout=REQUEST_TIMEOUT, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.Timeout:
            logger.error("Request timed out: %s", url)
        except requests.exceptions.ConnectionError:
            logger.error("Connection error for: %s", url)
        except requests.exceptions.HTTPError as exc:
            logger.error("HTTP error %s for: %s", exc.response.status_code, url)
        except requests.exceptions.RequestException as exc:
            logger.error("Request failed for %s: %s", url, exc)
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search_web(self, query: str, num_results: int = 5) -> List[Dict[str, str]]:
        """
        Search the web and return a list of results.

        Tries ``googlesearch-python`` first; falls back to DuckDuckGo
        Instant-Answer API if that library is unavailable.

        Args:
            query:       Search query string.
            num_results: Maximum number of results to return (default 5).

        Returns:
            List of dicts, each with keys ``title``, ``url``, ``snippet``.
        """
        results: List[Dict[str, str]] = []

        if GOOGLE_SEARCH_AVAILABLE:
            try:
                logger.info("Searching Google for: %s", query)
                for url in google_search(query, num_results=num_results, sleep_interval=1):
                    results.append({"title": url, "url": url, "snippet": ""})
                    if len(results) >= num_results:
                        break
                return results
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("Google search failed: %s. Falling back to DuckDuckGo.", exc)

        # DuckDuckGo fallback
        logger.info("Using DuckDuckGo for: %s", query)
        response = self._get(
            DDG_API,
            params={
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            },
        )
        if response is None:
            return results

        try:
            data = response.json()
            # AbstractURL from DDG
            if data.get("AbstractURL"):
                results.append(
                    {
                        "title": data.get("Heading", query),
                        "url": data["AbstractURL"],
                        "snippet": data.get("AbstractText", ""),
                    }
                )
            # Related topics
            for topic in data.get("RelatedTopics", []):
                if len(results) >= num_results:
                    break
                if isinstance(topic, dict) and topic.get("FirstURL"):
                    results.append(
                        {
                            "title": topic.get("Text", "")[:80],
                            "url": topic["FirstURL"],
                            "snippet": topic.get("Text", ""),
                        }
                    )
        except (ValueError, KeyError) as exc:
            logger.error("Failed to parse DuckDuckGo response: %s", exc)

        return results[:num_results]

    def get_weather(self, city: str = "") -> str:
        """
        Fetch current weather information using the wttr.in JSON API (no key needed).

        Args:
            city: City name. Uses IP-based location if empty.

        Returns:
            Human-readable weather string, or an error message.
        """
        location = city.strip().replace(" ", "+") if city.strip() else ""
        url = WTTR_API.format(city=location)
        response = self._get(url)
        if response is None:
            return f"Sorry, I couldn't fetch the weather for '{city}'."

        try:
            data = response.json()
            current = data["current_condition"][0]
            area = data["nearest_area"][0]

            area_name = area["areaName"][0]["value"]
            country = area["country"][0]["value"]
            temp_c = current["temp_C"]
            temp_f = current["temp_F"]
            feels_c = current["FeelsLikeC"]
            humidity = current["humidity"]
            desc = current["weatherDesc"][0]["value"]
            wind_kmph = current["windspeedKmph"]
            wind_dir = current["winddir16Point"]

            return (
                f"Weather in {area_name}, {country}: {desc}. "
                f"Temperature: {temp_c}°C ({temp_f}°F), feels like {feels_c}°C. "
                f"Humidity: {humidity}%. Wind: {wind_kmph} km/h from {wind_dir}."
            )
        except (KeyError, IndexError, ValueError) as exc:
            logger.error("Failed to parse weather data: %s", exc)
            return f"Couldn't parse weather data for '{city}'."

    def get_news(self, topic: str = "") -> List[Dict[str, str]]:
        """
        Fetch recent news headlines.

        Uses NewsAPI.org if a key is configured; otherwise falls back to
        BBC News RSS feed.

        Args:
            topic: Optional topic/keyword to filter news (e.g. 'technology').

        Returns:
            List of dicts with keys ``title``, ``url``, ``description``,
            ``source``, ``published_at``.
        """
        articles: List[Dict[str, str]] = []

        if self.newsapi_key:
            params: Dict[str, Any] = {
                "apiKey": self.newsapi_key,
                "language": "en",
                "pageSize": 5,
                "sortBy": "publishedAt",
            }
            if topic.strip():
                params["q"] = topic.strip()
            else:
                params["q"] = "latest"

            response = self._get(NEWSAPI_URL, params=params)
            if response:
                try:
                    data = response.json()
                    for item in data.get("articles", [])[:5]:
                        articles.append(
                            {
                                "title": item.get("title", "No title"),
                                "url": item.get("url", ""),
                                "description": item.get("description", ""),
                                "source": item.get("source", {}).get("name", "Unknown"),
                                "published_at": item.get("publishedAt", ""),
                            }
                        )
                    return articles
                except (ValueError, KeyError) as exc:
                    logger.warning("NewsAPI parse error: %s. Falling back to RSS.", exc)

        # RSS fallback (BBC News)
        logger.info("Fetching news from BBC RSS feed.")
        rss_url = BBC_RSS
        response = self._get(rss_url)
        if response is None:
            return articles

        if not BS4_AVAILABLE:
            logger.warning("BeautifulSoup not available; cannot parse RSS feed.")
            return articles

        try:
            soup = BeautifulSoup(response.content, features="xml")
            items = soup.find_all("item")
            for item in items[:5]:
                title_tag = item.find("title")
                link_tag = item.find("link")
                desc_tag = item.find("description")
                pub_tag = item.find("pubDate")
                title_text = title_tag.get_text(strip=True) if title_tag else "No title"
                # Filter by topic if requested
                if topic.strip() and topic.lower() not in title_text.lower():
                    continue
                articles.append(
                    {
                        "title": title_text,
                        "url": link_tag.get_text(strip=True) if link_tag else "",
                        "description": desc_tag.get_text(strip=True) if desc_tag else "",
                        "source": "BBC News",
                        "published_at": pub_tag.get_text(strip=True) if pub_tag else "",
                    }
                )
                if len(articles) >= 5:
                    break
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("RSS parse error: %s", exc)

        return articles

    def fetch_url(self, url: str) -> str:
        """
        Fetch a webpage and return its main text content.

        Uses BeautifulSoup to strip HTML if available; returns raw text
        otherwise.

        Args:
            url: Full URL to fetch (must include scheme, e.g. https://).

        Returns:
            Extracted text content or an error message.
        """
        response = self._get(url)
        if response is None:
            return f"Failed to fetch content from: {url}"

        if not BS4_AVAILABLE:
            return response.text[:4000]

        try:
            soup = BeautifulSoup(response.content, "html.parser")
            # Remove script / style noise
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            # Collapse whitespace
            text = re.sub(r"\s{2,}", " ", text)
            return text[:4000]
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("HTML parse error for %s: %s", url, exc)
            return response.text[:4000]

    def get_definition(self, word: str) -> str:
        """
        Fetch the definition of an English word using the Free Dictionary API.

        Args:
            word: Word to look up.

        Returns:
            Definition string or an error message.
        """
        if not word.strip():
            return "Please provide a word to define."

        url = FREE_DICT_API.format(word=word.strip().lower())
        response = self._get(url)
        if response is None:
            return f"Couldn't look up the definition of '{word}'."

        try:
            data = response.json()
            if isinstance(data, list) and data:
                entry = data[0]
                word_out = entry.get("word", word)
                phonetic = entry.get("phonetic", "")
                meanings = entry.get("meanings", [])
                parts: List[str] = []
                for meaning in meanings[:2]:
                    pos = meaning.get("partOfSpeech", "")
                    defs = meaning.get("definitions", [])
                    if defs:
                        definition = defs[0].get("definition", "")
                        example = defs[0].get("example", "")
                        part = f"{word_out} ({pos}): {definition}"
                        if example:
                            part += f' Example: "{example}"'
                        parts.append(part)
                if parts:
                    result = " | ".join(parts)
                    if phonetic:
                        result = f"[{phonetic}] " + result
                    return result
            # API may return a dict with a 'title' key on error
            if isinstance(data, dict):
                return data.get("title", f"No definition found for '{word}'.")
        except (ValueError, KeyError, IndexError) as exc:
            logger.error("Definition parse error: %s", exc)

        return f"No definition found for '{word}'."

    def get_time_info(self, timezone: str = "Asia/Kolkata") -> str:
        """
        Return current date and time in the given timezone.

        Args:
            timezone: IANA timezone string (default 'Asia/Kolkata').

        Returns:
            Human-readable date/time string.
        """
        try:
            if PYTZ_AVAILABLE:
                tz = pytz.timezone(timezone)
                now = datetime.now(tz)
            else:
                now = datetime.now()
                timezone = "local"

            weekday = now.strftime("%A")
            date_str = now.strftime("%d %B %Y")
            time_str = now.strftime("%I:%M %p")
            return (
                f"It is {weekday}, {date_str}. "
                f"The current time in {timezone} is {time_str}."
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Time info error: %s", exc)
            now = datetime.now()
            return f"Current local time: {now.strftime('%A, %d %B %Y, %I:%M %p')}."

    def calculate(self, expression: str) -> str:
        """
        Safely evaluate a mathematical expression.

        Only allows numeric literals and the functions / constants exposed
        from the ``math`` module. No arbitrary Python execution.

        Args:
            expression: Math expression string, e.g. ``"sqrt(144) + 2 ** 8"``.

        Returns:
            Result as a string or an error message.
        """
        if not expression.strip():
            return "Please provide a mathematical expression."

        # Whitelist of safe names
        safe_names: Dict[str, Any] = {
            "__builtins__": {},
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum,
            "pow": pow,
        }
        # Expose all math module attributes
        for name in dir(math):
            if not name.startswith("_"):
                safe_names[name] = getattr(math, name)

        # Strip potentially dangerous tokens
        cleaned = re.sub(r"[^0-9+\-*/().,%^!a-zA-Z_ ]", "", expression)

        try:
            result = eval(cleaned, safe_names)  # nosec B307
            if isinstance(result, float):
                if result == int(result):
                    return f"{expression} = {int(result)}"
                return f"{expression} = {result:.6g}"
            return f"{expression} = {result}"
        except ZeroDivisionError:
            return "Error: Division by zero."
        except (SyntaxError, NameError, TypeError, ValueError) as exc:
            logger.warning("Calculate error for '%s': %s", expression, exc)
            return f"Couldn't evaluate '{expression}'. Please check the expression."

    def get_stock_price(self, symbol: str) -> Dict[str, Any]:
        """
        Fetch the latest stock price information using yfinance.

        Args:
            symbol: Stock ticker symbol, e.g. ``"AAPL"`` or ``"RELIANCE.NS"``.

        Returns:
            Dict with keys ``symbol``, ``price``, ``currency``,
            ``change``, ``change_pct``, ``name``, ``market_state``,
            or an ``error`` key on failure.
        """
        if not YFINANCE_AVAILABLE:
            return {"error": "yfinance is not installed. Run: pip install yfinance"}

        symbol = symbol.strip().upper()
        if not symbol:
            return {"error": "Please provide a stock ticker symbol."}

        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            fast_info = ticker.fast_info

            price = fast_info.get("last_price") or info.get("currentPrice", 0)
            prev_close = fast_info.get("previous_close") or info.get("previousClose", price)
            change = round(price - prev_close, 4) if price and prev_close else 0
            change_pct = round((change / prev_close) * 100, 2) if prev_close else 0

            return {
                "symbol": symbol,
                "name": info.get("longName", info.get("shortName", symbol)),
                "price": round(price, 4) if price else "N/A",
                "currency": info.get("currency", "USD"),
                "change": change,
                "change_pct": change_pct,
                "market_state": info.get("marketState", "UNKNOWN"),
            }
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Stock price error for '%s': %s", symbol, exc)
            return {"error": f"Couldn't fetch stock data for '{symbol}': {exc}"}

    def format_search_results(self, results: List[Dict[str, str]]) -> str:
        """
        Convert a list of search result dicts into a natural-language string
        suitable for text-to-speech output.

        Args:
            results: List returned by :py:meth:`search_web`.

        Returns:
            TTS-friendly string summarising the results.
        """
        if not results:
            return "I didn't find any results for that search."

        lines: List[str] = [f"I found {len(results)} result(s)."]
        for idx, item in enumerate(results, start=1):
            title = item.get("title", "No title")
            snippet = item.get("snippet", "")
            url = item.get("url", "")

            # Truncate for TTS
            if len(title) > 80:
                title = title[:77] + "..."
            if len(snippet) > 150:
                snippet = snippet[:147] + "..."

            line = f"Result {idx}: {title}."
            if snippet:
                line += f" {snippet}"
            if url and url != title:
                # Just state the domain for voice
                domain = re.sub(r"https?://(www\.)?", "", url).split("/")[0]
                line += f" Source: {domain}."
            lines.append(line)

        return " ".join(lines)
