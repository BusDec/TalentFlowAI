#!/bin/bash
# Azure deployment script for TalentFlowAI
# Usage: ./scripts/deploy.sh [resource-group] [location]
#
# Prerequisites:
#   - Azure CLI installed and logged in (az login)
#   - Docker installed (for building images)
#   - .env.production filled in with real values

set -euo pipefail

RESOURCE_GROUP="${1:-talentflow-rg}"
LOCATION="${2:-centralindia}"
ACR_NAME="talentflowacr"
APP_SERVICE_PLAN="talentflow-plan"
WEB_APP="talentflow-prod"
CELERY_APP="talentflow-celery"
DB_SERVER="talentflow-prod-db"
DB_NAME="talentflow"
DB_ADMIN="talentflowadmin"
REDIS_NAME="talentflow-prod-redis"
STORAGE_ACCOUNT="talentflowprod"
CONTAINER_NAME="resumes"

echo "=== TalentFlowAI Azure Deployment ==="
echo "Resource Group: $RESOURCE_GROUP"
echo "Location: $LOCATION"
echo ""

# 1. Resource Group
echo "[1/8] Creating resource group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

# 2. Azure Container Registry
echo "[2/8] Creating Azure Container Registry..."
az acr create --resource-group "$RESOURCE_GROUP" \
  --name "$ACR_NAME" --sku Basic --admin-enabled true --output none

# 3. PostgreSQL Flexible Server
echo "[3/8] Creating PostgreSQL Flexible Server..."
az postgres flexible-server create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$DB_SERVER" \
  --admin-user "$DB_ADMIN" \
  --admin-password "$(read -sp 'DB Password: ' pwd && echo "$pwd")" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --public-access 0.0.0.0 \
  --storage-size 32 \
  --version 16 \
  --output none

az postgres flexible-server db create \
  --resource-group "$RESOURCE_GROUP" \
  --server-name "$DB_SERVER" \
  --database-name "$DB_NAME" \
  --output none

# 4. Azure Cache for Redis
echo "[4/8] Creating Azure Cache for Redis..."
az redis create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$REDIS_NAME" \
  --location "$LOCATION" \
  --sku Basic \
  --vm-size C0 \
  --output none

# 5. Storage Account + Blob Container
echo "[5/8] Creating Storage Account..."
az storage account create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$STORAGE_ACCOUNT" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --output none

az storage container create \
  --account-name "$STORAGE_ACCOUNT" \
  --name "$CONTAINER_NAME" \
  --public-access blob \
  --output none

# 6. App Service Plan (Linux)
echo "[6/8] Creating App Service Plan..."
az appservice plan create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$APP_SERVICE_PLAN" \
  --sku B1 \
  --is-linux \
  --output none

# 7. Web App
echo "[7/8] Creating Web App..."
az webapp create \
  --resource-group "$RESOURCE_GROUP" \
  --plan "$APP_SERVICE_PLAN" \
  --name "$WEB_APP" \
  --deployment-container-image-name "$ACR_NAME.azurecr.io/talentflow:latest" \
  --output none

az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEB_APP" \
  --settings \
    WEBSITES_PORT=8000 \
    SCM_DO_BUILD_DURING_DEPLOYMENT=false \
    DJANGO_SETTINGS_MODULE=config.settings \
  --output none

# 8. Celery Worker App
echo "[8/8] Creating Celery Worker App..."
az webapp create \
  --resource-group "$RESOURCE_GROUP" \
  --plan "$APP_SERVICE_PLAN" \
  --name "$CELERY_APP" \
  --deployment-container-image-name "$ACR_NAME.azurecr.io/talentflow:latest" \
  --output none

az webapp config appsettings set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CELERY_APP" \
  --settings \
    WEBSITES_PORT=8000 \
    SCM_DO_BUILD_DURING_DEPLOYMENT=false \
    DJANGO_SETTINGS_MODULE=config.settings \
  --output none

# Override the CMD for Celery worker
az webapp config container set \
  --resource-group "$RESOURCE_GROUP" \
  --name "$CELERY_APP" \
  --docker-custom-image-name "$ACR_NAME.azurecr.io/talentflow:latest" \
  --output none

echo ""
echo "=== Deployment Complete ==="
echo ""
echo "Next steps:"
echo "  1. Build and push Docker image:"
echo "     az acr build --registry $ACR_NAME --image talentflow:latest ."
echo ""
echo "  2. Configure environment variables:"
echo "     Copy .env.production to .env and fill in real values."
echo "     Then run: ./scripts/configure-env.sh"
echo ""
echo "  3. Run migrations:"
echo "     ./scripts/migrate.sh"
echo ""
echo "  4. Seed data:"
echo "     az webapp ssh --resource-group $RESOURCE_GROUP --name $WEB_APP"
echo "     python manage.py populate_neepco_real"
echo ""
echo "  5. Access the app:"
echo "     https://$WEB_APP.azurewebsites.net"
