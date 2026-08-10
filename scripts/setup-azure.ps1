# Azure Setup Script for TalentFlowAI
# Run this in PowerShell as Administrator

$ErrorActionPreference = "Continue"

Write-Host "=== TalentFlowAI Azure Setup ===" -ForegroundColor Cyan
Write-Host ""

# Step 5: Storage Account
Write-Host "[5/10] Creating Storage Account..." -ForegroundColor Yellow
$null = az storage account show --resource-group tf-neepco-rg --name tfneepcostorage 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Storage Account already exists (skipping)" -ForegroundColor Green
} else {
    az storage account create --resource-group tf-neepco-rg --name tfneepcostorage --location eastus --sku Standard_LRS --kind StorageV2 --output none 2>&1 | Out-Null
    Write-Host "  Storage Account created" -ForegroundColor Green
}

# Step 6: Storage Container
Write-Host "[6/10] Creating Storage Container..." -ForegroundColor Yellow
az storage container create --account-name tfneepcostorage --name resumes --public-access blob --auth-mode login --output none 2>&1 | Out-Null
Write-Host "  Storage Container created" -ForegroundColor Green

# Step 7: Get Storage Key
Write-Host "[7/10] Getting Storage Account Key..." -ForegroundColor Yellow
$storageKey = az storage account keys list --resource-group tf-neepco-rg --account-name tfneepcostorage --query "[0].value" -o tsv 2>&1
Write-Host "  Storage Key: $storageKey" -ForegroundColor Green

# Step 8: Container Registry
Write-Host "[8/10] Creating Container Registry..." -ForegroundColor Yellow
$null = az acr show --resource-group tf-neepco-rg --name tfneepcoacr 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Container Registry already exists (skipping)" -ForegroundColor Green
} else {
    az acr create --resource-group tf-neepco-rg --name tfneepcoacr --sku Basic --admin-enabled true --output none 2>&1 | Out-Null
    Write-Host "  Container Registry created" -ForegroundColor Green
}

# Step 9: App Service Plan
Write-Host "[9/10] Creating App Service Plan..." -ForegroundColor Yellow
az appservice plan create --resource-group tf-neepco-rg --name tf-neepco-plan --sku B1 --is-linux --location eastus --output none 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  App Service Plan created" -ForegroundColor Green
} else {
    Write-Host "  App Service Plan may already exist or failed - check Azure Portal" -ForegroundColor Yellow
}

# Step 10: Django Web App
Write-Host "[10/10] Creating Django Web App..." -ForegroundColor Yellow
az webapp create --resource-group tf-neepco-rg --plan tf-neepco-plan --name tf-neepco-prod --deployment-container-image-name tfneepcoacr.azurecr.io/talentflow:latest --output none 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Django Web App created" -ForegroundColor Green
} else {
    Write-Host "  Django Web App may already exist or failed - check Azure Portal" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Azure Resources Setup Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Verify in Azure Portal: https://portal.azure.com" -ForegroundColor Yellow
Write-Host "Resource Group: tf-neepco-rg" -ForegroundColor White
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Run: .\scripts\configure-env.ps1" -ForegroundColor White
Write-Host "  2. Build Docker image: az acr build --registry tfneepcoacr --image talentflow:latest ." -ForegroundColor White
Write-Host "  3. Configure environment variables in Azure Portal" -ForegroundColor White
Write-Host ""
Write-Host "Storage Key (save this): $storageKey" -ForegroundColor Cyan
