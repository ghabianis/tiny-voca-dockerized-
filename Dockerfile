FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TINY_VOCA_FRONTEND=own \
    DIZIONE_DATA=/app/weights/phonemizer \
    TINY_VOCA_WEB_DIR=/app/web/server-ui

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY tiny-voca/pyproject.toml tiny-voca/README.md ./
COPY tiny-voca/src ./src
COPY tiny-voca/weights/tiny-voca.pt ./weights/tiny-voca.pt
COPY tiny-voca/weights/phonemizer ./weights/phonemizer
COPY tiny-voca/web/server-ui ./web/server-ui

RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu "torch>=2.4,<3" \
    && pip install --no-cache-dir ".[own]"

EXPOSE 8000

CMD ["python", "-m", "tiny_voca.server", "--checkpoint", "/app/weights/tiny-voca.pt", "--host", "0.0.0.0", "--port", "8000"]