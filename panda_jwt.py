"""Panda-compatible HS256 JWT signing with private local configuration."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
from pathlib import Path

from vendor_config import PANDA_CONFIG


def _load_key() -> str:
    environment_key = os.environ.get("PANDA_JWT_SECRET", "").strip()
    if environment_key:
        return environment_key
    configured_file = os.environ.get("PANDA_JWT_SECRET_FILE", "").strip()
    key_file = (
        Path(configured_file).expanduser()
        if configured_file
        else Path(__file__).resolve().parent / PANDA_CONFIG["signing_key_file"]
    )
    try:
        return key_file.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return ""


# Keep the original signer's attribute name for the issuer interface. HS256
# uses a shared secret; this value is private despite the legacy name.
PUBLIC_KEY = _load_key()


def _secret_bytes(secret: str | None) -> bytes:
    configured = PUBLIC_KEY if secret is None else secret
    if not isinstance(configured, str) or not configured.strip():
        raise ValueError("未配置 Panda JWT 签名密钥，请检查 config/private/panda_signing.key 或 PANDA_JWT_SECRET。")
    return configured.encode("utf-8")


def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def base64url_decode(value: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("JWT 编码格式不正确。")
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("JWT 编码格式不正确。") from None
    if base64url_encode(decoded) != value:
        raise ValueError("JWT 编码格式不正确。")
    return decoded


def jwt_encode(payload: dict, secret: str | None = None) -> str:
    key = _secret_bytes(secret)
    if not isinstance(payload, dict):
        raise ValueError("JWT 内容必须是 JSON 对象。")
    header = {"alg": "HS256", "typ": "JWT"}
    try:
        header_part = base64url_encode(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        payload_part = base64url_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ValueError("JWT 内容格式不正确。") from None
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    signature = base64url_encode(hmac.new(key, signing_input, hashlib.sha256).digest())
    return f"{header_part}.{payload_part}.{signature}"


def jwt_decode(token: str, secret: str | None = None) -> dict:
    key = _secret_bytes(secret)
    if not isinstance(token, str) or len(token.split(".")) != 3:
        raise ValueError("JWT 格式不正确。")
    header_part, payload_part, signature_part = token.split(".")
    try:
        header = json.loads(base64url_decode(header_part))
        if not isinstance(header, dict) or header.get("alg") != "HS256" or header.get("typ") != "JWT":
            raise ValueError
        signature = base64url_decode(signature_part)
        signing_input = f"{header_part}.{payload_part}".encode("ascii")
        expected = hmac.new(key, signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        payload = json.loads(base64url_decode(payload_part))
        if not isinstance(payload, dict):
            raise ValueError
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValueError("JWT 校验失败，请检查链接和签名配置。") from None
    # Match Panda validation: the outer JWT exp is not enforced. The issuer
    # preserves the login session and only updates the debug claim and expiry.
    return payload
