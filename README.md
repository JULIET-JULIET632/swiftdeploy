# SwiftDeploy

> Build the tool that builds the stack.

SwiftDeploy is a declarative deployment system. You describe your stack in `manifest.yaml`, and the CLI generates all configs, manages the container lifecycle, and keeps your stack running.

## Project Structure

swiftdeploy/
├── manifest.yaml
├── swiftdeploy
├── Dockerfile
├── app/
│   └── main.py
└── templates/
    ├── nginx.conf.tmpl
    ├── log_format.conf.tmpl
    └── docker-compose.yml.tmpl

Generated at runtime (do not commit): nginx.conf, log_format.conf, docker-compose.yml

## Prerequisites

- Docker Engine 24+
- Docker Compose v2
- Python 3.10+
- pip install pyyaml

## Quick Start

Step 1: Build the app image
docker build -t swift-deploy-1-node:latest .

Step 2: Generate configs
./swiftdeploy init

Step 3: Validate everything
./swiftdeploy validate

Step 4: Deploy
./swiftdeploy deploy

Your service is now running at http://localhost:8080

## Subcommand Reference

init - Parses manifest.yaml and generates nginx.conf, log_format.conf and docker-compose.yml from templates.
./swiftdeploy init

validate - Runs 5 pre-flight checks. Exits non-zero if any fail.
./swiftdeploy validate
Check 1: manifest.yaml exists and is valid YAML
Check 2: All required fields are present and non-empty
Check 3: Docker image referenced in manifest exists locally
Check 4: Nginx port is not already bound on the host
Check 5: Generated nginx.conf is syntactically valid

deploy - Runs init, brings up the stack, and blocks until health checks pass or 60s timeout.
./swiftdeploy deploy

promote - Switches deployment mode with a rolling restart of the app container only.
./swiftdeploy promote canary
./swiftdeploy promote stable

teardown - Stops and removes all containers, networks, and volumes.
./swiftdeploy teardown
./swiftdeploy teardown --clean

## API Endpoints

GET /       - Welcome message with mode, version, timestamp
GET /healthz  - Status and process uptime in seconds
POST /chaos   - Simulate degraded behaviour (canary mode only)

Chaos modes (canary only):

Slow - sleep N seconds before each response
curl -X POST http://localhost:8080/chaos -H 'Content-Type: application/json' -d '{"mode": "slow", "duration": 3}'

Error - return 500 on ~50% of requests
curl -X POST http://localhost:8080/chaos -H 'Content-Type: application/json' -d '{"mode": "error", "rate": 0.5}'

Recover - cancel active chaos
curl -X POST http://localhost:8080/chaos -H 'Content-Type: application/json' -d '{"mode": "recover"}'

## Nginx Access Log Format

Format: $time_iso8601 | $status | ${request_time}s | $upstream_addr | $request
Example: 2026-05-13T23:56:13+00:00 | 200 | 0.000s | 172.18.0.2:3000 | GET / HTTP/1.1

## Security

- Containers run as non-root users (UID 1000 for app)
- All Linux capabilities dropped except NET_BIND_SERVICE
- no-new-privileges security option set
- App port never exposed directly, all traffic routes through Nginx
- Image size: python:3.12-slim approximately 150MB, under 300MB limit
