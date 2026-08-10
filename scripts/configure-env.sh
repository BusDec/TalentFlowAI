#!/bin/bash
# Configure Azure App Service environment variables from .env file
# Usage: ./scripts/configure-env.sh [web-app-name] [resource-group]

set -euo pipefail

WEB_APP="${1:-tf-neepco-prod}"
RESOURCE_GROUP="${2:-tf-neepco-rg}"
ENV_FILE="${3:-.env}"

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found. Copy .env.production to .env first."
    exit 1
fi

echo "=== Configuring environment variables for $WEB_APP ==="

# Read .env file and convert to Azure App Service settings format
SETTINGS=""
while IFS= read -r line; do
    # Skip comments and empty lines
    [[ "$line" =~ ^#.*$ ]] && continue
    [[ -z "$line" ]] && continue
    # Remove inline comments
    line="${line%%#*}"
    # Trim whitespace
    line=$(echo "$line" | xargs)
    SETTINGS="$SETTINGS $line"
done < "$ENV_FILE"

echo "Setting $(echo "$SETTINGS" | wc -w) environment variables..."

az webapp config appsettings set \
    --resource-group "$RESOURCE_GROUP" \
    --name "$WEB_APP" \
    --settings $SETTINGS \
    --output none

echo "Environment variables configured successfully."
echo ""
echo "Restart the app to apply changes:"
echo "  az webapp restart --resource-group $RESOURCE_GROUP --name $WEB_APP"
