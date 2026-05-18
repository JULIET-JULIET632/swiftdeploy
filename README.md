# SwiftDeploy

> Build the tool that builds the stack — with observability, policy enforcement, and auditing.

SwiftDeploy is a declarative deployment system. You describe your stack in manifest.yaml and the CLI generates all configs, manages the container lifecycle, enforces deployment policies via OPA, and provides real-time observability.

## Project Structure

swiftdeploy/
├── manifest.yaml                 ← Single source of truth (only file you edit)
├── swiftdeploy                   ← CLI executable
├── Dockerfile                    ← Lightweight app image
├── app/
│   └── main.py                   ← Python HTTP service with metrics
├── policies/
│   ├── infrastructure.rego       ← Pre-deploy policy
│   ├── canary.rego               ← Pre-promote policy
│   └── data.json                 ← Policy thresholds
└── templates/
    ├── nginx.conf.tmpl           ← Nginx config template
    ├── log_format.conf.tmpl      ← Nginx log format template
    └── docker-compose.yml.tmpl   ← Compose template

Generated at runtime (do not commit): nginx.conf, log_format.conf, docker-compose.yml, history.jsonl, audit_report.md

## Prerequisites

- Docker Engine 24+
- Docker Compose v2
- Python 3.10+
- pip install pyyaml

## Quick Start

Step 1: Build the app image
docker build -t swift-deploy-1-node:latest .

Step 2: Deploy (OPA starts first, policy check runs, then full stack)
./swiftdeploy deploy

Your service is now running at http://localhost:8080

## Subcommand Reference

### init
Parses manifest.yaml and generates nginx.conf, log_format.conf and docker-compose.yml from templates.
./swiftdeploy init

### validate
Runs 5 pre-flight checks. Exits non-zero if any fail.
./swiftdeploy validate

Check 1: manifest.yaml exists and is valid YAML
Check 2: All required fields are present and non-empty
Check 3: Docker image referenced in manifest exists locally
Check 4: Nginx port is not already bound on the host
Check 5: Generated nginx.conf is syntactically valid

### deploy
Starts OPA first, runs pre-deploy infrastructure policy check, then brings up the full stack. Blocks if policy fails.
./swiftdeploy deploy

Pre-deploy check sends host stats to OPA:
- Disk free must be above 10GB
- CPU load must be below 2.0

If policy fails:
[BLOCKED] Deployment denied by infrastructure policy
  → Disk free (8.2GB) is below minimum threshold (10.0GB)

### promote
Runs pre-promote canary safety policy check, then switches mode with a rolling restart of the app container only. Blocks if policy fails.
./swiftdeploy promote canary
./swiftdeploy promote stable

Pre-promote check sends metrics to OPA:
- Error rate must be below 1%
- P99 latency must be below 500ms

If policy fails:
[BLOCKED] Promotion denied by canary safety policy
  → Error rate (3.2%) exceeds maximum threshold (1.00%)

### teardown
Stops and removes all containers, networks, and volumes.
./swiftdeploy teardown
./swiftdeploy teardown --clean

### status
Live-refreshing terminal dashboard showing real-time metrics and policy compliance. Appends every scrape to history.jsonl.
./swiftdeploy status

Shows:
- Current mode (stable/canary)
- Requests per second
- Error rate
- P99 latency
- Chaos state
- Infrastructure policy: PASS/FAIL
- Canary safety policy: PASS/FAIL

Press Ctrl+C to exit.

### audit
Generates audit_report.md from history.jsonl showing timeline, mode changes, policy violations, and chaos events.
./swiftdeploy audit

## API Endpoints

GET /         - Welcome message with mode, version, timestamp
GET /healthz  - Status and process uptime in seconds
GET /metrics  - Prometheus format metrics
POST /chaos   - Simulate degraded behaviour (canary mode only)

### Metrics exposed

http_requests_total{method, path, status_code} - Request counter
http_request_duration_seconds{method, path, le} - Latency histogram
app_uptime_seconds                              - App uptime
app_mode                                        - 0=stable 1=canary
chaos_active                                    - 0=none 1=slow 2=error

### Chaos modes (canary only)

Slow: sleep N seconds before each response
curl -X POST http://localhost:8080/chaos -H 'Content-Type: application/json' -d '{"mode": "slow", "duration": 3}'

Error: return 500 on ~50% of requests
curl -X POST http://localhost:8080/chaos -H 'Content-Type: application/json' -d '{"mode": "error", "rate": 0.5}'

Recover: cancel active chaos
curl -X POST http://localhost:8080/chaos -H 'Content-Type: application/json' -d '{"mode": "recover"}'

## OPA Policy Engine

OPA runs as a separate container on an isolated internal network. It is not accessible through nginx.

### Infrastructure Policy (pre-deploy)
File: policies/infrastructure.rego
Blocks deployment if:
- Disk free is below min_disk_free_gb (default 10GB)
- CPU load is above max_cpu_load (default 2.0)

### Canary Safety Policy (pre-promote)
File: policies/canary.rego
Blocks promotion if:
- Error rate is above max_error_rate_pct (default 1%)
- P99 latency is above max_p99_latency_ms (default 500ms)

### Changing thresholds
Edit policies/data.json only. Never touch the .rego files to change limits.

Example: raise disk threshold to 20GB
{
  "infrastructure": {
    "min_disk_free_gb": 20.0,
    "max_cpu_load": 2.0,
    "min_memory_free_gb": 0.5
  },
  "canary": {
    "max_error_rate_pct": 1.0,
    "max_p99_latency_ms": 500.0
  }
}

## Nginx Access Log Format

Format: $time_iso8601 | $status | ${request_time}s | $upstream_addr | $request
Example: 2026-05-18T19:56:13+00:00 | 200 | 0.000s | 172.18.0.2:3000 | GET / HTTP/1.1

Logs written to: /var/log/nginx/swiftdeploy.log inside the nginx container

## Security

- App container runs as non-root user (UID 1000)
- All Linux capabilities dropped except NET_BIND_SERVICE
- no-new-privileges security option set
- App port never exposed directly, all traffic routes through nginx
- OPA port bound to 127.0.0.1 only, not accessible from public internet
- OPA runs on isolated internal network, not reachable via nginx
- Image size: python:3.12-slim approximately 150MB, under 300MB limit
