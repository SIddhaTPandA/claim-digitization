param sqlServerName string
param sqlDatabaseName string
param sqlAdminLogin string
param sqlAdminPassword string

resource sqlServer 'Microsoft.Sql/servers@2021-02-01-preview' = {
  name: sqlServerName
  location: resourceGroup().location
  properties: {
    administratorLogin: sqlAdminLogin
    administratorLoginPassword: sqlAdminPassword
    version: '12.0'
    sslEnforcement: 'Enabled'
  }
}

resource sqlDatabase 'Microsoft.Sql/servers/databases@2021-02-01-preview' = {
  name: sqlDatabaseName
  parent: sqlServer
  properties: {
    edition: 'Standard'
    requestedServiceObjective: 'S0'
  }
}

output sqlServerName string = sqlServer.name
output sqlDatabaseName string = sqlDatabase.name