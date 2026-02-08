FROM node:22-bookworm-slim

ARG CODEX_VERSION=0.92.0

RUN apt-get update -y \
  && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    g++ \
    make \
    python3 \
    python3-venv \
    python3-pip \
    time \
  && rm -rf /var/lib/apt/lists/*

RUN npm install -g "@openai/codex@${CODEX_VERSION}" \
  && codex --version

RUN useradd -m -u 10001 -s /bin/bash runner

WORKDIR /app
COPY app/ /app/
COPY schemas/ /app/schemas/

RUN chmod +x /app/run.sh

ENV CODEX_HOME=/codex_home
RUN mkdir -p /codex_home && chmod 0777 /codex_home

ENTRYPOINT ["/app/run.sh"]
