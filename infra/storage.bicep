// Azure Storage Account + Table Storage for distributed rate limiting

param prefix string
param location string
param tags object

// Storage account names must be 3-24 chars, lowercase alphanumeric only.
// Strip hyphens from prefix and truncate to leave room for suffix.
var saName = take(replace(replace(prefix, '-', ''), '_', ''), 20)

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: '${saName}rl'
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    accessTier: 'Hot'
  }
}

resource tableService 'Microsoft.Storage/storageAccounts/tableServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource rateLimitTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-05-01' = {
  parent: tableService
  name: 'ratelimits'
}

output storageAccountName string = storageAccount.name
output storageAccountKey string = storageAccount.listKeys().keys[0].value
