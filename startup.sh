#!/bin/bash
set -e

export DJANGO_SETTINGS_MODULE=config.settings

echo "========================================"
echo "TalentFlowAI Starting..."
echo "========================================"
echo "Working directory: $(pwd)"
echo "Python: $(python --version 2>&1)"
echo "PORT: ${PORT:-8000}"

# Install dependencies
echo ""
echo "[1/6] Installing dependencies..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo "[1/6] Done."

# Run shared (public-schema) migrations
echo ""
echo "[2/6] Running shared migrations..."
python manage.py migrate_schemas --shared --noinput
echo "[2/6] Done."

# Create neepco tenant + domain if they don't exist
echo ""
echo "[3/6] Ensuring neepco tenant and domain exist..."
python -c "
import os, django, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.db import connection
from django_tenants.utils import schema_context, get_public_schema_name
from tenants.models import Client, Domain

# Ensure we're in the public schema
connection.set_schema_to_public()

# Create tenant if missing
tenant, created = Client.objects.get_or_create(
    schema_name='neepco',
    defaults={'name': 'NEEPCO', 'code': 'neepco'}
)
if created:
    tenant.create_schema(check_if_exists=True)
    print(f'  Created neepco tenant (id={tenant.pk})')
else:
    print(f'  Neepco tenant already exists (id={tenant.pk})')

# Register Azure domain
domain_name = os.environ.get('AZURE_DOMAIN', 'tf-neepco-prod.azurewebsites.net')
domain, d_created = Domain.objects.get_or_create(
    domain=domain_name,
    defaults={'tenant': tenant, 'is_primary': True}
)
if d_created:
    print(f'  Created domain: {domain_name}')
else:
    print(f'  Domain already exists: {domain_name}')

# Verify domain is linked to tenant
assert domain.tenant_id == tenant.pk, 'Domain tenant mismatch!'
print('  Domain verified OK')
"
echo "[3/6] Done."

# Run all tenant schema migrations
echo ""
echo "[4/6] Running tenant migrations..."
python manage.py migrate_schemas --noinput
echo "[4/6] Done."

# Collect static files
echo ""
echo "[5/6] Collecting static files..."
python manage.py collectstatic --noinput 2>/dev/null || echo "  collectstatic skipped (no static files)"
echo "[5/6] Done."

# Start gunicorn
echo ""
echo "[6/6] Starting gunicorn on port ${PORT:-8000}..."
exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8000} \
    --workers 2 \
    --threads 2 \
    --timeout 120 \
    --graceful-timeout 30 \
    --access-logfile '-' \
    --error-logfile '-' \
    --log-level info
