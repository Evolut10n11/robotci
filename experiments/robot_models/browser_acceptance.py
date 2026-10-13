"""Interactive Chromium checks of shipped viewer assets, not a simulation run."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import threading
from pathlib import Path


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    from playwright.sync_api import expect, sync_playwright

    from robotci.viewer import VIEWER_ASSETS_DIR, create_viewer_server
    from robotci.viewer_session import demo_session, suite_session

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("output already exists; choose a fresh evidence directory")
    output.mkdir(parents=True)
    suite = args.suite.resolve(strict=True)
    before = file_hash(suite)
    report = {
        "kind": "interactive_viewer_acceptance", "schema_version": 1,
        "robotci_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "suite_sha256": before, "checks": [], "errors": [],
        "assets": {
            p.relative_to(VIEWER_ASSETS_DIR).as_posix(): file_hash(p)
            for p in VIEWER_ASSETS_DIR.rglob("*") if p.is_file()
        },
        "limitations": ["Chromium only; software WebGL; not physical GPU performance",
                        "Recorded native suite; see browser-source.json for producing CI run",
                        "Suite self-comparison tests UI only, not a controller intervention"],
    }
    servers, threads = [], []

    def serve(session: dict) -> str:
        server = create_viewer_server(None, port=0, session=session)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
        threads.append(thread)
        return f"http://127.0.0.1:{server.server_address[1]}/"

    def passed(name: str) -> None:
        report["checks"].append({"name": name, "status": "PASS"})
        print("PASS", name, flush=True)

    success = False
    try:
        with sync_playwright() as engine:
            browser = engine.chromium.launch(headless=True, args=[
                "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
            ])
            report["browser"] = browser.version
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(12000)
            page.on("pageerror", lambda exc: report["errors"].append(str(exc)))
            try:
                page.goto(serve(demo_session()), wait_until="networkidle")
                expect(page.locator("#source-badge")).to_have_text("Демонстрационные данные")
                expect(page.locator("#session-footnote")).to_contain_text("без проверки регрессий")
                expect(page.locator(".trajectory-svg")).to_be_visible()
                passed("Russian demo and synthetic gate disclaimer")
                page.screenshot(path=str(output / "demo-2d.png"), full_page=True)
                page.locator("#play-button").click()
                expect(page.locator("#play-button")).to_have_attribute("aria-label", "Пауза")
                page.wait_for_function("Number(document.querySelector('#seek').value) > 0.2")
                page.locator("#play-button").click()
                play = page.locator("#play-button")
                expect(play).to_have_attribute("aria-label", "Воспроизвести")
                paused = page.locator("#seek").input_value()
                page.wait_for_timeout(200)
                assert page.locator("#seek").input_value() == paused
                passed("Play advances time and pause stops it")
                page.locator("#speed").select_option("2")
                assert page.locator("#speed").input_value() == "2"
                seek = page.locator("#seek")
                seek.evaluate("e => { e.value = '6'; e.dispatchEvent(new Event('input')); }")
                assert float(seek.input_value()) == 6.0
                passed("Playback speed selector and seek")
                seek.evaluate("e => { e.value = '0'; e.dispatchEvent(new Event('input')); }")
                page.locator("#next-event").click()
                assert float(seek.input_value()) > 0
                page.locator("#previous-event").click()
                passed("Next and previous recorded events")
                metrics = page.locator("#metrics-body").inner_text()
                for profile in ("rover", "quadruped", "humanoid"):
                    button = page.locator(f'[data-profile="{profile}"]')
                    button.click()
                    expect(button).to_have_attribute("aria-pressed", "true")
                    assert page.locator("#metrics-body").inner_text() == metrics
                passed("Three visual profiles preserve recorded metrics")
                page.locator("#scene-button").click()
                expect(page.locator("#viewport canvas")).to_be_visible()
                expect(page.locator("#scene-button")).to_have_attribute("aria-pressed", "true")
                page.locator("#fit-button").click()
                page.locator("#focus-button").click()
                page.screenshot(path=str(output / "demo-3d.png"), full_page=True)
                page.locator("#top-button").click()
                expect(page.locator(".trajectory-svg")).to_be_visible()
                passed("Rendered 3D, fit/focus camera and return to 2D")
                page.locator("#help-button").click()
                expect(page.locator("#help-dialog")).to_be_visible()
                page.keyboard.press("Escape")
                expect(page.locator("#help-dialog")).not_to_be_visible()
                passed("Keyboard-help dialog and Escape")
                page.goto(serve(suite_session(suite, suite)), wait_until="networkidle")
                expect(page.locator("#source-badge")).to_have_text("Проверенные результаты")
                scenarios = page.locator("[data-scenario]")
                assert scenarios.count() == 3
                title = page.locator("#scenario-title").inner_text()
                scenarios.nth(1).click()
                assert page.locator("#scenario-title").inner_text() != title
                page.locator('[data-mode="compare"]').click()
                expect(page.locator("#mode-label")).to_have_text("Сравнение прогонов")
                page.screenshot(path=str(output / "native-suite-compare.png"), full_page=True)
                passed("Three recorded native routes and verified self-comparison display")
                with page.expect_download() as download_info:
                    page.locator("#export-button").click()
                download_info.value.save_as(str(output / "browser-export.json"))
                exported = json.loads((output / "browser-export.json").read_text())
                assert exported["kind"] == "suite_regression"
                assert exported["status"] == "PASS"
                passed("Export verified gate JSON from browser")
                page.locator("#open-button").click()
                page.locator("#candidate-file").set_input_files({
                    "name": "invalid.json", "mimeType": "application/json", "buffer": b"not json",
                })
                page.locator("#import-button").click()
                expect(page.locator("#import-error")).to_be_visible()
                assert page.locator("#import-error").inner_text().strip()
                expect(page.locator("#source-badge")).to_have_text("Проверенные результаты")
                passed("Invalid imported JSON is rejected without replacing verified data")
                replay = next((suite.parent / "results").glob("*.replay.json"))
                page.locator("#candidate-file").set_input_files(str(replay))
                page.locator("#baseline-file").set_input_files(str(replay))
                page.locator("#import-button").click()
                expect(page.locator("#open-dialog")).not_to_be_visible()
                expect(page.locator("#source-badge")).to_have_text("Replay v1")
                expect(page.locator("#export-button")).to_contain_text("Скачать запись")
                passed("Imported replay pair stays visual-only, no official gate")
                page.set_viewport_size({"width": 960, "height": 720})
                expect(page.locator("#play-button")).to_be_visible()
                page.locator("#scene-button").click()
                expect(page.locator("#viewport canvas")).to_be_visible()
                page.screenshot(path=str(output / "recorded-replay-960.png"), full_page=True)
                passed("Recorded replay renders at a smaller desktop viewport")
                assert not report["errors"], report["errors"]
                assert file_hash(suite) == before
                assert re.search("[А-Яа-я]", page.locator("body").inner_text())
                passed("No uncaught JavaScript errors; source suite bytes unchanged")
                success = True
            finally:
                page.screenshot(path=str(output / "last-page.png"), full_page=True)
                browser.close()
    except Exception as exc:
        report["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=3)
        report["status"] = "PASS" if success else "FAIL"
        (output / "browser-summary.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
