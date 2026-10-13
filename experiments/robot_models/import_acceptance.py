"""Browser acceptance of actual model import, local mesh resolution and replay isolation."""

from __future__ import annotations

import argparse
import json
import tempfile
import threading
from pathlib import Path


def main() -> None:
    from playwright.sync_api import expect, sync_playwright

    from robotci.viewer import create_viewer_server, demo_replay

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    replay = demo_replay()
    replay["robot"]["model"] = "unitree_g1"
    server = create_viewer_server(replay, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    report = {"status": "FAIL", "checks": [], "errors": [], "external_requests": []}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
            )
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda error: report["errors"].append(str(error)))
            page.on(
                "request",
                lambda request: (
                    report["external_requests"].append(request.url)
                    if not request.url.startswith(base)
                    else None
                ),
            )
            page.goto(base)
            expect(page.locator("#imported-model-summary")).to_contain_text(
                "29 суставов", timeout=60000
            )
            expect(page.locator("#viewport canvas")).to_have_count(1)
            expect(page.locator('.profile-card[aria-pressed="true"]')).to_have_count(0)
            report["checks"].append("imported model is distinct from conditional profiles")
            page.locator("#focus-button").click()
            page.screenshot(path=str(args.output / "auto-g1-from-recording.png"))
            report["checks"].append("automatic model selection from recording metadata")
            before = page.evaluate(
                "async () => JSON.stringify(await (await fetch('/api/replay')).json())"
            )
            for model_id, label, joints in [
                ("unitree_go2", "Unitree Go2", 12),
                ("unitree_g1", "Unitree G1", 29),
                ("franka_emika_panda", "Franka Panda", 9),
            ]:
                page.locator("#robot-import-button").click()
                page.get_by_role("button", name=label, exact=True).click()
                page.locator("#robot-import-apply").click()
                expect(page.locator("#robot-import-status")).to_contain_text(
                    "Робот встроен", timeout=60000
                )
                expect(page.locator("#robot-import-result")).to_contain_text(f"{joints} суставов")
                page.locator("#robot-import-cancel").click()
                expect(page.locator("#scene-button")).to_have_attribute("aria-pressed", "true")
                page.screenshot(path=str(args.output / f"{model_id}.png"))
                report["checks"].append(f"pasted YAML / bundled meshes: {model_id}")
            page.locator("#robot-import-button").click()
            page.locator("#robot-description-file").set_input_files(
                str(args.source / "unitree_go2/go2.xml")
            )
            page.wait_for_function(
                "document.querySelector('#robot-description-text').value.includes('<mujoco')"
            )
            page.locator("#robot-import-apply").click()
            expect(page.locator("#robot-import-status")).to_contain_text(
                "Робот встроен", timeout=60000
            )
            expect(page.locator("#robot-import-result")).to_contain_text("Точное совпадение")
            report["checks"].append("exact pinned MJCF file resolves catalog, not name guessing")
            page.locator("#robot-description-text").fill(
                '<robot name="Unitree G1"><link name="base"/></robot>'
            )
            page.locator("#robot-import-apply").click()
            expect(page.locator("#robot-import-status")).to_contain_text(
                "Робот встроен", timeout=15000
            )
            expect(page.locator("#robot-import-result")).to_contain_text("Тип не определён")
            report["checks"].append("misleading robot name does not select branded mesh")
            page.locator("#robot-description-text").fill(
                '<!DOCTYPE robot [<!ENTITY x SYSTEM "file:///etc/passwd">]><robot/>'
            )
            page.locator("#robot-import-apply").click()
            expect(page.locator("#robot-import-status")).to_have_class(
                "notice error", timeout=15000
            )
            report["checks"].append("unsafe XML rejected without replacement")
            page.locator("#robot-description-text").fill(
                '<robot name="custom_local"><link name="base"><visual><geometry>'
                '<box size="0.4 0.2 0.1"/></geometry></visual></link></robot>'
            )
            page.locator("#robot-import-apply").click()
            expect(page.locator("#robot-import-status")).to_contain_text(
                "Робот встроен", timeout=15000
            )
            page.locator("#robot-import-cancel").click()
            page.screenshot(path=str(args.output / "custom-urdf.png"))
            report["checks"].append("arbitrary URDF geometry rendered")
            with tempfile.TemporaryDirectory(prefix="robot-import-files-") as temporary:
                directory = Path(temporary) / "local_robot"
                directory.mkdir()
                (directory / "shape.obj").write_text(
                    "v 0 0 0\nv 0.3 0 0\nv 0 0.2 0\nv 0 0 0.1\nf 1 2 3\nf 1 4 2\nf 2 4 3\nf 1 3 4\n"
                )
                (directory / "robot.urdf").write_text(
                    '<robot name="local_mesh"><link name="base"><visual><geometry>'
                    '<mesh filename="shape.obj"/></geometry></visual></link></robot>'
                )
                page.locator("#robot-import-button").click()
                page.locator("#robot-description-folder").set_input_files(str(directory))
                page.wait_for_function(
                    "document.querySelector('#robot-description-text').value.includes('local_mesh')"
                )
                page.locator("#robot-import-apply").click()
                expect(page.locator("#robot-import-status")).to_contain_text(
                    "Робот встроен", timeout=15000
                )
                expect(page.locator("#robot-import-result")).not_to_contain_text("Не найдены")
                page.locator("#robot-import-cancel").click()
                page.screenshot(path=str(args.output / "local-obj.png"))
                report["checks"].append("explicit local folder and OBJ mesh, no remote requests")
            after = page.evaluate(
                "async () => JSON.stringify(await (await fetch('/api/replay')).json())"
            )
            assert before == after
            report["checks"].append("source replay unchanged by all imports")
            assert not report["errors"], report["errors"]
            assert not report["external_requests"], report["external_requests"]
            page.set_viewport_size({"width": 960, "height": 720})
            page.locator("#robot-import-button").click()
            page.screenshot(path=str(args.output / "import-dialog-960.png"))
            report["checks"].append("import dialog at 960px; local network only; no JS errors")
            browser.close()
        report["status"] = "PASS"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
        (args.output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
