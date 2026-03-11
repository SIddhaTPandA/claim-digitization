param keyVaultName string
param location string = resourceGroup().location

resource keyVault 'Microsoft.KeyVault/vaults@2021-04-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    accessPolicies: []
    enabledForDeployment: true
    enabledForTemplateDeployment: true
    enabledForDiskEncryption: true
  }
}

output keyVaultUri string = keyVault.properties.vaultUri