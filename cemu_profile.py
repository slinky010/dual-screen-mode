#!/usr/bin/env python3

"""Create DSM's Cemu Deck-controls-plus-gyro profile without losing mappings."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


PROFILE_NAME = "Dual Screen Mode Deck Gyro"
MOTION_DISPLAY_NAME = "DSMController"


def candidate_profile_dirs(home: Path) -> Iterable[Path]:
    yield home / ".config" / "Cemu" / "controllerProfiles"
    yield home / ".var" / "app" / "info.cemu.Cemu" / "data" / "cemu" / "controllerProfiles"
    yield home / ".var" / "app" / "info.cemu.Cemu" / "config" / "Cemu" / "controllerProfiles"
    yield home / ".var" / "app" / "info.cemu.Cemu" / "config" / "cemu" / "controllerProfiles"
    yield home / ".local" / "share" / "Cemu" / "controllerProfiles"
    # EmuDeck's desktop Proton build keeps Cemu beside its Wii U files.
    yield home / "Emulation" / "roms" / "wiiu" / "controllerProfiles"


def find_profile_dir(home: Path) -> Optional[Path]:
    candidates = list(candidate_profile_dirs(home))
    for directory in candidates:
        if (directory / "controller0.xml").is_file():
            return directory
    for directory in candidates:
        if directory.is_dir() and any(directory.glob("*.xml")):
            return directory
    for directory in candidates:
        if directory.parent.exists() and (directory.parent / "settings.xml").is_file():
            directory.mkdir(parents=True, exist_ok=True)
            return directory
    return None


def find_settings_path(home: Path, profile_dir: Path) -> Optional[Path]:
    """Find the settings.xml paired with the selected Cemu profile tree.

    The Flatpak keeps controllerProfiles under data/cemu but keeps Cemu's
    settings.xml under config/Cemu. Native installs normally keep both files
    under the same ~/.config/Cemu directory.
    """
    candidates = [profile_dir.parent / "settings.xml"]
    flatpak_data = home / ".var" / "app" / "info.cemu.Cemu" / "data" / "cemu"
    if profile_dir == flatpak_data / "controllerProfiles":
        candidates.append(home / ".var" / "app" / "info.cemu.Cemu" / "config" / "Cemu" / "settings.xml")
    for path in candidates:
        if path.is_file():
            return path
    return None


def text(node: ET.Element, name: str, value: str) -> None:
    child = node.find(name)
    if child is None:
        child = ET.SubElement(node, name)
    child.text = value


def controller_api(node: ET.Element) -> str:
    return (node.findtext("api") or "").strip()


def existing_source(profile_dir: Path) -> Optional[Path]:
    current = profile_dir / "controller0.xml"
    if current.is_file():
        return current
    named = profile_dir / f"{PROFILE_NAME}.xml"
    if named.is_file():
        return named
    return next(iter(sorted(profile_dir.glob("*.xml"))), None)


def load_tree(source: Optional[Path]) -> ET.ElementTree:
    if source is None:
        root = ET.Element("emulated_controller")
        return ET.ElementTree(root)
    return ET.parse(source)


def add_motion_controller(root: ET.Element, host: str, port: int, slot: int) -> None:
    text(root, "type", "Wii U GamePad")
    text(root, "profile", PROFILE_NAME)

    # Cemu may normalize the DSU display name to "Controller 1" when it
    # loads or saves a profile.  Do not rely on DSMController surviving that
    # round trip: remove every old DSU entry before adding DSM's single,
    # authoritative motion entry.  Non-DSU mappings are preserved unchanged.
    for node in list(root.findall("controller")):
        if controller_api(node) == "DSUController":
            root.remove(node)

    controller = ET.SubElement(root, "controller")
    text(controller, "api", "DSUController")
    # Cemu's DSU profile format uses uuid 0 for the first DSU controller slot.
    # Keep the selected slot in the metadata so DSM can update it predictably.
    text(controller, "uuid", str(slot))
    text(controller, "display_name", MOTION_DISPLAY_NAME)
    text(controller, "motion", "true")
    axis = ET.SubElement(controller, "axis")
    text(axis, "deadzone", "0.25")
    text(axis, "range", "1")
    rotation = ET.SubElement(controller, "rotation")
    text(rotation, "deadzone", "0.25")
    text(rotation, "range", "1")
    trigger = ET.SubElement(controller, "trigger")
    text(trigger, "deadzone", "0.25")
    text(trigger, "range", "1")
    text(controller, "ip", host)
    text(controller, "port", str(port))
    ET.SubElement(controller, "mappings")


def serialise(tree: ET.ElementTree) -> bytes:
    ET.indent(tree, space="  ")
    with tempfile.NamedTemporaryFile() as temporary:
        tree.write(temporary.name, encoding="utf-8", xml_declaration=True)
        temporary.seek(0)
        return temporary.read()


def backup_file(source: Path, backup_dir: Path) -> None:
    if not source.is_file():
        return
    backup_dir.mkdir(parents=True, exist_ok=True)
    destination = backup_dir / source.name
    if destination.exists():
        destination = backup_dir / f"{source.stem}-{datetime.now().strftime('%H%M%S%f')}{source.suffix}"
    shutil.copy2(source, destination)


def atomic_write(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
        temporary.write(payload)
        temporary.flush()
        temporary_name = Path(temporary.name)
    try:
        temporary_name.replace(destination)
    finally:
        temporary_name.unlink(missing_ok=True)


def update_dsu_settings(settings_path: Path, host: str, port: int) -> Optional[bytes]:
    """Update Cemu's global DSU host and port when settings.xml exists."""
    if not settings_path.is_file():
        return None
    try:
        tree = ET.parse(settings_path)
        root = tree.getroot()
        input_node = root.find("Input")
        if input_node is None:
            input_node = ET.SubElement(root, "Input")
        dsuc = input_node.find("DSUC")
        if dsuc is None:
            dsuc = ET.SubElement(input_node, "DSUC")
        dsuc.set("host", host)
        dsuc.set("port", str(port))
        return serialise(tree)
    except (ET.ParseError, OSError, ValueError):
        return None


def update_profile(args: argparse.Namespace) -> str:
    profile_dir = find_profile_dir(Path.home())
    if profile_dir is None:
        return "NOT_FOUND"

    current = profile_dir / "controller0.xml"
    source = existing_source(profile_dir)
    try:
        tree = load_tree(source)
        add_motion_controller(tree.getroot(), args.host, args.port, args.slot)
        payload = serialise(tree)
    except (ET.ParseError, OSError, ValueError) as error:
        return f"ERROR {error}"

    named = profile_dir / f"{PROFILE_NAME}.xml"
    settings_path = find_settings_path(Path.home(), profile_dir)
    settings_payload = update_dsu_settings(settings_path, args.host, args.port) if settings_path else None
    current_settings = settings_path.read_bytes() if settings_path else None
    settings_changed = settings_payload is not None and current_settings != settings_payload
    changed = (not current.is_file() or current.read_bytes() != payload or
               not named.is_file() or named.read_bytes() != payload or
               settings_changed)
    if not changed:
        return f"UNCHANGED {current}"

    backup_dir = Path(args.backup_dir).expanduser()
    backup_file(current, backup_dir)
    backup_file(named, backup_dir)
    if settings_changed:
        backup_file(settings_path, backup_dir)
    try:
        atomic_write(named, payload)
        atomic_write(current, payload)
        if settings_changed and settings_payload is not None:
            atomic_write(settings_path, settings_payload)
    except OSError as error:
        return f"ERROR {error}"
    updated = f"UPDATED {current} {named}"
    if settings_changed:
        updated += f" {settings_path}"
    return updated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=26760)
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument("--backup-dir", required=True)
    args = parser.parse_args()
    if not (1 <= args.port <= 65535):
        parser.error("--port must be between 1 and 65535")
    if not (0 <= args.slot <= 3):
        parser.error("--slot must be between 0 and 3")
    return args


if __name__ == "__main__":
    print(update_profile(parse_args()))
