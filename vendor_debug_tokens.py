"""Vendor-specific debug tools, independent of the running game service."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from ipaddress import ip_address
from urllib.parse import unquote, unquote_plus, urlsplit

from make_panda_natural_free_token import issue_token, jwt_encode
from vendor_config import PANDA_CONFIG


MAX_INPUT_LENGTH = 60 * 1024
SESSION_NOTE = "请使用当前能正常进入游戏的链接。重新登录或会话被清理后，需要用最新链接重新生成。"
VENDORS = [
    {
        "id": "panda",
        "name": "Panda",
        "description": "Panda 游戏调试工具",
        "tools": [
            {
                "id": "natural-free-token",
                "name": "自然免费调试 Token",
                "description": "让普通旋转抽取自然触发免费局的结果包。",
            }
        ],
    }
]


def _normalize_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("请粘贴完整的游戏 URL。")
    if len(value) > MAX_INPUT_LENGTH:
        raise ValueError("游戏链接过长，请检查输入内容。")
    value = value.strip()
    # Chat/Markdown copies may contain a label plus destination, or escaped
    # query separators. Decode only Markdown escaping, never the whole URL.
    markdown = re.fullmatch(r"\[.*\]\(\s*(https?://.*?)\s*\)", value, re.DOTALL | re.IGNORECASE)
    if markdown:
        value = markdown.group(1)
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1]
    value = value.replace("\\&", "&").replace("\\_", "_")
    if re.search(r"[\s\x00-\x1f\x7f\\]", value):
        raise ValueError("URL 中不能包含空格、换行或反斜杠，请重新复制完整链接。")
    try:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError
        if parts.username is not None or parts.password is not None:
            raise ValueError
        if any(character in parts.netloc for character in '<>"{}|^`'):
            raise ValueError
        hostname = parts.hostname
        try:
            ip_address(hostname)
        except ValueError:
            ascii_hostname = hostname.encode("idna").decode("ascii").removesuffix(".")
            if len(ascii_hostname) > 253 or not all(
                re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in ascii_hostname.split(".")
            ):
                raise ValueError
        # Reading port also rejects malformed/out-of-range ports.
        if parts.port is not None and not 1 <= parts.port <= 65535:
            raise ValueError
    except (ValueError, UnicodeError):
        raise ValueError("请输入有效的 http 或 https 游戏链接，且链接中不能包含账号密码。") from None
    return value


def _extract_token(url: str) -> tuple[str, int, int]:
    before_fragment = url.partition("#")[0]
    query_start = before_fragment.find("?")
    if query_start < 0:
        raise ValueError("链接中缺少 token 参数，请复制完整的游戏链接。")
    offset = query_start + 1
    matches = []
    for segment in before_fragment[offset:].split("&"):
        key, separator, raw_value = segment.partition("=")
        if unquote_plus(key) == "token":
            if not separator or not raw_value:
                raise ValueError("链接中的 token 不能为空。")
            start = offset + len(key) + 1
            matches.append((unquote_plus(raw_value), start, start + len(raw_value)))
        offset += len(segment) + 1
    if not matches:
        raise ValueError("链接中缺少 token 参数，请复制完整的游戏链接。")
    if len(matches) != 1:
        raise ValueError("链接中包含多个 token 参数，请保留一个后重试。")
    token, start, end = matches[0]
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token):
        raise ValueError("token 格式不正确，请使用完整的 Panda 游戏链接。")
    try:
        header = json.loads(jwt_encode.base64url_decode(token.split(".", 1)[0]))
        if not isinstance(header, dict) or header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("token 签名类型不正确，请使用 Panda 游戏链接。") from None
    return token, start, end


def _generate_panda(request: dict) -> dict:
    url = _normalize_url(request.get("url"))
    token, start, end = _extract_token(url)
    validity = request.get("validity", "long_term")
    if validity not in ("long_term", "30_days", "90_days"):
        raise ValueError("请选择长期、30 天或 90 天有效期。")
    try:
        new_token, expires_at = issue_token(
            token,
            days=90 if validity == "90_days" else 30,
            no_expiry=validity == "long_term",
        )
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        if "PANDA_JWT_SECRET" in str(exc):
            message = "请检查 config/private/panda_signing.key，或设置 PANDA_JWT_SECRET 后重启服务。"
        elif "test merchant" in str(exc):
            message = "该链接不属于支持的 Panda 测试商户，请使用测试环境的游戏链接。"
        elif "session fields" in str(exc):
            message = "token 缺少账号登录会话信息，请重新进入游戏后复制链接。"
        else:
            message = "token 校验失败，请确认链接来自当前 Panda 测试环境且复制完整。"
        raise ValueError(message) from None

    segments = [unquote(segment) for segment in urlsplit(url).path.split("/") if segment]
    game = segments[-2] if len(segments) >= 2 and "." in segments[-1] else (segments[-1] if segments else "Panda")
    game_info = next((value for value in PANDA_CONFIG["games"].values() if value["name"] == game), {})
    return {
        "vendor": "panda",
        "tool": "natural-free-token",
        "game": game,
        "game_name": game_info.get("desc", game),
        # Splice only the token value; preserve the exact query encoding,
        # parameter order, duplicates, path, host, and fragment supplied.
        "url": url[:start] + new_token + url[end:],
        "token": new_token,
        "expires_at": expires_at,
        "expires_label": datetime.fromtimestamp(expires_at, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "session_note": SESSION_NOTE,
        "session_verified": False,
    }


TOOL_HANDLERS = {("panda", "natural-free-token"): _generate_panda}


def generate_debug_url(request: dict) -> dict:
    if not isinstance(request, dict):
        raise ValueError("请求内容必须是 JSON 对象。")
    vendor = request.get("vendor", "panda")
    tool = request.get("tool", "natural-free-token")
    if not isinstance(vendor, str) or not isinstance(tool, str):
        raise ValueError("请选择有效的厂商和调试工具。")
    handler = TOOL_HANDLERS.get((vendor, tool))
    if handler is None:
        raise ValueError("暂不支持所选厂商或调试工具。")
    return handler(request)
