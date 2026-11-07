#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from display_layout import choose_position  # noqa: E402


class DisplayLayoutTests(unittest.TestCase):
    def test_unscaled_main_display_is_touching_and_centered(self):
        config = {
            "outputs": [
                {
                    "name": "DP-1",
                    "primary": True,
                    "enabled": True,
                    "pos": {"x": 0, "y": 0},
                    "size": {"width": 3840, "height": 2160},
                },
                {
                    "name": "Virtual-DualScreen",
                    "enabled": True,
                    "pos": {"x": 2649, "y": 0},
                    "size": {"width": 1280, "height": 800},
                },
            ]
        }
        self.assertEqual(
            choose_position(config, "Virtual-DualScreen", "1280x800"),
            ("Virtual-DualScreen", 1280, 2160),
        )

    def test_fractional_scale_uses_logical_geometry(self):
        config = {
            "outputs": [
                {
                    "name": "eDP-1",
                    "primary": True,
                    "enabled": True,
                    "pos": {"x": 0, "y": 0},
                    "scale": 1.5,
                    "size": {"width": 2880, "height": 1800},
                },
                {
                    "name": "Virtual-DualScreen",
                    "enabled": True,
                    "scale": 1.0,
                    "size": {"width": 1280, "height": 800},
                },
            ]
        }
        self.assertEqual(
            choose_position(config, "Virtual-DualScreen", "1280x800"),
            ("Virtual-DualScreen", 320, 1200),
        )

    def test_explicit_logical_geometry_wins_over_rendered_size(self):
        config = {
            "outputs": [
                {
                    "name": "DP-1",
                    "priority": 1,
                    "enabled": True,
                    "pos": {"x": 10, "y": 20},
                    "scale": 2.0,
                    "size": {"width": 3840, "height": 2160},
                    "explicitLogicalSize": {"width": 1800.5, "height": 1000.25},
                },
                {
                    "name": "Virtual-DualScreen",
                    "enabled": True,
                    "size": {"width": 1280, "height": 800},
                },
            ]
        }
        self.assertEqual(
            choose_position(config, "Virtual-DualScreen", "1280x800"),
            ("Virtual-DualScreen", 270, 1021),
        )


if __name__ == "__main__":
    unittest.main()
