#!/usr/bin/env python3
"""Visual client for the Cemuhook/DSU motion protocol.

This is intentionally independent of Moonlight, Sunshine, Cemu, and Azahar.
The Deck (or another DSU server) is the target; this program only subscribes
to controller metadata and motion packets and visualizes what arrives.

The ``--mock`` mode starts a tiny local DSU server so the UI and protocol
parser can be exercised without a Deck.
"""

from __future__ import annotations

import argparse
import math
import queue
import random
import select
import socket
import struct
import threading
import time
import zlib
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, Optional, Sequence, Tuple


PROTOCOL_VERSION = 1001
DEFAULT_PORT = 26760

MAGIC_CLIENT = b"DSUC"
MAGIC_SERVER = b"DSUS"

MSG_VERSION = 0x100000
MSG_PORT_INFO = 0x100001
MSG_PAD_DATA = 0x100002

# The first 16 bytes are the common header.  The message type follows it and
# is included in the packet-length field, which makes the complete framing
# header 20 bytes long.
HEADER = struct.Struct("<4sHHIII")
HEADER_SIZE = HEADER.size

MESSAGE_NAMES = {
    MSG_VERSION: "Version",
    MSG_PORT_INFO: "PortInfo",
    MSG_PAD_DATA: "PadData",
}


def message_type_name(message_type: int) -> str:
    return MESSAGE_NAMES.get(message_type, f"0x{message_type:06x}")


class DsuProtocolError(ValueError):
    """Raised when a datagram is not a valid DSU packet."""


@dataclass(frozen=True)
class DsuPacket:
    magic: bytes
    version: int
    declared_length: int
    sender_id: int
    message_type: int
    payload: bytes
    crc_ok: bool


@dataclass(frozen=True)
class ControllerInfo:
    slot: int
    state: int
    model: int
    connection_type: int
    mac: bytes
    battery: int
    active: int

    @property
    def connected(self) -> bool:
        return self.state == 2

    @property
    def model_name(self) -> str:
        return {0: "not reported", 1: "partial/no gyro", 2: "full gyro"}.get(
            self.model, f"model {self.model}"
        )

    @property
    def connection_name(self) -> str:
        return {0: "not reported", 1: "USB", 2: "Bluetooth"}.get(
            self.connection_type, f"type {self.connection_type}"
        )


@dataclass(frozen=True)
class MotionSample:
    slot: int
    connected: bool
    sequence: int
    timestamp_us: int
    accel: Tuple[float, float, float]
    gyro: Tuple[float, float, float]


def build_packet(
    magic: bytes,
    message_type: int,
    payload: bytes = b"",
    sender_id: Optional[int] = None,
) -> bytes:
    """Build a DSU packet and calculate its CRC32."""

    if magic not in (MAGIC_CLIENT, MAGIC_SERVER):
        raise ValueError("magic must be DSUC or DSUS")
    if not 0 <= message_type <= 0xFFFFFFFF:
        raise ValueError("message type is outside uint32 range")
    if len(payload) + 4 > 0xFFFF:
        raise ValueError("payload is too large for the DSU length field")

    if sender_id is None:
        sender_id = random.randrange(1, 0xFFFFFFFF)

    # The length starts at offset 16, so it includes the message type itself.
    declared_length = 4 + len(payload)
    packet = bytearray(
        HEADER.pack(
            magic,
            PROTOCOL_VERSION,
            declared_length,
            0,
            sender_id & 0xFFFFFFFF,
            message_type,
        )
        + payload
    )
    crc = zlib.crc32(packet) & 0xFFFFFFFF
    packet[8:12] = struct.pack("<I", crc)
    return bytes(packet)


def parse_packet(data: bytes, *, require_server: bool = False) -> DsuPacket:
    """Validate and decode one DSU datagram.

    DSU's length is the number of bytes from offset 16 onward, meaning it
    includes the four-byte message type but not the first 16 header bytes.
    """

    if len(data) < HEADER_SIZE:
        raise DsuProtocolError(f"packet too short ({len(data)} bytes)")

    magic, version, declared_length, received_crc, sender_id, message_type = (
        HEADER.unpack_from(data)
    )
    if require_server and magic != MAGIC_SERVER:
        raise DsuProtocolError(f"unexpected magic {magic!r}")
    if magic not in (MAGIC_CLIENT, MAGIC_SERVER):
        raise DsuProtocolError(f"unknown magic {magic!r}")
    if version != PROTOCOL_VERSION:
        raise DsuProtocolError(f"unsupported protocol version {version}")

    expected_total = 16 + declared_length
    if declared_length < 4:
        raise DsuProtocolError("length does not include a message type")
    if len(data) != expected_total:
        raise DsuProtocolError(
            f"length mismatch: datagram={len(data)} expected={expected_total}"
        )

    candidate = bytearray(data)
    candidate[8:12] = b"\x00\x00\x00\x00"
    calculated_crc = zlib.crc32(candidate) & 0xFFFFFFFF
    if calculated_crc != received_crc:
        raise DsuProtocolError(
            f"CRC mismatch: received=0x{received_crc:08x} "
            f"calculated=0x{calculated_crc:08x}"
        )

    return DsuPacket(
        magic=magic,
        version=version,
        declared_length=declared_length,
        sender_id=sender_id,
        message_type=message_type,
        payload=data[20:],
        crc_ok=True,
    )


def inspect_invalid_datagram(data: bytes, error: Exception) -> Dict[str, object]:
    """Collect enough raw-header information to explain a rejected datagram."""

    reason = str(error)
    lowered = reason.lower()
    if "crc" in lowered:
        category = "CRC"
    elif "length" in lowered or "short" in lowered:
        category = "length"
    elif "version" in lowered:
        category = "version"
    elif "magic" in lowered:
        category = "magic"
    else:
        category = "framing"

    detail: Dict[str, object] = {
        "stage": "framing",
        "category": category,
        "reason": reason,
        "actual_length": len(data),
    }
    if len(data) >= HEADER_SIZE:
        magic, version, declared_length, received_crc, sender_id, message_type = (
            HEADER.unpack_from(data)
        )
        expected_length = 16 + declared_length
        calculated_crc = None
        if len(data) >= 12:
            candidate = bytearray(data)
            candidate[8:12] = b"\x00\x00\x00\x00"
            calculated_crc = zlib.crc32(candidate) & 0xFFFFFFFF
        detail.update(
            magic=magic.decode("ascii", errors="replace"),
            version=version,
            declared_length=declared_length,
            expected_length=expected_length,
            message_type=message_type,
            message_name=message_type_name(message_type),
            sender_id=sender_id,
            received_crc=f"0x{received_crc:08x}",
            calculated_crc=(
                None if calculated_crc is None else f"0x{calculated_crc:08x}"
            ),
            crc_matches=(calculated_crc == received_crc),
        )
    return detail


def inspect_payload_rejection(
    packet: DsuPacket, error: Exception
) -> Dict[str, object]:
    """Describe a framed packet whose message payload we could not decode."""

    return {
        "stage": "payload",
        "category": "payload",
        "reason": str(error),
        "message_type": packet.message_type,
        "message_name": message_type_name(packet.message_type),
        "payload_length": len(packet.payload),
        "declared_length": packet.declared_length,
        "sender_id": packet.sender_id,
    }


def format_rejection_detail(detail: Dict[str, object]) -> str:
    """Turn a structured rejection into a compact UI/terminal message."""

    name = str(detail.get("message_name", "unknown"))
    reason = str(detail.get("reason", "unknown reason"))
    if detail.get("stage") == "payload":
        return (
            f"{name} payload: {reason} "
            f"(payload={detail.get('payload_length', '?')} bytes)"
        )

    if "actual_length" not in detail:
        return reason
    actual = detail["actual_length"]
    declared = detail.get("declared_length", "?")
    expected = detail.get("expected_length", "?")
    crc = detail.get("crc_matches")
    crc_text = "n/a" if crc is None else ("ok" if crc else "BAD")
    return (
        f"{name}: {reason} "
        f"(actual={actual}, declared={declared}, expected={expected}, CRC={crc_text})"
    )


def detect_padded_version_reply(data: bytes) -> Optional[Dict[str, object]]:
    """Recognize SteamDeckGyroDSU's observed padded version response.

    The normal DSU version reply is 22 bytes: a 20-byte header plus a
    two-byte version payload.  The Deck service currently answers our version
    probe with a 24-byte, CRC-valid variant whose header declares six bytes
    after the first 16 bytes and whose event field is zero.  It is harmless
    handshake traffic, not motion data, so keep it visible without reporting
    it as a bad motion packet.
    """

    if len(data) != 24 or len(data) < HEADER_SIZE:
        return None
    magic, version, declared_length, received_crc, sender_id, message_type = (
        HEADER.unpack_from(data)
    )
    if (
        magic != MAGIC_SERVER
        or version != PROTOCOL_VERSION
        or declared_length != 6
        or message_type != 0
    ):
        return None
    candidate = bytearray(data)
    candidate[8:12] = b"\x00\x00\x00\x00"
    calculated_crc = zlib.crc32(candidate) & 0xFFFFFFFF
    if calculated_crc != received_crc:
        return None
    return {
        "message_name": "Version (padded)",
        "sender_id": sender_id,
        "actual_length": len(data),
        "declared_length": declared_length,
        "payload_hex": data[20:].hex(" "),
        "crc": f"0x{received_crc:08x}",
    }


def make_version_request(client_id: int) -> bytes:
    return build_packet(MAGIC_CLIENT, MSG_VERSION, sender_id=client_id)


def make_port_info_request(client_id: int, slots: Iterable[int]) -> bytes:
    slots = tuple(slots)
    if not 1 <= len(slots) <= 4:
        raise ValueError("DSU port-info request needs one to four slots")
    if any(slot not in range(4) for slot in slots):
        raise ValueError("DSU slots must be in the range 0..3")
    payload = struct.pack("<i", len(slots)) + bytes(slots)
    return build_packet(MAGIC_CLIENT, MSG_PORT_INFO, payload, client_id)


def make_pad_data_request(client_id: int, slot: int) -> bytes:
    if slot not in range(4):
        raise ValueError("DSU slots must be in the range 0..3")
    # Flag 1 means slot-based registration.  The remaining six bytes are the
    # MAC field, unused for slot registration, and are required by the format.
    payload = bytes((1, slot)) + b"\x00" * 6
    return build_packet(MAGIC_CLIENT, MSG_PAD_DATA, payload, client_id)


def parse_controller_info(payload: bytes) -> ControllerInfo:
    if len(payload) < 12:
        raise DsuProtocolError("controller-info payload is too short")
    slot, state, model, connection_type = struct.unpack_from("<BBBB", payload)
    mac = payload[4:10]
    battery = payload[10]
    active = payload[11]
    return ControllerInfo(slot, state, model, connection_type, mac, battery, active)


def parse_motion_sample(payload: bytes) -> MotionSample:
    # The protocol's controller-data payload is 80 bytes after the message
    # type.  Motion begins at offset 48 for the timestamp and 56 for accel.
    if len(payload) < 80:
        raise DsuProtocolError("controller-data payload is too short")
    slot = payload[0]
    connected = bool(payload[11])
    sequence = struct.unpack_from("<I", payload, 12)[0]
    timestamp_us = struct.unpack_from("<Q", payload, 48)[0]
    accel = struct.unpack_from("<fff", payload, 56)
    gyro = struct.unpack_from("<fff", payload, 68)
    return MotionSample(slot, connected, sequence, timestamp_us, accel, gyro)


def battery_name(value: int) -> str:
    return {
        0x00: "not reported",
        0x01: "dying",
        0x02: "low",
        0x03: "medium",
        0x04: "high",
        0x05: "full",
        0xEE: "charging",
        0xEF: "charged",
    }.get(value, f"0x{value:02x}")


class SequenceTracker:
    """Track DSU packet gaps without treating normal 32-bit wrap as a drop."""

    def __init__(self) -> None:
        self.last: Optional[int] = None
        self.dropped = 0

    def observe(self, sequence: int) -> int:
        gap = 0
        if self.last is not None:
            delta = (sequence - self.last) & 0xFFFFFFFF
            if 1 < delta < 0x80000000:
                gap = delta - 1
                self.dropped += gap
        self.last = sequence
        return gap


@dataclass
class ProbeEvent:
    kind: str
    value: object = None


class DsuClient(threading.Thread):
    """Background UDP client that periodically renews a DSU subscription."""

    def __init__(
        self,
        host: str,
        port: int,
        slot: int,
        events: "queue.Queue[ProbeEvent]",
        timeout: float = 1.0,
    ) -> None:
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.slot = slot
        self.events = events
        self.timeout = timeout
        self.stop_event = threading.Event()
        self.client_id = random.randrange(1, 0xFFFFFFFF)
        self.sequence_tracker = SequenceTracker()
        self.valid_packets = 0
        self.invalid_packets = 0
        self.accepted_types: Counter[str] = Counter()
        self.rejected_reasons: Counter[str] = Counter()
        self.last_invalid_detail: Optional[Dict[str, object]] = None
        self.last_packet_monotonic: Optional[float] = None
        self.packet_times: Deque[float] = deque(maxlen=300)

    def emit(self, kind: str, value: object = None) -> None:
        self.events.put(ProbeEvent(kind, value))

    def stop(self) -> None:
        self.stop_event.set()

    def _send_subscriptions(self, sock: socket.socket) -> None:
        address = (self.host, self.port)
        sock.sendto(make_version_request(self.client_id), address)
        sock.sendto(make_port_info_request(self.client_id, (self.slot,)), address)
        sock.sendto(make_pad_data_request(self.client_id, self.slot), address)

    def _packet_rate(self, now: float) -> float:
        cutoff = now - 1.0
        while self.packet_times and self.packet_times[0] < cutoff:
            self.packet_times.popleft()
        return float(len(self.packet_times))

    def _record_invalid(self, detail: Dict[str, object]) -> None:
        self.invalid_packets += 1
        category = str(detail.get("category", "unknown"))
        self.rejected_reasons[category] += 1
        self.last_invalid_detail = detail
        self.emit("invalid", detail)

    def _handle_packet(self, data: bytes) -> None:
        now = time.monotonic()
        padded_version = detect_padded_version_reply(data)
        if padded_version is not None:
            self.valid_packets += 1
            self.accepted_types["Version (padded)"] += 1
            self.last_packet_monotonic = now
            self.packet_times.append(now)
            self.emit("special", padded_version)
            self.emit("stats", self.stats(now))
            return

        try:
            packet = parse_packet(data, require_server=True)
        except DsuProtocolError as exc:
            self._record_invalid(inspect_invalid_datagram(data, exc))
            self.emit("stats", self.stats(now))
            return

        self.valid_packets += 1
        self.accepted_types[message_type_name(packet.message_type)] += 1
        self.last_packet_monotonic = now
        self.packet_times.append(now)
        self.emit("packet", packet)

        try:
            if packet.message_type == MSG_VERSION:
                if len(packet.payload) < 2:
                    raise DsuProtocolError("version payload is too short")
                self.emit("version", struct.unpack_from("<H", packet.payload)[0])
            elif packet.message_type == MSG_PORT_INFO:
                self.emit("info", parse_controller_info(packet.payload))
            elif packet.message_type == MSG_PAD_DATA:
                sample = parse_motion_sample(packet.payload)
                if sample.slot == self.slot:
                    self.sequence_tracker.observe(sample.sequence)
                    self.emit("motion", sample)
        except DsuProtocolError as exc:
            self._record_invalid(inspect_payload_rejection(packet, exc))

        self.emit("stats", self.stats(now))

    def stats(self, now: Optional[float] = None) -> Dict[str, object]:
        if now is None:
            now = time.monotonic()
        age = None
        if self.last_packet_monotonic is not None:
            age = max(0.0, now - self.last_packet_monotonic)
        return {
            "valid": self.valid_packets,
            "invalid": self.invalid_packets,
            "dropped": self.sequence_tracker.dropped,
            "rate": self._packet_rate(now),
            "age": age,
            "accepted_types": {
                message_name: count
                for message_name, count in self.accepted_types.items()
            },
            "rejected_reasons": dict(self.rejected_reasons),
            "last_invalid": self.last_invalid_detail,
        }

    def run(self) -> None:
        self.emit("started", (self.host, self.port, self.slot))
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setblocking(False)
                next_subscription = 0.0
                while not self.stop_event.is_set():
                    now = time.monotonic()
                    if now >= next_subscription:
                        try:
                            self._send_subscriptions(sock)
                            self.emit("subscription", None)
                        except OSError as exc:
                            self.emit("error", f"Could not send to {self.host}:{self.port}: {exc}")
                        next_subscription = now + 1.0

                    readable, _, _ = select.select([sock], [], [], 0.1)
                    if readable:
                        try:
                            data, address = sock.recvfrom(4096)
                        except OSError as exc:
                            self.emit("error", f"Could not read UDP data: {exc}")
                        else:
                            self.emit("source", address)
                            self._handle_packet(data)
                    self.emit("stats", self.stats())
        except OSError as exc:
            self.emit("error", f"Could not open UDP socket: {exc}")
        finally:
            self.emit("stopped", None)


class MockDsuServer(threading.Thread):
    """Small synthetic DSU server used for UI/protocol development."""

    def __init__(self, port: int = 0, slot: int = 0) -> None:
        super().__init__(daemon=True)
        self.port = port
        self.slot = slot
        self.server_id = random.randrange(1, 0xFFFFFFFF)
        self.stop_event = threading.Event()
        self.ready = threading.Event()
        self.error: Optional[Exception] = None
        self._socket: Optional[socket.socket] = None
        self._subscriber: Optional[Tuple[str, int]] = None
        self._sequence = 0
        self._started_at = time.monotonic()

    def stop(self) -> None:
        self.stop_event.set()
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass

    def _controller_info(self) -> bytes:
        mac = b"\x02\x44\x53\x55\x01\x00"
        return struct.pack("<BBBB6sBB", self.slot, 2, 2, 2, mac, 0x05, 1)

    def _motion_data(self) -> bytes:
        elapsed = time.monotonic() - self._started_at
        self._sequence = (self._sequence + 1) & 0xFFFFFFFF
        # Synthetic values are intentionally obvious but physically plausible.
        accel = (
            0.18 * math.sin(elapsed * 1.4),
            0.12 * math.cos(elapsed * 1.1),
            0.98 + 0.02 * math.sin(elapsed * 0.7),
        )
        gyro = (
            45.0 * math.sin(elapsed * 1.3),
            28.0 * math.cos(elapsed * 0.9),
            18.0 * math.sin(elapsed * 1.8),
        )
        prefix = struct.pack(
            "<BBBB6sBBI",
            self.slot,
            2,
            2,
            2,
            b"\x02\x44\x53\x55\x01\x00",
            0x05,
            1,
            self._sequence,
        )
        controls = bytes(4 + 4 + 12)  # buttons, sticks, analog buttons
        touch = bytes(12)
        timestamp = struct.pack("<Q", int(time.monotonic_ns() / 1000))
        motion = struct.pack("<fff", *accel) + struct.pack("<fff", *gyro)
        return prefix + controls + touch + timestamp + motion

    def run(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket = sock
            sock.bind(("127.0.0.1", self.port))
            sock.setblocking(False)
            self.port = sock.getsockname()[1]
            self.ready.set()
            next_sample = time.monotonic()
            while not self.stop_event.is_set():
                now = time.monotonic()
                if self._subscriber and now >= next_sample:
                    sock.sendto(
                        build_packet(
                            MAGIC_SERVER,
                            MSG_PAD_DATA,
                            self._motion_data(),
                            self.server_id,
                        ),
                        self._subscriber,
                    )
                    next_sample = now + (1 / 60)

                readable, _, _ = select.select([sock], [], [], 0.02)
                if not readable:
                    continue
                try:
                    data, address = sock.recvfrom(4096)
                    packet = parse_packet(data)
                except (OSError, DsuProtocolError):
                    continue
                if packet.message_type == MSG_VERSION:
                    sock.sendto(
                        build_packet(
                            MAGIC_SERVER,
                            MSG_VERSION,
                            struct.pack("<H", PROTOCOL_VERSION),
                            self.server_id,
                        ),
                        address,
                    )
                elif packet.message_type == MSG_PORT_INFO:
                    sock.sendto(
                        build_packet(
                            MAGIC_SERVER,
                            MSG_PORT_INFO,
                            self._controller_info(),
                            self.server_id,
                        ),
                        address,
                    )
                elif packet.message_type == MSG_PAD_DATA:
                    self._subscriber = address
        except Exception as exc:  # pragma: no cover - shown in UI if it occurs
            self.error = exc
            self.ready.set()
        finally:
            if self._socket is not None:
                try:
                    self._socket.close()
                except OSError:
                    pass


def _format_vector(values: Sequence[float], suffix: str = "") -> str:
    return "  ".join(f"{value: .3f}{suffix}" for value in values)


class ProbeApp:
    """Tkinter front end for :class:`DsuClient`."""

    BG = "#0f1720"
    PANEL = "#172532"
    PANEL_2 = "#1c2d3a"
    BORDER = "#2b4a5e"
    TEXT = "#e9f1f7"
    MUTED = "#9db4c5"
    CYAN = "#12c8e8"
    GREEN = "#57e6ad"
    ORANGE = "#ffbf69"
    RED = "#ff7878"
    PURPLE = "#c6a7ff"

    def __init__(
        self,
        root,
        initial_host: str,
        initial_port: int,
        initial_slot: int,
        mock_server: Optional[MockDsuServer] = None,
    ) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = root
        self.root.title("DSU Motion Probe")
        self.root.geometry("1120x820")
        self.root.minsize(900, 680)
        self.root.configure(bg=self.BG)
        self.events: "queue.Queue[ProbeEvent]" = queue.Queue()
        self.client: Optional[DsuClient] = None
        self.mock_server = mock_server
        self.motion_history: Deque[MotionSample] = deque(maxlen=120)
        self.info: Optional[ControllerInfo] = None
        self.last_motion: Optional[MotionSample] = None
        self.gravity_reference: Optional[Tuple[float, float, float]] = None
        self.last_stats: Dict[str, object] = {
            "valid": 0,
            "invalid": 0,
            "dropped": 0,
            "rate": 0.0,
            "age": None,
            "accepted_types": {},
            "rejected_reasons": {},
            "last_invalid": None,
        }
        self.server_id: Optional[int] = None
        self.last_error = ""

        self.host_var = tk.StringVar(value=initial_host)
        self.port_var = tk.StringVar(value=str(initial_port))
        self.slot_var = tk.StringVar(value=str(initial_slot))
        self.status_var = tk.StringVar(value="Not connected")
        self.connection_var = tk.StringVar(value="Waiting to start")
        self.info_var = tk.StringVar(value="No controller info yet")
        self.packet_var = tk.StringVar(value="Valid 0   Invalid 0   Dropped 0")
        self.rate_var = tk.StringVar(value="0 packets/s")
        self.age_var = tk.StringVar(value="—")
        self.accepted_var = tk.StringVar(value="Accepted types: —")
        self.rejection_var = tk.StringVar(value="Last rejected: —")
        self.source_var = tk.StringVar(value="Source: —")
        self.gyro_var = tk.StringVar(value="Pitch  0.000   Yaw  0.000   Roll  0.000  deg/s")
        self.accel_var = tk.StringVar(value="X  0.000   Y  0.000   Z  0.000  g")
        self.sequence_var = tk.StringVar(value="Sequence: —")
        self.message_var = tk.StringVar(
            value="Move the Deck after connecting; motion should change here in real time."
        )

        self._configure_style()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(50, self._drain_events)
        if self.mock_server is not None:
            self.root.after(50, self._start_mock_when_ready)

    def _configure_style(self) -> None:
        style = self.ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except self.tk.TclError:
            pass
        style.configure("TFrame", background=self.BG)
        style.configure("Panel.TFrame", background=self.PANEL)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT)
        style.configure("Panel.TLabel", background=self.PANEL, foreground=self.TEXT)
        style.configure("Muted.Panel.TLabel", background=self.PANEL, foreground=self.MUTED)
        style.configure("Title.TLabel", background=self.BG, foreground=self.TEXT, font=("Sans", 20, "bold"))
        style.configure("Subtitle.TLabel", background=self.BG, foreground=self.MUTED, font=("Sans", 10))
        style.configure("PanelTitle.TLabel", background=self.PANEL, foreground=self.TEXT, font=("Sans", 12, "bold"))
        style.configure("Status.TLabel", background=self.BG, foreground=self.ORANGE, font=("Sans", 11, "bold"))
        style.configure("TButton", padding=(10, 6))
        style.configure("Accent.TButton", background="#2a83c7", foreground="white")
        style.map("Accent.TButton", background=[("active", "#3e9de4")])

    def _panel(self, parent, title: str):
        frame = self.ttk.Frame(parent, style="Panel.TFrame", padding=12)
        self.ttk.Label(frame, text=title, style="PanelTitle.TLabel").pack(anchor="w", pady=(0, 8))
        return frame

    def _build_ui(self) -> None:
        tk = self.tk
        ttk = self.ttk
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="DSU Motion Probe", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="A direct, visual check of the Deck motion-data path — independent of Moonlight, Sunshine, and emulators.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(3, 0))

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 12))
        ttk.Label(controls, text="Deck / DSU host:").pack(side="left")
        self.host_entry = ttk.Entry(controls, textvariable=self.host_var, width=18)
        self.host_entry.pack(side="left", padx=(6, 12))
        ttk.Label(controls, text="Port:").pack(side="left")
        ttk.Entry(controls, textvariable=self.port_var, width=7).pack(side="left", padx=(6, 12))
        ttk.Label(controls, text="Slot:").pack(side="left")
        ttk.Entry(controls, textvariable=self.slot_var, width=4).pack(side="left", padx=(6, 12))
        self.connect_button = ttk.Button(controls, text="Connect", style="Accent.TButton", command=self.toggle_connection)
        self.connect_button.pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="Clear", command=self.clear_data).pack(side="left")
        ttk.Button(controls, text="Calibrate", command=self.calibrate).pack(side="left", padx=(8, 0))
        ttk.Label(controls, textvariable=self.status_var, style="Status.TLabel").pack(side="right")

        summary = ttk.Frame(outer)
        summary.pack(fill="x", pady=(0, 12))
        status_panel = self._panel(summary, "Connection")
        status_panel.pack(side="left", fill="both", expand=True, padx=(0, 6))
        ttk.Label(status_panel, textvariable=self.connection_var, style="Panel.TLabel").pack(anchor="w")
        ttk.Label(status_panel, textvariable=self.source_var, style="Muted.Panel.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(status_panel, textvariable=self.info_var, style="Muted.Panel.TLabel", wraplength=380).pack(anchor="w", pady=(4, 0))

        packet_panel = self._panel(summary, "Packet health")
        packet_panel.pack(side="left", fill="both", expand=True, padx=6)
        ttk.Label(packet_panel, textvariable=self.packet_var, style="Panel.TLabel").pack(anchor="w")
        ttk.Label(packet_panel, textvariable=self.rate_var, style="Muted.Panel.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(packet_panel, textvariable=self.age_var, style="Muted.Panel.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(
            packet_panel,
            textvariable=self.accepted_var,
            style="Muted.Panel.TLabel",
            wraplength=360,
        ).pack(anchor="w", pady=(4, 0))

        motion_panel = self._panel(summary, "Latest motion")
        motion_panel.pack(side="left", fill="both", expand=True, padx=(6, 0))
        ttk.Label(motion_panel, textvariable=self.gyro_var, style="Panel.TLabel").pack(anchor="w")
        ttk.Label(motion_panel, textvariable=self.accel_var, style="Panel.TLabel").pack(anchor="w", pady=(4, 0))
        ttk.Label(motion_panel, textvariable=self.sequence_var, style="Muted.Panel.TLabel").pack(anchor="w", pady=(4, 0))

        charts = ttk.Frame(outer)
        charts.pack(fill="both", expand=True)
        left = ttk.Frame(charts)
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))
        right = ttk.Frame(charts)
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))

        gyro_frame = self._panel(left, "Gyroscope · deg/s")
        gyro_frame.pack(fill="both", expand=True, pady=(0, 6))
        self.gyro_canvas = tk.Canvas(gyro_frame, bg=self.PANEL, highlightthickness=0, height=190)
        self.gyro_canvas.pack(fill="both", expand=True)
        self.gyro_bars = self._bar_group(gyro_frame, ("Pitch", "Yaw", "Roll"), self.PURPLE, -500.0, 500.0)

        accel_frame = self._panel(left, "Accelerometer · g")
        accel_frame.pack(fill="both", expand=True, pady=(6, 0))
        self.accel_canvas = tk.Canvas(accel_frame, bg=self.PANEL, highlightthickness=0, height=190)
        self.accel_canvas.pack(fill="both", expand=True)
        self.accel_bars = self._bar_group(accel_frame, ("X", "Y", "Z"), self.CYAN, -2.0, 2.0)

        view_frame = self._panel(right, "Gravity view · approximate")
        view_frame.pack(fill="both", expand=True, pady=(0, 6))
        self.tilt_canvas = tk.Canvas(view_frame, bg=self.PANEL, highlightthickness=0, height=300)
        self.tilt_canvas.pack(fill="both", expand=True)
        self._draw_tilt(None)
        ttk.Label(
            view_frame,
            text="Uses acceleration to show the current gravity direction. It is a sanity check, not a fused orientation solution.",
            style="Muted.Panel.TLabel",
            wraplength=430,
        ).pack(anchor="w", pady=(8, 0))

        log_frame = self._panel(right, "Probe message")
        log_frame.pack(fill="x", pady=(6, 0))
        ttk.Label(log_frame, textvariable=self.message_var, style="Muted.Panel.TLabel", wraplength=430).pack(anchor="w")
        ttk.Label(
            log_frame,
            textvariable=self.rejection_var,
            style="Muted.Panel.TLabel",
            wraplength=430,
        ).pack(anchor="w", pady=(8, 0))

    def _bar_group(self, parent, names, color, low, high):
        tk = self.tk
        rows = []
        for name in names:
            row = tk.Frame(parent, bg=self.PANEL)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{name:>5}", width=6, anchor="e", bg=self.PANEL, fg=self.MUTED).pack(side="left")
            canvas = tk.Canvas(row, height=18, bg=self.PANEL_2, highlightthickness=1, highlightbackground=self.BORDER)
            canvas.pack(side="left", fill="x", expand=True, padx=7)
            value = tk.Label(row, text=" 0.000", width=10, anchor="e", bg=self.PANEL, fg=self.TEXT)
            value.pack(side="left")
            rows.append((canvas, value, color, low, high))
        return rows

    def _draw_bars(self, bars, values):
        for (canvas, label, color, low, high), value in zip(bars, values):
            width = max(canvas.winfo_width(), 10)
            height = max(canvas.winfo_height(), 10)
            canvas.delete("all")
            midpoint = width / 2
            canvas.create_line(midpoint, 0, midpoint, height, fill=self.BORDER)
            normalized = min(1.0, max(-1.0, (value - low) / (high - low) * 2 - 1))
            x = midpoint + normalized * (width / 2 - 3)
            if normalized >= 0:
                x0, x1 = midpoint, x
            else:
                x0, x1 = x, midpoint
            canvas.create_rectangle(x0, 3, x1, height - 3, fill=color, outline="")
            label.configure(text=f"{value: .3f}")

    def _draw_graph(self, canvas, history, selector, colors, y_limit):
        width = max(canvas.winfo_width(), 10)
        height = max(canvas.winfo_height(), 10)
        canvas.delete("all")
        canvas.create_line(0, height / 2, width, height / 2, fill=self.BORDER)
        canvas.create_line(0, 12, width, 12, fill=self.PANEL_2)
        canvas.create_line(0, height - 12, width, height - 12, fill=self.PANEL_2)
        if len(history) < 2:
            return
        samples = list(history)
        for axis, color in enumerate(colors):
            points = []
            for index, sample in enumerate(samples):
                values = selector(sample)
                x = 8 + (width - 16) * index / (len(samples) - 1)
                normalized = min(1.0, max(-1.0, values[axis] / y_limit))
                y = height / 2 - normalized * (height / 2 - 16)
                points.extend((x, y))
            if len(points) >= 4:
                canvas.create_line(*points, fill=color, width=2, smooth=True)

    def _display_accel(self, sample: MotionSample) -> Tuple[float, float, float]:
        """Return acceleration adjusted for the probe's optional neutral pose."""
        if self.gravity_reference is None:
            return sample.accel
        ax, ay, az = sample.accel
        rx, ry, rz = self.gravity_reference
        # Keep the neutral gravity magnitude near 1g while moving the chosen
        # resting pose to the center of the visualizer. Raw DSU data remains
        # untouched and is still shown in the accelerometer readout.
        return ax - rx, ay - ry, az - rz + 1.0

    def _draw_tilt(self, sample: Optional[MotionSample]) -> None:
        canvas = self.tilt_canvas
        width = max(canvas.winfo_width(), 10)
        height = max(canvas.winfo_height(), 10)
        canvas.delete("all")
        cx, cy = width / 2, height / 2
        radius = max(30, min(width, height) / 3)
        canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline=self.BORDER, width=2)
        canvas.create_line(cx - radius, cy, cx + radius, cy, fill=self.PANEL_2)
        canvas.create_line(cx, cy - radius, cx, cy + radius, fill=self.PANEL_2)
        if sample is None:
            canvas.create_text(cx, cy, text="No motion data", fill=self.MUTED, font=("Sans", 13))
            return
        ax, ay, az = self._display_accel(sample)
        magnitude = math.sqrt(ax * ax + ay * ay + az * az)
        scale = radius / max(1.0, magnitude)
        dot_x = cx + max(-radius, min(radius, ax * scale))
        dot_y = cy - max(-radius, min(radius, ay * scale))
        canvas.create_oval(dot_x - 10, dot_y - 10, dot_x + 10, dot_y + 10, fill=self.CYAN, outline="")
        canvas.create_text(cx, height - 18, text=f"|accel| {magnitude:.3f} g", fill=self.MUTED)

    def _start_mock_when_ready(self) -> None:
        if self.mock_server is None:
            return
        if not self.mock_server.ready.is_set():
            self.root.after(25, self._start_mock_when_ready)
            return
        if self.mock_server.error:
            self.message_var.set(f"Mock server failed: {self.mock_server.error}")
            return
        self.host_var.set("127.0.0.1")
        self.port_var.set(str(self.mock_server.port))
        self.toggle_connection()

    def toggle_connection(self) -> None:
        if self.client and self.client.is_alive():
            self.client.stop()
            self.connect_button.configure(text="Connect")
            self.status_var.set("Stopping…")
            return
        try:
            host = self.host_var.get().strip()
            port = int(self.port_var.get().strip())
            slot = int(self.slot_var.get().strip())
            if not host:
                raise ValueError("host is empty")
            if not 1 <= port <= 65535:
                raise ValueError("port must be 1..65535")
            if slot not in range(4):
                raise ValueError("slot must be 0..3")
        except ValueError as exc:
            self.message_var.set(f"Check the target fields: {exc}")
            return
        self.clear_data()
        self.client = DsuClient(host, port, slot, self.events)
        self.client.start()
        self.connect_button.configure(text="Disconnect")
        self.status_var.set("Connecting…")

    def clear_data(self) -> None:
        self.motion_history.clear()
        self.info = None
        self.last_motion = None
        self.server_id = None
        self.last_stats = {"valid": 0, "invalid": 0, "dropped": 0, "rate": 0.0, "age": None}
        self.info_var.set("No controller info yet")
        self.packet_var.set("Valid 0   Invalid 0   Dropped 0")
        self.rate_var.set("0 packets/s")
        self.age_var.set("Last packet: —")
        self.accepted_var.set("Accepted types: —")
        self.rejection_var.set("Last rejected: —")
        self.source_var.set("Source: —")
        self.sequence_var.set("Sequence: —")
        self.gyro_var.set("Pitch  0.000   Yaw  0.000   Roll  0.000  deg/s")
        self.accel_var.set("X  0.000   Y  0.000   Z  0.000  g")
        self._draw_tilt(None)
        self._draw_bars(self.gyro_bars, (0, 0, 0))
        self._draw_bars(self.accel_bars, (0, 0, 0))
        self._draw_graph(self.gyro_canvas, self.motion_history, lambda s: s.gyro, (self.PURPLE,) * 3, 500)
        self._draw_graph(self.accel_canvas, self.motion_history, lambda s: s.accel, (self.CYAN,) * 3, 2)

    def calibrate(self) -> None:
        if self.last_motion is None:
            self.message_var.set("Connect and wait for motion data before calibrating.")
            return
        samples = list(self.motion_history)[-30:]
        if not samples:
            samples = [self.last_motion]
        self.gravity_reference = tuple(
            sum(sample.accel[index] for sample in samples) / len(samples)
            for index in range(3)
        )
        self.message_var.set("Gravity view calibrated to the current resting position.")
        self._draw_tilt(self.last_motion)

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        self._redraw()
        self.root.after(50, self._drain_events)

    def _handle_event(self, event: ProbeEvent) -> None:
        if event.kind == "started":
            host, port, slot = event.value
            self.status_var.set("Waiting for DSU data…")
            self.connection_var.set(f"Target {host}:{port} · slot {slot}")
            self.message_var.set("Subscription sent. Waiting for a DSU response…")
        elif event.kind == "source":
            address = event.value
            self.source_var.set(f"Source: {address[0]}:{address[1]}")
        elif event.kind == "packet":
            packet: DsuPacket = event.value
            self.server_id = packet.sender_id
            self.status_var.set("Receiving live data")
        elif event.kind == "special":
            self.status_var.set("Receiving live data")
            self.message_var.set(
                "Accepted the DSU service's padded version response; it is not motion data."
            )
        elif event.kind == "version":
            self.message_var.set(f"DSU server reports protocol version {event.value}.")
        elif event.kind == "info":
            self.info = event.value
            info: ControllerInfo = event.value
            state = "connected" if info.connected else f"state {info.state}"
            self.info_var.set(
                f"Slot {info.slot}: {state} · {info.model_name} · {info.connection_name} · battery {battery_name(info.battery)}"
            )
        elif event.kind == "motion":
            sample: MotionSample = event.value
            self.last_motion = sample
            self.motion_history.append(sample)
            self.sequence_var.set(f"Sequence: {sample.sequence} · timestamp {sample.timestamp_us} μs")
            self.gyro_var.set(f"Pitch {sample.gyro[0]: .3f}   Yaw {sample.gyro[1]: .3f}   Roll {sample.gyro[2]: .3f}  deg/s")
            self.accel_var.set(f"X {sample.accel[0]: .3f}   Y {sample.accel[1]: .3f}   Z {sample.accel[2]: .3f}  g")
            self.message_var.set("Motion packets are arriving. Move or tilt the Deck and watch the values respond.")
        elif event.kind == "invalid":
            detail = event.value
            rejection = format_rejection_detail(detail)
            self.rejection_var.set(f"Last rejected: {rejection}")
            self.message_var.set("A datagram was rejected; the details are shown below.")
        elif event.kind == "subscription":
            if self.status_var.get() == "Connecting…":
                self.status_var.set("Waiting for DSU data…")
        elif event.kind == "stats":
            self.last_stats = event.value
        elif event.kind == "error":
            self.last_error = str(event.value)
            self.status_var.set("Connection error")
            self.message_var.set(self.last_error)
        elif event.kind == "stopped":
            if not self.client or not self.client.is_alive():
                self.connect_button.configure(text="Connect")
                if self.status_var.get() == "Stopping…":
                    self.status_var.set("Not connected")

    def _redraw(self) -> None:
        stats = self.last_stats
        self.packet_var.set(
            f"Valid {stats.get('valid', 0)}   Invalid {stats.get('invalid', 0)}   Dropped {stats.get('dropped', 0)}"
        )
        self.rate_var.set(f"{stats.get('rate', 0.0):.1f} packets/s")
        age = stats.get("age")
        self.age_var.set("Last packet: —" if age is None else f"Last packet: {age:.2f}s ago")
        accepted_types = stats.get("accepted_types", {})
        if accepted_types:
            accepted_text = " · ".join(
                f"{name} {count}" for name, count in sorted(accepted_types.items())
            )
            self.accepted_var.set(f"Accepted types: {accepted_text}")
        if self.last_motion is not None:
            self._draw_bars(self.gyro_bars, self.last_motion.gyro)
            self._draw_bars(self.accel_bars, self.last_motion.accel)
        self._draw_graph(self.gyro_canvas, self.motion_history, lambda s: s.gyro, (self.PURPLE,) * 3, 500)
        self._draw_graph(self.accel_canvas, self.motion_history, lambda s: s.accel, (self.CYAN,) * 3, 2)
        self._draw_tilt(self.last_motion)

    def close(self) -> None:
        if self.client:
            self.client.stop()
        if self.mock_server:
            self.mock_server.stop()
        self.root.destroy()


def run_headless(host: str, port: int, slot: int, duration: float) -> int:
    """Run without Tk, useful for quick checks from a terminal."""

    events: "queue.Queue[ProbeEvent]" = queue.Queue()
    client = DsuClient(host, port, slot, events)
    client.start()
    deadline = time.monotonic() + duration
    latest_motion: Optional[MotionSample] = None
    while time.monotonic() < deadline:
        try:
            event = events.get(timeout=0.1)
        except queue.Empty:
            continue
        if event.kind == "motion":
            latest_motion = event.value
            sample: MotionSample = event.value
            print(
                f"motion seq={sample.sequence} accel=({_format_vector(sample.accel)}) "
                f"gyro=({_format_vector(sample.gyro, ' deg/s')})"
            )
        elif event.kind == "info":
            info: ControllerInfo = event.value
            print(f"controller slot={info.slot} {info.model_name} {info.connection_name}")
        elif event.kind == "invalid":
            print(f"invalid: {format_rejection_detail(event.value)}")
        elif event.kind == "error":
            print(f"error: {event.value}")
    client.stop()
    client.join(timeout=1.0)
    stats = client.stats()
    print(
        f"summary valid={stats['valid']} invalid={stats['invalid']} "
        f"dropped={stats['dropped']} rate={stats['rate']:.1f}/s"
    )
    return 0 if latest_motion is not None else 1


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Deck/DSU server IPv4 address")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="DSU UDP port (default: 26760)")
    parser.add_argument("--slot", type=int, default=0, help="controller slot 0..3 (default: 0)")
    parser.add_argument("--mock", action="store_true", help="use a local synthetic DSU server")
    parser.add_argument("--headless", action="store_true", help="print packets without opening the GUI")
    parser.add_argument("--duration", type=float, default=5.0, help="headless run time in seconds")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    mock: Optional[MockDsuServer] = None
    if args.mock:
        mock = MockDsuServer(slot=args.slot)
        mock.start()
        if not mock.ready.wait(2.0):
            print("mock server did not start")
            return 1
        if mock.error:
            print(f"mock server failed: {mock.error}")
            return 1
        args.host, args.port = "127.0.0.1", mock.port

    if args.headless:
        try:
            return run_headless(args.host, args.port, args.slot, args.duration)
        finally:
            if mock:
                mock.stop()

    try:
        import tkinter as tk
    except ImportError:
        print("Tkinter is required for the visual probe. Try --headless or install python-tk.")
        if mock:
            mock.stop()
        return 2

    root = tk.Tk()
    app = ProbeApp(root, args.host, args.port, args.slot, mock_server=mock)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


