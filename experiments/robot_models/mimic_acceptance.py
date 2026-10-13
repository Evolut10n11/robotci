"""Check actual Panda URDF/local OBJ import and a coupled gripper in Chromium."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import threading
from pathlib import Path

PANDA_REVISION = "d3afe76132fc76b0f9b2359cbaef47a3766e7fbb"
PANDA_URDF_BLOB = "abb3b2edc01e71191a504b7b068bf9253a1b82de"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    from playwright.sync_api import expect, sync_playwright

    from robotci.model_import import inspect_description
    from robotci.viewer import create_viewer_server, demo_replay

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("choose a fresh evidence directory")
    args.output.mkdir(parents=True)
    source = args.source.resolve(strict=True)
    urdf = source / "panda.urdf"
    data = urdf.read_bytes()
    assert subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip() == PANDA_REVISION
    assert hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() == PANDA_URDF_BLOB
    before = {p.relative_to(source).as_posix(): digest(p) for p in source.rglob("*") if p.is_file()}
    report = {
        "status": "FAIL", "checks": [], "errors": [], "external_requests": [],
        "source_revision": PANDA_REVISION, "source_urdf_sha256": digest(urdf),
        "robotci_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "limitations": ["Static reference pose, not dynamics or measured joint playback",
                        "Pinned Bullet Panda URDF/OBJ, not the bundled MJCF catalog model",
                        "Chromium software rendering; OBJ materials/textures are not imported"],
    }
    replay = demo_replay()
    server = create_viewer_server(replay, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        description = inspect_description(data.decode("utf-8"))
        joints = {j["name"]: j for n in description["nodes"] for j in n["joints"]}
        assert description["link_count"] == 13 and description["joint_count"] == 9
        assert description["classification"]["kind"] == "manipulator"
        assert description["model_id"] is None and description["identification"] == "structural"
        assert joints["panda_finger_joint2"]["mimic"]["joint"] == "panda_finger_joint1"
        assert joints["panda_finger_joint1"]["value"] == joints["panda_finger_joint2"]["value"]
        report["checks"].append("unmodified pinned Panda: 13 links, 9 joints, coupled fingers")
        (args.output / "panda-description.json").write_text(
            json.dumps(description, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        example = Path("examples/robot-models/mimic-gripper.urdf")
        gripper = inspect_description(example.read_text(encoding="utf-8"))
        gripper_path = args.output / "gripper-description.json"
        gripper_path.write_text(json.dumps(gripper), encoding="utf-8")
        rendered = json.loads(subprocess.check_output(
            ["node", "experiments/robot_models/verify-mimic-reference.mjs", str(gripper_path)],
            text=True, timeout=30,
        ))
        assert rendered["status"] == "PASS"
        (args.output / "gripper-rendered-frames.json").write_text(
            json.dumps(rendered, indent=2), encoding="utf-8"
        )
        report["checks"].append("actual Three.js gripper frames agree with analytic coordinates")
        with sync_playwright() as p:
            browser = p.chromium.launch(
                args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
            )
            report["browser"] = browser.version
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda e: report["errors"].append(str(e)))
            page.on("request", lambda r: report["external_requests"].append(r.url)
                    if not r.url.startswith(base + "/") else None)
            page.goto(base)
            initial_replay = page.evaluate(
                "async () => JSON.stringify(await (await fetch('/api/replay')).json())"
            )
            page.locator("#robot-import-button").click()
            page.locator("#robot-description-folder").set_input_files(str(source))
            page.wait_for_function(
                "document.querySelector('#robot-description-text').value"
                ".includes('panda_finger_joint2')"
            )
            page.locator("#robot-import-apply").click()
            expect(page.locator("#robot-import-status")).to_contain_text(
                "Робот встроен", timeout=60000
            )
            expect(page.locator("#robot-import-result")).to_contain_text(
                "Связанных mimic-суставов: 1"
            )
            expect(page.locator("#robot-import-result")).not_to_contain_text("Не найдены")
            page.locator("#robot-import-cancel").click()
            expect(page.locator("#viewport canvas")).to_have_count(1)
            expect(page.locator("#imported-model-summary")).to_contain_text("9 суставов")
            page.locator("#focus-button").click()
            page.screenshot(path=str(args.output / "panda-urdf-mimic.png"))
            report["checks"].append("actual Panda OBJ folder rendered with no missing meshes")
            page.locator("#robot-import-button").click()
            page.locator("#robot-description-file").set_input_files(
                str(Path("examples/robot-models/mimic-gripper.urdf").resolve())
            )
            page.wait_for_function(
                "document.querySelector('#robot-description-text').value"
                ".includes('left_finger_joint')"
            )
            page.locator("#robot-import-apply").click()
            expect(page.locator("#robot-import-status")).to_contain_text(
                "Робот встроен", timeout=15000
            )
            page.locator("#robot-import-cancel").click()
            expect(page.locator("#imported-model-summary")).to_contain_text("2 суставов")
            page.locator("#focus-button").click()
            page.screenshot(path=str(args.output / "coupled-gripper.png"))
            summary = page.locator("#imported-model-summary").text_content()
            report["checks"].append("shipped primitive gripper imports without external meshes")
            page.locator("#robot-import-button").click()
            text = Path("examples/robot-models/mimic-gripper.urdf").read_text(encoding="utf-8")
            text = text.replace('<mimic joint="left_finger_joint"/>',
                                '<mimic joint="right_finger_joint"/>')
            page.locator("#robot-description-text").fill(text)
            page.locator("#robot-import-apply").click()
            expect(page.locator("#robot-import-status")).to_contain_text("Цикл", timeout=15000)
            expect(page.locator("#imported-model-summary")).to_have_text(summary)
            page.locator("#robot-import-cancel").click()
            report["checks"].append("mimic cycle rejected without replacing the current model")
            assert initial_replay == page.evaluate(
                "async () => JSON.stringify(await (await fetch('/api/replay')).json())"
            )
            assert not report["errors"] and not report["external_requests"], report
            report["checks"].append("source replay unchanged; no JS errors or external requests")
            browser.close()
        assert before == {
            p.relative_to(source).as_posix(): digest(p) for p in source.rglob("*") if p.is_file()
        }
        report["checks"].append("all upstream source file hashes unchanged")
        report["status"] = "PASS"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
        (args.output / "summary.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
