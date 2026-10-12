// Site Guard AI on Azure: one resource group per environment (staging, production).
//
// Phase 1 (deployApps=false) creates the network, monitoring, identity, registry, Key Vault, evidence storage,
// PostgreSQL and the Container Apps environment. The owner then adds the Key Vault secrets and the deploy workflow
// pushes the first image. Phase 2 (deployApps=true, with that image reference) creates the app (API + web app in one
// container), the jobs, the availability test and the deploy identity's app-level roles.
// docs/DEPLOYMENT.md#azure has the full procedure.
//
// Nothing here holds a secret value: the PostgreSQL admin password is a secure parameter read from the
// environment at deployment time, and the apps read their secrets from Key Vault through a managed identity.

targetScope = 'resourceGroup'

@allowed(['staging', 'production'])
param environmentName string

@minLength(3)
@maxLength(12)
@description('Lowercase letters and digits; prefixes every resource name.')
param namePrefix string

param location string = resourceGroup().location

@description('false: infrastructure only (first deployment). true: also the apps and jobs (needs pushed images).')
param deployApps bool = false

@description('Full image reference (API + web app), for example <registry>.azurecr.io/siteguard-api@sha256:...')
param apiImage string = ''

param postgresAdminLogin string = 'siteguardadmin'

@secure()
@minLength(16)
param postgresAdminPassword string

param postgresSkuName string = 'Standard_B2s'

@allowed(['Burstable', 'GeneralPurpose', 'MemoryOptimized'])
param postgresSkuTier string = 'Burstable'

param postgresStorageGiB int = 32

@minValue(7)
@maxValue(35)
param postgresBackupRetentionDays int = 7

param postgresGeoRedundantBackup bool = false

@description('Zone-redundant high availability; not available on the Burstable tier.')
param postgresHighAvailability bool = false

@description('Write database-url (admin login) to Key Vault. Set false once the app uses a dedicated role.')
param writeDatabaseUrlSecret bool = true

param evidenceShareQuotaGiB int = 100

param evidenceShareSoftDeleteDays int = 14

@description('Admit only the Container Apps subnet to the evidence storage account.')
param restrictStorageToSubnet bool = true

@description('Object ID of the GitHub Actions OIDC service principal; empty to grant nothing.')
param deployPrincipalId string = ''

@description('Public https URL of the web app (custom domain); empty uses the Container Apps default domain.')
param publicWebUrl string = ''

@allowed(['rules', 'anthropic'])
param aiProvider string = 'rules'

@description('Cron schedule (UTC) for python -m app.jobs escalate-overdue (idempotent; hourly is plenty).')
param jobsCron string = '7 * * * *'

@minValue(30)
@maxValue(730)
param logRetentionDays int = 30

param vnetAddressPrefix string = '10.40.0.0/16'
param appsSubnetPrefix string = '10.40.0.0/23'
param postgresSubnetPrefix string = '10.40.2.0/24'

var prefix = '${toLower(namePrefix)}-${environmentName == 'production' ? 'prod' : 'stg'}'
var unique = uniqueString(resourceGroup().id, namePrefix, environmentName)
var compactPrefix = toLower(replace(prefix, '-', ''))
var tags = {
  application: 'siteguard-ai'
  environment: environmentName
}

module network 'modules/network.bicep' = {
  name: 'network'
  params: {
    namePrefix: prefix
    location: location
    tags: tags
    addressPrefix: vnetAddressPrefix
    appsSubnetPrefix: appsSubnetPrefix
    postgresSubnetPrefix: postgresSubnetPrefix
  }
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    namePrefix: prefix
    location: location
    tags: tags
    retentionDays: logRetentionDays
  }
}

module security 'modules/security.bicep' = {
  name: 'security'
  params: {
    namePrefix: prefix
    location: location
    tags: tags
    keyVaultName: take('${prefix}-kv-${unique}', 24)
    registryName: take('${compactPrefix}acr${unique}', 50)
    deployPrincipalId: deployPrincipalId
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    location: location
    tags: tags
    storageAccountName: take('${compactPrefix}ev${unique}', 24)
    shareQuotaGiB: evidenceShareQuotaGiB
    softDeleteDays: evidenceShareSoftDeleteDays
    restrictToSubnet: restrictStorageToSubnet
    appsSubnetId: network.outputs.appsSubnetId
  }
}

module database 'modules/database.bicep' = {
  name: 'database'
  params: {
    location: location
    tags: tags
    serverName: '${prefix}-pg-${unique}'
    databaseName: 'siteguard'
    adminLogin: postgresAdminLogin
    adminPassword: postgresAdminPassword
    skuName: postgresSkuName
    skuTier: postgresSkuTier
    storageSizeGiB: postgresStorageGiB
    backupRetentionDays: postgresBackupRetentionDays
    geoRedundantBackup: postgresGeoRedundantBackup
    highAvailability: postgresHighAvailability
    delegatedSubnetId: network.outputs.postgresSubnetId
    privateDnsZoneId: network.outputs.postgresDnsZoneId
    keyVaultName: security.outputs.keyVaultName
    writeDatabaseUrlSecret: writeDatabaseUrlSecret
  }
}

module containerEnvironment 'modules/environment.bicep' = {
  name: 'container-environment'
  params: {
    namePrefix: prefix
    location: location
    tags: tags
    appsSubnetId: network.outputs.appsSubnetId
    workspaceName: monitoring.outputs.workspaceName
    storageAccountName: storage.outputs.accountName
    shareName: storage.outputs.shareName
  }
}

module apps 'modules/apps.bicep' = if (deployApps) {
  name: 'apps'
  params: {
    namePrefix: prefix
    location: location
    tags: tags
    environmentId: containerEnvironment.outputs.environmentId
    defaultDomain: containerEnvironment.outputs.defaultDomain
    appIdentityName: '${prefix}-apps-id'
    registryLoginServer: security.outputs.registryLoginServer
    keyVaultUri: security.outputs.keyVaultUri
    evidenceStorageName: containerEnvironment.outputs.evidenceStorageName
    appInsightsId: monitoring.outputs.appInsightsId
    apiImage: apiImage
    siteguardEnv: environmentName
    publicWebUrl: publicWebUrl
    aiProvider: aiProvider
    jobsCron: jobsCron
    deployPrincipalId: deployPrincipalId
  }
  dependsOn: [database]
}

output registryLoginServer string = security.outputs.registryLoginServer
output registryName string = security.outputs.registryName
output keyVaultName string = security.outputs.keyVaultName
output postgresServerName string = database.outputs.serverName
output postgresFqdn string = database.outputs.serverFqdn
output storageAccountName string = storage.outputs.accountName
output containerEnvironmentName string = containerEnvironment.outputs.environmentName
output logAnalyticsWorkspaceName string = monitoring.outputs.workspaceName
output webUrl string = deployApps ? apps!.outputs.webUrl : ''
output apiName string = deployApps ? apps!.outputs.apiName : ''
