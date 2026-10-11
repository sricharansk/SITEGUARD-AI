// Container Apps environment in the virtual network, logging to Log Analytics, with the evidence share registered
// as environment storage so the API can mount it.

param namePrefix string
param location string
param tags object
param appsSubnetId string
param workspaceName string
param storageAccountName string
param shareName string

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: workspaceName
}

resource account 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${namePrefix}-env'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: appsSubnetId
      internal: false
    }
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
    zoneRedundant: false
  }
}

resource evidenceStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: environment
  name: 'evidence'
  properties: {
    azureFile: {
      accountName: account.name
      accountKey: account.listKeys().keys[0].value
      shareName: shareName
      accessMode: 'ReadWrite'
    }
  }
}

output environmentId string = environment.id
output environmentName string = environment.name
output defaultDomain string = environment.properties.defaultDomain
output evidenceStorageName string = evidenceStorage.name
