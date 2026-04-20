import sys
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.headless_capture import (
    _find_free_port,
    _prepare_browser_env,
    _start_demo_server,
    _stop_demo_server,
    _wait_for_dashboard,
)


@pytest.fixture
def page(tmp_path):
    host = "127.0.0.1"
    port = _find_free_port()
    server, thread = _start_demo_server(host, port, tmp_path / "demo.db")

    try:
        with sync_playwright() as playwright:
            try:
                browser_env = _prepare_browser_env(playwright.chromium.executable_path)
                browser = playwright.chromium.launch(headless=True, env=browser_env)
            except Exception as exc:  # pragma: no cover - environment dependent
                pytest.skip(f"Playwright browser unavailable: {exc}")

            browser_page = browser.new_page(viewport={"width": 1600, "height": 1200})
            browser_page.goto(f"http://{host}:{port}/", wait_until="domcontentloaded", timeout=30_000)
            _wait_for_dashboard(browser_page)
            yield browser_page
            browser.close()
    finally:
        _stop_demo_server(server, thread)


def inspector_is_open(page) -> bool:
    return page.locator("#inspector-panel").evaluate(
        "element => element.classList.contains('is-open')"
    )


def rail_is_open(page) -> bool:
    return page.locator("#node-rail").get_attribute("data-state") == "expanded"


def traffic_is_open(page) -> bool:
    return page.locator("#mesh-traffic").get_attribute("aria-hidden") == "false"


def selected_node_count(page) -> int:
    return page.locator("#node-list .node-row.selected").count()


def open_nodes_rail(page) -> None:
    page.click("#rail-toggle-nodes")
    expect_rail_open(page)


def expect_rail_open(page) -> None:
    page.wait_for_function(
        "() => document.querySelector('#node-rail')?.dataset.state === 'expanded'"
    )


def expect_traffic_open(page) -> None:
    page.wait_for_function(
        "() => document.querySelector('#mesh-traffic')?.getAttribute('aria-hidden') === 'false'"
    )


def expect_inspector_open(page) -> None:
    page.wait_for_function(
        "() => document.querySelector('#inspector-panel')?.classList.contains('is-open')"
    )


def test_escape_closes_selected_node_then_traffic_then_rail(page):
    open_nodes_rail(page)
    page.click("#rail-toggle-traffic")
    expect_traffic_open(page)

    page.locator("#node-list [data-node-num]").first.click()
    expect_inspector_open(page)

    assert selected_node_count(page) == 1
    assert inspector_is_open(page) is True
    assert traffic_is_open(page) is True
    assert rail_is_open(page) is True

    page.evaluate(
        """
        () => {
          document.dispatchEvent(new KeyboardEvent('keydown', {
            bubbles: true,
            cancelable: true,
            key: 'Escape',
            repeat: true,
          }));
        }
        """
    )

    assert selected_node_count(page) == 1
    assert inspector_is_open(page) is True
    assert traffic_is_open(page) is True
    assert rail_is_open(page) is True

    page.keyboard.press("Escape")
    page.wait_for_function(
        """
        () => (
          document.querySelectorAll('#node-list .node-row.selected').length === 0
          && !document.querySelector('#inspector-panel')?.classList.contains('is-open')
        )
        """
    )
    assert traffic_is_open(page) is True
    assert rail_is_open(page) is True

    page.keyboard.press("Escape")
    page.wait_for_function(
        "() => document.querySelector('#mesh-traffic')?.getAttribute('aria-hidden') === 'true'"
    )
    assert rail_is_open(page) is True

    page.keyboard.press("Escape")
    page.wait_for_function(
        "() => document.querySelector('#node-rail')?.dataset.state === 'collapsed'"
    )

    assert selected_node_count(page) == 0
    assert inspector_is_open(page) is False
    assert traffic_is_open(page) is False
    assert rail_is_open(page) is False

    page.keyboard.press("Escape")
    assert selected_node_count(page) == 0
    assert inspector_is_open(page) is False
    assert traffic_is_open(page) is False
    assert rail_is_open(page) is False


def test_escape_keeps_native_search_behavior(page):
    open_nodes_rail(page)
    page.click("#rail-toggle-traffic")
    expect_traffic_open(page)

    page.fill("#node-search", "alpha")
    page.locator("#node-search").focus()
    page.keyboard.press("Escape")
    page.wait_for_timeout(100)

    assert rail_is_open(page) is True
    assert traffic_is_open(page) is True
