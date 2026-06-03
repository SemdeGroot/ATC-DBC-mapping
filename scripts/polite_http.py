"""Polite HTTP client: identifies itself, respects robots.txt, throttles, and caches.

One shared client is used for every scrape so a host is never hit faster than the
configured delay and a page is never refetched once it is on disk.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

USER_AGENT = (
    "Mozilla/5.0 (compatible; RKZ-research-scraper/0.1; "
    "non-commercial research; contact: research)"
)
REQUEST_DELAY_SECONDS = 3.0
REQUEST_TIMEOUT_SECONDS = 30
MAX_RETRIES = 3
CACHE_DIR = Path(__file__).parent / "cache"


class FetchError(RuntimeError):
    """A page could not be fetched after retries, or is disallowed by robots.txt."""


class PoliteClient:
    def __init__(self, delay: float = REQUEST_DELAY_SECONDS, cache_dir: Path = CACHE_DIR):
        self.delay = delay
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._session = requests.Session()
        self._session.headers["User-Agent"] = USER_AGENT
        self._last_request_at = 0.0
        self._robots: dict[str, RobotFileParser | None] = {}

    def _robots_for(self, url: str) -> RobotFileParser | None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            parser = RobotFileParser()
            parser.set_url(f"{origin}/robots.txt")
            try:
                parser.read()
            except Exception:
                # Unreachable robots.txt is treated as "disallowed" so we never
                # scrape a host whose rules we could not read.
                parser = None
            self._robots[origin] = parser
        return self._robots[origin]

    def _allowed(self, url: str) -> bool:
        parser = self._robots_for(url)
        if parser is None:
            return False
        return parser.can_fetch(USER_AGENT, url)

    def _cache_path(self, url: str) -> Path:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{key}.html"

    def _throttle(self) -> None:
        wait = self.delay - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)
        self._last_request_at = time.monotonic()

    def get(self, url: str, use_cache: bool = True) -> str:
        cache_path = self._cache_path(url)
        if use_cache and cache_path.exists():
            return cache_path.read_text(encoding="utf-8")

        if not self._allowed(url):
            raise FetchError(f"robots.txt disallows fetching {url}")

        last_error: object = None
        for attempt in range(1, MAX_RETRIES + 1):
            self._throttle()
            try:
                response = self._session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
            except requests.RequestException as exc:
                last_error = exc
            else:
                if response.status_code == 200:
                    cache_path.write_text(response.text, encoding="utf-8")
                    return response.text
                if response.status_code == 404:
                    raise FetchError(f"page not found (404): {url}")
                last_error = FetchError(f"HTTP {response.status_code} for {url}")
            time.sleep(self.delay * attempt)
        raise FetchError(f"failed to fetch {url} after {MAX_RETRIES} attempts: {last_error}")
