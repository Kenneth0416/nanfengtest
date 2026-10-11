"""Local HTTP tool server so a non-Python engine (Pi Durable) can call the
Python skills. Listens on 127.0.0.1 only."""
from __future__ import annotations

import json
import threading
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


DECK_TOOLS = {"brief_deck_data", "brief_deck_guide", "build_brief_pptx"}


def allowed(tool, mode: str) -> bool:
    """In the slide editor ("deck" mode) the Copilot may read the library and build decks, nothing else: an
    editing instruction is never filed as a tip, a deal or a rule."""
    return mode != "deck" or tool.name in DECK_TOOLS or (tool.read_only and tool.name != "add_watch_rule")


class ToolBridge:
    def __init__(self, app):
        self.app = app
        self.traces: dict[str, list] = defaultdict(list)
        self.modes: dict[str, str] = {}  # request id -> "deck" for slide-editor requests
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
                q = parse_qs(url.query)
                role = q.get("role", ["team"])[0]
                mode = q.get("mode", [""])[0]
                tools = [{"name": t.name, "description": t.description, "parameters": t.parameters,
                          "readOnly": t.read_only and t.name not in ("add_watch_rule",)}
                         for t in bridge.app.tools.values() if allowed(t, mode)]
                self._send(200, {"system": system_prompt(bridge.app, role), "tools": tools,
                                 "info": bridge.app.info_manifest()})

            def do_POST(self):
                if self.path != "/call":
                    return self._send(404, {"error": "not found"})
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                rid = self.headers.get("x-request-id", "")
                tool = bridge.app.tools.get(body.get("tool", ""))
                if tool is not None and not allowed(tool, bridge.modes.get(rid, "")):
                    return self._send(403, {"error": f"{tool.name} is not available while editing slides: an editing "
                                                     "instruction is not filed as a tip, a deal or a rule."})
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
