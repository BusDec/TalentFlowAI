#!/bin/bash
echo "========================================"
echo "TalentFlowAI Startup Script"
echo "========================================"

echo "[1/4] Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[2/4] Running Django migrations..."
python manage.py migrate_schemas --noinput

echo "[3/4] Collecting static files..."
python manage.py collectstatic --noinput

echo "[4/4] Starting Gunicorn..."
gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120

echo "========================================"
echo "Startup complete"
echo "========================================"
