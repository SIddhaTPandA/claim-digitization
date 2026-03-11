param location string = resourceGroup().location
param appName string
param storageAccountName string
param serviceBusNamespace string
param sqlServerName string
param keyVaultName string
param appInsightsName string

// Storage Account
module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    location: location
    storageAccountName: storageAccountName
  }
}

// Azure Functions
module functions 'modules/functions.bicep' = {
  name: 'functions'
  params: {
    location: location
    appName: appName
    storageAccountName: storageAccountName
  }
}

// Service Bus
module serviceBus 'modules/servicebus.bicep' = {
  name: 'serviceBus'
  params: {
    location: location
    serviceBusNamespace: serviceBusNamespace
  }
}

// SQL Database
module sql 'modules/sql.bicep' = {
  name: 'sql'
  params: {
    location: location
    sqlServerName: sqlServerName
  }
}

// Key Vault
module keyVault 'modules/keyvault.bicep' = {
  name: 'keyVault'
  params: {
    location: location
    keyVaultName: keyVaultName
  }
}

// Application Insights
module appInsights 'modules/appinsights.bicep' = {
  name: 'appInsights'
  params: {
    location: location
    appInsightsName: appInsightsName
  }
}

// Document Intelligence
module documentIntelligence 'modules/documentintelligence.bicep' = {
  name: 'documentIntelligence'
  params: {
    location: location
    appName: appName
  }
}