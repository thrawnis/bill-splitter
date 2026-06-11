FROM python:3.12-slim

WORKDIR /app

RUN groupadd --system app && useradd --system --gid app --no-create-home app

RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=$GIT_COMMIT

ENTRYPOINT ["./entrypoint.sh"]
