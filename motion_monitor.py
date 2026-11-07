#!/usr/bin/env python3
"""Keep an optional DSU motion connection healthy while the mode is active.

This is deliberately a small, user-scoped helper.  It does not replace the
Deck's DSU service and it does not feed an emulator by itself; it renews a DSU
subscription, records connection health, and lets Dual Screen Mode show a clear
status when the Deck goes away.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import time
from pathlib import Path
from typing import Any, Dict, Optional

from motion_probe.dsu_motion_probe import DsuClient, ProbeEvent, format_rejection_detail


STALE_AFTER = 3.0
STATUS_INTERVAL = 0.5


def atomic_write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def write_status(path: Path, *, state: str, host: str, port: int, slot: int,
                 started_at: float, client: Optional[DsuClient] = None,
                 last_motion: Optional[float] = None,
                 controller: Optional[Dict[str, Any]] = None,
                 source: Optional[str] = None, last_error: str = "",
                 last_rejected: str = "") -> None:
    now = time.monotonic()
    stats: Dict[str, Any] = client.stats(now) if client else {
        "valid": 0,
        "invalid": 0,
        "dropped": 0,
        "rate": 0.0,
        "age": None,
        "accepted_types": {},
        "rejected_reasons": {},
        "last_invalid": None,
    }
    motion_age = None if last_motion is None else max(0.0, now - last_motion)
    atomic_write_json(
        path,
        {
            "state": state,
            "healthy": state == "connected",
            "host": host,
            "port": port,
            "slot": slot,
            "updated": time.time(),
            "uptime": max(0.0, now - started_at),
            "valid": stats.get("valid", 0),
            "invalid": stats.get("invalid", 0),
            "dropped": stats.get("dropped", 0),
            "rate": stats.get("rate", 0.0),
            "last_packet_age": stats.get("age"),
            "last_motion_age": motion_age,
            "accepted_types": stats.get("accepted_types", {}),
            "rejected_reasons": stats.get("rejected_reasons", {}),
            "controller": controller,
            "source": source,
            "last_error": last_error,
            "last_rejected": last_rejected,
        },
    )


def valid_target(host: str, port: int, slot: int) -> bool:
    return bool(host) and len(host) <= 253 and not any(character.isspace() for character in host) and 1 <= port <= 65535 and slot in range(4)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=26760)
    parser.add_argument("--slot", type=int, default=0)
    parser.add_argument("--status-file", type=Path, required=True)
    parser.add_argument("--pid-file", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not valid_target(args.host, args.port, args.slot):
        write_status(
            args.status_file,
            state="invalid_config",
            host=args.host,
            port=args.port,
            slot=args.slot,
            started_at=time.monotonic(),
            last_error="Check the Deck address, port, and controller slot.",
        )
        return 2

    stop_requested = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    args.pid_file.parent.mkdir(parents=True, exist_ok=True)
    args.pid_file.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    os.chmod(args.pid_file, 0o600)
    started_at = time.monotonic()
    events: "queue.Queue[ProbeEvent]" = queue.Queue()
    client: Optional[DsuClient] = None
    last_motion: Optional[float] = None
    controller: Optional[Dict[str, Any]] = None
    source: Optional[str] = None
    last_error = ""
    last_rejected = ""
    next_status = 0.0
    next_reconnect = 0.0
    reconnect_delay = 1.0
    client_started_at = started_at

    def consume(event: ProbeEvent) -> None:
        nonlocal last_motion, controller, source, last_error, last_rejected, reconnect_delay
        if event.kind == "motion":
            last_motion = time.monotonic()
            last_error = ""
            reconnect_delay = 1.0
        elif event.kind == "info":
            info = event.value
            controller = {
                "slot": info.slot,
                "connected": info.connected,
                "model": info.model_name,
                "connection": info.connection_name,
            }
        elif event.kind == "source":
            address = event.value
            source = f"{address[0]}:{address[1]}"
        elif event.kind == "invalid":
            last_rejected = format_rejection_detail(event.value)
        elif event.kind == "error":
            last_error = str(event.value)

    try:
        while not stop_requested:
            now = time.monotonic()
            if client is None and now >= next_reconnect:
                events = queue.Queue()
                client = DsuClient(args.host, args.port, args.slot, events)
                client.start()
                client_started_at = now
            try:
                event = events.get(timeout=0.1)
            except queue.Empty:
                event = None

            if event is not None:
                consume(event)
            while True:
                try:
                    consume(events.get_nowait())
                except queue.Empty:
                    break

            now = time.monotonic()
            if client is not None and not client.is_alive():
                client.join(timeout=0.1)
                if not stop_requested:
                    client = None
                    next_reconnect = now + reconnect_delay
                    reconnect_delay = min(15.0, reconnect_delay * 2.0)
                    last_error = last_error or "The motion socket stopped; reconnecting."
            elif client is not None and (
                (last_motion is None and now - client_started_at > STALE_AFTER)
                or (last_motion is not None and now - last_motion > STALE_AFTER)
            ):
                # UDP has no disconnect event. Force a fresh subscription when
                # the Deck stops sending so a vanished/restarted DSU service
                # does not leave the monitor looking alive forever.
                client.stop()
                client.join(timeout=0.5)
                client = None
                next_reconnect = now
                last_error = "No motion packets; reconnecting."
            if now >= next_status:
                if client is not None and client.is_alive() and last_motion is not None and now - last_motion <= STALE_AFTER:
                    state = "connected"
                elif client is None:
                    state = "reconnecting"
                elif client is not None and now - client_started_at <= STALE_AFTER:
                    state = "connecting"
                elif last_error:
                    state = "unreachable"
                else:
                    state = "no_motion"
                write_status(
                    args.status_file,
                    state=state,
                    host=args.host,
                    port=args.port,
                    slot=args.slot,
                    started_at=started_at,
                    client=client,
                    last_motion=last_motion,
                    controller=controller,
                    source=source,
                    last_error=last_error,
                    last_rejected=last_rejected,
                )
                next_status = now + STATUS_INTERVAL
    finally:
        if client is not None:
            client.stop()
            client.join(timeout=1.0)
        write_status(
            args.status_file,
            state="stopped",
            host=args.host,
            port=args.port,
            slot=args.slot,
            started_at=started_at,
            client=client,
            last_motion=last_motion,
            controller=controller,
            source=source,
            last_error=last_error,
            last_rejected=last_rejected,
        )
        try:
            if args.pid_file.read_text(encoding="utf-8").strip() == str(os.getpid()):
                args.pid_file.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
