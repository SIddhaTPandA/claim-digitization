param functionAppName string
param location string
param storageAccountName string
param appInsightsName string
param serviceBusNamespace string
param keyVaultName string

resource functionApp 'Microsoft.Web/sites@2021-02-01' = {
  name: functionAppName
  location: location
  kind: 'functionapp'
  properties: {
    serverFarmId: functionHostingPlan.id
    httpsOnly: true
    siteConfig: {
      appSettings: [
        {
          name: 'AzureWebJobsStorage'
          value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccountName};AccountKey=<your_account_key>;EndpointSuffix=core.windows.net'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'python'
        }
        {
          name: 'APPINSIGHTS_INSTRUMENTATIONKEY'
          value: appInsights.properties.InstrumentationKey
        }
        {
          name: 'SERVICE_BUS_CONNECTION_STRING'
          value: 'Endpoint=sb://${serviceBusNamespace}.servicebus.windows.net/;SharedAccessKeyName=<your_key_name>;SharedAccessKey=<your_key>'
        }
        {
          name: 'KEY_VAULT_URI'
          value: 'https://${keyVaultName}.vault.azure.net/'
        }
      ]
    }
  }
}

resource functionHostingPlan 'Microsoft.Web/serverfarms@2021-02-01' = {
  name: '${functionAppName}-plan'
  location: location
  sku: {
    Tier: 'Dynamic'
    Name: 'Y1'
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
  }
}