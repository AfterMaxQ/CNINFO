from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from importlib.resources import files
from typing import Any
from urllib.parse import urlparse

from cninfo_chain.config import Settings
from cninfo_chain.endpoints import ENDPOINTS
from cninfo_chain.errors import AuthenticationPaused, CollectorError, SecurityBoundaryError
from cninfo_chain.parsers import parse_chain_list
from cninfo_chain.storage import MySQLStore


SENSITIVE_KEYS = {"cookie", "authorization", "token", "sign", "password"}
HEALTH_PAGE_URL = (
    "https://pis.cninfo.com.cn/ics/index.html#/industryChain/"
    "A02n019/lsx019/A02n019/%E5%A4%AA%E9%98%B3%E8%83%BDEVA%E8%83%B6%E8%86%9C"
)


def validate_cdp_url(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.port != 9222
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise SecurityBoundaryError("CDP must be exactly http://127.0.0.1:9222")
    return "http://127.0.0.1:9222"


def assert_safe_bridge_result(value: Any) -> dict[str, Any]:
    def inspect(item: Any) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if str(key).casefold() in SENSITIVE_KEYS:
                    raise SecurityBoundaryError(
                        f"sensitive key crossed browser boundary: {str(key).casefold()}"
                    )
                inspect(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                inspect(child)

    inspect(value)
    if not isinstance(value, dict) or set(value) != {"status", "json"}:
        raise SecurityBoundaryError("bridge result must contain only status and json")
    if not isinstance(value["status"], int) or not isinstance(value["json"], dict):
        raise SecurityBoundaryError("bridge result has an invalid shape")
    return value


class BrowserSession:
    def __init__(self, page: Any) -> None:
        self.page = page

    def ready(self) -> bool:
        return bool(self.page.evaluate("() => Boolean(window.__cninfoBridge?.ready())"))

    def call(self, endpoint_key: str, params: dict[str, Any]) -> dict[str, Any]:
        endpoint = ENDPOINTS[endpoint_key]
        request = {
            "key": endpoint.key,
            "path": "/ics/aasKnowledgeBase" + endpoint.path,
            "encoding": endpoint.encoding,
            "params": params,
        }
        result = self.page.evaluate(
            "request => window.__cninfoBridge.call(request)", request
        )
        return assert_safe_bridge_result(result)


def prepare_bridge(page: Any, source: str) -> None:
    page.add_init_script(source)
    page.evaluate(source)
    if not page.evaluate("() => Boolean(window.__cninfoBridge?.ready())"):
        page.goto(HEALTH_PAGE_URL, wait_until="domcontentloaded")
        page.wait_for_function(
            "() => Boolean(window.__cninfoBridge?.ready())", timeout=20_000
        )


@contextmanager
def connect_browser(cdp_url: str) -> Iterator[BrowserSession]:
    from playwright.sync_api import sync_playwright

    validated_url = validate_cdp_url(cdp_url)
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(validated_url)
        pages = [page for context in browser.contexts for page in context.pages]
        page = next(
            (item for item in pages if urlparse(item.url).hostname == "pis.cninfo.com.cn"),
            None,
        )
        if page is None:
            raise AuthenticationPaused("open a signed-in pis.cninfo.com.cn page in Chrome")
        source = files("cninfo_chain").joinpath("bridge.js").read_text(encoding="utf-8")
        try:
            prepare_bridge(page, source)
        except Exception as error:
            raise AuthenticationPaused(
                "CNINFO page did not produce an authenticated API request on the health page"
            ) from error
        yield BrowserSession(page)
    finally:
        playwright.stop()


def doctor(settings: Settings, store: MySQLStore | None = None) -> dict[str, Any]:
    active_store = store or MySQLStore(settings)
    active_store.migrate()
    with connect_browser(settings.cdp_url) as browser:
        if not browser.ready():
            raise AuthenticationPaused("CNINFO browser bridge is not ready")
        result = browser.call("chain_list", {"chainId": "ROOT"})
        if result["status"] in {401, 403}:
            raise AuthenticationPaused("CNINFO login is no longer valid")
        if not 200 <= result["status"] < 300:
            raise CollectorError(f"CNINFO health request returned HTTP {result['status']}")
        if str(result["json"].get("code")) in {"401", "403"}:
            raise AuthenticationPaused("CNINFO login is no longer valid")
        chains = parse_chain_list(result["json"])
    return {
        "status": "ok",
        "cdp_url": validate_cdp_url(settings.cdp_url),
        "mysql_host": settings.mysql_host,
        "mysql_database": settings.mysql_database,
        "theme_count": len(chains),
    }
