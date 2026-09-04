from __future__ import annotations

from importlib.resources import files
from contextlib import contextmanager

import pytest

from cninfo_chain.browser import (
    BrowserSession,
    HEALTH_PAGE_URL,
    assert_safe_bridge_result,
    doctor,
    prepare_bridge,
    validate_cdp_url,
)
from cninfo_chain.errors import AuthenticationPaused, SecurityBoundaryError


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
    assert 'localStorage.getItem("checkToken")' in source
    assert 'localStorage.getItem("checkSign")' in source


def test_windows_powershell_launcher_is_ascii_for_legacy_parser_compatibility():
    script = (
        files("cninfo_chain")
        .joinpath("..", "..", "scripts", "start_cninfo_chrome.ps1")
        .read_bytes()
    )
    assert script.isascii()


def test_bridge_preparation_navigates_empty_route_to_known_health_page():
    class FakePage:
        def __init__(self):
            self.goto_url = None
            self.init_source = None
            self.waited = False

        def add_init_script(self, source):
            self.init_source = source

        def evaluate(self, expression):
            return False if expression.startswith("() =>") else None

        def goto(self, url, wait_until):
            self.goto_url = url
            assert wait_until == "domcontentloaded"

        def wait_for_function(self, expression, timeout):
            self.waited = True
            assert timeout == 20_000

    page = FakePage()
    prepare_bridge(page, "bridge-source")

    assert page.init_source == "bridge-source"
    assert page.goto_url == HEALTH_PAGE_URL
    assert page.waited is True


def test_doctor_treats_http_200_business_401_as_authentication_pause(monkeypatch, tmp_path):
    class Store:
        def migrate(self):
            pass

    class Session:
        def ready(self):
            return True

        def call(self, endpoint, params):
            return {
                "status": 200,
                "json": {"code": 401, "ok": False, "msg": "unauthorized", "data": {}},
            }

    @contextmanager
    def connection(_):
        yield Session()

    from cninfo_chain.config import Settings

    settings = Settings(
        mysql_host="127.0.0.1",
        mysql_port=3306,
        mysql_user="collector",
        mysql_password="secret",
        mysql_database="cninfo",
        cdp_url="http://127.0.0.1:9222",
        raw_dir=tmp_path / "raw",
        export_path=tmp_path / "result.xlsx",
    )
    monkeypatch.setattr("cninfo_chain.browser.connect_browser", connection)
    with pytest.raises(AuthenticationPaused):
        doctor(settings, Store())
