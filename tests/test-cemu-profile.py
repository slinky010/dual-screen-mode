#!/usr/bin/env python3

import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def controller_xml() -> str:
    return """<?xml version='1.0' encoding='UTF-8'?>
<emulated_controller>
  <type>Wii U GamePad</type>
  <profile>Existing Profile</profile>
  <controller>
    <api>SDLController</api>
    <uuid>deck-controller</uuid>
    <display_name>Steam Deck Controller</display_name>
    <mappings><entry><mapping>1</mapping><button>1</button></entry></mappings>
  </controller>
  <controller>
    <api>DSUController</api>
    <uuid>0</uuid>
    <display_name>Controller 1</display_name>
    <motion>true</motion>
    <ip>192.168.1.55</ip>
    <port>26760</port>
  </controller>
  <controller>
    <api>DSUController</api>
    <uuid>0</uuid>
    <display_name>Controller 1</display_name>
    <motion>true</motion>
    <ip>192.168.1.55</ip>
    <port>26760</port>
  </controller>
</emulated_controller>
"""


with tempfile.TemporaryDirectory() as temporary:
    home = Path(temporary)
    profiles = home / ".config" / "Cemu" / "controllerProfiles"
    profiles.mkdir(parents=True)
    current = profiles / "controller0.xml"
    current.write_text(controller_xml(), encoding="utf-8")
    settings = profiles.parent / "settings.xml"
    settings.write_text("<content><Input><DSUC host=\"127.0.0.1\" port=\"26760\" /></Input></content>", encoding="utf-8")
    backup = home / "backups"

    environment = dict(os.environ, HOME=str(home))
    command = [
        sys.executable,
        str(ROOT / "cemu_profile.py"),
        "--host", "192.168.1.55",
        "--port", "26760",
        "--slot", "0",
        "--backup-dir", str(backup),
    ]
    first = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
    assert first.stdout.startswith("UPDATED "), first.stdout

    updated = ET.parse(current).getroot()
    assert updated.findtext("profile") == "Dual Screen Mode Deck Gyro"
    controllers = updated.findall("controller")
    assert len(controllers) == 2
    assert controllers[0].findtext("api") == "SDLController"
    assert controllers[0].findtext("mappings/entry/mapping") == "1"
    motion = controllers[1]
    assert motion.findtext("api") == "DSUController"
    assert motion.findtext("ip") == "192.168.1.55"
    assert motion.findtext("port") == "26760"
    assert motion.findtext("uuid") == "0"
    assert motion.findtext("display_name") == "DSMController"
    assert motion.findtext("motion") == "true"
    assert motion.findtext("mappings") is not None
    dsu_settings = ET.parse(settings).getroot().find("Input/DSUC")
    assert dsu_settings is not None
    assert dsu_settings.get("host") == "192.168.1.55"
    assert dsu_settings.get("port") == "26760"
    assert (profiles / "Dual Screen Mode Deck Gyro.xml").is_file()
    assert list(backup.glob("controller0.xml"))
    assert list(backup.glob("settings.xml"))

    second = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
    assert second.stdout.startswith("UNCHANGED "), second.stdout


with tempfile.TemporaryDirectory() as temporary:
    home = Path(temporary)
    profiles = home / ".var" / "app" / "info.cemu.Cemu" / "data" / "cemu" / "controllerProfiles"
    profiles.mkdir(parents=True)
    (profiles / "controller0.xml").write_text(controller_xml(), encoding="utf-8")
    settings = home / ".var" / "app" / "info.cemu.Cemu" / "config" / "Cemu" / "settings.xml"
    settings.parent.mkdir(parents=True)
    settings.write_text("<content><Input><DSUC host=\"127.0.0.1\" port=\"26760\" /></Input></content>", encoding="utf-8")
    backup = home / "backups"
    environment = dict(os.environ, HOME=str(home))
    command = [
        sys.executable,
        str(ROOT / "cemu_profile.py"),
        "--host", "192.168.1.55",
        "--port", "26760",
        "--slot", "0",
        "--backup-dir", str(backup),
    ]
    result = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
    assert result.stdout.startswith("UPDATED "), result.stdout
    dsu_settings = ET.parse(settings).getroot().find("Input/DSUC")
    assert dsu_settings is not None
    assert dsu_settings.get("host") == "192.168.1.55"
    assert list(backup.glob("settings.xml"))


with tempfile.TemporaryDirectory() as temporary:
    home = Path(temporary)
    profiles = home / "Emulation" / "roms" / "wiiu" / "controllerProfiles"
    profiles.mkdir(parents=True)
    current = profiles / "controller0.xml"
    current.write_text(controller_xml(), encoding="utf-8")
    settings = profiles.parent / "settings.xml"
    settings.write_text("<content><Input><DSUC host=\"127.0.0.1\" port=\"26760\" /></Input></content>", encoding="utf-8")
    backup = home / "backups"
    environment = dict(os.environ, HOME=str(home))
    command = [
        sys.executable,
        str(ROOT / "cemu_profile.py"),
        "--host", "192.168.1.55",
        "--port", "26760",
        "--slot", "0",
        "--backup-dir", str(backup),
    ]
    result = subprocess.run(command, env=environment, capture_output=True, text=True, check=True)
    assert result.stdout.startswith("UPDATED "), result.stdout
    assert (profiles / "Dual Screen Mode Deck Gyro.xml").is_file()

print("PASS Cemu profile preserves controls and adds DSU motion")
