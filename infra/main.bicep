// CrewInsight — Azure infrastructure entry point
// Shares Azure OpenAI, AI Search, and Container Apps Managed Environment with RiskScout
// to avoid duplicate resource costs (~$250/mo savings on AI Search alone).

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Environment name (dev / staging / prod)')
@allowed(['dev', 'staging', 'prod'])
param environment string = 'dev'

@description('Azure Container Registry login server')
param containerRegistryServer string

@description('Container image tag to deploy')
param imageTag string = 'latest'

@secure()
@description('Azure OpenAI API key (shared with RiskScout)')
param azureOpenAiApiKey string

@description('Azure OpenAI endpoint (shared with RiskScout)')
param azureOpenAiEndpoint string

@secure()
@description('Azure AI Search admin key (shared with RiskScout)')
param azureSearchApiKey string

@description('Azure AI Search endpoint (shared with RiskScout)')
param azureSearchEndpoint string

@description('Resource ID of existing Container Apps Managed Environment (shared with RiskScout)')
param managedEnvironmentId string

var prefix = 'crewinsight-${environment}'
var tags = {
  project: 'crewinsight'
  environment: environment
  managedBy: 'bicep'
}

// ---------------------------------------------------------------------------
// Application Insights (separate for CrewInsight telemetry isolation)
// ---------------------------------------------------------------------------

module monitoring 'monitoring.bicep' = {
  name: 'monitoring'
  params: {
    prefix: prefix
    location: location
    tags: tags
  }
}

// ---------------------------------------------------------------------------
// Storage Account (Azure Table Storage for distributed rate limiting)
// ---------------------------------------------------------------------------

module storage 'storage.bicep' = {
  name: 'storage'
  params: {
    prefix: prefix
    location: location
    tags: tags
  }
}

// ---------------------------------------------------------------------------
// Container App (joins the shared RiskScout managed environment)
// ---------------------------------------------------------------------------

module containerApp 'container-app.bicep' = {
  name: 'container-app'
  params: {
    prefix: prefix
    location: location
    tags: tags
    containerRegistryServer: containerRegistryServer
    imageTag: imageTag
    managedEnvironmentId: managedEnvironmentId
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    azureOpenAiEndpoint: azureOpenAiEndpoint
    azureOpenAiApiKey: azureOpenAiApiKey
    azureSearchEndpoint: azureSearchEndpoint
    azureSearchApiKey: azureSearchApiKey
    storageAccountName: storage.outputs.storageAccountName
    storageAccountKey: storage.outputs.storageAccountKey
  }
}

// ---------------------------------------------------------------------------
// Outputs
// ---------------------------------------------------------------------------

output containerAppUrl string = containerApp.outputs.url
output appInsightsConnectionString string = monitoring.outputs.appInsightsConnectionString
output storageAccountName string = storage.outputs.storageAccountName
