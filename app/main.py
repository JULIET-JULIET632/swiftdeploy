#!/usr/bin/env python3
import os
import time
import random
import threading
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Environment ────────────────────────────────────────────────
MODE        = os.environ.get("MODE", "stable")
APP_VERSION = os.environ.get("APP_VERSION", "1.0.0")
APP_PORT    = int(os.environ.get("APP_PORT", 3000))
START_TIME  = time.time()

# ── Chaos state ────────────────────────────────────────────────
chaos_lock  = threading.Lock()
chaos_state = {"mode": None, "duration": 0, "rate": 0.0}

# ── Metrics state ──────────────────────────────────────────────
metrics_lock = threading.Lock()

# Counters: key = (method, path, status_code)
request_counts = {}

# Histogram buckets for latency in seconds
BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

# Histogram state: key = (method, path)
# value = {"buckets": {le: count}, "sum": float, "count": int}
latency_histograms = {}


def record_request(method, path, status_code, duration):
    """Record one request into metrics state."""
    with metrics_lock:
        # counter
        key = (method, path, str(status_code))
        request_counts[key] = request_counts.get(key, 0) + 1

        # histogram
        hkey = (method, path)
        if hkey not in latency_histograms:
            latency_histograms[hkey] = {
                "buckets": {le: 0 for le in BUCKETS},
                "sum": 0.0,
                "count": 0
            }
        h = latency_histograms[hkey]
        for le in BUCKETS:
            if duration <= le:
                h["buckets"][le] += 1
        h["sum"]   += duration
        h["count"] += 1


def build_metrics():
    """Build Prometheus text format metrics string."""
    lines = []

    # ── http_requests_total ──────────────────────────────────
    lines.append("# HELP http_requests_total Total HTTP requests")
    lines.append("# TYPE http_requests_total counter")
    with metrics_lock:
        for (method, path, status_code), count in request_counts.items():
            lines.append(
                f'http_requests_total{{method="{method}",path="{path}",status_code="{status_code}"}} {count}'
            )

    # ── http_request_duration_seconds ────────────────────────
    lines.append("# HELP http_request_duration_seconds Request latency histogram")
    lines.append("# TYPE http_request_duration_seconds histogram")
    with metrics_lock:
        for (method, path), h in latency_histograms.items():
            for le, count in h["buckets"].items():
                lines.append(
                    f'http_request_duration_seconds_bucket{{method="{method}",path="{path}",le="{le}"}} {count}'
                )
            lines.append(
                f'http_request_duration_seconds_bucket{{method="{method}",path="{path}",le="+Inf"}} {h["count"]}'
            )
            lines.append(
                f'http_request_duration_seconds_sum{{method="{method}",path="{path}"}} {h["sum"]}'
            )
            lines.append(
                f'http_request_duration_seconds_count{{method="{method}",path="{path}"}} {h["count"]}'
            )

    # ── app_uptime_seconds ───────────────────────────────────
    lines.append("# HELP app_uptime_seconds Seconds since app started")
    lines.append("# TYPE app_uptime_seconds gauge")
    lines.append(f"app_uptime_seconds {round(time.time() - START_TIME, 2)}")

    # ── app_mode ─────────────────────────────────────────────
    lines.append("# HELP app_mode Current mode: 0=stable 1=canary")
    lines.append("# TYPE app_mode gauge")
    lines.append(f"app_mode {1 if MODE == 'canary' else 0}")

    # ── chaos_active ─────────────────────────────────────────
    lines.append("# HELP chaos_active Active chaos: 0=none 1=slow 2=error")
    lines.append("# TYPE chaos_active gauge")
    with chaos_lock:
        cmode = chaos_state["mode"]
    if cmode == "slow":
        chaos_val = 1
    elif cmode == "error":
        chaos_val = 2
    else:
        chaos_val = 0
    lines.append(f"chaos_active {chaos_val}")

    return "\n".join(lines) + "\n"


def apply_chaos():
    """Apply active chaos. Returns True if request should 500."""
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
        start = time.time()
        if self.path == "/":
            status = self._handle_root()
        elif self.path == "/healthz":
            status = self._handle_healthz()
        elif self.path == "/metrics":
            status = self._handle_metrics()
            return
        else:
            self._json(404, {"error": "not found"})
            status = 404
        duration = time.time() - start
        record_request("GET", self.path, status, duration)

    def do_POST(self):
        start = time.time()
        if self.path == "/chaos":
            status = self._handle_chaos()
        else:
            self._json(404, {"error": "not found"})
            status = 404
        duration = time.time() - start
        record_request("POST", self.path, status, duration)

    def _handle_root(self):
        if MODE == "canary" and apply_chaos():
            self._json(500, {"error": "chaos error", "mode": MODE})
            return 500
        self._json(200, {
            "message": "Welcome to SwiftDeploy API",
            "mode":    MODE,
            "version": APP_VERSION,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
        return 200

    def _handle_healthz(self):
        uptime = round(time.time() - START_TIME, 2)
        self._json(200, {
            "status": "ok",
            "mode":   MODE,
            "uptime": uptime,
        })
        return 200

    def _handle_metrics(self):
        """Expose Prometheus format metrics."""
        payload = build_metrics().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)

    def _handle_chaos(self):
        if MODE != "canary":
            self._json(403, {"error": "chaos endpoint only available in canary mode"})
            return 403
        length = int(self.headers.get("Content-Length", 0))
        raw    = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid JSON"})
            return 400
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
                return 400
        return 200


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", APP_PORT), Handler)
    print(f"SwiftDeploy API | port={APP_PORT} | mode={MODE} | version={APP_VERSION}")
    server.serve_forever()
