"""Local HTTP tool server so a non-Python engine (Pi Durable) can call the
Python skills. Listens on 127.0.0.1 only."""
from __future__ import annotations

import json
import threading
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class ToolBridge:
    def __init__(self, app):
        self.app = app
        self.traces: dict[str, list] = defaultdict(list)
        self.lock = threading.Lock()
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body):
                data = json.dumps(body, default=str).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except BrokenPipeError:   # engine process went away; Pi Durable will retry
                    pass

            def do_GET(self):
                from .pi_engine import system_prompt
                url = urlparse(self.path)
                if url.path != "/manifest":
                    return self._send(404, {"error": "not found"})
                role = parse_qs(url.query).get("role", ["team"])[0]
                tools = [{"name": t.name, "description": t.description, "parameters": t.parameters,
                          "readOnly": t.read_only and t.name not in ("add_watch_rule",)} for t in bridge.app.tools.values()]
                self._send(200, {"system": system_prompt(bridge.app, role), "tools": tools,
                                 "info": bridge.app.info_manifest()})

            def do_POST(self):
                if self.path != "/call":
                    return self._send(404, {"error": "not found"})
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                rid = self.headers.get("x-request-id", "")
                try:
                    with bridge.lock:   # the SQLite store is shared with the UI
                        result = bridge.app.call(body["tool"], body.get("args") or {}, body.get("role"))
                except Exception as e:
                    return self._send(400, {"error": str(e)})
                bridge.traces[rid].append({"tool": body["tool"], "args": body.get("args") or {}, "result": result})
                self._send(200, {k: v for k, v in result.items() if k != "chart"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def pop_trace(self, rid: str) -> list:
        return self.traces.pop(rid, [])
