FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai \
    APP_TIMEZONE=Asia/Shanghai \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       curl ca-certificates tzdata build-essential libpq-dev bash \
    && rm -rf /var/lib/apt/lists/*

RUN ARCH="$(dpkg --print-architecture)" \
    && case "$ARCH" in \
         arm64) SUPERCRONIC_ARCH="linux-arm64" ;; \
         amd64) SUPERCRONIC_ARCH="linux-amd64" ;; \
         *) echo "Unsupported arch: $ARCH" && exit 1 ;; \
       esac \
    && curl -fsSL -o /usr/local/bin/supercronic \
       "https://github.com/aptible/supercronic/releases/download/v0.2.29/supercronic-${SUPERCRONIC_ARCH}" \
    && chmod +x /usr/local/bin/supercronic

COPY pyproject.toml /app/pyproject.toml
COPY README.md /app/README.md
COPY src /app/src
COPY alembic.ini /app/alembic.ini
COPY alembic /app/alembic
COPY scripts /app/scripts
COPY deploy /app/deploy
COPY sql /app/sql
COPY docs /app/docs

ARG PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn

ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST} \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir backtrader \
    && pip install --no-cache-dir .

RUN chmod +x /app/scripts/run_daily_runtime.sh \
    && chmod +x /app/scripts/sync_strategy_release.py

CMD ["/bin/bash", "-lc", "sleep infinity"]