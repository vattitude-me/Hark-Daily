FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    MODEL_DIR=/models \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY web ./web

# Bake the Kokoro voice model (~350 MB) into the image so the first briefing is instant.
# Build with --build-arg BAKE_MODEL=0 to download it on first use instead.
ARG BAKE_MODEL=1
RUN if [ "$BAKE_MODEL" = "1" ]; then python -m app setup; fi

VOLUME ["/data"]
EXPOSE 8000
CMD ["python", "-m", "app", "serve"]
