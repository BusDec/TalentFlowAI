#!/bin/bash
# TalentFlowAI — Azure App Service startup script.
# Runs on every container start. Must be idempotent.

export DJANGO_SETTINGS_MODULE=config.settings

echo "========================================"
echo "TalentFlowAI Starting..."
echo "========================================"
echo "  Working directory: $(pwd)"
echo "  Python:            $(python --version 2>&1)"
echo "  PORT:              ${PORT:-8000}"
echo ""

# ── 1. Install dependencies (skip if Django already importable) ───────────────
echo "[1/7] Checking dependencies..."
if python -c "import django" 2>/dev/null; then
    echo "  Django already installed — skipping pip install."
else
    echo "  Installing dependencies..."
    pip install --upgrade pip --quiet 2>&1 | tail -1
    pip install -r requirements.txt --quiet 2>&1 | tail -5
    if [ $? -ne 0 ]; then
        echo "  WARNING: pip install had errors."
    fi
fi
echo "[1/7] Done."
echo ""

# ── 2. Shared (public-schema) migrations ─────────────────────────────────────
echo "[2/7] Running shared migrations..."
python manage.py migrate_schemas --shared --noinput 2>&1 | tail -5
echo "[2/7] Done."
echo ""

# ── 3. Create neepco tenant + domain + OrgProfile ────────────────────────────
echo "[3/7] Ensuring neepco tenant and domain..."
python manage.py setup_tenant 2>&1
echo "[3/7] Done."
echo ""

# ── 4. Tenant schema migrations ──────────────────────────────────────────────
echo "[4/7] Running tenant migrations..."
python manage.py migrate_schemas --noinput 2>&1 | tail -5
echo "[4/7] Done."
echo ""

# ── 5. Seed staff users ──────────────────────────────────────────────────────
echo "[5/7] Seeding staff users..."
python manage.py seed_staff_users 2>&1
echo "[5/7] Done."
echo ""

# ── 6. Seed cloud test data ──────────────────────────────────────────────────
echo "[6/7] Seeding test data..."
python manage.py seed_cloud_data 2>&1
echo "[6/7] Done."
echo ""

# ── 7. Collect static files ──────────────────────────────────────────────────
echo "[7/7] Collecting static files..."
python manage.py collectstatic --noinput 2>/dev/null
echo "[7/7] Done."
echo ""

# ── Start gunicorn ────────────────────────────────────────────────────────────
echo "========================================"
echo "Starting gunicorn on port ${PORT:-8000}..."
echo "========================================"
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --threads 2 \
    --timeout 120 \
    --graceful-timeout 30 \
    --access-logfile '-' \
    --error-logfile '-' \
    --log-level info
