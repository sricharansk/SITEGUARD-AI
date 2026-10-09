// Azure Database for PostgreSQL Flexible Server 16 with private access only, pgvector allow-listed
// (azure.extensions = VECTOR; the first migration runs CREATE EXTENSION vector), TLS required (server default
// require_secure_transport = on), automated backups with point-in-time restore.

param location string
param tags object
param serverName string
param databaseName string
param adminLogin string
@secure()
param adminPassword string
param skuName string
param skuTier string
param storageSizeGiB int
param backupRetentionDays int
param geoRedundantBackup bool
param highAvailability bool
param delegatedSubnetId string
param privateDnsZoneId string
param keyVaultName string
@description('Write the application database URL (admin login) to Key Vault as database-url.')
param writeDatabaseUrlSecret bool

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: serverName
  location: location
  tags: tags
  sku: { name: skuName, tier: skuTier }
  properties: {
    version: '16'
    administratorLogin: adminLogin
    administratorLoginPassword: adminPassword
    authConfig: { passwordAuth: 'Enabled', activeDirectoryAuth: 'Disabled' }
    storage: { storageSizeGB: storageSizeGiB, autoGrow: 'Enabled' }
    backup: {
      backupRetentionDays: backupRetentionDays
      geoRedundantBackup: geoRedundantBackup ? 'Enabled' : 'Disabled'
    }
    highAvailability: { mode: highAvailability ? 'ZoneRedundant' : 'Disabled' }
    network: {
      delegatedSubnetResourceId: delegatedSubnetId
      privateDnsZoneArmResourceId: privateDnsZoneId
      publicNetworkAccess: 'Disabled'
    }
  }
}

resource extensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: server
  name: 'azure.extensions'
  properties: { value: 'VECTOR', source: 'user-override' }
}

resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: server
  name: databaseName
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
  dependsOn: [extensions]
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

// The admin login is convenient for a first deployment; docs/DEPLOYMENT.md#azure shows how to switch the app to a
// dedicated role and set writeDatabaseUrlSecret=false so later deployments keep that secret.
resource databaseUrl 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (writeDatabaseUrlSecret) {
  parent: vault
  name: 'database-url'
  properties: {
    contentType: 'SQLAlchemy URL'
    value: 'postgresql+psycopg://${uriComponent(adminLogin)}:${uriComponent(adminPassword)}@${server.properties.fullyQualifiedDomainName}:5432/${databaseName}?sslmode=require'
  }
  dependsOn: [database]
}

output serverName string = server.name
output serverFqdn string = server.properties.fullyQualifiedDomainName
output databaseName string = database.name
