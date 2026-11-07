#!/usr/bin/env python3

"""Small, user-facing helper for checking and downloading DSM updates."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Tuple


RELEASES_URL = "https://api.github.com/repos/slinky010/dual-screen-mode/releases"
USER_AGENT = "Dual-Screen-Mode-Updater/0.1"
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024


class UpdateError(RuntimeError):
    """A safe, user-readable update failure."""


def _version_key(value: str) -> Tuple[int, int, int, int, Tuple[Tuple[int, object], ...]]:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", value.strip())
    if not match:
        raise ValueError(f"Unsupported version: {value}")
    major, minor, patch = (int(part) for part in match.group(1, 2, 3))
    prerelease = match.group(4)
    if prerelease is None:
        return major, minor, patch, 1, ()
    tokens = []
    for token in prerelease.split("."):
        if token.isdigit():
            tokens.append((0, int(token)))
        else:
            tokens.append((1, token.lower()))
    return major, minor, patch, 0, tuple(tokens)


def is_newer(candidate: str, current: str) -> bool:
    try:
        return _version_key(candidate) > _version_key(current)
    except ValueError:
        return False


def _asset_map(release: Dict[str, object]) -> Dict[str, Dict[str, object]]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        return {}
    result = {}
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = asset.get("name")
        url = asset.get("browser_download_url")
        if isinstance(name, str) and isinstance(url, str) and asset.get("state", "uploaded") == "uploaded":
            result[name] = asset
    return result


def _release_has_linux_package(release: Dict[str, object]) -> bool:
    assets = _asset_map(release)
    for name in assets:
        if name.endswith(".tar.gz") and not name.endswith(".sha256") and f"{name}.sha256" in assets:
            return True
    return False


def find_update(releases: Iterable[Dict[str, object]], current_version: str) -> Optional[Dict[str, object]]:
    candidates = []
    for release in releases:
        if not isinstance(release, dict) or release.get("draft"):
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not is_newer(tag, current_version):
            continue
        if not _release_has_linux_package(release):
            continue
        try:
            key = _version_key(tag)
        except ValueError:
            continue
        candidates.append((key, release))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _read_url(url: str, limit: int) -> bytes:
    if not url.startswith("https://"):
        raise UpdateError("The update source did not use a secure connection.")
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            length = response.headers.get("Content-Length")
            if length and int(length) > limit:
                raise UpdateError("The update download is larger than expected.")
            chunks = []
            total = 0
            while True:
                chunk = response.read(1024 * 128)
                if not chunk:
                    break
                total += len(chunk)
                if total > limit:
                    raise UpdateError("The update download is larger than expected.")
                chunks.append(chunk)
            return b"".join(chunks)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise UpdateError(f"Could not download the update: {exc}") from exc


def fetch_releases() -> list[Dict[str, object]]:
    try:
        data = json.loads(_read_url(RELEASES_URL, MAX_METADATA_BYTES).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateError("GitHub returned an unreadable update list.") from exc
    if not isinstance(data, list):
        raise UpdateError("GitHub returned an invalid update list.")
    return [item for item in data if isinstance(item, dict)]


def _package_assets(release: Dict[str, object]) -> Tuple[Dict[str, object], Dict[str, object]]:
    assets = _asset_map(release)
    packages = [asset for name, asset in assets.items() if name.endswith(".tar.gz") and not name.endswith(".sha256")]
    packages = [asset for asset in packages if f"{asset['name']}.sha256" in assets]
    if not packages:
        raise UpdateError("This release does not include a verifiable Linux package.")
    package = packages[0]
    checksum = assets[f"{package['name']}.sha256"]
    return package, checksum


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as handle:
        members = handle.getmembers()
        for member in members:
            if member.issym() or member.islnk():
                raise UpdateError("The update package contains an unsupported link.")
            target = (destination / member.name).resolve()
            if target != destination.resolve() and destination.resolve() not in target.parents:
                raise UpdateError("The update package contains an unsafe path.")
        for member in members:
            handle.extract(member, destination)


def download_and_extract(release: Dict[str, object], progress: Optional[Callable[[str], None]] = None) -> Path:
    package, checksum = _package_assets(release)
    package_name = str(package["name"])
    checksum_name = str(checksum["name"])
    work_dir = Path(tempfile.mkdtemp(prefix="dual-screen-mode-update-"))
    archive = work_dir / package_name
    checksum_file = work_dir / checksum_name
    extracted = work_dir / "package"
    try:
        if progress:
            progress("Downloading the update…")
        archive.write_bytes(_read_url(str(package["browser_download_url"]), MAX_ARCHIVE_BYTES))
        checksum_file.write_bytes(_read_url(str(checksum["browser_download_url"]), 4096))
        expected_match = re.search(rb"\b([0-9a-fA-F]{64})\b", checksum_file.read_bytes())
        if not expected_match:
            raise UpdateError("The update checksum file was not readable.")
        actual = hashlib.sha256(archive.read_bytes()).hexdigest()
        expected = expected_match.group(1).decode("ascii").lower()
        if actual != expected:
            raise UpdateError("The downloaded update failed its checksum check.")
        if progress:
            progress("Download verified. Preparing the installer…")
        _safe_extract(archive, extracted)
        if not (extracted / "setup-wizard.sh").is_file() or not (extracted / "update_runner.py").is_file():
            raise UpdateError("The downloaded package is missing its installer.")
        return extracted
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
