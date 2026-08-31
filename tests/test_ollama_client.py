"""OllamaClient behavior: keep_alive payload, error surfacing, unload."""
from __future__ import annotations

import unittest
from unittest import mock

from llm.client import OllamaClient


class _Resp:
    def __init__(self, status_code, json=None, text=""):
        self.status_code = status_code
        self._json = json
        self.text = text

    def json(self):
        return self._json


class OllamaClientTest(unittest.TestCase):
    def test_sends_keep_alive_in_payload(self):
        with mock.patch("llm.client.requests.post", return_value=_Resp(200, {"response": "hi"})) as post:
            OllamaClient(model="m").generate("Say hi")
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["keep_alive"], "5m")
        self.assertIn("keep_alive", body)

    def test_ok_response_returns_text(self):
        with mock.patch("llm.client.requests.post", return_value=_Resp(200, {"response": "Hello"})):
            self.assertEqual(OllamaClient(model="m").generate("x"), "Hello")

    def test_404_model_not_found_surfaces_pull_hint(self):
        with mock.patch(
            "llm.client.requests.post",
            return_value=_Resp(404, {"error": "model 'nope' not found"}),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                OllamaClient(model="nope").generate("x")
        msg = str(ctx.exception)
        self.assertIn("HTTP 404", msg)
        self.assertIn("model 'nope' not found", msg)
        self.assertIn("ollama pull nope", msg)

    def test_other_http_error_mentions_status(self):
        with mock.patch(
            "llm.client.requests.post",
            return_value=_Resp(500, {"error": "boom"}),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                OllamaClient(model="m").generate("x")
        self.assertIn("HTTP 500", str(ctx.exception))

    def test_requests_connection_error_is_legible(self):
        import requests

        with mock.patch(
            "llm.client.requests.post",
            side_effect=requests.ConnectionError("refused"),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                OllamaClient(model="m").generate("x")
        self.assertIn("Could not reach Ollama", str(ctx.exception))

    def test_unload_posts_keep_alive_zero(self):
        with mock.patch("llm.client.requests.post") as post:
            OllamaClient(model="m").unload()
        body = post.call_args.kwargs["json"]
        self.assertEqual(body, {"model": "m", "keep_alive": 0})


if __name__ == "__main__":
    unittest.main()