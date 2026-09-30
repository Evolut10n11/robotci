#!/usr/bin/env bash
# GitHub's Azure Ubuntu mirror can stall ROS provisioning for the entire job.
# Keep changes local to the disposable hosted runner and bound network retries.
set -euo pipefail

sudo python3 - <<'PY'
from pathlib import Path

files = [Path("/etc/apt/sources.list")]
directory = Path("/etc/apt/sources.list.d")
files.extend(directory.glob("*.list"))
files.extend(directory.glob("*.sources"))
for path in files:
    if not path.is_file():
        continue
    original = path.read_text()
    updated = original
    for source in (
        "http://azure.archive.ubuntu.com/ubuntu",
        "https://azure.archive.ubuntu.com/ubuntu",
        "mirror+file:/etc/apt/apt-mirrors.txt",
    ):
        updated = updated.replace(source, "https://archive.ubuntu.com/ubuntu")
    if updated != original:
        path.write_text(updated)

Path("/etc/apt/apt.conf.d/99robotci-network").write_text(
    'Acquire::Retries "2";\n'
    'Acquire::http::Timeout "30";\n'
    'Acquire::https::Timeout "30";\n'
)
PY
