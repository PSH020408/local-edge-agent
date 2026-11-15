"""Offline test of the model call log (agent/llm.py), against a tiny local stand-in for Ollama."""

import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent import llm  # noqa: E402


class _Fake(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self._send({"message": {"role": "assistant", "content": "ok"}, "prompt_eval_count": 1681, "eval_count": 400,
                    "load_duration": 4.5e9, "prompt_eval_duration": 6e9, "eval_duration": 20e9, "total_duration": 31e9})

    def do_GET(self):
        self._send({"models": [{"name": "qwen3-vl:8b-instruct", "size": 7.9e9, "size_vram": 7.9e9}]})


class CallLogTests(unittest.TestCase):
    def test_each_call_is_logged_with_its_phases_and_the_loaded_models(self):
        server = HTTPServer(("127.0.0.1", 0), _Fake)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        saved = llm.CALL_LOG
        try:
            with tempfile.TemporaryDirectory() as tmp:
                llm.CALL_LOG = Path(tmp) / "calls.jsonl"
                client = llm.OllamaClient("qwen3-vl:8b-instruct", host=f"http://127.0.0.1:{server.server_port}",
                                          options={"num_ctx": 8192})
                reply = client.chat([{"role": "user", "content": "page", "images": ["abc"]}])
                self.assertEqual(reply["stats"]["load_s"], 4.5)
                record = json.loads(llm.CALL_LOG.read_text().splitlines()[0])
                self.assertEqual((record["images"], record["prompt_s"], record["gen_s"], record["num_ctx"]), (1, 6.0, 20.0, 8192))
                self.assertEqual(record["loaded"][0]["gb"], 7.9)
                llm.CALL_LOG = Path(tmp) / "missing" / "x" / "\0bad"  # a broken path never breaks the call
                self.assertEqual(client.chat([{"role": "user", "content": "x"}])["message"]["content"], "ok")
        finally:
            llm.CALL_LOG = saved
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
