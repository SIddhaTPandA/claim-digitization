param location string = resourceGroup().location
param documentIntelligenceName string = 'spdDocumentIntelligence'
param sku string = 'S1'

resource documentIntelligence 'Microsoft.CognitiveServices/accounts@2021-04-30' = {
  name: documentIntelligenceName
  location: location
  kind: 'FormRecognizer'
  sku: {
    name: sku
    tier: sku
  }
  properties: {
    apiProperties: {
      customSubDomainName: documentIntelligenceName
    }
  }
}

output documentIntelligenceEndpoint string = documentIntelligence.properties.endpoint
output documentIntelligenceKey string = listKeys(documentIntelligence.id, '2021-04-30').keys[0].value