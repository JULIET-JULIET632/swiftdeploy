#!/usr/bin/env python3
import os
import time
import random
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

MODE        = os.environ.get("MODE", "stable")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
APP_PORT    = int(os.environ.get("APP_PORT", 3000))

START_TIME  = time.time()

chaos_lock  = threading.Lock()
chaos_state = {"mode": None, "duration": 0, "rate": 0.0}


def apply_chaos():
    with chaos_lock:
        state = dict(chaos_state)
    if state["mode"] == "slow":
        time.sleep(state["duration"])
    elif state["mode"] == "error":
        if random.random() < state["rate"]:
            return True
    return False


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _headers(self, status, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Connection", "close")
        if MODE == "canary":
            self.send_header("X-Mode", "canary")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()

    def _json(self, status, body, extra_headers=None):
        payload = json.dumps(body).encode()
        self._headers(status, extra_headers)
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        if self.path == "/":
            self._handle_root()
        elif self.path == "/healthz":
            self._handle_healthz()
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/chaos":
            self._handle_chaos()
        else:
            self._json(404, {"error": "not found"})

    def _handle_root(self):
        if MODE == "canary" and apply_chaos():
            self._json(500, {"error": "chaos error", "mode": MODE})
            return
        self._json(200, {
            "message": "Welcome to SwiftDeploy API",
            "mode":    MODE,
            "version": APP_VERSION,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })

    def _handle_healthz(self):
        uptime = round(time.time() - START_TIME, 2)
        self._json(200, {
            "status": "ok",
            "mode":   MODE,
            "uptime": uptime,
        })

    def _handle_chaos(self):
        if MODE != "canary":
            self._json(403, {"error": "chaos endpoint only available in canary mode"})
            return
        length = int(self.headers.get("Content-Length", 0))
        raw    = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid JSON"})
            return
        chaos_mode = body.get("mode")
        with chaos_lock:
            if chaos_mode == "slow":
                duration = int(body.get("duration", 1))
                chaos_state.update({"mode": "slow", "duration": duration, "rate": 0.0})
                self._json(200, {"chaos": "slow", "duration": duration})
            elif chaos_mode == "error":
                rate = float(body.get("rate", 0.5))
                chaos_state.update({"mode": "error", "duration": 0, "rate": rate})
                self._json(200, {"chaos": "error", "rate": rate})
            elif chaos_mode == "recover":
                chaos_state.update({"mode": None, "duration": 0, "rate": 0.0})
                self._json(200, {"chaos": "recovered"})
            else:
                self._json(400, {"error": f"unknown chaos mode: {chaos_mode}"})


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", APP_PORT), Handler)
    print(f"SwiftDeploy API running on port {APP_PORT} | mode={MODE} | version={APP_VERSION}")
    server.serve_forever()
