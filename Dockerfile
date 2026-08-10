# Multi-stage build for Azure App Service (Linux)
FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (Tesseract for OCR, libpq for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-hin \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Collect static files (Azure Storage in prod, WhiteNoise fallback)
RUN python manage.py collectstatic --noinput 2>/dev/null || true

# Default port for Azure App Service
EXPOSE 8000

# Entrypoint: gunicorn for web, celery for worker
CMD ["gunicorn", "config.wsgi:application", "--config", "gunicorn.conf.py"]
