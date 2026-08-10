# Configure Azure App Service Environment Variables
# Run this in PowerShell after Azure resources are created

$ErrorActionPreference = "Stop"

Write-Host "=== Configuring Environment Variables ===" -ForegroundColor Cyan

# Get Redis connection details
Write-Host "Getting Redis connection details..." -ForegroundColor Yellow
$redisHost = az redisenterprise show --resource-group tf-neepco-rg --name tf-neepco-redis --query "hostName" -o tsv
$redisKey = az redisenterprise list-keys --resource-group tf-neepco-rg --name tf-neepco-redis --query "primaryKey" -o tsv

# Get ACR credentials
Write-Host "Getting ACR credentials..." -ForegroundColor Yellow
$acrServer = az acr show --resource-group tf-neepco-rg --name tfneepcoacr --query "loginServer" -o tsv
$acrUser = az acr credential show --resource-group tf-neepco-rg --name tfneepcoacr --query "username" -o tsv
$acrPass = az acr credential show --resource-group tf-neepco-rg --name tfneepcoacr --query "passwords[0].value" -o tsv

Write-Host ""
Write-Host "=== Environment Variables ===" -ForegroundColor Cyan
Write-Host "Add these to Azure Portal -> App Services -> tf-neepco-prod -> Settings -> Environment variables" -ForegroundColor Yellow
Write-Host ""

Write-Host "DJANGO_SECRET_KEY=django-insecure-CHANGE-ME-IN-PRODUCTION" -ForegroundColor White
Write-Host "DJANGO_DEBUG=False" -ForegroundColor White
Write-Host "DJANGO_SETTINGS_MODULE=config.settings" -ForegroundColor White
Write-Host "DJANGO_ALLOWED_HOSTS=tf-neepco-prod.azurewebsites.net" -ForegroundColor White
Write-Host "CSRF_TRUSTED_ORIGINS=https://tf-neepco-prod.azurewebsites.net" -ForegroundColor White
Write-Host "DB_NAME=talentflow" -ForegroundColor White
Write-Host "DB_USER=talentflowadmin" -ForegroundColor White
Write-Host "DB_PASSWORD=MyPassword123" -ForegroundColor White
Write-Host "DB_HOST=tf-neepco-db.postgres.database.azure.com" -ForegroundColor White
Write-Host "DB_PORT=5432" -ForegroundColor White
Write-Host "DB_SSLMODE=require" -ForegroundColor White
Write-Host "AZURE_STORAGE_ACCOUNT_NAME=tfneepcostorage" -ForegroundColor White
Write-Host "AZURE_STORAGE_KEY=$storageKey" -ForegroundColor White
Write-Host "AZURE_STORAGE_CONTAINER=resumes" -ForegroundColor White
Write-Host "CELERY_BROKER_URL=rediss://:${redisKey}@${redisHost}:6380/0?ssl_cert_reqs=required" -ForegroundColor White
Write-Host "CELERY_RESULT_BACKEND=rediss://:${redisKey}@${redisHost}:6380/0?ssl_cert_reqs=required" -ForegroundColor White
Write-Host "CELERY_TASK_ALWAYS_EAGER=False" -ForegroundColor White
Write-Host "DJANGO_ENCRYPTION_KEY=your-fernet-key-here" -ForegroundColor White
Write-Host "LLM_PROVIDER=deepseek" -ForegroundColor White
Write-Host "LLM_API_BASE=https://api.deepseek.com/v1" -ForegroundColor White
Write-Host "LLM_API_KEY=your-deepseek-key" -ForegroundColor White
Write-Host "LLM_MODEL=deepseek-chat" -ForegroundColor White
Write-Host "DIGILOCKER_MOCK=True" -ForegroundColor White
Write-Host "AADHAAR_MOCK=True" -ForegroundColor White
Write-Host "NCS_MOCK=True" -ForegroundColor White
Write-Host "NOTIFY_PROVIDER=console" -ForegroundColor White

Write-Host ""
Write-Host "=== ACR Credentials ===" -ForegroundColor Cyan
Write-Host "Server: $acrServer" -ForegroundColor White
Write-Host "Username: $acrUser" -ForegroundColor White
Write-Host "Password: $acrPass" -ForegroundColor White
Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
