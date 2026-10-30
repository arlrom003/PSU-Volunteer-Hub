FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production \
    PRIVATE_UPLOAD_FOLDER=/data/private
WORKDIR /app

# mysqlclient is already part of the project's pinned dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Explicit allowlist: no dumps, local uploads, .env, Git history or QA artifacts.
COPY app ./app
COPY templates ./templates
COPY static ./static
COPY migrations ./migrations
COPY config.py wsgi.py ./
RUN ln -s /data/public /app/static/uploads

# Railway mounts /data at runtime. No schema setup or seeding in startup/build.
CMD ["sh", "-c", "mkdir -p /data/public /data/private && exec gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 1 --timeout 120 wsgi:app"]
