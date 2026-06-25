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
    locale: str | None = None,
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
                page_options = {"viewport": {"width": 1600, "height": 1200}}
                if locale is not None:
                    page_options["locale"] = locale
                browser_page = browser.new_page(**page_options)
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
    assert page.locator("#node-detail .hud-metric-label", has_text="Hops Away").count() == 0


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


def test_node_detail_path_metric_shows_hop_count_not_direct_label(page):
    labels = page.evaluate(
        """
        () => {
          state.perspective = { ...(state.perspective || {}), local_node_num: 77 };
          return {
            zero: nodePathLabel({ hops_away: 0 }),
            one: nodePathLabel({ hops_away: 1 }),
            two: nodePathLabel({ hops_away: 2 }),
            local: nodePathLabel({ node_num: 77, hops_away: 0 }),
            mqtt: nodePathLabel({ via_mqtt: true }),
            traced: nodePathLabel(
              { node_num: 202, hops_away: 0 },
              { latest_complete_traceroute: { forward_path_node_nums: [77, 303, 202] } },
            ),
            tracedDescription: nodePathDescription(
              { node_num: 202, hops_away: 0 },
              { latest_complete_traceroute: { forward_path_node_nums: [77, 303, 202] } },
            ),
          };
        }
        """
    )

    assert labels == {
        "zero": "Direct",
        "one": "1 Hop",
        "two": "2 Hops",
        "local": "Local",
        "mqtt": "MQTT",
        "traced": "1 Hop",
        "tracedDescription": "1 hops away from this receiver",
    }


def test_receiver_local_packets_render_local_path_in_traffic_drawer(page):
    packet = page.evaluate(
        """
        () => {
          const packet = {
            path_tone: 'local',
            path_label: 'Local',
            relay_node: 0,
            next_hop: 0,
            from_node_num: 101,
            to_node_num: 4294967295,
            portnum: 'POSITION_APP',
            received_at: '2026-03-30T12:10:00Z',
            rx_snr: 5.2,
          };
          return {
            label: packetPathLabel(packet),
            markup: packetRowMarkup(packet),
          };
        }
        """
    )

    assert packet["label"] == "Local"
    assert ">Local<" in packet["markup"]
    assert "Unknown" not in packet["markup"]
    assert "path-badge local" in packet["markup"]


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


def test_active_mesh_routes_prefer_latest_complete_family_over_newer_single_for_same_pair(page):
    routes = page.evaluate(
        """
        () => {
          const now = Date.now();
          const iso = (offsetMs = 0) => new Date(now - offsetMs).toISOString();
          state.showRoutes = true;
          state.selectedNodeNum = null;
          state.perspective = { ...(state.perspective || {}), local_node_num: 101 };
          state.nodes = [
            { node_num: 101, latitude: 10.1, longitude: -84.1, last_heard_at: iso(0), hops_away: 0 },
            { node_num: 202, latitude: 10.2, longitude: -84.2, last_heard_at: iso(0), hops_away: 1 },
            { node_num: 303, latitude: 10.3, longitude: -84.3, last_heard_at: iso(0), hops_away: 1 },
          ];
          state.meshRoutes = {
            routes: [
              {
                mesh_packet_id: 9002,
                packet_id: 9002,
                received_at: iso(5_000),
                direction: 'forward',
                source_node_num: 101,
                destination_node_num: 202,
                path_node_nums: [101, 202],
              },
              {
                mesh_packet_id: 9001,
                packet_id: 9001,
                received_at: iso(30_000),
                direction: 'forward',
                source_node_num: 101,
                destination_node_num: 202,
                path_node_nums: [101, 303, 202],
              },
              {
                mesh_packet_id: 9001,
                packet_id: 9001,
                received_at: iso(30_000),
                direction: 'return',
                source_node_num: 202,
                destination_node_num: 101,
                path_node_nums: [202, 303, 101],
              },
            ],
            stats: { total: 3, forward: 2, return: 1 },
          };
          return activeMeshRoutes().map((route) => ({
            mesh_packet_id: route.mesh_packet_id,
            direction: route.direction,
            path_node_nums: route.path_node_nums,
          }));
        }
        """
    )

    assert routes == [
        {"mesh_packet_id": 9001, "direction": "forward", "path_node_nums": [101, 303, 202]},
        {"mesh_packet_id": 9001, "direction": "return", "path_node_nums": [202, 303, 101]},
    ]


def test_selected_local_node_keeps_all_route_families_and_neighborhood_nodes(page):
    result = page.evaluate(
        """
        () => {
          const now = Date.now();
          const iso = (offsetMs = 0) => new Date(now - offsetMs).toISOString();
          state.showRoutes = true;
          state.selectedNodeNum = 101;
          state.perspective = { ...(state.perspective || {}), local_node_num: 101 };
          state.nodes = [
            { node_num: 101, latitude: 10.1, longitude: -84.1, last_heard_at: iso(0), hops_away: 0 },
            { node_num: 202, latitude: 10.2, longitude: -84.2, last_heard_at: iso(0), hops_away: 1 },
            { node_num: 303, latitude: 10.3, longitude: -84.3, last_heard_at: iso(0), hops_away: 1 },
            { node_num: 404, latitude: 10.4, longitude: -84.4, last_heard_at: iso(0), hops_away: 1 },
            { node_num: 505, latitude: 10.5, longitude: -84.5, last_heard_at: iso(0), hops_away: 2 },
          ];
          state.meshRoutes = {
            routes: [
              {
                mesh_packet_id: 9101,
                packet_id: 9101,
                received_at: iso(15_000),
                direction: 'forward',
                source_node_num: 101,
                destination_node_num: 202,
                path_node_nums: [101, 303, 202],
              },
              {
                mesh_packet_id: 9101,
                packet_id: 9101,
                received_at: iso(15_000),
                direction: 'return',
                source_node_num: 202,
                destination_node_num: 101,
                path_node_nums: [202, 303, 101],
              },
              {
                mesh_packet_id: 9102,
                packet_id: 9102,
                received_at: iso(10_000),
                direction: 'forward',
                source_node_num: 101,
                destination_node_num: 505,
                path_node_nums: [101, 404, 505],
              },
            ],
            stats: { total: 3, forward: 2, return: 1 },
          };
          const routes = activeMeshRoutes();
          return {
            routePaths: routes.map((route) => route.path_node_nums),
            neighborhood: [...selectedNeighborhood(routes)].sort((left, right) => left - right),
          };
        }
        """
    )

    assert result == {
        "routePaths": [[101, 404, 505], [101, 303, 202], [202, 303, 101]],
        "neighborhood": [101, 202, 303, 404, 505],
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


def test_channel_scoped_ui_uses_actual_channel_name(tmp_path):
    with open_page(tmp_path) as page:
        def rewrite_status(route):
            response = route.fetch()
            payload = response.json()
            payload["perspective"]["channel_name"] = "MediumSlow"
            route.fulfill(
                response=response,
                json=payload,
            )

        page.route("**/api/status", rewrite_status)
        page.route("**/api/nodes/roster", lambda route: route.fulfill(json=[]))
        page.route("**/api/chat", lambda route: route.fulfill(json=[]))
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#collector-card", state="visible", timeout=20_000)
        page.wait_for_function(
            """
            () => Boolean(document.querySelector('#leaflet-map.leaflet-container'))
            """
        )

        page.click("#rail-toggle-nodes")
        expect_rail_open(page)
        page.click("#rail-toggle-chat")
        expect_rail_open(page)
        page.wait_for_function(
            """
            () => (
              document.title === 'Meshseer | MediumSlow Mesh Console'
              && document.querySelector('#leaflet-map')?.getAttribute('aria-label') === 'MediumSlow node map'
              && document.querySelector('#map-empty')?.textContent.includes('Waiting for MediumSlow node locations.')
              && document.querySelector('#chat-panel-subtitle')?.textContent === 'Broadcast · MediumSlow'
            )
            """
        )
        page.evaluate(
            """
            () => {
              if (typeof window.renderChat === 'function') {
                window.renderChat([]);
              }
            }
            """
        )
        page.wait_for_function(
            """
            () => (
              document.querySelector('#chat-feed')?.textContent.includes('Broadcast MediumSlow messages')
              && document.querySelector('#node-list')?.textContent.includes('MediumSlow nodes appear here')
            )
            """
        )

        assert page.evaluate("() => document.title") == "Meshseer | MediumSlow Mesh Console"
        assert page.locator("#leaflet-map").get_attribute("aria-label") == "MediumSlow node map"
        assert "Waiting for MediumSlow node locations." in (page.locator("#map-empty").text_content() or "")
        assert page.locator("#chat-panel-subtitle").text_content() == "Broadcast · MediumSlow"
        assert "Broadcast MediumSlow messages" in (page.locator("#chat-feed").text_content() or "")
        assert "MediumSlow nodes appear here" in (page.locator("#node-list").text_content() or "")


def test_spanish_browser_locale_is_used_and_manual_language_choice_persists(tmp_path):
    with open_page(tmp_path, locale="es-AR") as page:
        page.click("#rail-toggle-options")
        expect_rail_open(page)

        page.wait_for_function(
            """
            () => (
              document.documentElement.lang === 'es'
              && document.querySelector('#ui-language-select')?.value === 'es'
              && document.querySelector('#mesh-options h2')?.textContent === 'Opciones'
            )
            """
        )
        assert page.locator("#rail-toggle-nodes .rail-icon-label").text_content() == "Nodos"

        page.click("#rail-toggle-traffic")
        expect_traffic_open(page)
        assert page.locator("#mesh-traffic thead th").nth(4).text_content() == "Entregado por"

        page.select_option("#ui-language-select", "en")
        page.wait_for_function(
            """
            () => (
              document.documentElement.lang === 'en'
              && document.querySelector('#ui-language-select')?.value === 'en'
              && document.querySelector('#mesh-options h2')?.textContent === 'Options'
            )
            """
        )
        assert page.evaluate("() => window.localStorage.getItem('meshseer.ui.language')") == "en"
        assert page.locator("#mesh-traffic thead th").nth(4).text_content() == "Delivered By"

        page.reload(wait_until="domcontentloaded")
        _wait_for_dashboard(page)
        page.click("#rail-toggle-options")
        expect_rail_open(page)

        assert page.evaluate("() => document.documentElement.lang") == "en"
        assert page.locator("#ui-language-select").input_value() == "en"
        assert page.locator("#mesh-options h2").text_content() == "Options"


def test_unsupported_browser_locale_falls_back_to_english(tmp_path):
    with open_page(tmp_path, locale="fr-FR") as page:
        page.click("#rail-toggle-options")
        expect_rail_open(page)

        assert page.evaluate("() => document.documentElement.lang") == "en"
        assert page.locator("#ui-language-select").input_value() == "en"
        assert page.locator("#mesh-options h2").text_content() == "Options"
