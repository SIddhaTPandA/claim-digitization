param serviceBusName string
param location string = resourceGroup().location

resource serviceBus 'Microsoft.ServiceBus/namespaces@2021-06-01' = {
  name: serviceBusName
  location: location
  sku: {
    name: 'Standard'
    tier: 'Standard'
  }
  properties: {
    isAutoInflateEnabled: true
    maximumThroughputUnits: 20
  }
}

output serviceBusConnectionString string = listKeys(serviceBus.id, 'default').primaryConnectionString