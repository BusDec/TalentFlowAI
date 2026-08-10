# TalentFlowAI — Azure Deployment Guide

**Complete step-by-step guide to deploy TalentFlowAI on Azure App Service.**

---

## Part 1: Create Azure Account

### Step 1: Sign up for Azure
1. Go to [portal.azure.com](https://portal.azure.com)
2. Click **"Start free"** or **"Create a free account"**
3. Use your Microsoft account (or create one)
4. Enter payment details (required, but you get $200 free credit for 30 days)
5. Complete verification (phone + credit card)

### Step 2: Install Azure CLI
**Windows (PowerShell):**
```powershell
winget install Microsoft.AzureCLI
```

**Or download from:** https://learn.microsoft.com/en-us/cli/azure/install-azure-cli

**Verify installation:**
```bash
az --version
```

### Step 3: Login to Azure
```bash
az login
```
This opens your browser — sign in with your Azure account.

---

## Part 2: Create Resource Group

A resource group is a container for all your Azure resources.

```bash
az group create \
  --name tf-neepco-rg \
  --location centralindia
```

**Location options:**
- `centralindia` — India (recommended for NEEPCO)
- `eastus` — US East (cheapest)
- `westeurope` — Europe
- `southeastasia` — Singapore

---

## Part 3: Create Azure Database for PostgreSQL

### Step 1: Create PostgreSQL Flexible Server

```bash
az postgres flexible-server create \
  --resource-group tf-neepco-rg \
  --name tf-neepco-db \
  --admin-user talentflowadmin \
  --admin-password "YourStrongPassword123!" \
  --sku-name Standard_B1ms \
  --tier Burstable \
  --public-access 0.0.0.0 \
  --storage-size 32 \
  --version 16
```

**Settings explained:**
| Setting | Value | Why |
|---|---|---|
| `sku-name` | `Standard_B1ms` | 1 vCPU, 2 GB RAM — enough for dev/staging |
| `tier` | `Burstable` | Cheapest tier, scales down when idle |
| `public-access` | `0.0.0.0` | Allows connections from anywhere (lock down later) |
| `storage-size` | `32` GB | Minimum, auto-grows |
| `version` | `16` | Matches your local PostgreSQL |

### Step 2: Create Database

```bash
az postgres flexible-server db create \
  --resource-group tf-neepco-rg \
  --server-name tf-neepco-db \
  --name talentflow
```

### Step 3: Note Connection Details

```bash
az postgres flexible-server show \
  --resource-group tf-neepco-rg \
  --name tf-neepco-db \
  --query "fullyQualifiedDomainName" -o tsv
```

**Save these values:**
```
DB_HOST=tf-neepco-db.postgres.database.azure.com
DB_USER=talentflowadmin
DB_PASSWORD=YourStrongPassword123!
DB_NAME=talentflow
DB_PORT=5432
DB_SSLMODE=require
```

---

## Part 4: Create Azure Cache for Redis

### Step 1: Use PostgreSQL as Celery Broker (No Redis Required)

Azure Cache for Redis is retiring in Central India. Use PostgreSQL as the Celery broker instead:

```bash
# No additional Azure resources needed — uses your existing PostgreSQL server
# The connection string will be configured in the environment variables later
```

**Settings explained:**
| Setting | Value | Why |
|---|---|---|
| Broker | PostgreSQL | No Redis required, uses existing database |
| Backend | PostgreSQL | Stores task results in the same database |

### Step 2: Get PostgreSQL Connection String for Celery

Your PostgreSQL server is already created. Use this connection string format:

```
db+postgresql://talentflowadmin:MyPassword123@tf-neepco-db.postgres.database.azure.com:5432/talentflow
```

**Update your .env file:**
```
CELERY_BROKER_URL=db+postgresql://talentflowadmin:MyPassword123@tf-neepco-db.postgres.database.azure.com:5432/talentflow
CELERY_RESULT_BACKEND=db+postgresql://talentflowadmin:MyPassword123@tf-neepco-db.postgres.database.azure.com:5432/talentflow
```

---

## Part 5: Create Azure Blob Storage

### Step 1: Create Storage Account

```bash
az storage account create \
  --resource-group tf-neepco-rg \
  --name tfneepcostorage \
  --location centralindia \
  --sku Standard_LRS \
  --kind StorageV2
```

**Settings explained:**
| Setting | Value | Why |
|---|---|---|
| `sku` | `Standard_LRS` | Locally redundant, cheapest |
| `kind` | `StorageV2` | General purpose v2, supports blobs |

### Step 2: Create Container for Media Files

```bash
az storage container create \
  --account-name tfneepcostorage \
  --name resumes \
  --public-access blob
```

### Step 3: Get Storage Account Key

```bash
az storage account keys list \
  --resource-group tf-neepco-rg \
  --account-name tfneepcostorage \
  --query "[0].value" -o tsv
```

**Save these values:**
```
AZURE_STORAGE_ACCOUNT_NAME=tfneepcostorage
AZURE_STORAGE_KEY=your-storage-key-here
AZURE_STORAGE_CONTAINER=resumes
```

---

## Part 6: Create Azure Container Registry (ACR)

### Step 1: Create ACR

```bash
az acr create \
  --resource-group tf-neepco-rg \
  --name tfneepcoacr \
  --sku Basic \
  --admin-enabled true
```

### Step 2: Login to ACR

```bash
az acr login --name tfneepcoacr
```

### Step 3: Get ACR Login Server

```bash
az acr show \
  --resource-group tf-neepco-rg \
  --name tfneepcoacr \
  --query "loginServer" -o tsv
```

**Save this value:**
```
ACR_NAME=tfneepcoacr
ACR_LOGIN_SERVER=tfneepcoacr.azurecr.io
```

---

## Part 7: Create App Service Plan + Web App

### Step 1: Create App Service Plan (Linux)

```bash
az appservice plan create \
  --resource-group tf-neepco-rg \
  --name tf-neepco-plan \
  --sku B1 \
  --is-linux
```

**SKU options:**
| SKU | vCPU | RAM | Price/month | Use case |
|---|---|---|---|---|
| `B1` | 1 | 1.75 GB | ~$13 | Dev/staging |
| `B2` | 2 | 3.5 GB | ~$26 | Production |
| `S1` | 1 | 1.75 GB | ~$55 | Production + SLA |
| `P1v2` | 1 | 3.5 GB | ~$73 | High performance |

### Step 2: Create Web App for Django

```bash
az webapp create \
  --resource-group tf-neepco-rg \
  --plan tf-neepco-plan \
  --name tf-neepco-prod \
  --deployment-container-image-name tfneepcoacr.azurecr.io/talentflow:latest
```

### Step 3: Create Web App for Celery Worker

```bash
az webapp create \
  --resource-group tf-neepco-rg \
  --plan tf-neepco-plan \
  --name tf-neepco-celery \
  --deployment-container-image-name tfneepcoacr.azurecr.io/talentflow:latest
```

---

## Part 8: Configure Environment Variables

### Step 1: Open Azure Portal

1. Go to [portal.azure.com](https://portal.azure.com)
2. Navigate to **App Services** → **tf-neepco-prod**
3. Click **Settings** → **Environment variables**

### Step 2: Add Application Settings

Click **"+ Add"** for each variable:

#### Django Core
| Name | Value |
|---|---|
| `DJANGO_SECRET_KEY` | Generate at [djecrety.ir](https://djecrety.ir/) |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_SETTINGS_MODULE` | `config.settings` |
| `DJANGO_ALLOWED_HOSTS` | `tf-neepco-prod.azurewebsites.net` |
| `CSRF_TRUSTED_ORIGINS` | `https://tf-neepco-prod.azurewebsites.net` |

#### Database
| Name | Value |
|---|---|
| `DB_NAME` | `talentflow` |
| `DB_USER` | `talentflowadmin` |
| `DB_PASSWORD` | `YourStrongPassword123!` |
| `DB_HOST` | `tf-neepco-db.postgres.database.azure.com` |
| `DB_PORT` | `5432` |
| `DB_SSLMODE` | `require` |

#### Azure Storage
| Name | Value |
|---|---|
| `AZURE_STORAGE_ACCOUNT_NAME` | `tfneepcostorage` |
| `AZURE_STORAGE_KEY` | (from Part 5, Step 3) |
| `AZURE_STORAGE_CONTAINER` | `resumes` |

#### Redis / Celery
| Name | Value |
|---|---|
| `CELERY_BROKER_URL` | `rediss://:your-key@tf-neepco-redis.redis.cache.windows.net:6380/0?ssl_cert_reqs=required` |
| `CELERY_RESULT_BACKEND` | `rediss://:your-key@tf-neepco-redis.redis.cache.windows.net:6380/0?ssl_cert_reqs=required` |
| `CELERY_TASK_ALWAYS_EAGER` | `False` |

#### PII Encryption
| Name | Value |
|---|---|
| `DJANGO_ENCRYPTION_KEY` | Generate: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

#### LLM (Optional)
| Name | Value |
|---|---|
| `LLM_PROVIDER` | `deepseek` |
| `LLM_API_BASE` | `https://api.deepseek.com/v1` |
| `LLM_API_KEY` | (your DeepSeek API key) |
| `LLM_MODEL` | `deepseek-chat` |

#### External Integrations (Optional — leave empty for mocks)
| Name | Value |
|---|---|
| `DIGILOCKER_MOCK` | `True` |
| `AADHAAR_MOCK` | `True` |
| `NCS_MOCK` | `True` |
| `NOTIFY_PROVIDER` | `console` |

### Step 3: Save and Restart

1. Click **"Save"** at the top
2. Click **"Overview"** → **"Restart"**

---

## Part 9: Configure Celery Worker App

### Step 1: Open Celery App

1. Go to **App Services** → **tf-neepco-celery**
2. Click **Settings** → **Environment variables**

### Step 2: Add Same Environment Variables

Copy ALL the same variables from Part 8, Step 2.

### Step 3: Override Startup Command

1. Go to **Settings** → **Configuration** → **General settings**
2. Set **Startup Command** to:
   ```
   celery -A config worker -l info --concurrency=2
   ```
3. Click **Save**

---

## Part 10: Build and Deploy Docker Image

### Step 1: Build Docker Image Locally

```bash
# From the TalentFlowAI directory
docker build -t tfneepcoacr.azurecr.io/talentflow:latest .
```

### Step 2: Push to Azure Container Registry

```bash
docker push tfneepcoacr.azurecr.io/talentflow:latest
```

### Step 3: Configure Web App to Use ACR Image

**For Django app (tf-neepco-prod):**
```bash
az webapp config container set \
  --resource-group tf-neepco-rg \
  --name tf-neepco-prod \
  --docker-custom-image-name tfneepcoacr.azurecr.io/talentflow:latest \
  --docker-registry-server-url https://tfneepcoacr.azurecr.io
```

**For Celery app (tf-neepco-celery):**
```bash
az webapp config container set \
  --resource-group tf-neepco-rg \
  --name tf-neepco-celery \
  --docker-custom-image-name tfneepcoacr.azurecr.io/talentflow:latest \
  --docker-registry-server-url https://tfneepcoacr.azurecr.io
```

---

## Part 11: Run Migrations

### Option A: Via Azure Portal SSH

1. Go to **App Services** → **tf-neepco-prod**
2. Click **Development Tools** → **SSH**
3. Run:
   ```bash
   python manage.py migrate_schemas
   python manage.py collectstatic --noinput
   ```

### Option B: Via Azure CLI

```bash
az webapp ssh \
  --resource-group tf-neepco-rg \
  --name tf-neepco-prod \
  --command "python manage.py migrate_schemas"
```

---

## Part 12: Seed Initial Data

### Step 1: SSH into the App

```bash
az webapp ssh \
  --resource-group tf-neepco-rg \
  --name tf-neepco-prod
```

### Step 2: Run Seed Commands

```bash
# Create tenant + domain
python manage.py shell -c "
from tenants.models import Client, Domain
c = Client.objects.create(schema_name='neepco', name='NEEPCO', code='neepco')
Domain.objects.create(domain='neepco.azurewebsites.net', tenant=c, is_primary=True)
"

# Create staff users
python manage.py seed_staff_users

# Populate sample data (optional)
python manage.py populate_neepco_real
```

---

## Part 13: Configure Custom Domain (Optional)

### Step 1: Add Custom Domain

```bash
az webapp config hostname add \
  --resource-group tf-neepco-rg \
  --webapp-name tf-neepco-prod \
  --hostname yourdomain.com
```

### Step 2: Add DNS Records

In your domain registrar (GoDaddy, Namecheap, etc.):

| Type | Name | Value |
|---|---|---|
| `CNAME` | `www` | `tf-neepco-prod.azurewebsites.net` |
| `TXT` | `asuid` | (verification ID from Azure) |

### Step 3: Enable SSL

```bash
az webapp config hostname add \
  --resource-group tf-neepco-rg \
  --webapp-name tf-neepco-prod \
  --hostname yourdomain.com \
  --ssl-state SniEnabled \
  --thumbprint (certificate thumbprint)
```

**Or use Azure Managed Certificate (free):**
1. Go to **App Services** → **tf-neepco-prod** → **Custom domains**
2. Click **"+ Add custom domain"**
3. Enter your domain
4. Click **"Add binding"** → Select **"App Service Managed Certificate"**
5. Click **"Add"**

---

## Part 14: Configure Monitoring

### Step 1: Enable Application Insights

```bash
az monitor app-insights component create \
  --resource-group tf-neepco-rg \
  --app talentflow-insights \
  --location centralindia \
  --kind web
```

### Step 2: Get Instrumentation Key

```bash
az monitor app-insights component show \
  --resource-group tf-neepco-rg \
  --app talentflow-insights \
  --query "instrumentationKey" -o tsv
```

### Step 3: Add to App Settings

| Name | Value |
|---|---|
| `APPINSIGHTS_INSTRUMENTATIONKEY` | (from Step 2) |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | (from Step 2) |

### Step 4: Enable Logging

```bash
az webapp log config \
  --resource-group tf-neepco-rg \
  --name tf-neepco-prod \
  --application-logging filesystem \
  --detailed-error-messages true \
  --failed-request-tracing true \
  --web-server-logging filesystem
```

### Step 5: View Logs

```bash
az webapp log tail \
  --resource-group tf-neepco-rg \
  --name tf-neepco-prod
```

---

## Part 15: Backup and Recovery

### Step 1: Enable Automated Backups

```bash
az webapp config backup create \
  --resource-group tf-neepco-rg \
  --webapp-name tf-neepco-prod \
  --backup-name talentflow-backup \
  --storage-url https://tfneepcostorage.blob.core.windows.net/backups \
  --frequency 1d \
  --retention 30d
```

### Step 2: PostgreSQL Backups

Azure Database for PostgreSQL automatically creates:
- **Daily backups** (retained for 7 days)
- **Weekly backups** (retained for 5 weeks)
- **Monthly backups** (retained for 12 months)

To restore:
```bash
az postgres flexible-server restore \
  --resource-group tf-neepco-rg \
  --name tf-neepco-db-restored \
  --source-server tf-neepco-db \
  --restore-time "2026-08-09T00:00:00"
```

---

## Part 16: Scaling

### Scale Up (More Power)

```bash
az appservice plan update \
  --resource-group tf-neepco-rg \
  --name tf-neepco-plan \
  --sku B2
```

### Scale Out (More Instances)

```bash
az webapp scale \
  --resource-group tf-neepco-rg \
  --name tf-neepco-prod \
  --instance-count 2
```

### Auto-Scale (Based on CPU)

```bash
az monitor autoscale create \
  --resource-group tf-neepco-rg \
  --resource tf-neepco-plan \
  --resource-type Microsoft.Web/serverfarms \
  --name talentflow-autoscale \
  --min-count 1 \
  --max-count 3 \
  --count 1
```

---

## Troubleshooting

### App Won't Start

**Check logs:**
```bash
az webapp log tail \
  --resource-group tf-neepco-rg \
  --name tf-neepco-prod
```

**Common issues:**
1. **Missing environment variables** — Check Settings → Environment variables
2. **Database connection failed** — Verify DB_HOST, DB_PASSWORD, DB_SSLMODE
3. **Static files not loading** — Run `collectstatic` or check Azure Storage config
4. **Migrations not applied** — Run `migrate_schemas`

### Database Connection Issues

**Test connection:**
```bash
az postgres flexible-server connect \
  --resource-group tf-neepco-rg \
  --name tf-neepco-db \
  --admin-user talentflowadmin \
  --admin-password "YourStrongPassword123!"
```

**Check firewall:**
```bash
az postgres flexible-server firewall-rule list \
  --resource-group tf-neepco-rg \
  --server-name tf-neepco-db
```

**Add your IP:**
```bash
az postgres flexible-server firewall-rule create \
  --resource-group tf-neepco-rg \
  --server-name tf-neepco-db \
  --name allow-my-ip \
  --start-ip-address YOUR_IP \
  --end-ip-address YOUR_IP
```

### Redis Connection Issues

**Test connection:**
```bash
az redis show \
  --resource-group tf-neepco-rg \
  --name tf-neepco-redis \
  --query "hostName" -o tsv
```

**Check if Redis is running:**
```bash
az redis show \
  --resource-group tf-neepco-rg \
  --name tf-neepco-redis \
  --query "provisioningState" -o tsv
```

### Celery Worker Not Processing

**Check worker logs:**
```bash
az webapp log tail \
  --resource-group tf-neepco-rg \
  --name tf-neepco-celery
```

**Verify environment variables:**
```bash
az webapp config appsettings list \
  --resource-group tf-neepco-rg \
  --name tf-neepco-celery \
  --query "[?name=='CELERY_BROKER_URL'].value" -o tsv
```

---

## Cost Optimization

### Development/Staging (~$30/month)

```bash
# Use cheaper SKUs
az appservice plan update --sku B1
az postgres flexible-server update --sku-name Standard_B1ms
az redis update --sku Basic --vm-size C0
```

### Production (~$100/month)

```bash
# Use production SKUs
az appservice plan update --sku S1
az postgres flexible-server update --sku-name Standard_D2s_v3
az redis update --sku Standard --vm-size C1
```

### Cost Alerts

```bash
az monitor budget create \
  --resource-group tf-neepco-rg \
  --amount 100 \
  --time-grain Monthly \
  --start-date 2026-08-01 \
  --end-date 2026-12-31
```

---

## Security Checklist

- [ ] **Database**: Restrict firewall to App Service IPs only
- [ ] **Redis**: Enable SSL (already done with `rediss://`)
- [ ] **Storage**: Use SAS tokens instead of account keys
- [ ] **App Service**: Enable HTTPS only
- [ ] **Secrets**: Use Azure Key Vault for sensitive values
- [ ] **Network**: Consider VNet integration for production
- [ ] **Backups**: Enable automated backups
- [ ] **Monitoring**: Set up alerts for errors and downtime

---

## Quick Reference Commands

```bash
# View all resources
az resource list --resource-group tf-neepco-rg --output table

# Restart app
az webapp restart --resource-group tf-neepco-rg --name tf-neepco-prod

# View logs
az webapp log tail --resource-group tf-neepco-rg --name tf-neepco-prod

# SSH into app
az webapp ssh --resource-group tf-neepco-rg --name tf-neepco-prod

# Scale up
az appservice plan update --resource-group tf-neepco-rg --name tf-neepco-plan --sku B2

# Delete everything (CAREFUL!)
az group delete --name tf-neepco-rg --yes --no-wait
```

---

## Next Steps

1. **Set up CI/CD**: Push to GitHub → auto-deploy (`.github/workflows/deploy.yml`)
2. **Custom domain**: Add your domain + SSL certificate
3. **Monitoring**: Set up alerts for errors and downtime
4. **Backup**: Verify automated backups are working
5. **Security**: Restrict database firewall, use Key Vault for secrets
6. **Performance**: Monitor and scale as needed

---

**Questions? Check the [Azure App Service documentation](https://learn.microsoft.com/en-us/azure/app-service/) or the [Azure Database for PostgreSQL documentation](https://learn.microsoft.com/en-us/azure/postgresql/).**
