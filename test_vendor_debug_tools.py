"""Regression tests for the local vendor tools; all player sessions are synthetic."""

from __future__ import annotations

import copy
import hashlib
import hmac
import io
import json
import os
import threading
import time
import unittest
from contextlib import redirect_stderr
from http.client import HTTPConnection
from urllib.parse import quote

os.environ.setdefault("PANDA_JWT_SECRET", "synthetic-panda-signing-key-for-tests")

import make_panda_natural_free_token as issuer
from vendor_debug_tokens import generate_debug_url
from vendor_debug_server import create_server


def source_payload() -> dict:
    return {
        "app_key": issuer.TEST_APP_KEY,
        "iat": 100,
        "exp": 200,
        "token": "synthetic-outer-session-hash",
        "custom": {"preserve": [1, "two"]},
        "body": {
            "account": "synthetic-test-account",
            "account_type": 1,
            "id": "synthetic-test-player",
            "login_time": 100,
            "token": "synthetic-inner-session-token",
            "now_game_id": "21",
            "uid": 123,
            "language": "zh",
            "custom": {"keep": True},
        },
    }


def sign(payload: dict) -> str:
    return issuer.jwt_encode.jwt_encode(payload, secret=issuer.jwt_encode.PUBLIC_KEY)


def launch_url(token: str) -> str:
    return (
        "https://panda-test.example/smash-fury/index.html?isFun=true"
        "&server_url=https%3A%2F%2Fpanda-api.example&token=" + token
        + "&lang=zh-CN&l=zh-CN&provider_name=panda"
    )


class GenerateDebugURLTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = source_payload()
        self.token = sign(self.payload)
        self.url = launch_url(self.token)

    def generate(self, url: str | None = None, **values) -> dict:
        return generate_debug_url({"url": self.url if url is None else url, **values})

    def assert_invalid(self, request) -> None:
        with self.assertRaises(ValueError) as error:
            generate_debug_url(request)
        self.assertRegex(str(error.exception), r"[\u4e00-\u9fff]")
        self.assertNotIn(self.token, str(error.exception))

    def test_replaces_only_token_preserving_every_other_url_byte(self) -> None:
        # The source JWT also appears in a different parameter and the fragment.
        # A global string replace would silently alter those values as well.
        url = (
            "https://PANDA-test.example:443/smash-fury/index.html?"
            "server_url=https%3a%2f%2fpanda-api.example%2fapi%3fa%3d1%26b%3d2"
            "&label=a+b&label=a%20b&empty=&bare&keep=" + self.token
            + "&token=" + self.token + "&tail=%2f#snapshot=" + self.token
        )
        result = self.generate(url)
        self.assertNotEqual(result["token"], self.token)
        self.assertEqual(result["url"], url.replace("&token=" + self.token, "&token=" + result["token"], 1))
        self.assertEqual(result["vendor"], "panda")
        self.assertEqual(result["tool"], "natural-free-token")
        self.assertIn("game", result)
        self.assertIs(result["session_verified"], False)
        self.assertTrue(result["session_note"])

    def test_preserves_signed_account_game_and_session(self) -> None:
        result = self.generate()
        decoded = issuer.jwt_encode.jwt_decode(result["token"], issuer.jwt_encode.PUBLIC_KEY)
        expected = copy.deepcopy(self.payload)
        expected["iat"] = decoded["iat"]
        expected["exp"] = decoded["exp"]
        expected["body"]["panda_test"] = decoded["body"]["panda_test"]
        self.assertEqual(decoded, expected)
        claim = decoded["body"]["panda_test"]
        self.assertEqual(claim["mode"], "force_natural_free_v1")
        self.assertEqual(claim["games"], "all")
        self.assertEqual(claim["expires_at"], result["expires_at"])
        self.assertTrue(claim["token_id"])
        # JWT expiry deliberately differs from the unchanged login session time.
        self.assertGreater(decoded["exp"], time.time())
        self.assertEqual(decoded["body"]["login_time"], 100)

    def test_default_expiry_is_long_term_and_finite_choices_work(self) -> None:
        result = self.generate()
        self.assertEqual(result["expires_at"], issuer.NO_EXPIRY_TIMESTAMP)
        self.assertIn("9999", result["expires_label"])
        for validity, days in (("30_days", 30), ("90_days", 90)):
            with self.subTest(validity=validity):
                before = int(time.time())
                finite = self.generate(validity=validity)
                after = int(time.time())
                self.assertGreaterEqual(finite["expires_at"], before + days * 86400)
                self.assertLessEqual(finite["expires_at"], after + days * 86400)
                decoded = issuer.jwt_encode.jwt_decode(finite["token"], issuer.jwt_encode.PUBLIC_KEY)
                self.assertEqual(decoded["exp"], finite["expires_at"])

    def test_each_generation_replaces_previous_debug_claim(self) -> None:
        first = self.generate()
        second = self.generate(first["url"], validity="30_days")
        decoded_first = issuer.jwt_encode.jwt_decode(first["token"], issuer.jwt_encode.PUBLIC_KEY)
        decoded_second = issuer.jwt_encode.jwt_decode(second["token"], issuer.jwt_encode.PUBLIC_KEY)
        self.assertNotEqual(decoded_first["body"]["panda_test"]["token_id"], decoded_second["body"]["panda_test"]["token_id"])
        self.assertLess(second["expires_at"], first["expires_at"])
        self.assertEqual(decoded_second["body"]["token"], self.payload["body"]["token"])

    def test_accepts_chat_markdown_and_uses_link_target(self) -> None:
        escaped = self.url.replace("&", r"\&").replace("_", r"\_")
        inputs = [
            self.url,
            "  " + self.url + "\n",
            "<" + self.url + ">",
            escaped,
            "[https://ignored.example/wrong?token=invalid](" + escaped + ")",
        ]
        for value in inputs:
            with self.subTest(value=value[:80]):
                result = self.generate(value)
                self.assertEqual(result["url"], self.url.replace("token=" + self.token, "token=" + result["token"], 1))

    def test_encoded_token_value_and_parameter_name(self) -> None:
        encoded_token = quote(self.token, safe="").replace(".", "%2E")
        url = self.url.replace("&token=" + self.token, "&%74oken=" + encoded_token)
        result = self.generate(url)
        self.assertEqual(result["url"], url.replace(encoded_token, result["token"], 1))

    def test_rejects_invalid_urls_and_ambiguous_token_parameters(self) -> None:
        cases = [
            "", "not a url", "javascript:alert(1)", "file:///tmp/index.html?token=" + self.token,
            "https:///index.html?token=" + self.token,
            self.url.replace("panda-test.example", "user:pass@panda-test.example"),
            self.url.replace("panda-test.example", "bad host.example"),
            self.url.replace("panda-test.example", "panda-test.example:bad"),
            self.url.replace("panda-test.example", "panda-test.example:99999"),
            self.url.replace("panda-test.example", "."),
            self.url.replace("panda-test.example", "%zz"),
            self.url.replace("panda-test.example", "%00.example"),
            self.url.replace("panda-test.example", "example..com"),
            self.url.replace("&token=" + self.token, ""),
            self.url.replace(self.token, ""),
            self.url + "&token=another",
            self.url + "&%74oken=another",
            self.url + "\r\nInjected: value",
        ]
        for value in cases:
            with self.subTest(value=value[:100]):
                self.assert_invalid({"url": value})

    def test_rejects_untrusted_signatures_and_invalid_payloads(self) -> None:
        wrong_signature = issuer.jwt_encode.jwt_encode(self.payload, secret="synthetic-wrong-secret")
        cases = ["invalid", "a.b.c", wrong_signature]
        wrong_merchant = copy.deepcopy(self.payload)
        wrong_merchant["app_key"] = "UNSUPPORTED_MERCHANT"
        cases.append(sign(wrong_merchant))
        for field in ("account", "id", "login_time", "token"):
            invalid = copy.deepcopy(self.payload)
            del invalid["body"][field]
            cases.append(sign(invalid))
        invalid_body = copy.deepcopy(self.payload)
        invalid_body["body"] = []
        cases.append(sign(invalid_body))
        for token in cases:
            with self.subTest(token=token[:24]):
                self.assert_invalid({"url": launch_url(token)})

    def test_rejects_invalid_jwt_algorithm_even_with_valid_signature(self) -> None:
        header = issuer.jwt_encode.base64url_encode(b'{"alg":"none","typ":"JWT"}')
        _, payload, _ = self.token.split(".")
        signing_input = (header + "." + payload).encode("ascii")
        signature = hmac.new(issuer.jwt_encode.PUBLIC_KEY.encode(), signing_input, hashlib.sha256).digest()
        token = header + "." + payload + "." + issuer.jwt_encode.base64url_encode(signature)
        self.assert_invalid({"url": launch_url(token)})

    def test_rejects_invalid_request_fields(self) -> None:
        cases = [None, [], "url", {}, {"url": 123}, {"url": self.url, "vendor": "other"},
                 {"url": self.url, "tool": "other"}, {"url": self.url, "validity": "forever"}]
        for request in cases:
            with self.subTest(request=str(request)[:100]):
                self.assert_invalid(request)


class DebugToolHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server(host="127.0.0.1", port=0)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def request(self, method, path, body=None, headers=None):
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def generate(self, request=None, headers=None):
        if request is None:
            request = {"url": launch_url(sign(source_payload()))}
        if headers is None:
            headers = {"Content-Type": "application/json", "X-Debug-Tool": "1"}
        return self.request("POST", "/api/generate", json.dumps(request), headers)

    def assert_no_store(self, headers):
        normalized = {key.lower(): value for key, value in headers.items()}
        self.assertIn("no-store", normalized.get("cache-control", ""))

    def test_health_registry_and_ui(self) -> None:
        status, _, body = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ok": True})
        status, _, body = self.request("GET", "/api/vendors")
        self.assertEqual(status, 200)
        json.loads(body)
        self.assertIn(b"panda", body)
        self.assertIn(b"natural-free-token", body)
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        self.assertIn(b"<html", body.lower())

    def test_generates_result_without_exposing_tokens_in_headers_or_logs(self) -> None:
        token = sign(source_payload())
        capture = io.StringIO()
        with redirect_stderr(capture):
            status, headers, body = self.generate({"url": launch_url(token)})
            # Even unexpected request paths may contain pasted credentials.
            self.request("GET", "/missing?token=" + token)
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertIn("token", result)
        self.assertIs(result["session_verified"], False)
        self.assert_no_store(headers)
        for exposed in (str(headers), capture.getvalue()):
            self.assertNotIn(token, exposed)
            self.assertNotIn(result["token"], exposed)

    def test_rejects_bad_requests_with_json_errors(self) -> None:
        for request in ({"url": "invalid"}, [], None):
            status, headers, body = self.generate(request if request is not None else {"url": None})
            self.assertEqual(status, 400)
            self.assertIn("error", json.loads(body))
            self.assert_no_store(headers)
        status, headers, body = self.request("POST", "/api/generate", "{", {
            "Content-Type": "application/json", "X-Debug-Tool": "1",
        })
        self.assertEqual(status, 400)
        self.assertIn("error", json.loads(body))
        self.assert_no_store(headers)

    def test_requires_ui_marker_and_rejects_cross_origin(self) -> None:
        for headers in (
            {"Content-Type": "application/json"},
            {"Content-Type": "application/json", "X-Debug-Tool": "wrong"},
            {"Content-Type": "application/json", "X-Debug-Tool": "1", "Origin": "https://untrusted.example"},
        ):
            with self.subTest(headers=headers):
                status, response_headers, body = self.generate(headers=headers)
                self.assertEqual(status, 403)
                self.assertIn("error", json.loads(body))
                self.assert_no_store(response_headers)
        status, _, _ = self.generate(headers={
            "Content-Type": "application/json", "X-Debug-Tool": "1",
            "Origin": "http://127.0.0.1:" + str(self.port),
        })
        self.assertEqual(status, 200)

    def test_rejects_wrong_content_type_and_oversized_request(self) -> None:
        status, _, body = self.generate(headers={"Content-Type": "text/plain", "X-Debug-Tool": "1"})
        self.assertEqual(status, 415)
        self.assertIn("error", json.loads(body))
        status, headers, body = self.request("POST", "/api/generate", "x" * (64 * 1024 + 1), {
            "Content-Type": "application/json", "X-Debug-Tool": "1",
        })
        self.assertEqual(status, 413)
        self.assertIn("error", json.loads(body))
        self.assert_no_store(headers)

    def test_rejects_rebinding_host_even_with_matching_origin(self) -> None:
        host = "arbitrary.example:" + str(self.port)
        status, headers, body = self.generate(headers={
            "Content-Type": "application/json", "X-Debug-Tool": "1",
            "Host": host, "Origin": "http://" + host,
        })
        self.assertEqual(status, 403)
        self.assertIn("error", json.loads(body))
        self.assert_no_store(headers)

    def test_accepts_localhost_host_with_matching_origin(self) -> None:
        host = "localhost:" + str(self.port)
        status, headers, body = self.generate(headers={
            "Content-Type": "application/json", "X-Debug-Tool": "1",
            "Host": host, "Origin": "http://" + host,
        })
        self.assertEqual(status, 200)
        self.assertIn("token", json.loads(body))
        self.assert_no_store(headers)


if __name__ == "__main__":
    unittest.main()
