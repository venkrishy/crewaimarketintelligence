// Azure AI Search service (Standard tier for vector search support)

param prefix string
param location string
param tags object

resource searchService 'Microsoft.Search/searchServices@2024-03-01-preview' = {
  name: '${prefix}-search'
  location: location
  tags: tags
  sku: {
    name: 'standard'
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'Enabled'
    semanticSearch: 'standard'
  }
}

output endpoint string = 'https://${searchService.name}.search.windows.net'
output serviceName string = searchService.name
