FROM python:3.12-slim AS base

RUN groupadd -g 1000 appuser && \
    useradd  -u 1000 -g appuser -s /bin/sh -m appuser

WORKDIR /app

COPY app/main.py .

RUN chown -R appuser:appuser /app

USER appuser

ENV MODE=stable \
    APP_VERSION=1.0.0 \
    APP_PORT=3000

EXPOSE 3000

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/healthz')"

CMD ["python3", "main.py"]
