"""Tests for the POST /ask route on the tap endpoint.

A real ThreadedServer is bound to an ephemeral port on 127.0.0.1 and
exercised through http.client. mikai_ask is never imported — the
`_run_ask` seam is mocked, so no LLM, no brain, no wiki. The existing
tap-redirect routes get a smoke check to prove /ask didn't break them.
"""

from __future__ import annotations

import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tap_endpoint  # noqa: E402


FAKE_RESULT = {
    "answer": "Germaine is Brian's partner — **grounded** answer.",
    "retrieved": {
        "wiki_hits": 4,
        "entities": ["germaine"],
        "threads": ["wedding-venue"],
        "prompt_chars": 12345,
    },
}


class AskRouteTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = tap_endpoint.ThreadedServer(
            ("127.0.0.1", 0), tap_endpoint.TapHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    # ── helpers ──────────────────────────────────────────────────────

    def _request(self, method: str, path: str, body: bytes | None = None,
                 headers: dict | None = None):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        hdrs = {"Content-Type": "application/json"} if body is not None else {}
        hdrs.update(headers or {})
        conn.request(method, path, body=body, headers=hdrs)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    def _post_ask(self, payload: bytes):
        return self._request("POST", "/ask", body=payload)

    # ── tests ────────────────────────────────────────────────────────

    def test_post_ask_routes_and_json_round_trips(self):
        with mock.patch.object(tap_endpoint, "_run_ask",
                               return_value=FAKE_RESULT) as run:
            body = json.dumps({"query": "who is Germaine — café?"}).encode()
            resp, data = self._post_ask(body)
        self.assertEqual(resp.status, 200)
        self.assertIn("application/json", resp.getheader("Content-Type"))
        out = json.loads(data.decode("utf-8"))
        self.assertEqual(out["answer"], FAKE_RESULT["answer"])
        self.assertEqual(out["retrieved"], FAKE_RESULT["retrieved"])
        run.assert_called_once_with("who is Germaine — café?")

    def test_post_ask_sends_cors_header(self):
        with mock.patch.object(tap_endpoint, "_run_ask",
                               return_value=FAKE_RESULT):
            resp, _ = self._post_ask(json.dumps({"query": "hi"}).encode())
        self.assertEqual(resp.getheader("Access-Control-Allow-Origin"), "*")

    def test_options_preflight_passes(self):
        resp, data = self._request("OPTIONS", "/ask")
        self.assertEqual(resp.status, 204)
        self.assertEqual(data, b"")
        self.assertEqual(resp.getheader("Access-Control-Allow-Origin"), "*")
        self.assertIn("POST", resp.getheader("Access-Control-Allow-Methods"))
        self.assertIn("Content-Type",
                      resp.getheader("Access-Control-Allow-Headers"))

    def test_malformed_json_rejected_400(self):
        with mock.patch.object(tap_endpoint, "_run_ask") as run:
            resp, data = self._post_ask(b"{not json!!")
        self.assertEqual(resp.status, 400)
        self.assertIn("error", json.loads(data.decode()))
        run.assert_not_called()

    def test_missing_or_empty_query_rejected_400(self):
        with mock.patch.object(tap_endpoint, "_run_ask") as run:
            for payload in (b"{}", b'{"query": "   "}', b'{"query": 7}',
                            b'["not", "a", "dict"]'):
                resp, data = self._post_ask(payload)
                self.assertEqual(resp.status, 400, payload)
                self.assertIn("error", json.loads(data.decode()), payload)
        run.assert_not_called()

    def test_oversize_payload_rejected_413(self):
        big = json.dumps({"query": "x" * 5000}).encode()
        self.assertGreater(len(big), tap_endpoint.MAX_ASK_BYTES)
        with mock.patch.object(tap_endpoint, "_run_ask") as run:
            resp, data = self._post_ask(big)
        self.assertEqual(resp.status, 413)
        self.assertIn("error", json.loads(data.decode()))
        run.assert_not_called()

    def test_ask_failure_surfaces_as_500_json_error(self):
        with mock.patch.object(tap_endpoint, "_run_ask",
                               side_effect=RuntimeError("model exploded")):
            resp, data = self._post_ask(json.dumps({"query": "boom"}).encode())
        self.assertEqual(resp.status, 500)
        out = json.loads(data.decode())
        self.assertIn("model exploded", out["error"])
        self.assertEqual(resp.getheader("Access-Control-Allow-Origin"), "*")

    # ── /ask/stream (SSE) ────────────────────────────────────────────

    def _get_stream(self, path: str):
        """Open a raw HTTP GET, return (resp, full body bytes). The
        server closes the connection when the generator finishes, so
        rfile.read() on the response drains the whole SSE stream."""
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", path)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    def test_get_ask_stream_emits_retrieved_chunks_done_in_order(self):
        events = [
            {"type": "retrieved",
             "data": {"wiki_hits": 2, "entities": ["germaine"],
                      "threads": ["wedding-venue"], "prompt_chars": 4321}},
            {"type": "chunk", "text": "Hello "},
            {"type": "chunk", "text": "Brian, "},
            {"type": "chunk", "text": "here you go."},
            {"type": "done", "answer": "Hello Brian, here you go."},
        ]
        with mock.patch.object(tap_endpoint, "_run_ask_stream",
                               return_value=iter(events)):
            resp, data = self._get_stream("/ask/stream?q=who+is+Germaine")

        self.assertEqual(resp.status, 200)
        self.assertIn("text/event-stream",
                      resp.getheader("Content-Type") or "")
        self.assertEqual(resp.getheader("Cache-Control"),
                         "no-cache, no-transform")

        body = data.decode("utf-8")
        # Every event appears in order as an SSE frame
        for ev in events:
            self.assertIn("event: " + ev["type"] + "\n", body,
                          f"missing SSE event for {ev['type']}")
        # Order preserved: retrieved before first chunk before done
        idx_retrieved = body.index("event: retrieved")
        idx_first_chunk = body.index("event: chunk")
        idx_done = body.index("event: done")
        self.assertLess(idx_retrieved, idx_first_chunk)
        self.assertLess(idx_first_chunk, idx_done)
        # Data payload for the chunk parses back to the same text
        chunk_line = [ln for ln in body.splitlines()
                      if ln.startswith("data: ")
                      and '"type": "chunk"' in ln][0]
        parsed = json.loads(chunk_line[len("data: "):])
        self.assertEqual(parsed["text"], "Hello ")

    def test_get_ask_stream_sets_cors_header(self):
        with mock.patch.object(tap_endpoint, "_run_ask_stream",
                               return_value=iter([{"type": "done"}])):
            resp, _ = self._get_stream("/ask/stream?q=hi")
        self.assertEqual(resp.getheader("Access-Control-Allow-Origin"), "*")

    def test_get_ask_stream_oversize_query_413(self):
        big_q = "x" * (tap_endpoint.MAX_ASK_BYTES + 10)
        with mock.patch.object(tap_endpoint, "_run_ask_stream") as run:
            resp, data = self._get_stream("/ask/stream?q=" + big_q)
        self.assertEqual(resp.status, 413)
        self.assertIn("error", json.loads(data.decode()))
        run.assert_not_called()

    def test_get_ask_stream_missing_query_400(self):
        with mock.patch.object(tap_endpoint, "_run_ask_stream") as run:
            resp, data = self._get_stream("/ask/stream")
            self.assertEqual(resp.status, 400)
            self.assertIn("error", json.loads(data.decode()))
            resp2, _ = self._get_stream("/ask/stream?q=%20%20")
            self.assertEqual(resp2.status, 400)
        run.assert_not_called()

    def test_post_ask_stream_returns_405(self):
        with mock.patch.object(tap_endpoint, "_run_ask_stream") as run:
            resp, _ = self._request(
                "POST", "/ask/stream", body=b'{"query":"hi"}')
        self.assertEqual(resp.status, 405)
        self.assertIn("GET", resp.getheader("Allow") or "")
        run.assert_not_called()

    def test_get_ask_stream_provider_error_becomes_sse_error_event(self):
        def blowup(_q):
            yield {"type": "retrieved", "data": {"wiki_hits": 0}}
            raise RuntimeError("model exploded mid-stream")
        with mock.patch.object(tap_endpoint, "_run_ask_stream",
                               side_effect=blowup):
            resp, data = self._get_stream("/ask/stream?q=please+break")
        self.assertEqual(resp.status, 200)  # SSE already opened OK
        body = data.decode("utf-8")
        self.assertIn("event: retrieved", body)
        self.assertIn("event: error", body)
        err_line = [ln for ln in body.splitlines()
                    if ln.startswith("data: ") and "exploded" in ln][0]
        parsed = json.loads(err_line[len("data: "):])
        self.assertIn("model exploded", parsed["error"])

    def test_existing_routes_still_work(self):
        resp, data = self._request("GET", "/healthz")
        self.assertEqual(resp.status, 200)
        self.assertEqual(data, b"ok\n")
        # unknown tap id still 404s (redirect route intact, malformed id path)
        resp, _ = self._request("GET", "/t/not-a-real-id")
        self.assertEqual(resp.status, 404)
        # POST to a non-/ask path is a JSON 404, not a crash
        resp, data = self._request("POST", "/t/abcdefabcdef", body=b"{}")
        self.assertEqual(resp.status, 404)


if __name__ == "__main__":
    unittest.main()
