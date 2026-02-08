FROM node:22-bookworm-slim

ARG CODEX_VERSION=0.92.0
ARG USE_CN_MIRROR=1
ARG APT_MIRROR=http://mirrors.aliyun.com
ARG NPM_REGISTRY=https://registry.npmmirror.com

RUN if [ "${USE_CN_MIRROR}" = "1" ] && [ -n "${APT_MIRROR}" ]; then \
      if [ -f /etc/apt/sources.list ]; then \
        sed -i -E "s|https?://deb.debian.org|${APT_MIRROR}|g; s|https?://security.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list; \
      fi; \
      if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
        sed -i -E "s|https?://deb.debian.org|${APT_MIRROR}|g; s|https?://security.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
      fi; \
    fi \
  && apt-get update -y \
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

RUN if [ "${USE_CN_MIRROR}" = "1" ] && [ -n "${NPM_REGISTRY}" ]; then \
      npm config set registry "${NPM_REGISTRY}"; \
    fi \
  && npm install -g "@openai/codex@${CODEX_VERSION}" \
  && codex --version

RUN useradd -m -u 10001 -s /bin/bash runner

WORKDIR /app
COPY app/ /app/
COPY schemas/ /app/schemas/

RUN chmod +x /app/run.sh

ENV CODEX_HOME=/codex_home
RUN mkdir -p /codex_home && chmod 0777 /codex_home

ENTRYPOINT ["/app/run.sh"]
