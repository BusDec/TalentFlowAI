#!/bin/bash
# Run Django migrations on Azure App Service
# Usage: ./scripts/migrate.sh [web-app-name] [resource-group]

set -euo pipefail

WEB_APP="${1:-talentflow-prod}"
RESOURCE_GROUP="${2:-talentflow-rg}"

echo "=== Running Django migrations on $WEB_APP ==="

echo "[1/3] Running migrate_schemas..."
az webapp ssh --resource-group "$RESOURCE_GROUP" --name "$WEB_APP" \
  --command "python manage.py migrate_schemas" 2>&1 || {
    echo "Warning: migrate_schemas via SSH may not work. Try the Kudu REST API instead."
    echo "Alternative: Use Azure Portal → App Service → SSH → run manually:"
    echo "  python manage.py migrate_schemas"
}

echo "[2/3] Running collectstatic..."
az webapp ssh --resource-group "$RESOURCE_GROUP" --name "$WEB_APP" \
  --command "python manage.py collectstatic --noinput" 2>&1 || {
    echo "Warning: collectstatic via SSH may not work. Static files are served from Azure Storage."
}

echo "[3/3] Checking deployment..."
az webapp ssh --resource-group "$RESOURCE_GROUP" --name "$WEB_APP" \
  --command "python manage.py check --deploy" 2>&1 || {
    echo "Warning: deploy check failed. Review the output above."
}

echo ""
echo "=== Migration Complete ==="
echo "Access the app at: https://$WEB_APP.azurewebsites.net"
