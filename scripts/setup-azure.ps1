# Azure Setup Script for TalentFlowAI
# Run this in PowerShell as Administrator

$ErrorActionPreference = "Stop"

Write-Host "=== TalentFlowAI Azure Setup ===" -ForegroundColor Cyan
Write-Host ""

# Step 5: Storage Account
Write-Host "[5/10] Creating Storage Account..." -ForegroundColor Yellow
az storage account create --resource-group tf-neepco-rg --name tfneepcostorage --location eastus --sku Standard_LRS --kind StorageV2 --output none
if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: Storage Account" -ForegroundColor Red; exit 1 }
Write-Host "  Storage Account created" -ForegroundColor Green

# Step 6: Storage Container
Write-Host "[6/10] Creating Storage Container..." -ForegroundColor Yellow
az storage container create --account-name tfneepcostorage --name resumes --public-access blob --auth-mode login --output none
if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: Storage Container" -ForegroundColor Red; exit 1 }
Write-Host "  Storage Container created" -ForegroundColor Green

# Step 7: Get Storage Key
Write-Host "[7/10] Getting Storage Account Key..." -ForegroundColor Yellow
$storageKey = az storage account keys list --resource-group tf-neepco-rg --account-name tfneepcostorage --query "[0].value" -o tsv
Write-Host "  Storage Key: $storageKey" -ForegroundColor Green

# Step 8: Container Registry
Write-Host "[8/10] Creating Container Registry..." -ForegroundColor Yellow
az acr create --resource-group tf-neepco-rg --name tfneepcoacr --sku Basic --admin-enabled true --output none
if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: Container Registry" -ForegroundColor Red; exit 1 }
Write-Host "  Container Registry created" -ForegroundColor Green

# Step 9: App Service Plan
Write-Host "[9/10] Creating App Service Plan..." -ForegroundColor Yellow
az appservice plan create --resource-group tf-neepco-rg --name tf-neepco-plan --sku B1 --is-linux --location eastus --output none
if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: App Service Plan" -ForegroundColor Red; exit 1 }
Write-Host "  App Service Plan created" -ForegroundColor Green

# Step 10: Django Web App
Write-Host "[10/10] Creating Django Web App..." -ForegroundColor Yellow
az webapp create --resource-group tf-neepco-rg --plan tf-neepco-plan --name tf-neepco-prod --deployment-container-image-name tfneepcoacr.azurecr.io/talentflow:latest --output none
if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: Django Web App" -ForegroundColor Red; exit 1 }
Write-Host "  Django Web App created" -ForegroundColor Green

Write-Host ""
Write-Host "=== All Azure Resources Created ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Build Docker image: az acr build --registry tfneepcoacr --image talentflow:latest ." -ForegroundColor White
Write-Host "  2. Configure environment variables (see .env.production)" -ForegroundColor White
Write-Host "  3. Run migrations" -ForegroundColor White
Write-Host ""
Write-Host "Storage Key (save this): $storageKey" -ForegroundColor Cyan
