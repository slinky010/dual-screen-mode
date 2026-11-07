#!/usr/bin/env python3

import hashlib
import io
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import update_support as support


def asset(name):
    return {
        "name": name,
        "state": "uploaded",
        "browser_download_url": f"https://github.com/slinky010/dual-screen-mode/releases/download/v0.1.6-beta/{name}",
    }


releases = [
    {"tag_name": "v0.1.5-beta", "draft": False, "assets": [asset("old.tar.gz"), asset("old.tar.gz.sha256")]},
    {"tag_name": "v0.1.6-beta", "draft": False, "assets": [asset("new.tar.gz"), asset("new.tar.gz.sha256")]},
]
assert support.find_update(releases, "0.1.5-beta")["tag_name"] == "v0.1.6-beta"
assert support.find_update(releases[:1], "0.1.5-beta") is None
assert support.is_newer("v0.1.6-beta", "0.1.5-beta")
assert not support.is_newer("v0.1.5-beta", "0.1.5-beta")


with tempfile.TemporaryDirectory() as temporary:
    temporary_path = Path(temporary)
    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w:gz") as archive:
        content = b"#!/usr/bin/env bash\n"
        info = tarfile.TarInfo("setup-wizard.sh")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
        runner = b"#!/usr/bin/env python3\n"
        info = tarfile.TarInfo("update_runner.py")
        info.size = len(runner)
        archive.addfile(info, io.BytesIO(runner))
    package = archive_bytes.getvalue()
    digest = hashlib.sha256(package).hexdigest()
    original_reader = support._read_url
    support._read_url = lambda url, limit: package if url.endswith(".tar.gz") else f"{digest}  update.tar.gz\n".encode()
    try:
        release = {
            "tag_name": "v0.1.6-beta",
            "assets": [
                asset("update.tar.gz"),
                asset("update.tar.gz.sha256"),
            ],
        }
        extracted = support.download_and_extract(release)
        assert (extracted / "setup-wizard.sh").is_file()
        assert (extracted / "update_runner.py").is_file()
    finally:
        support._read_url = original_reader


print("PASS update discovery, checksum verification, and safe extraction")
