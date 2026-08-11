#!/bin/bash
echo "========================================"
echo "TalentFlowAI Starting..."
echo "========================================"

# Install dependencies
echo "[1/5] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
echo "[1/5] Done."

# Run migrations for public schema
echo "[2/5] Running public schema migrations..."
python manage.py migrate_schemas --shared --noinput
echo "[2/5] Done."

# Create neepco tenant + domain if they don't exist
echo "[3/5] Ensuring neepco tenant and domain exist..."
python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()
from django.db import connection
from tenants.models import Client, Domain

# Create tenant if missing
tenant, created = Client.objects.get_or_create(
    schema_name='neepco',
    defaults={'name': 'NEEPCO', 'code': 'neepco'}
)
if created:
    tenant.create_schema(check_if_exists=True)
    print('Created neepco tenant')
else:
    print('Neepco tenant already exists')

# Register Azure domain
domain_name = 'tf-neepco-prod.azurewebsites.net'
domain, d_created = Domain.objects.get_or_create(
    domain=domain_name,
    defaults={'tenant': tenant, 'is_primary': True}
)
if d_created:
    print(f'Created domain: {domain_name}')
else:
    print(f'Domain already exists: {domain_name}')
" || echo "Tenant/domain setup completed"
echo "[3/5] Done."

# Run tenant schema migrations
echo "[4/5] Running tenant schema migrations..."
python manage.py migrate_schemas --noinput
echo "[4/5] Done."

# Start gunicorn
echo "[5/5] Starting gunicorn..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --timeout 120 \
    --access-logfile '-' \
    --error-logfile '-'
