#!/bin/bash
set -e

echo "========================================"
echo "TalentFlowAI Starting..."
echo "========================================"

# Install dependencies
echo "[1/3] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Run migrations
echo "[2/3] Running migrations..."
python manage.py migrate_schemas --noinput

# Start gunicorn
echo "[3/3] Starting gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --timeout 120 \
    --access-logfile '-' \
    --error-logfile '-'
