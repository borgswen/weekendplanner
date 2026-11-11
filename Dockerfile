FROM node:22-bookworm-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

# Claude Code (CLI). Updaten = image opnieuw bouwen: docker compose build --pull
RUN npm install -g @anthropic-ai/claude-code

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /venv && /venv/bin/pip install --no-cache-dir -r requirements.txt
COPY planner ./planner
COPY config.yaml ./config.yaml

ENV TZ=Europe/Amsterdam \
    HOME=/data/home \
    PATH=/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    DISABLE_AUTOUPDATER=1 \
    PLANNER_CONFIG=/app/config.yaml \
    PLANNER_DATA=/data

VOLUME /data
EXPOSE 8088
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8088/health')" || exit 1
CMD ["python", "-m", "planner", "serve"]
