#!/usr/bin/env python3
"""Run the standalone vendor debug web service with Python's standard library."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from vendor_debug_tokens import VENDORS, generate_debug_url


WEB_ROOT = Path(__file__).resolve().parent / "vendor_debug_web"
MAX_BODY_BYTES = 64 * 1024
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/icon.png": ("icon.png", "image/png"),
    "/favicon.ico": ("icon.png", "image/png"),
}


class DebugToolHandler(BaseHTTPRequestHandler):
    server_version = "VendorDebugTools/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format, *args):
        # Game URLs contain credentials. Do not put paths, request bodies, or
        # headers in an access log (including BaseHTTPRequestHandler errors).
        pass

    def _respond(self, status: int, body: bytes, content_type: str):
        self.send_response(status)
        if status != 204:
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, HEAD, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Debug-Tool")
        self.end_headers()
        if self.command != "HEAD" and status != 204:
            self.wfile.write(body)

    def _json(self, status: int, payload: dict):
        self._respond(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def send_error(self, code, message=None, explain=None):
        self._json(code, {"error": "请求无法处理。"})

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._json(200, {"ok": True})
        elif path == "/api/vendors":
            self._json(200, {"vendors": VENDORS})
        elif path in STATIC_FILES:
            name, content_type = STATIC_FILES[path]
            try:
                body = (WEB_ROOT / name).read_bytes()
            except FileNotFoundError:
                self._json(404, {"error": "页面文件不存在。"})
            else:
                self._respond(200, body, content_type)
        else:
            self._json(404, {"error": "页面或接口不存在。"})

    def do_HEAD(self):
        self.do_GET()

    def do_OPTIONS(self):
        self._respond(204, b"", "")

    def do_POST(self):
        if urlsplit(self.path).path != "/api/generate":
            self._json(404, {"error": "接口不存在。"})
            return
        if self.headers.get_content_type() != "application/json":
            self._json(415, {"error": "请求必须使用 application/json。"})
            return
        if self.headers.get("Transfer-Encoding"):
            self._json(400, {"error": "不支持此请求传输格式。"})
            return
        lengths = self.headers.get_all("Content-Length", [])
        try:
            if len(lengths) != 1:
                raise ValueError
            length = int(lengths[0])
            if length < 0:
                raise ValueError
        except ValueError:
            self._json(400, {"error": "请求长度不正确。"})
            return
        if length > MAX_BODY_BYTES:
            self._json(413, {"error": "输入内容过长，请只粘贴游戏 URL。"})
            return
        try:
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError
            request = json.loads(body)
        except (ValueError, UnicodeDecodeError, TimeoutError):
            self._json(400, {"error": "请求 JSON 格式不正确。"})
            return
        try:
            result = generate_debug_url(request)
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except Exception:
            # Never expose source credentials or signer details via errors.
            self._json(500, {"error": "生成失败，请检查服务配置后重试。"})
        else:
            self._json(200, result)


def create_server(host: str = "127.0.0.1", port: int = 9100) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), DebugToolHandler)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="listen address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9100, help="listen port (default: 9100)")
    args = parser.parse_args()
    from panda_jwt import PUBLIC_KEY
    if not PUBLIC_KEY:
        parser.exit(1, "服务启动失败：请配置 config/private/panda_signing.key 或 PANDA_JWT_SECRET。\n")
    try:
        server = create_server(args.host, args.port)
    except OSError as exc:
        parser.exit(1, f"服务启动失败：{exc}\n")
    print(f"厂商调试工具已启动：http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
