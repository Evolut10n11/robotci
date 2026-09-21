from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "linux" or shutil.which("bash") is None,
    reason="Nav2 process cleanup requires Linux process groups",
)


def test_cleanup_kills_surviving_child_after_launch_parent_exits(tmp_path: Path) -> None:
    helper = Path(__file__).resolve().parents[1] / "scripts/nav2_process_cleanup.sh"
    marker = tmp_path / "child-pid"
    driver = tmp_path / "launch.py"
    driver.write_text(
        "import os, signal, sys, time\n"
        "from pathlib import Path\n"
        "child = os.fork()\n"
        "if child == 0:\n"
        "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "    marker = Path(sys.argv[1])\n"
        "    ready = marker.with_suffix('.ready')\n"
        "    ready.write_text(str(os.getpid()))\n"
        "    ready.replace(marker)\n"
        "while True:\n"
        "    time.sleep(0.05)\n",
        encoding="utf-8",
    )
    launch = subprocess.Popen(
        [sys.executable, str(driver), str(marker)], start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists(), "test child failed to start"
        child_pid = int(marker.read_text())

        # Reproduce the launch leader disappearing while its child stays alive.
        launch.terminate()
        launch.wait(timeout=5)
        assert Path(f"/proc/{child_pid}/stat").exists()

        completed = subprocess.run(
            ["bash", "-c", 'source "$1"; stop_nav2_process_group "$2"',
             "cleanup-test", str(helper), str(launch.pid)],
            capture_output=True, text=True, timeout=10, check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert "sending SIGKILL" in completed.stdout
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            stat = Path(f"/proc/{child_pid}/stat")
            try:
                state = stat.read_text().split(") ", 1)[1]
            except FileNotFoundError:
                break
            if state.startswith("Z"):
                break
            time.sleep(0.02)
        else:
            pytest.fail("Nav2 descendant survived process-group cleanup")
    finally:
        try:
            os.killpg(launch.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        launch.wait(timeout=5)
