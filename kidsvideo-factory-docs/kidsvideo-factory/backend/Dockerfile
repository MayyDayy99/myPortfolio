# "Már ezt is tudom" video factory — backend image.
# ComfyUI is NEVER in this image (ADR-2): it runs natively on the macOS host
# and is reached at host.docker.internal:8188.
FROM python:3.12-slim

# ffmpeg + ffprobe are required by the render/audio pipeline.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data

WORKDIR /srv

# Install Python deps first for layer caching.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY app ./app

# Built frontend (optional). The CI/build step stages the Vite output into the
# backend context as ./frontend_dist before building; main.py serves it from
# app/static when present. We glob together with requirements.txt (always
# present) so the COPY never fails when frontend_dist is absent; the stray
# requirements.txt copy is harmless and ignored by the static mount.
COPY requirements.txt frontend_dist[/]* ./app/static/

VOLUME ["/data"]
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
