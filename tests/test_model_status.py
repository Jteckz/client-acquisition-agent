"""model-status CLI command: reflects what Ollama actually has loaded (§11, §12.5)."""
from __future__ import annotations

import argparse
import io
import unittest
import unittest.mock
from contextlib import redirect_stdout

import main


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class ModelStatusTest(unittest.TestCase):
    def test_lists_resident_models(self):
        payload = {
            "models": [
                {
                    "name": "qwen2.5:7b-instruct",
                    "size": 5_200_000_000,
                    "size_vram": 0,
                    "expires_at": "2026-08-11T00:00:00Z",
                },
            ]
        }
        with unittest.mock.patch("requests.get", return_value=FakeResponse(payload)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                main.cmd_model_status(argparse.Namespace())
        out = buf.getvalue()
        self.assertIn("qwen2.5:7b-instruct", out)
        self.assertIn("GB", out)

    def test_no_models_prints_empty_state(self):
        with unittest.mock.patch("requests.get", return_value=FakeResponse({"models": []})):
            buf = io.StringIO()
            with redirect_stdout(buf):
                main.cmd_model_status(argparse.Namespace())
        self.assertIn("No models currently resident", buf.getvalue())

    def test_unreachable_ollama_raises_system_exit(self):
        import requests

        with unittest.mock.patch(
            "requests.get", side_effect=requests.ConnectionError("refused")
        ):
            with self.assertRaises(SystemExit):
                main.cmd_model_status(argparse.Namespace())


if __name__ == "__main__":
    unittest.main()
