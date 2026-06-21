"""Tests for the secret/PII detection library (stdlib unittest)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.environ.setdefault("CLAUDE_PLUGIN_ROOT", str(_ROOT))

from cpl.shared import secrets  # noqa: E402


class Detects(unittest.TestCase):
    def _kinds(self, text, cfg=None):
        return {f.kind for f in secrets.scan(text, cfg)}

    def test_aws_access_key_blocks(self):
        ks = self._kinds("my key is AKIAIOSFODNN7EXAMPLE here")
        self.assertIn("aws_access_key", ks)

    def test_openai_key(self):
        self.assertIn("openai_key",
                      self._kinds("token sk-abcdefghijklmnop0123456789"))

    def test_github_token(self):
        self.assertIn("github_token",
                      self._kinds("ghp_0123456789abcdefghijklmnopqrstuvwxyz"))

    def test_private_key(self):
        self.assertIn("private_key",
                      self._kinds("-----BEGIN RSA PRIVATE KEY-----\nMII..."))

    def test_jwt(self):
        jwt = "eyJhbGciOiJI.eyJzdWIiOiIxMjM0NTY.SflKxwRJSMeKKF2QT4"
        self.assertIn("jwt", self._kinds(f"here is a token {jwt}"))

    def test_secret_assignment(self):
        self.assertIn("secret_assignment",
                      self._kinds('api_key = "abcd1234efgh"'))

    def test_password_assignment(self):
        self.assertIn("password_assignment",
                      self._kinds("password: hunter2pass"))

    def test_connection_string(self):
        self.assertIn("connection_string",
                      self._kinds("postgres://user:s3cret@db.example.com/app"))

    def test_email_is_pii_warn(self):
        fs = secrets.scan("contact me at jane.doe@example.com please")
        self.assertEqual([f.severity for f in fs if f.kind == "email"], ["warn"])

    def test_ssn(self):
        self.assertIn("ssn", self._kinds("ssn 123-45-6789"))


class NoFalsePositives(unittest.TestCase):
    def _kinds(self, text):
        return {f.kind for f in secrets.scan(text)}

    def test_prose_is_clean(self):
        self.assertEqual(
            self._kinds("Refactor parseToken() in auth.py and add a test"), set())

    def test_git_sha_not_a_secret(self):
        self.assertEqual(self._kinds("see commit 4932ddb for the fix"), set())

    def test_uuid_not_a_secret(self):
        self.assertEqual(
            self._kinds("id 550e8400-e29b-41d4-a716-446655440000"), set())

    def test_non_card_16_digits_rejected_by_luhn(self):
        # 16 digits that fail Luhn must NOT be flagged as a credit card.
        self.assertNotIn("credit_card", self._kinds("order number 1234567812345678"))

    def test_valid_card_passes_luhn(self):
        self.assertIn("credit_card", self._kinds("card 4242 4242 4242 4242"))


class Behavior(unittest.TestCase):
    def test_mask_text_redacts_in_place(self):
        text = "key sk-abcdefghijklmnop0123456789 end"
        fs = secrets.scan(text)
        masked = secrets.mask_text(text, fs)
        self.assertNotIn("sk-abcdefghijklmnop0123456789", masked)
        self.assertIn("end", masked)

    def test_preview_never_contains_full_secret(self):
        fs = secrets.scan("ghp_0123456789abcdefghijklmnopqrstuvwxyz")
        self.assertTrue(fs)
        self.assertNotIn("0123456789abcdefghijklmnopqrstuvwxyz", fs[0].preview)

    def test_allowlist_drops_match(self):
        cfg = {"mask": {"allowlist": ["AKIAIOSFODNN7EXAMPLE"]}}
        self.assertEqual(secrets.scan("AKIAIOSFODNN7EXAMPLE", cfg), [])

    def test_custom_pattern_honored(self):
        cfg = {"mask": {"custom_patterns": [
            {"name": "acme_token", "regex": r"ACME-[0-9]{6}", "severity": "block"}]}}
        ks = {f.kind for f in secrets.scan("token ACME-123456", cfg)}
        self.assertIn("acme_token", ks)

    def test_bad_custom_regex_is_skipped(self):
        cfg = {"mask": {"custom_patterns": [
            {"name": "bad", "regex": "(", "severity": "block"}]}}
        # Must not raise; built-ins still work.
        self.assertIn("openai_key",
                      {f.kind for f in secrets.scan("sk-abcdefghijklmnop0123456789", cfg)})

    def test_scan_failsafe_on_bad_input(self):
        self.assertEqual(secrets.scan(None), [])  # type: ignore

    def test_has_block_and_has_warn(self):
        fs = secrets.scan("postgres://u:p@h/db and jane@example.com")
        self.assertTrue(secrets.has_block(fs))
        self.assertTrue(secrets.has_warn(fs))


if __name__ == "__main__":
    unittest.main()
