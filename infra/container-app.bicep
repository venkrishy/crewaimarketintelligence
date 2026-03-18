// Azure Container Apps — hosts the CrewInsight FastAPI service
// Joins an existing Container Apps Managed Environment (shared with RiskScout)

param prefix string
param location string
param tags object
param containerRegistryServer string
param imageTag string

@description('Resource ID of the existing Container Apps Managed Environment')
param managedEnvironmentId string

param appInsightsConnectionString string
param azureOpenAiEndpoint string
@secure()
param azureOpenAiApiKey string
param azureSearchEndpoint string
@secure()
param azureSearchApiKey string
param storageAccountName string
@secure()
param storageAccountKey string

var imageName = '${containerRegistryServer}/crewinsight:${imageTag}'

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${prefix}-app'
  location: location
  tags: tags
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        corsPolicy: {
          allowedOrigins: ['*']
          allowedMethods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS']
          allowedHeaders: ['*']
        }
      }
      registries: [
        {
          server: containerRegistryServer
          identity: 'system'
        }
      ]
      secrets: [
        { name: 'azure-openai-key', value: azureOpenAiApiKey }
        { name: 'azure-search-key', value: azureSearchApiKey }
        { name: 'azure-storage-key', value: storageAccountKey }
      ]
    }
    template: {
      scale: {
        minReplicas: 1
        maxReplicas: 5
        rules: [
          {
            name: 'http-scaling'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
      containers: [
        {
          name: 'crewinsight'
          image: imageName
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          env: [
            { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'azure-openai-key' }
            { name: 'AZURE_SEARCH_ENDPOINT', value: azureSearchEndpoint }
            { name: 'AZURE_SEARCH_API_KEY', secretRef: 'azure-search-key' }
            { name: 'AZURE_SEARCH_INDEX', value: 'crewinsight-index' }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'AZURE_STORAGE_ACCOUNT_NAME', value: storageAccountName }
            { name: 'AZURE_STORAGE_ACCOUNT_KEY', secretRef: 'azure-storage-key' }
            { name: 'LOG_LEVEL', value: 'INFO' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/docs'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/docs'
                port: 8000
              }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
    }
  }
  identity: {
    type: 'SystemAssigned'
  }
}

output url string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output containerAppName string = containerApp.name
