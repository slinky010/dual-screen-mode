#!/usr/bin/env python3

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SPEC = importlib.util.spec_from_file_location("motion_discovery", ROOT / "motion_discovery.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_saved_host_is_preferred():
    original_probe = MODULE.probe_motion_host
    original_discover = MODULE.discover_motion_hosts
    calls = []
    try:
        MODULE.probe_motion_host = lambda host, port: calls.append((host, port)) or True
        MODULE.discover_motion_hosts = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("fallback scan should not run")
        )
        assert MODULE.find_motion_hosts(26760, preferred_host="192.168.1.20") == ["192.168.1.20"]
        assert calls == [("192.168.1.20", 26760)]
    finally:
        MODULE.probe_motion_host = original_probe
        MODULE.discover_motion_hosts = original_discover


def test_stale_host_falls_back_to_discovery():
    original_probe = MODULE.probe_motion_host
    original_discover = MODULE.discover_motion_hosts
    calls = []
    try:
        MODULE.probe_motion_host = lambda host, port: calls.append((host, port)) or False
        MODULE.discover_motion_hosts = lambda port, timeout, preferred_host, attempts: [
            "192.168.1.44"
        ]
        assert MODULE.find_motion_hosts(26760, preferred_host="192.168.1.20") == ["192.168.1.44"]
        assert calls == [("192.168.1.20", 26760)]
    finally:
        MODULE.probe_motion_host = original_probe
        MODULE.discover_motion_hosts = original_discover


def test_public_preferred_host_is_not_probed():
    original_targets = MODULE.discovery_targets
    original_socket = MODULE.socket.socket
    sent = []

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def setsockopt(self, *_args):
            pass

        def settimeout(self, *_args):
            pass

        def sendto(self, _payload, address):
            sent.append(address[0])

        def recvfrom(self, _size):
            raise MODULE.socket.timeout

    try:
        MODULE.discovery_targets = lambda: ["192.168.1.20"]
        MODULE.socket.socket = lambda *_args: FakeSocket()
        assert MODULE.discover_motion_hosts(
            port=26760,
            timeout=0.01,
            preferred_host="8.8.8.8",
            attempts=1,
        ) == []
        assert "8.8.8.8" not in sent
        assert "192.168.1.20" in sent
    finally:
        MODULE.discovery_targets = original_targets
        MODULE.socket.socket = original_socket


if __name__ == "__main__":
    test_saved_host_is_preferred()
    test_stale_host_falls_back_to_discovery()
    test_public_preferred_host_is_not_probed()
    print("PASS saved-host preference, stale-host fallback, and LAN-only probing")
