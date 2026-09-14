"""Configuration and compatibility checks without real merchant secrets."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("PANDA_JWT_SECRET", "synthetic-panda-signing-key-for-tests")

import panda_jwt


class PandaJWTTests(unittest.TestCase):
    def test_environment_key_takes_precedence_over_local_file(self) -> None:
        with patch.dict(os.environ, {"PANDA_JWT_SECRET": "synthetic-environment-key", "PANDA_JWT_SECRET_FILE": "/run/secrets/ignored"}), patch.object(Path, "read_text") as read:
            self.assertEqual(panda_jwt._load_key(), "synthetic-environment-key")
            read.assert_not_called()

    def test_local_file_is_used_without_environment_key(self) -> None:
        with patch.dict(os.environ, {"PANDA_JWT_SECRET": "", "PANDA_JWT_SECRET_FILE": ""}), patch.object(Path, "read_text", autospec=True, return_value="synthetic-file-key\n") as read:
            self.assertEqual(panda_jwt._load_key(), "synthetic-file-key")
            read.assert_called_once_with(Path(panda_jwt.__file__).with_name(".panda_signing_key"), encoding="utf-8")

    def test_configured_secret_file_takes_precedence_over_default(self) -> None:
        key_file = "/run/secrets/panda_jwt_secret"
        with patch.dict(os.environ, {"PANDA_JWT_SECRET": "", "PANDA_JWT_SECRET_FILE": key_file}), patch.object(Path, "read_text", autospec=True, return_value="synthetic-docker-key\n") as read:
            self.assertEqual(panda_jwt._load_key(), "synthetic-docker-key")
            read.assert_called_once_with(Path(key_file), encoding="utf-8")

    def test_missing_configured_secret_does_not_fall_back_to_another_key(self) -> None:
        key_file = "/run/secrets/missing"
        with patch.dict(os.environ, {"PANDA_JWT_SECRET": "", "PANDA_JWT_SECRET_FILE": key_file}), patch.object(Path, "read_text", autospec=True, side_effect=FileNotFoundError) as read:
            self.assertEqual(panda_jwt._load_key(), "")
            read.assert_called_once_with(Path(key_file), encoding="utf-8")

    def test_missing_configuration_fails_clearly_without_exposing_token(self) -> None:
        with patch.dict(os.environ, {"PANDA_JWT_SECRET": ""}), patch.object(Path, "read_text", side_effect=FileNotFoundError):
            self.assertEqual(panda_jwt._load_key(), "")
        with patch.object(panda_jwt, "PUBLIC_KEY", ""):
            with self.assertRaisesRegex(ValueError, "PANDA_JWT_SECRET"):
                panda_jwt.jwt_encode({"value": "synthetic"})
            with self.assertRaisesRegex(ValueError, "PANDA_JWT_SECRET") as error:
                panda_jwt.jwt_decode("private-synthetic-token")
            self.assertNotIn("private-synthetic-token", str(error.exception))

    def test_round_trip_preserves_expired_source_payload(self) -> None:
        payload = {"exp": 1, "iat": 0, "body": {"token": "synthetic-session", "name": "测试"}}
        token = panda_jwt.jwt_encode(payload)
        self.assertEqual(panda_jwt.jwt_decode(token), payload)
        self.assertEqual(panda_jwt.jwt_encode(dict(reversed(list(payload.items())))), token)

    def test_matches_original_panda_signer_fixture(self) -> None:
        # Captured from Panda's original signer with this synthetic key/payload.
        payload = {"exp": 1, "iat": 0, "body": {"token": "synthetic-session", "name": "测试"}}
        expected = (
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJib2R5Ijp7Im5hbWUiOiJcdTZkNGJcdThiZDUiLCJ0b2tlbiI6InN5bnRoZXRpYy1zZXNzaW9uIn0sImV4cCI6MSwiaWF0IjowfQ."
            "bK6MpQSZqEHIWQ9IhxbWSTM0hXiuyxYlzpVdkSGlP-U"
        )
        self.assertEqual(panda_jwt.jwt_encode(payload, secret="synthetic-fixture-key"), expected)
        self.assertEqual(panda_jwt.jwt_decode(expected, secret="synthetic-fixture-key"), payload)

    def test_wrong_key_and_malformed_tokens_fail_without_credentials(self) -> None:
        token = panda_jwt.jwt_encode({"body": {"token": "synthetic-session"}}, secret="synthetic-one")
        invalid = [token, "a.b.c", "not-a-jwt", "e30.e30.bad%signature"]
        for value in invalid:
            with self.subTest(value=value[:12]):
                with self.assertRaises(ValueError) as error:
                    panda_jwt.jwt_decode(value, secret="synthetic-two")
                self.assertNotIn(value, str(error.exception))


if __name__ == "__main__":
    unittest.main()
