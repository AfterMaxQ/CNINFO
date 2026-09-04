from __future__ import annotations

from importlib.resources import files

import pytest

from cninfo_chain.browser import (
    BrowserSession,
    assert_safe_bridge_result,
    validate_cdp_url,
)
from cninfo_chain.errors import SecurityBoundaryError


@pytest.mark.parametrize(
    "url",
    [
        "http://0.0.0.0:9222",
        "http://localhost:9222",
        "http://192.168.1.8:9222",
        "https://127.0.0.1:9222",
        "http://127.0.0.1:9000",
    ],
)
def test_cdp_rejects_anything_except_local_http_9222(url):
    with pytest.raises(SecurityBoundaryError):
        validate_cdp_url(url)


def test_cdp_accepts_the_required_loopback_endpoint():
    assert validate_cdp_url("http://127.0.0.1:9222") == "http://127.0.0.1:9222"


@pytest.mark.parametrize("key", ["cookie", "Authorization", "token", "sign", "password"])
def test_bridge_result_fails_if_sensitive_material_crosses_to_python(key):
    with pytest.raises(SecurityBoundaryError):
        assert_safe_bridge_result({"status": 200, "json": {"nested": {key: "secret"}}})


def test_browser_session_sends_only_endpoint_contract_to_page():
    class FakePage:
        def __init__(self):
            self.argument = None

        def evaluate(self, expression, argument):
            assert "__cninfoBridge.call" in expression
            self.argument = argument
            return {"status": 200, "json": {"code": 200, "data": [], "ok": True}}

    page = FakePage()
    result = BrowserSession(page).call("chain_list", {"chainId": "ROOT"})

    assert set(page.argument) == {"key", "path", "encoding", "params"}
    assert "headers" not in repr(page.argument).casefold()
    assert result["status"] == 200


def test_bridge_source_returns_only_status_and_json():
    source = files("cninfo_chain").joinpath("bridge.js").read_text(encoding="utf-8")
    assert "document.cookie" not in source
    assert "return { status: response.status, json: payload };" in source
    assert "allowedPaths" in source


def test_windows_powershell_launcher_is_ascii_for_legacy_parser_compatibility():
    script = (
        files("cninfo_chain")
        .joinpath("..", "..", "scripts", "start_cninfo_chrome.ps1")
        .read_bytes()
    )
    assert script.isascii()
