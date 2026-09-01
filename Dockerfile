# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --no-create-home app

RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# BuildKit cache mount: pip's download cache persists across builds in
# BuildKit's own cache store (not baked into an image layer), so when
# requirements change only genuinely new packages hit the network. Note the
# absence of --no-cache-dir — we WANT pip to populate the mounted cache.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY app/ ./app/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=$GIT_COMMIT

ENTRYPOINT ["./entrypoint.sh"]
