"""Gunicorn configuration for Azure App Service."""

import multiprocessing
import os

# Bind to the port Azure App Service expects
bind = "0.0.0.0:" + os.getenv("PORT", "8000")

# Workers: 2-4x CPU cores, but cap at 4 for the B1 tier (1 vCPU)
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
worker_class = "gthread"
threads = 2

# Timeout: long enough for resume parsing (OCR can be slow)
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# Security
limit_request_line = 8190
limit_request_fields = 100
