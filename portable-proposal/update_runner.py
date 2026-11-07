#!/usr/bin/env python3

"""Apply a verified update after the Settings process has exited."""

from __future__ import annotations

import argparse
import os
import subprocess
import time
from pathlib import Path


def wait_for_parent(pid: int) -> bool:
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if not Path(f"/proc/{pid}").exists():
            return True
        time.sleep(0.1)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--parent-pid", required=True, type=int)
    parser.add_argument("--resolution", required=True)
    parser.add_argument("--audio", required=True, choices=("host", "handheld", "both"))
    args = parser.parse_args()

    if not wait_for_parent(args.parent_pid):
        return 1
    setup = args.package / "setup-wizard.sh"
    if not setup.is_file():
        return 1

    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "dual-screen-mode"
    runtime.mkdir(parents=True, exist_ok=True)
    log_path = runtime / "update.log"
    with log_path.open("a", encoding="utf-8") as log:
        result = subprocess.run(
            [
                "bash",
                str(setup),
                "--execute",
                "--resolution",
                args.resolution,
                "--audio",
                args.audio,
                "--no-test",
            ],
            cwd=str(args.package),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            env=os.environ.copy(),
        )

    launcher = Path.home() / ".local" / "share" / "dual-screen-mode" / "settings-launcher.sh"
    if launcher.is_file():
        subprocess.Popen(["bash", str(launcher)], start_new_session=True)
    if result.returncode != 0 and shutil_notify_available():
        subprocess.Popen(
            [
                "notify-send",
                "Dual Screen Mode",
                f"The update needs attention. See {log_path}",
            ],
            start_new_session=True,
        )
    return result.returncode


def shutil_notify_available() -> bool:
    return any(
        Path(directory, "notify-send").is_file()
        for directory in os.environ.get("PATH", "").split(os.pathsep)
        if directory
    )


if __name__ == "__main__":
    raise SystemExit(main())
