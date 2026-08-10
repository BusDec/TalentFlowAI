#!/bin/bash
echo "========================================"
echo "TalentFlowAI Starting..."
echo "========================================"

# Install dependencies
echo "[1/4] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "[1/4] Done."

# Run migrations
echo "[2/4] Running migrations..."
python manage.py migrate_schemas --noinput
echo "[2/4] Done."

# Register Azure domain for neepco tenant
echo "[3/4] Registering Azure domain..."
python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.db import connection
cur = connection.cursor()
# Check if domain exists
cur.execute(\"SELECT id FROM public.tenant_domain WHERE domain='tf-neepco-prod.azurewebsites.net'\")
if cur.fetchone():
    print('Domain already registered')
else:
    # Get neepco tenant id
    cur.execute(\"SELECT id FROM public.tenant_client WHERE schema_name='neepco'\")
    row = cur.fetchone()
    if row:
        cur.execute(\"INSERT INTO public.tenant_domain (domain, tenant_id, is_primary) VALUES ('tf-neepco-prod.azurewebsites.net', %s, false)\", [row[0]])
        connection.commit()
        print('Domain registered successfully')
    else:
        print('ERROR: neepco tenant not found')
" || echo "Domain registration completed (may have failed)"
echo "[3/4] Done."

# Start gunicorn
echo "[4/4] Starting gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --timeout 120 \
    --access-logfile '-' \
    --error-logfile '-'
