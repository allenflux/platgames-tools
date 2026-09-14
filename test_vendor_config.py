"""Check editable vendor configuration using synthetic temporary files."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vendor_config import load_panda_config


class VendorConfigTests(unittest.TestCase):
    def test_loads_vendor_settings_and_game_catalog_from_selected_file(self) -> None:
        config = {
            "signing_key_file": "config/private/panda_signing.key",
            "test_app_keys": ["SHYFBTESTMCH9057"],
            "natural_free_mode": "force_natural_free_v1",
            "game_scope": "all",
            "default_days": 30,
            "max_days": 90,
            "no_expiry_timestamp": 253402300799,
            "games": {"21": {"name": "测试游戏", "desc": "仅用于配置回归测试"}},
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "panda.json"
            path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
            actual = load_panda_config(path)
        for key, value in config.items():
            with self.subTest(key=key):
                self.assertEqual(actual[key], value)


if __name__ == "__main__":
    unittest.main()
