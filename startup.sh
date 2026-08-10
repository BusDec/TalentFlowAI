#!/bin/bash

echo "========================================"
echo "TalentFlowAI Starting..."
echo "========================================"

# Install dependencies
echo "[1/4] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "Dependencies installed."

# Run migrations
echo "[2/4] Running migrations..."
python manage.py migrate_schemas --noinput
echo "Migrations complete."

# Register Azure domain for neepco tenant
echo "[3/4] Registering Azure domain..."
python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from tenants.models import Client, Domain
try:
    tenant = Client.objects.get(schema_name='neepco')
except Client.DoesNotExist:
    print('ERROR: neepco tenant not found')
    exit(1)
domain_name = os.environ.get('DJANGO_ALLOWED_HOSTS', 'tf-neepco-prod.azurewebsites.net')
for host in domain_name.split(','):
    host = host.strip()
    if host and not Domain.objects.filter(domain=host).exists():
        Domain.objects.create(domain=host, tenant=tenant, is_primary=False)
        print(f'Added domain: {host}')
print('Domain setup complete')
" || echo "Domain registration failed (may already exist)"

# Start gunicorn
echo "[4/4] Starting gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --timeout 120 \
    --access-logfile '-' \
    --error-logfile '-'
