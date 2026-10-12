// Log Analytics (container stdout/stderr: the API's JSON request logs with correlation IDs, the web app, jobs)
// and a workspace-based Application Insights resource for availability tests. The app has no telemetry SDK yet
// (docs/OBSERVABILITY.md), so Application Insights holds availability results only.

param namePrefix string
param location string
param tags object
param retentionDays int

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${namePrefix}-logs'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: retentionDays
    features: { enableLogAccessUsingOnlyResourcePermissions: true }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${namePrefix}-appi'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
    DisableLocalAuth: true
  }
}

output workspaceName string = workspace.name
output workspaceId string = workspace.id
output appInsightsId string = appInsights.id
output appInsightsName string = appInsights.name
