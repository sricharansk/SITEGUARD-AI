// Container apps and jobs: API (internal ingress by default; browsers use the web app's BFF), web app (external,
// HTTPS only), the scheduled jobs (escalation and notification delivery) and a manual migration job that the deploy
// workflow runs before rolling out a new API image. Secrets are Key Vault references resolved through the apps'
// managed identity. An availability test checks the web app and, through it, the API.

param namePrefix string
param location string
param tags object
param environmentId string
param defaultDomain string
param appIdentityName string
param registryLoginServer string
param keyVaultUri string
param evidenceStorageName string
param appInsightsId string
@minLength(1)
param apiImage string
@minLength(1)
param webImage string
@allowed(['staging', 'production'])
param siteguardEnv string
@description('Public https URL of the web app; empty uses the Container Apps default domain.')
param publicWebUrl string
@allowed(['rules', 'anthropic'])
param aiProvider string
@allowed(['disabled', 'log'])
param notificationEmailAdapter string
param apiExternalIngress bool
param webMaxReplicas int
param jobsCron string
@description('Object ID of the GitHub Actions OIDC service principal; empty to grant nothing.')
param deployPrincipalId string

var apiName = '${namePrefix}-api'
var webName = '${namePrefix}-web'
var webUrl = empty(publicWebUrl) ? 'https://${webName}.${defaultDomain}' : publicWebUrl
var useAnthropic = aiProvider == 'anthropic'

resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: appIdentityName
}

var registries = [{ server: registryLoginServer, identity: appIdentity.id }]

// Key Vault secret names the owner creates (docs/DEPLOYMENT.md#azure); database-url can come from database.bicep.
var databaseSecret = { name: 'database-url', keyVaultUrl: '${keyVaultUri}secrets/database-url', identity: appIdentity.id }
var jwtSecret = { name: 'jwt-secret', keyVaultUrl: '${keyVaultUri}secrets/jwt-secret', identity: appIdentity.id }
var anthropicSecret = {
  name: 'anthropic-api-key'
  keyVaultUrl: '${keyVaultUri}secrets/anthropic-api-key'
  identity: appIdentity.id
}

// Settings shared by the API and the jobs. SITEGUARD_ENV=staging|production turns on every startup check.
var commonEnv = [
  { name: 'SITEGUARD_ENV', value: siteguardEnv }
  { name: 'SITEGUARD_DATABASE_URL', secretRef: 'database-url' }
  { name: 'SITEGUARD_SEED_DEMO_DATA', value: 'false' }
  { name: 'SITEGUARD_PUBLIC_WEB_URL', value: webUrl }
  { name: 'SITEGUARD_NOTIFICATION_EMAIL_ADAPTER', value: notificationEmailAdapter }
  { name: 'SITEGUARD_AI_PROVIDER', value: aiProvider }
]
var anthropicEnv = useAnthropic ? [{ name: 'ANTHROPIC_API_KEY', secretRef: 'anthropic-api-key' }] : []

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: apiName
  location: location
  tags: union(tags, { 'siteguard-role': 'api' })
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${appIdentity.id}': {} } }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: apiExternalIngress
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        traffic: [{ latestRevision: true, weight: 100 }]
      }
      registries: registries
      secrets: concat([databaseSecret, jwtSecret], useAnthropic ? [anthropicSecret] : [])
    }
    template: {
      containers: [
        {
          name: 'api'
          image: apiImage
          resources: { cpu: json('1.0'), memory: '2Gi' }
          env: concat(
            commonEnv,
            [
              { name: 'SITEGUARD_JWT_SECRET', secretRef: 'jwt-secret' }
              // Browsers call the web app (same origin), never the API directly.
              { name: 'SITEGUARD_CORS_ORIGINS', value: '' }
              { name: 'SITEGUARD_EVIDENCE_DIR', value: '/srv/evidence' }
            ],
            anthropicEnv
          )
          volumeMounts: [{ volumeName: 'evidence', mountPath: '/srv/evidence' }]
          probes: [
            {
              type: 'Startup'
              httpGet: { path: '/health', port: 8000 }
              initialDelaySeconds: 10
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 10
            }
            {
              type: 'Liveness'
              httpGet: { path: '/health', port: 8000 }
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/health', port: 8000 }
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      // One replica: the login rate limiter is in-process (open decision O10) and the API migrates on startup.
      scale: { minReplicas: 1, maxReplicas: 1 }
      volumes: [
        {
          name: 'evidence'
          storageType: 'AzureFile'
          storageName: evidenceStorageName
          // The image runs as uid/gid 10001.
          mountOptions: 'uid=10001,gid=10001,dir_mode=0750,file_mode=0640'
        }
      ]
    }
  }
}

resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: webName
  location: location
  tags: union(tags, { 'siteguard-role': 'web' })
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${appIdentity.id}': {} } }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 3000
        transport: 'auto'
        allowInsecure: false
        traffic: [{ latestRevision: true, weight: 100 }]
      }
      registries: registries
    }
    template: {
      containers: [
        {
          name: 'web'
          image: webImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'SITEGUARD_API_URL', value: 'https://${api.properties.configuration.ingress.fqdn}' }
            { name: 'SITEGUARD_ALLOWED_ORIGINS', value: webUrl }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/api/health', port: 3000 }
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: { path: '/api/health', port: 3000 }
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: webMaxReplicas }
    }
  }
}

resource scheduledJobs 'Microsoft.App/jobs@2024-03-01' = {
  name: '${namePrefix}-jobs'
  location: location
  tags: union(tags, { 'siteguard-role': 'jobs' })
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${appIdentity.id}': {} } }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Schedule'
      scheduleTriggerConfig: { cronExpression: jobsCron, parallelism: 1, replicaCompletionCount: 1 }
      replicaTimeout: 900
      replicaRetryLimit: 1
      registries: registries
      secrets: [databaseSecret]
    }
    template: {
      containers: [
        {
          name: 'jobs'
          image: apiImage
          command: ['python', '-m', 'app.jobs', 'all']
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: commonEnv
        }
      ]
    }
  }
}

// Started by the deploy workflow with the new API image before the API is updated, so a failing migration stops
// the rollout while the old revision keeps serving. Never retried automatically.
resource migrateJob 'Microsoft.App/jobs@2024-03-01' = {
  name: '${namePrefix}-migrate'
  location: location
  tags: union(tags, { 'siteguard-role': 'migrate' })
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${appIdentity.id}': {} } }
  properties: {
    environmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      triggerType: 'Manual'
      manualTriggerConfig: { parallelism: 1, replicaCompletionCount: 1 }
      replicaTimeout: 1800
      replicaRetryLimit: 0
      registries: registries
      secrets: [databaseSecret]
    }
    template: {
      containers: [
        {
          name: 'migrate'
          image: apiImage
          command: ['python', '-c', 'from app.core.db import run_migrations; run_migrations(); print("migrations applied")']
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: commonEnv
        }
      ]
    }
  }
}

resource availability 'Microsoft.Insights/webtests@2022-06-15' = {
  name: '${namePrefix}-web-health'
  location: location
  tags: union(tags, { 'hidden-link:${appInsightsId}': 'Resource' })
  kind: 'standard'
  properties: {
    SyntheticMonitorId: '${namePrefix}-web-health'
    Name: 'Site Guard web app and API health'
    Kind: 'standard'
    Enabled: true
    Frequency: 300
    Timeout: 30
    RetryEnabled: true
    Locations: [{ Id: 'emea-nl-ams-azr' }, { Id: 'us-va-ash-azr' }, { Id: 'apac-sg-sin-azr' }]
    Request: {
      RequestUrl: '${webUrl}/api/health'
      HttpVerb: 'GET'
      ParseDependentRequests: false
    }
    ValidationRules: {
      ExpectedHttpStatusCode: 200
      SSLCheck: true
      SSLCertRemainingLifetimeCheck: 14
      // /api/health answers 200 while the API is down; require the web app to report the API reachable.
      ContentValidation: { ContentMatch: '"api":"ok"', IgnoreCase: false, PassIfTextFound: true }
    }
  }
}

// The GitHub deploy identity may update these apps and jobs and start the migration job, nothing else in the
// environment (plus AcrPush and resource-group Reader from security.bicep).
var contributor = 'b24988ac-6180-42a0-ab88-20f7382dd24c'
var managedIdentityOperator = 'f1a07417-d97a-45cb-824c-7a7467783830'

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: last(split(environmentId, '/'))
}

resource deployOnEnvironment 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployPrincipalId)) {
  name: guid(environment.id, deployPrincipalId, contributor)
  scope: environment
  properties: {
    principalId: deployPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', contributor)
  }
}

resource deployOnApi 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployPrincipalId)) {
  name: guid(api.id, deployPrincipalId, contributor)
  scope: api
  properties: {
    principalId: deployPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', contributor)
  }
}

resource deployOnWeb 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployPrincipalId)) {
  name: guid(web.id, deployPrincipalId, contributor)
  scope: web
  properties: {
    principalId: deployPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', contributor)
  }
}

resource deployOnJobs 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployPrincipalId)) {
  name: guid(scheduledJobs.id, deployPrincipalId, contributor)
  scope: scheduledJobs
  properties: {
    principalId: deployPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', contributor)
  }
}

resource deployOnMigrate 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployPrincipalId)) {
  name: guid(migrateJob.id, deployPrincipalId, contributor)
  scope: migrateJob
  properties: {
    principalId: deployPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', contributor)
  }
}

// Updating an app that uses the managed identity needs permission to assign that identity.
resource deployOnIdentity 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(deployPrincipalId)) {
  name: guid(appIdentity.id, deployPrincipalId, managedIdentityOperator)
  scope: appIdentity
  properties: {
    principalId: deployPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', managedIdentityOperator)
  }
}

output webUrl string = webUrl
output apiFqdn string = api.properties.configuration.ingress.fqdn
output apiName string = api.name
output webName string = web.name
output jobsName string = scheduledJobs.name
output migrateJobName string = migrateJob.name
