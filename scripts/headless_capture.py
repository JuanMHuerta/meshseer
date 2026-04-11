from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from meshradar.demo import build_demo_app  # noqa: E402


LOCAL_BROWSER_DEPS_DIR = ROOT / ".cache" / "playwright-deps"
LOCAL_BROWSER_LIB_DIR = LOCAL_BROWSER_DEPS_DIR / "root" / "usr" / "lib" / "x86_64-linux-gnu"
LIBRARY_PACKAGE_MAP = {
    "libnspr4.so": "libnspr4",
    "libnss3.so": "libnss3",
    "libsmime3.so": "libnss3",
    "libnssutil3.so": "libnss3",
}


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_demo_server(host: str, port: int, db_path: Path) -> tuple[uvicorn.Server, threading.Thread]:
    config = uvicorn.Config(
        build_demo_app(db_path),
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="meshradar-demo-server", daemon=True)
    thread.start()

    deadline = time.time() + 15
    while time.time() < deadline:
        if getattr(server, "started", False):
            return server, thread
        if not thread.is_alive():
            break
        time.sleep(0.1)

    raise RuntimeError(f"Demo server did not start on {host}:{port}")


def _stop_demo_server(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    thread.join(timeout=10)


def _missing_shared_libraries(executable: str, ld_library_path: str | None = None) -> list[str]:
    env = os.environ.copy()
    if ld_library_path:
        env["LD_LIBRARY_PATH"] = ld_library_path
    result = subprocess.run(
        ["ldd", executable],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    missing: list[str] = []
    for line in result.stdout.splitlines():
        if "=> not found" not in line:
            continue
        missing.append(line.split("=>", maxsplit=1)[0].strip())
    return missing


def _download_browser_runtime_packages(packages: list[str]) -> None:
    LOCAL_BROWSER_DEPS_DIR.mkdir(parents=True, exist_ok=True)
    deb_dir = LOCAL_BROWSER_DEPS_DIR / "debs"
    extract_dir = LOCAL_BROWSER_DEPS_DIR / "root"
    deb_dir.mkdir(parents=True, exist_ok=True)
    extract_dir.mkdir(parents=True, exist_ok=True)

    for package in packages:
        subprocess.run(
            ["apt", "download", package],
            cwd=deb_dir,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        matches = sorted(deb_dir.glob(f"{package}_*.deb"))
        if not matches:
            raise RuntimeError(f"Unable to download Debian package {package}")
        subprocess.run(
            ["dpkg-deb", "-x", str(matches[-1]), str(extract_dir)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )


def _prepare_browser_env(executable: str) -> dict[str, str]:
    missing = _missing_shared_libraries(executable)
    if missing:
        packages = sorted({LIBRARY_PACKAGE_MAP[name] for name in missing if name in LIBRARY_PACKAGE_MAP})
        unresolved = sorted(set(missing) - set(LIBRARY_PACKAGE_MAP))
        if unresolved:
            raise RuntimeError(f"Missing unsupported browser libraries: {', '.join(unresolved)}")
        if packages:
            _download_browser_runtime_packages(packages)

    library_paths = [str(LOCAL_BROWSER_LIB_DIR)] if LOCAL_BROWSER_LIB_DIR.exists() else []
    current_ld_library_path = os.environ.get("LD_LIBRARY_PATH")
    if current_ld_library_path:
        library_paths.append(current_ld_library_path)

    env = os.environ.copy()
    if library_paths:
        env["LD_LIBRARY_PATH"] = ":".join(library_paths)

    remaining_missing = _missing_shared_libraries(executable, env.get("LD_LIBRARY_PATH"))
    if remaining_missing:
        raise RuntimeError(
            "Browser dependencies are still missing after bootstrap: "
            + ", ".join(sorted(remaining_missing))
        )
    return env


def _wait_for_dashboard(page) -> None:
    page.wait_for_selector("#collector-state", state="visible", timeout=20_000)
    page.wait_for_function(
        """
        () => {
          const nodes = document.querySelectorAll('#node-list [data-node-num]').length;
          const packets = document.querySelectorAll('#packets-body tr').length;
          const chat = document.querySelectorAll('#chat-feed .chat-message').length;
          const map = document.querySelector('#leaflet-map.leaflet-container');
          return nodes > 0 && packets > 0 && chat > 0 && Boolean(map);
        }
        """,
        timeout=20_000,
    )
    try:
        page.wait_for_function(
            """
            () => document.querySelectorAll('#leaflet-map .leaflet-tile-loaded, #leaflet-map path.leaflet-interactive').length > 0
            """,
            timeout=8_000,
        )
    except PlaywrightTimeoutError:
        pass
    page.wait_for_timeout(1500)


def _capture(url: str, out_path: Path, map_out_path: Path | None, viewport_width: int, viewport_height: int) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if map_out_path is not None:
        map_out_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser_env = _prepare_browser_env(playwright.chromium.executable_path)
        browser = playwright.chromium.launch(headless=True, env=browser_env)
        page = browser.new_page(viewport={"width": viewport_width, "height": viewport_height}, device_scale_factor=1.5)
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        _wait_for_dashboard(page)
        page.screenshot(path=str(out_path), full_page=True)
        if map_out_path is not None:
            page.locator("#mesh-map").screenshot(path=str(map_out_path))
        browser.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the Meshradar dashboard with Playwright and save screenshots.")
    parser.add_argument("--url", help="Render an existing URL instead of starting the seeded demo app.")
    parser.add_argument("--out", default="artifacts/headless/dashboard.png")
    parser.add_argument("--map-out", default="artifacts/headless/map-panel.png")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=2200)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    out_path = Path(args.out)
    map_out_path = Path(args.map_out) if args.map_out else None

    if args.url:
        _capture(args.url, out_path, map_out_path, args.width, args.height)
        print(f"Saved screenshot to {out_path}")
        if map_out_path is not None:
            print(f"Saved map panel screenshot to {map_out_path}")
        return

    host = "127.0.0.1"
    port = _find_free_port()
    with TemporaryDirectory(prefix="meshradar-headless-") as temp_dir:
        db_path = Path(temp_dir) / "demo.db"
        server, thread = _start_demo_server(host, port, db_path)
        try:
            _capture(f"http://{host}:{port}/", out_path, map_out_path, args.width, args.height)
        finally:
            _stop_demo_server(server, thread)

    print(f"Saved screenshot to {out_path}")
    if map_out_path is not None:
        print(f"Saved map panel screenshot to {map_out_path}")


if __name__ == "__main__":
    main()
