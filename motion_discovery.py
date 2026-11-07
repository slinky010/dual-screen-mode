#!/usr/bin/env python3
"""Find a DSU motion service on the local network."""

from __future__ import annotations

import argparse
import ipaddress
import json
import random
import socket
import subprocess
import time
from typing import Iterable, List

from motion_probe.dsu_motion_probe import (
    DsuProtocolError,
    MSG_VERSION,
    detect_padded_version_reply,
    make_version_request,
    parse_packet,
)


DEFAULT_PORT = 26760
DEFAULT_ATTEMPTS = 2
SAVED_HOST_TIMEOUT = 1.0
SAVED_HOST_ATTEMPTS = 5
MAX_DIRECT_SCAN_HOSTS = 4096


def _private_ipv4(value: str):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return None
    if address.version != 4 or not (address.is_private or address.is_link_local):
        return None
    return address


def _append_unique(targets: List[str], seen: set, values: Iterable[str]) -> None:
    for value in values:
        if value not in seen:
            seen.add(value)
            targets.append(value)


def probe_motion_host(
    host: str,
    port: int = DEFAULT_PORT,
    timeout: float = SAVED_HOST_TIMEOUT,
    attempts: int = SAVED_HOST_ATTEMPTS,
) -> bool:
    """Give one saved DSU address about five seconds before scanning."""
    address = _private_ipv4(host)
    if address is None:
        return False

    try:
        attempts = max(1, min(int(attempts), 10))
        timeout = max(0.05, float(timeout))
    except (TypeError, ValueError):
        attempts = SAVED_HOST_ATTEMPTS
        timeout = SAVED_HOST_TIMEOUT

    for _attempt in range(attempts):
        client_id = random.randrange(1, 0xFFFFFFFF)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(timeout)
                sock.sendto(make_version_request(client_id), (str(address), int(port)))
                while True:
                    data, _source = sock.recvfrom(4096)
                    if detect_padded_version_reply(data) is not None:
                        return True
                    try:
                        packet = parse_packet(data, require_server=True)
                    except DsuProtocolError:
                        continue
                    if packet.message_type == MSG_VERSION:
                        return True
        except (OSError, ValueError):
            continue
    return False


def _neighbor_targets() -> List[str]:
    """Return local IPv4 neighbors already known to the host's ARP table."""
    try:
        result = subprocess.run(
            ["ip", "-4", "neigh", "show"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    targets = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if not fields:
            continue
        address = _private_ipv4(fields[0])
        if address is not None:
            targets.append(str(address))
    return list(dict.fromkeys(targets))


def discovery_targets() -> List[str]:
    """Return local IPv4 targets only; discovery never leaves the LAN."""
    networks = []
    try:
        result = subprocess.run(
            ["ip", "-j", "-4", "addr", "show", "scope", "global"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        for interface in json.loads(result.stdout or "[]"):
            for address in interface.get("addr_info", []):
                local = address.get("local")
                prefix = address.get("prefixlen")
                if not local or not isinstance(prefix, int):
                    continue
                ip = _private_ipv4(local)
                if ip is not None:
                    networks.append(ipaddress.ip_network(f"{local}/{prefix}", strict=False))
    except (OSError, ValueError, TypeError, json.JSONDecodeError, subprocess.SubprocessError):
        pass

    targets: List[str] = []
    seen = set()
    # Moonlight normally leaves the handheld in the host's ARP/neighbour
    # table. These addresses are especially valuable on /16 or larger LANs,
    # where probing every possible host would be noisy and slow.
    _append_unique(targets, seen, _neighbor_targets())
    for network in networks:
        if network.num_addresses <= MAX_DIRECT_SCAN_HOSTS:
            _append_unique(targets, seen, (str(address) for address in network.hosts()))
        # Broadcast is useful even when direct host scanning is capped, but it
        # is kept after known neighbors and direct targets.
        _append_unique(targets, seen, (str(network.broadcast_address),))
    return targets


def discover_motion_hosts(
    port: int = DEFAULT_PORT,
    timeout: float = 1.2,
    preferred_host: str = "",
    attempts: int = DEFAULT_ATTEMPTS,
) -> List[str]:
    """Return DSU service addresses that answer a version request."""
    targets = discovery_targets()
    # A saved hostname is valid for the user's manual monitor connection, but
    # discovery must never turn it into an unbounded outbound probe.  Only put
    # a validated private/link-local IPv4 address ahead of the LAN targets.
    preferred_address = _private_ipv4(preferred_host) if preferred_host else None
    if preferred_address is not None:
        preferred = str(preferred_address)
        if preferred in targets:
            targets.remove(preferred)
        targets.insert(0, preferred)
    found = []
    try:
        attempts = max(1, min(int(attempts), 5))
    except (TypeError, ValueError):
        attempts = DEFAULT_ATTEMPTS
    for _attempt in range(attempts):
        client_id = random.randrange(1, 0xFFFFFFFF)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.settimeout(0.12)
                request = make_version_request(client_id)
                for target in targets:
                    try:
                        sock.sendto(request, (target, int(port)))
                    except (OSError, ValueError):
                        continue
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    try:
                        data, address = sock.recvfrom(4096)
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    try:
                        if detect_padded_version_reply(data) is not None:
                            found.append(address[0])
                            continue
                        packet = parse_packet(data, require_server=True)
                        if packet.message_type == MSG_VERSION:
                            found.append(address[0])
                    except DsuProtocolError:
                        continue
        except OSError:
            continue
        if found:
            break
    return list(dict.fromkeys(found))


def find_motion_hosts(
    port: int = DEFAULT_PORT,
    timeout: float = 1.2,
    preferred_host: str = "",
    attempts: int = DEFAULT_ATTEMPTS,
) -> List[str]:
    """Prefer the saved address, then fall back to local-network discovery."""
    if preferred_host and probe_motion_host(preferred_host, port):
        return [preferred_host]
    return discover_motion_hosts(port, timeout, preferred_host=preferred_host, attempts=attempts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout", type=float, default=1.2)
    parser.add_argument("--attempts", type=int, default=DEFAULT_ATTEMPTS)
    parser.add_argument("--preferred-host", default="")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.timeout <= 0 or not 1 <= args.attempts <= 5:
        return 2
    hosts = find_motion_hosts(
        args.port,
        args.timeout,
        preferred_host=args.preferred_host,
        attempts=args.attempts,
    )
    if not hosts:
        return 1
    print(hosts[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
