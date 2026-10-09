// Example parameters for deployment/azure/main.bicep. Copy it per environment (staging.bicepparam,
// production.bicepparam), change the values marked CHANGE, and keep secrets out of it: the PostgreSQL admin
// password is read from the deploying shell's environment, never written to a file.
//
//   export SITEGUARD_POSTGRES_ADMIN_PASSWORD="$(openssl rand -base64 36)"   # store it in your password manager
//   az deployment group create -g <resource group> -f deployment/azure/main.bicep -p <your copy>.bicepparam
//
// docs/DEPLOYMENT.md#azure describes both phases and the Key Vault secrets to create between them.
using './main.bicep'

param environmentName = 'staging'
param namePrefix = 'siteguard'

// Phase 1: false. Phase 2: true, with the images the deploy workflow pushed (tagged with the git commit SHA).
param deployApps = false
param apiImage = ''
param webImage = ''

param postgresAdminLogin = 'siteguardadmin'
param postgresAdminPassword = readEnvironmentVariable('SITEGUARD_POSTGRES_ADMIN_PASSWORD')

// Staging sizing. For production consider GeneralPurpose, zone-redundant HA, longer retention and geo backups.
param postgresSkuName = 'Standard_B2s'
param postgresSkuTier = 'Burstable'
param postgresStorageGiB = 32
param postgresBackupRetentionDays = 7
param postgresGeoRedundantBackup = false
param postgresHighAvailability = false
param writeDatabaseUrlSecret = true

param evidenceShareQuotaGiB = 100
param evidenceShareSoftDeleteDays = 14
param restrictStorageToSubnet = true

// Object ID of the service principal behind the GitHub OIDC federated credential (CHANGE; empty grants nothing).
param deployPrincipalId = ''

// Custom domain for the web app, for example https://staging.siteguard.example.com (CHANGE); empty uses the
// Container Apps default domain.
param publicWebUrl = ''

param aiProvider = 'rules'
param notificationEmailAdapter = 'disabled'
param apiExternalIngress = false
param webMaxReplicas = 2
param jobsCron = '*/5 * * * *'
param logRetentionDays = 30
