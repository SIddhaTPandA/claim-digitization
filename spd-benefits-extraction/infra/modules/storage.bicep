param storageAccountName string
param location string = resourceGroup().location
param sku string = 'Standard_LRS'

var storageAccountId = 'Microsoft.Storage/storageAccounts'

resource storageAccount 'Microsoft.Storage/storageAccounts@2021-04-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: sku
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
  }
}

output storageAccountEndpoint string = 'https://${storageAccount.name}.blob.core.windows.net/'