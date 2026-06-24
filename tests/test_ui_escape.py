import json
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.headless_capture import (  # noqa: E402
    _find_free_port,
    _prepare_browser_env,
    _start_demo_server,
    _stop_demo_server,
    _wait_for_dashboard,
)


@contextmanager
def open_page(
    tmp_path,
    *,
    initial_storage: dict[str, str] | None = None,
    status_ui_default_style: str | None = None,
):
    host = "127.0.0.1"
    port = _find_free_port()
    server, thread = _start_demo_server(host, port, tmp_path / "demo.db")

    try:
        with sync_playwright() as playwright:
            browser = None
            try:
                browser_env = _prepare_browser_env(playwright.chromium.executable_path)
                browser = playwright.chromium.launch(headless=True, env=browser_env)
            except Exception as exc:  # pragma: no cover - environment dependent
                pytest.skip(f"Playwright browser unavailable: {exc}")

            try:
                browser_page = browser.new_page(viewport={"width": 1600, "height": 1200})
                if initial_storage:
                    browser_page.add_init_script(
                        f"""
                        const entries = {json.dumps(initial_storage)};
                        Object.entries(entries).forEach(([key, value]) => {{
                          window.localStorage.setItem(key, value);
                        }});
                        """
                    )
                if status_ui_default_style is not None:
                    def rewrite_status(route):
                        response = route.fetch()
                        payload = response.json()
                        payload["ui"] = {"default_style": status_ui_default_style}
                        route.fulfill(
                            response=response,
                            json=payload,
                        )

                    browser_page.route("**/api/status", rewrite_status)

                browser_page.goto(f"http://{host}:{port}/", wait_until="domcontentloaded", timeout=30_000)
                _wait_for_dashboard(browser_page)
                yield browser_page
            finally:
                if browser is not None:
                    browser.close()
    finally:
        _stop_demo_server(server, thread)


@pytest.fixture
def page(tmp_path):
    with open_page(tmp_path) as browser_page:
        yield browser_page


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


def test_node_detail_shows_recent_packets_section(page):
    open_nodes_rail(page)
    page.locator("#node-list [data-node-num]").first.click()
    expect_inspector_open(page)
    page.wait_for_function(
        """
        () => {
          const root = document.querySelector('#node-detail');
          return !!root && root.textContent.includes('Recent packets');
        }
        """
    )
    page.wait_for_function(
        """
        () => {
          const root = document.querySelector('#node-detail');
          return !!root && root.textContent.includes('First ');
        }
        """
    )

    assert page.locator("#node-detail .node-hud-section h4", has_text="Recent packets").text_content() == "Recent packets"
    assert page.locator("#node-detail .node-packet-card, #node-detail .node-packets-empty").count() >= 1
    assert page.locator("#node-detail .hud-metric-detail", has_text="First ").count() >= 1


def test_packet_snr_is_rendered_in_node_detail_and_traffic_drawer(page):
    open_nodes_rail(page)
    node_rows = page.locator("#node-list [data-node-num]")
    found_recent_packets = False
    for index in range(min(node_rows.count(), 6)):
        node_rows.nth(index).click()
        expect_inspector_open(page)
        page.wait_for_function(
            """
            () => {
              const root = document.querySelector('#node-detail');
              return !!root
                && root.textContent.includes('Min')
                && root.textContent.includes('Max')
                && root.textContent.includes('Avg')
                && root.textContent.includes('SNR');
            }
            """
        )
        if page.locator("#node-detail .node-packet-card").count() > 0:
            found_recent_packets = True
            break

    assert page.locator("#node-detail .snr-card .hud-metric-meta").text_content() is not None
    if found_recent_packets:
        assert page.locator("#node-detail .node-packet-snr").count() >= 1

    page.click("#rail-toggle-traffic")
    expect_traffic_open(page)
    page.wait_for_function(
        """
        () => {
          const table = document.querySelector('#mesh-traffic table');
          return !!table && table.textContent.includes('SNR');
        }
        """
    )

    assert page.locator("#mesh-traffic thead th").nth(4).text_content() == "Delivered By"
    assert page.locator("#mesh-traffic thead th").nth(5).text_content() == "SNR"
    assert page.locator("#packets-body tr").first.locator("td").nth(4).text_content().strip() != ""
    assert page.locator("#packets-body tr").first.locator("td").nth(5).text_content().strip().endswith("dB")


def test_packet_delivery_label_only_shows_when_delivery_node_is_known(page):
    labels = page.evaluate(
        """
        () => ({
          direct: packetDeliveryNodeLabel({ path_tone: 'direct' }),
          relayedUnknown: packetDeliveryNodeLabel({ path_tone: 'relayed' }),
          mqtt: packetDeliveryNodeLabel({ path_tone: 'mqtt', via_mqtt: true }),
        })
        """
    )

    assert labels == {
        "direct": "",
        "relayedUnknown": "",
        "mqtt": "Via MQTT",
    }


def test_route_selection_includes_intermediate_nodes(page):
    matches = page.evaluate(
        """
        () => ({
          endpoint: routeIncludesNode({ path_node_nums: [101, 202, 303] }, 101),
          intermediate: routeIncludesNode({ path_node_nums: [101, 202, 303] }, 202),
          missing: routeIncludesNode({ path_node_nums: [101, 202, 303] }, 404),
        })
        """
    )

    assert matches == {
        "endpoint": True,
        "intermediate": True,
        "missing": False,
    }


def test_csv_export_sanitizes_formula_like_cells(page):
    sanitized = page.evaluate(
        r"""
        () => ({
          formula: csvSafeCellText("=2+2"),
          padded: csvSafeCellText("  =2+2"),
          tabbed: csvSafeCellText("\t=2+2"),
          number: csvSafeCellText(-12),
        })
        """
    )

    assert sanitized == {
        "formula": "'=2+2",
        "padded": "'  =2+2",
        "tabbed": "'\t=2+2",
        "number": "-12",
    }


def test_packet_storage_limit_stays_bounded(page):
    limits = page.evaluate(
        """
        () => ({
          defaultLimit: packetStorageLimit(20),
          capAtMax: packetStorageLimit(500),
          ignoreOverflow: packetStorageLimit(650),
        })
        """
    )

    assert limits == {
        "defaultLimit": 90,
        "capAtMax": 500,
        "ignoreOverflow": 500,
    }


def visible_tile_sources(page) -> list[str]:
    return page.locator(".leaflet-tile-pane img.leaflet-tile").evaluate_all(
        "tiles => tiles.map((tile) => tile.getAttribute('src') || '').filter(Boolean)"
    )


def test_theme_selection_persists_and_invalid_saved_value_falls_back(tmp_path):
    with open_page(tmp_path) as page:
        page.click("#rail-toggle-options")
        expect_rail_open(page)
        page.select_option("#ui-theme-select", "classic-dark")
        page.wait_for_function(
            """
            () => (
              document.querySelector('#ui-theme-select')?.value === 'classic-dark'
              && document.documentElement.dataset.theme === 'classic-dark'
              && Array.from(document.querySelectorAll('.leaflet-tile-pane img.leaflet-tile'))
                .some((tile) => (tile.getAttribute('src') || '').includes('dark_nolabels'))
            )
            """
        )
        assert page.evaluate("() => window.localStorage.getItem('meshseer.ui.theme')") == "classic-dark"
        assert page.evaluate("() => window.localStorage.getItem('meshseer.ui.style')") is None

        page.reload(wait_until="domcontentloaded")
        _wait_for_dashboard(page)
        page.click("#rail-toggle-options")
        expect_rail_open(page)
        assert page.locator("#ui-theme-select").input_value() == "classic-dark"
        assert any("dark_nolabels" in src for src in visible_tile_sources(page))

    with open_page(
        tmp_path,
        initial_storage={"meshseer.ui.style": "invalid-style"},
        status_ui_default_style="classic",
    ) as page:
        page.click("#rail-toggle-options")
        expect_rail_open(page)
        page.wait_for_function(
            """
            () => (
              document.querySelector('#ui-theme-select')?.value === 'classic'
              && document.documentElement.dataset.theme === 'classic'
              && window.localStorage.getItem('meshseer.ui.theme') === null
              && window.localStorage.getItem('meshseer.ui.style') === null
              && Array.from(document.querySelectorAll('.leaflet-tile-pane img.leaflet-tile'))
                .some((tile) => (tile.getAttribute('src') || '').includes('rastertiles/voyager'))
            )
            """
        )


def test_recent_packets_header_stays_isolated_in_dark_themes(tmp_path):
    with open_page(tmp_path) as page:
        page.click("#rail-toggle-traffic")
        expect_traffic_open(page)

        for theme in ("classic-dark", "amber-monochrome"):
            if not rail_is_open(page):
                page.click("#rail-toggle-options")
                expect_rail_open(page)
            page.select_option("#ui-theme-select", theme)
            page.wait_for_timeout(150)
            page.eval_on_selector("#mesh-traffic .table-wrap", "(element) => { element.scrollTop = 240; }")
            page.wait_for_timeout(100)

            table_styles = page.evaluate(
                """
                () => {
                  const table = document.querySelector('#mesh-traffic table');
                  const th = document.querySelector('#mesh-traffic thead th');
                  if (!table || !th) return null;
                  const tableStyles = window.getComputedStyle(table);
                  const headerStyles = window.getComputedStyle(th);
                  const colorText = headerStyles.backgroundColor;
                  const colorStart = colorText.indexOf('(');
                  const colorEnd = colorText.lastIndexOf(')');
                  const colorParts = colorStart >= 0 && colorEnd > colorStart
                    ? colorText.slice(colorStart + 1, colorEnd).split(',').map((part) => part.trim())
                    : [];
                  return {
                    borderCollapse: tableStyles.borderCollapse,
                    borderSpacing: tableStyles.borderSpacing,
                    headerPosition: headerStyles.position,
                    headerBackgroundAlpha: colorParts.length >= 4 ? Number(colorParts[3]) : 1,
                  };
                }
                """
            )

            assert table_styles is not None
            assert table_styles["borderCollapse"] == "separate"
            assert table_styles["borderSpacing"] == "0px"
            assert table_styles["headerPosition"] == "sticky"
            assert table_styles["headerBackgroundAlpha"] >= 0.9
