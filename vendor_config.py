"""Self-contained vendor configuration shipped with the development tools."""

from __future__ import annotations

import json
from pathlib import Path


PANDA_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "vendors" / "panda.json"


def load_panda_config(path: Path | None = None) -> dict:
    source = PANDA_CONFIG_PATH if path is None else Path(path)
    try:
        config = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise ValueError("无法读取 Panda 厂商配置，请检查 config/vendors/panda.json。") from None
    if not isinstance(config, dict):
        raise ValueError("Panda 厂商配置必须是 JSON 对象。")
    if not isinstance(config.get("signing_key_file"), str) or not config["signing_key_file"]:
        raise ValueError("Panda 厂商配置缺少 signing_key_file。")
    app_keys = config.get("test_app_keys")
    if not isinstance(app_keys, list) or not app_keys or not all(isinstance(key, str) and key for key in app_keys):
        raise ValueError("Panda 厂商配置的 test_app_keys 必须是非空字符串列表。")
    if not isinstance(config.get("natural_free_mode"), str) or not config["natural_free_mode"]:
        raise ValueError("Panda 厂商配置缺少 natural_free_mode。")
    if config.get("game_scope") != "all":
        raise ValueError("Panda 调试工具当前要求 game_scope 为 all。")
    for name in ("default_days", "max_days", "no_expiry_timestamp"):
        if type(config.get(name)) is not int or config[name] <= 0:
            raise ValueError(f"Panda 厂商配置中的 {name} 必须是正整数。")
    if config["default_days"] > config["max_days"]:
        raise ValueError("Panda 厂商配置的 default_days 不能大于 max_days。")
    games = config.get("games")
    if not isinstance(games, dict) or not all(
        isinstance(game, dict) and isinstance(game.get("name"), str) and isinstance(game.get("desc"), str)
        for game in games.values()
    ):
        raise ValueError("Panda 厂商配置的 games 必须包含游戏编号、name 和 desc。")
    return config


PANDA_CONFIG = load_panda_config()
