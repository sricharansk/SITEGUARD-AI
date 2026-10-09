// Evidence storage. The API stores evidence and original knowledge documents on a file path
// (SITEGUARD_EVIDENCE_DIR); there is no Blob Storage adapter yet (open decision O6), so an Azure Files share is
// mounted at that path. Shared-key access is required for the SMB mount; the key never leaves Azure (the
// Container Apps environment reads it at deployment). Retention and malware scanning are open (docs/GOVERNANCE.md).

param location string
param tags object
param storageAccountName string
param shareQuotaGiB int
param softDeleteDays int
@description('Admit only the Container Apps subnet (plus trusted Azure services); false leaves the account public.')
param restrictToSubnet bool
param appsSubnetId string

resource account 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_ZRS' }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    publicNetworkAccess: 'Enabled'
    networkAcls: restrictToSubnet
      ? {
          defaultAction: 'Deny'
          bypass: 'AzureServices'
          virtualNetworkRules: [{ id: appsSubnetId, action: 'Allow' }]
        }
      : { defaultAction: 'Allow', bypass: 'AzureServices' }
    encryption: {
      keySource: 'Microsoft.Storage'
      services: {
        file: { enabled: true, keyType: 'Account' }
        blob: { enabled: true, keyType: 'Account' }
      }
    }
  }
}

resource files 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: account
  name: 'default'
  properties: {
    shareDeleteRetentionPolicy: { enabled: true, days: softDeleteDays }
  }
}

resource evidenceShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: files
  name: 'evidence'
  properties: {
    shareQuota: shareQuotaGiB
    enabledProtocols: 'SMB'
  }
}

output accountName string = account.name
output shareName string = evidenceShare.name
