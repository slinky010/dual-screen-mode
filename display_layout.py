#!/usr/bin/env python3

"""Choose a predictable bottom-middle position for Dual Screen Mode."""

import json
import math
import sys
from typing import Any, Dict, Iterable, Optional, Tuple


def as_int(value: Any) -> Optional[int]:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def as_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def point(output: Dict[str, Any]) -> Tuple[int, int]:
    value = output.get("pos") or output.get("position") or {}
    if isinstance(value, dict):
        return as_int(value.get("x")) or 0, as_int(value.get("y")) or 0
    return 0, 0


def output_size(output: Dict[str, Any], virtual_name: str, resolution: str) -> Optional[Tuple[int, int]]:
    # Some callers expose the logical geometry directly. Prefer it when it is
    # available because that is the coordinate space used by KWin positions.
    for key in ("explicitLogicalSize", "explicitLogicalSizeInt", "logicalSize", "logical_size"):
        value = output.get(key) or {}
        if isinstance(value, dict):
            width = as_float(value.get("width"))
            height = as_float(value.get("height"))
            if width and height and width > 0 and height > 0:
                return math.ceil(width), math.ceil(height)

    raw_size: Optional[Tuple[int, int]] = None
    value = output.get("size") or {}
    if isinstance(value, dict):
        width = as_int(value.get("width"))
        height = as_int(value.get("height"))
        if width and height:
            raw_size = width, height

    if raw_size is None:
        current_id = str(output.get("currentModeId", ""))
        modes: Iterable[Dict[str, Any]] = output.get("modes", []) or []
        for mode in modes:
            if str(mode.get("id", "")) != current_id:
                continue
            value = mode.get("size") or {}
            width = as_int(value.get("width"))
            height = as_int(value.get("height"))
            if width and height:
                raw_size = width, height
                break

    if raw_size is not None:
        # KScreen's output size is the rendered size, while output positions
        # and the overall layout are logical coordinates. On a scaled Wayland
        # output, convert the rendered size back into that logical space. A
        # missing scale means the traditional 1:1 behavior.
        scale = as_float(output.get("scale"))
        if scale and scale > 0:
            return math.ceil(raw_size[0] / scale), math.ceil(raw_size[1] / scale)
        return raw_size

    if output.get("name") == virtual_name:
        try:
            width, height = resolution.lower().split("x", 1)
            return int(width), int(height)
        except (TypeError, ValueError):
            pass
    return None


def choose_position(config: Dict[str, Any], virtual_name: str, resolution: str) -> Optional[Tuple[Any, int, int]]:
    outputs = config.get("outputs", []) or []
    virtual = next((item for item in outputs if item.get("name") == virtual_name), None)
    virtual_size = output_size(virtual, virtual_name, resolution) if virtual else None
    if not virtual or not virtual_size:
        return None

    physical = []
    for item in outputs:
        if item is virtual or not item.get("enabled", True):
            continue
        dimensions = output_size(item, virtual_name, resolution)
        if dimensions:
            physical.append((item, dimensions))
    if not physical:
        return None

    primary = [
        item for item in physical
        if (
            item[0].get("primary") is True
            or item[0].get("isPrimary") is True
            or as_int(item[0].get("priority")) == 1
        )
    ]
    at_origin = [item for item in physical if point(item[0]) == (0, 0)]
    main, (main_width, main_height) = (
        primary[0]
        if primary
        else at_origin[0]
        if at_origin
        else max(physical, key=lambda item: item[1][0] * item[1][1])
    )

    main_x, main_y = point(main)
    virtual_width, _ = virtual_size
    target_x = main_x + max(0, (main_width - virtual_width) // 2)
    target_y = main_y + main_height
    return virtual.get("name"), target_x, target_y


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    try:
        config = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError, TypeError):
        return 0

    result = choose_position(config, f"Virtual-{sys.argv[1]}", sys.argv[2])
    if result is not None:
        print(*result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
