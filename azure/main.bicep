// ---------------------------------------------------------------------------
// FinKennis op Azure Container Apps, in dezelfde resource group en hetzelfde
// Container Apps-environment als de invulhulp en de centrale Keycloak.
//
// Maakt aan:
//   - user-assigned managed identity (pullt de images uit de bestaande ACR)
//   - storage account + Azure Files-shares voor de uploads en de databasebackups
//   - ca-finkennis-postgres-*  pgvector als container, interne TCP-ingress
//   - job-finkennis-pgbackup-* pg_dump naar Azure Files, elke nacht
//   - job-finkennis-pgdump-*   dezelfde dump op afroep (de pipeline, vóór elke deploy)
//   - ca-finkennis-backend-*   FastAPI, interne ingress :8000
//   - ca-finkennis-frontend-*  nginx + SPA, publieke ingress :80, IP-allowlist
//
// Postgres als container, niet als Flexible Server: de CCoE-policy 'SSC Allowed
// Resource Types' verbiedt Microsoft.DBforPostgreSQL/flexibleServers (zie
// innovatieteam-infra/keycloak/azure/main.bicep, waar dit is uitgezocht).
//
// De datadirectory staat op een EmptyDir, die zo lang leeft als de replica: Postgres
// kan niet op Azure Files over SMB draaien (geen hard links, geen fsync op mappen).
// Een schaalactie of platformonderhoud geeft Postgres dus een lege schijf. Daarom:
//
//   - pg-backup.sh dumpt de database elke nacht naar de share finkennis-pgbackup
//     (een gewoon bestand schrijven kan SMB prima), en vlak voor elke deploy.
//   - pg-restore.sh zit in /docker-entrypoint-initdb.d. De postgres-image draait
//     dat alleen na initdb, dus op een lege schijf, en zet dan de nieuwste dump
//     terug voordat de backend kan verbinden.
//
// Na een herstart is hooguit wat er sinds de laatste dump (nacht of deploy) is gebeurd weg. De geüploade bestanden
// staan los daarvan op Azure Files.
//
// Een gewone deploy laat Postgres staan: het template is constant, dus zonder
// postgresRevisionSuffix ontstaat er geen nieuwe revisie. FORCE_PG_REINIT=true in de
// pipeline maakt een nieuwe replica, die de nieuwste dump terugzet.
// ---------------------------------------------------------------------------

@description('Locatie van alle resources.')
param location string = resourceGroup().location

@description('Omgevingsachtervoegsel in de namen, bijvoorbeeld inno-d.')
param environmentName string

@description('Bestaand Container Apps-environment (dat van de invulhulp).')
param caeName string

@description('Bestaande ACR (zonder .azurecr.io) met de FinKennis-images.')
param acrName string

@description('Storage account voor de uploads. Globaal uniek, 3-24 kleine letters en cijfers.')
param storageAccountName string

param backendImage string
param frontendImage string

@description('Postgres-image met pgvector. Komt van Docker Hub, net als postgres:16 voor Keycloak.')
param postgresImage string = 'pgvector/pgvector:pg17'

@description('''Achtervoegsel voor de Postgres-revisie. Een nieuwe waarde forceert een
nieuwe revisie, dus een lege EmptyDir: de database wordt opnieuw en leeg
aangemaakt, met het huidige wachtwoord. Leeg (standaard) houdt de draaiende
database aan.''')
param postgresRevisionSuffix string = ''

@description('Cron-schema (UTC) van de databasebackup.')
param backupCron string = '0 2 * * *'

@description('Basis-URL van de centrale Keycloak, bijvoorbeeld https://ca-keycloak-inno-d.<domein>.')
param keycloakUrl string

param keycloakRealm string = 'finkennis'

@description('Publieke URL van de frontend. Leeg = de FQDN van de frontend-container app.')
param publicUrl string = ''

@description('IP-allowlist op de frontend: [{ name, ipAddressRange }]. Leeg = open voor iedereen.')
param allowedIpRanges array = []

param azureOpenAiDeployment string = 'gpt-5.3-chat'
param azureOpenAiApiVersion string = '2025-04-01-preview'
param azureOpenAiEmbeddingDeployment string = 'text-embedding-3-large'
param azureOpenAiEmbeddingApiVersion string = '2024-02-01'

@secure()
param azureOpenAiEndpoint string
@secure()
param azureOpenAiApiKey string
@secure()
param azureOpenAiEmbeddingEndpoint string
@secure()
param azureOpenAiEmbeddingApiKey string

@description('Wachtwoord van de Postgres-gebruiker. Gebruik hex (openssl rand -hex 24): het komt in een database-URL.')
@secure()
param postgresPassword string

@description('Secret van de finkennis-admin service-account-client. Moet gelijk zijn aan wat Keycloak in de realm rendert.')
@secure()
param oidcAdminClientSecret string

var postgresAppName = 'ca-finkennis-postgres-${environmentName}'
var backendAppName = 'ca-finkennis-backend-${environmentName}'
var frontendAppName = 'ca-finkennis-frontend-${environmentName}'
var postgresUser = 'finkennis'
var postgresDb = 'finkennis'
// De Postgres van Keycloak gebruikt 5432 al. TCP-poorten zijn uniek binnen het
// environment, dus deze krijgt 5433.
var postgresPort = 5433
var uploadsShareName = 'finkennis-uploads'
var backupShareName = 'finkennis-pgbackup'

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: caeName
}

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: acrName
}

// Backend en frontend kennen elkaars URL nodig; het domein van het environment is
// bekend, dus leiden we ze daaruit af in plaats van uit elkaars outputs.
var backendUrl = 'https://${backendAppName}.internal.${cae.properties.defaultDomain}'
var frontendUrl = 'https://${frontendAppName}.${cae.properties.defaultDomain}'
var effectivePublicUrl = empty(publicUrl) ? frontendUrl : publicUrl

resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-finkennis-${environmentName}'
  location: location
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, uami.id, 'acrpull')
  scope: acr
  properties: {
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d') // AcrPull
  }
}

// ─── Uploads op Azure Files ────────────────────────────────────────────────

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    // Container Apps mount de share met de accountsleutel.
    allowSharedKeyAccess: true
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource uploadsShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: uploadsShareName
  properties: { shareQuota: 32 }
}

// Registreren op het environment maakt de share koppelbaar als AzureFile-volume.
resource caeStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: cae
  name: uploadsShareName
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: uploadsShare.name
      accessMode: 'ReadWrite'
    }
  }
}

// ─── Databasebackups op Azure Files ────────────────────────────────────────

resource backupShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: backupShareName
  properties: { shareQuota: 64 }
}

resource caeBackupStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: cae
  name: backupShareName
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: backupShare.name
      accessMode: 'ReadWrite'
    }
  }
}

// ─── Postgres (pgvector) ───────────────────────────────────────────────────

resource postgres 'Microsoft.App/containerApps@2024-03-01' = {
  name: postgresAppName
  location: location
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      activeRevisionsMode: 'Single'
      // Alleen binnen het environment bereikbaar, op <app-naam>:5433.
      ingress: {
        external: false
        transport: 'tcp'
        targetPort: 5432
        exposedPort: postgresPort
        traffic: [ { weight: 100, latestRevision: true } ]
      }
      secrets: [
        { name: 'db-pw', value: postgresPassword }
      ]
    }
    // union() laat revisionSuffix weg als hij leeg is: dan geen nieuwe revisie en
    // blijft de database staan. Zie de kop van dit bestand.
    template: union(empty(postgresRevisionSuffix) ? {} : { revisionSuffix: postgresRevisionSuffix }, {
      containers: [
        {
          name: 'postgres'
          image: postgresImage
          // De gewone image, met pg-restore.sh als initdb-script. Zo hoeft er geen
          // eigen Postgres-image gebouwd te worden.
          command: [
            'bash'
            '-c'
            'printf "%s" "$PG_RESTORE_SCRIPT" > /docker-entrypoint-initdb.d/zz-restore.sh && exec docker-entrypoint.sh postgres'
          ]
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'POSTGRES_USER', value: postgresUser }
            { name: 'POSTGRES_PASSWORD', secretRef: 'db-pw' }
            { name: 'POSTGRES_DB', value: postgresDb }
            { name: 'PGDATA', value: '/var/lib/postgresql/data/pgdata' }
            { name: 'PG_RESTORE_SCRIPT', value: loadTextContent('pg-restore.sh') }
          ]
          volumeMounts: [
            { volumeName: 'pgdata', mountPath: '/var/lib/postgresql/data' }
            { volumeName: 'backup', mountPath: '/backup' }
          ]
          probes: [
            { type: 'Liveness', tcpSocket: { port: 5432 }, initialDelaySeconds: 30, periodSeconds: 30 }
            { type: 'Readiness', tcpSocket: { port: 5432 }, initialDelaySeconds: 10, periodSeconds: 10 }
          ]
        }
      ]
      volumes: [
        { name: 'pgdata', storageType: 'EmptyDir' }
        { name: 'backup', storageType: 'AzureFile', storageName: caeBackupStorage.name }
      ]
      // Precies één replica: een tweede krijgt een eigen, lege schijf.
      scale: { minReplicas: 1, maxReplicas: 1 }
    })
  }
}

// Twee jobs met hetzelfde template: één op schema, één die de pipeline vóór elke
// deploy start en afwacht. Ze bereiken Postgres over het environment-netwerk.
var backupJobs = [
  { name: 'job-finkennis-pgbackup-${environmentName}', trigger: 'Schedule' }
  { name: 'job-finkennis-pgdump-${environmentName}', trigger: 'Manual' }
]

resource pgBackupJobs 'Microsoft.App/jobs@2024-03-01' = [for job in backupJobs: {
  name: job.name
  location: location
  properties: {
    environmentId: cae.id
    configuration: union({
      triggerType: job.trigger
      replicaTimeout: 1800
      replicaRetryLimit: 1
      secrets: [
        { name: 'db-pw', value: postgresPassword }
      ]
    }, job.trigger == 'Schedule' ? {
      scheduleTriggerConfig: { cronExpression: backupCron, parallelism: 1, replicaCompletionCount: 1 }
    } : {
      manualTriggerConfig: { parallelism: 1, replicaCompletionCount: 1 }
    })
    template: {
      containers: [
        {
          name: 'pg-backup'
          image: postgresImage
          command: [ 'bash', '-c', loadTextContent('pg-backup.sh') ]
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'PGHOST', value: postgres.name }
            { name: 'PGPORT', value: string(postgresPort) }
            { name: 'PGUSER', value: postgresUser }
            { name: 'PGPASSWORD', secretRef: 'db-pw' }
            { name: 'PGDATABASE', value: postgresDb }
          ]
          volumeMounts: [
            { volumeName: 'backup', mountPath: '/backup' }
          ]
        }
      ]
      volumes: [
        { name: 'backup', storageType: 'AzureFile', storageName: caeBackupStorage.name }
      ]
    }
  }
}]

// ─── Backend ───────────────────────────────────────────────────────────────

resource backend 'Microsoft.App/containerApps@2024-03-01' = {
  name: backendAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  dependsOn: [ acrPull ]
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      activeRevisionsMode: 'Single'
      // Alleen de frontend praat met de backend, binnen het environment.
      ingress: {
        external: false
        targetPort: 8000
        transport: 'auto'
        traffic: [ { weight: 100, latestRevision: true } ]
      }
      registries: [
        { server: acr.properties.loginServer, identity: uami.id }
      ]
      secrets: [
        {
          name: 'database-url'
          value: 'postgresql+asyncpg://${postgresUser}:${postgresPassword}@${postgres.name}:${postgresPort}/${postgresDb}'
        }
        { name: 'openai-endpoint', value: azureOpenAiEndpoint }
        { name: 'openai-api-key', value: azureOpenAiApiKey }
        { name: 'openai-embedding-endpoint', value: azureOpenAiEmbeddingEndpoint }
        { name: 'openai-embedding-api-key', value: azureOpenAiEmbeddingApiKey }
        { name: 'oidc-admin-client-secret', value: oidcAdminClientSecret }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: backendImage
          // docling (PDF-layout en tabellen) is CPU- en geheugenhongerig.
          resources: { cpu: json('2.0'), memory: '4Gi' }
          env: [
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'UPLOAD_DIR', value: '/data/uploads' }
            { name: 'CORS_ORIGINS', value: '["${effectivePublicUrl}"]' }

            { name: 'LLM_PROVIDER', value: 'azure_openai' }
            { name: 'AZURE_OPENAI_ENDPOINT', secretRef: 'openai-endpoint' }
            { name: 'AZURE_OPENAI_API_KEY', secretRef: 'openai-api-key' }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: azureOpenAiDeployment }
            { name: 'AZURE_OPENAI_API_VERSION', value: azureOpenAiApiVersion }
            { name: 'AZURE_OPENAI_EMBEDDING_ENDPOINT', secretRef: 'openai-embedding-endpoint' }
            { name: 'AZURE_OPENAI_EMBEDDING_API_KEY', secretRef: 'openai-embedding-api-key' }
            { name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT', value: azureOpenAiEmbeddingDeployment }
            { name: 'AZURE_OPENAI_EMBEDDING_API_VERSION', value: azureOpenAiEmbeddingApiVersion }
            // text-embedding-3-large teruggebracht naar de dimensie van het schema.
            { name: 'EMBED_DIM', value: '768' }

            { name: 'AUTH_MODE', value: 'oidc' }
            { name: 'OIDC_ISSUER', value: '${keycloakUrl}/realms/${keycloakRealm}' }
            { name: 'OIDC_AUDIENCE', value: 'finkennis-api' }
            { name: 'OIDC_ADMIN_CLIENT_ID', value: 'finkennis-admin' }
            { name: 'OIDC_ADMIN_CLIENT_SECRET', secretRef: 'oidc-admin-client-secret' }
          ]
          volumeMounts: [
            { volumeName: 'uploads', mountPath: '/data/uploads' }
          ]
        }
      ]
      volumes: [
        { name: 'uploads', storageType: 'AzureFile', storageName: caeStorage.name }
      ]
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

// ─── Frontend ──────────────────────────────────────────────────────────────

resource frontend 'Microsoft.App/containerApps@2024-03-01' = {
  name: frontendAppName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${uami.id}': {} }
  }
  dependsOn: [ acrPull ]
  properties: {
    managedEnvironmentId: cae.id
    configuration: {
      activeRevisionsMode: 'Single'
      // Het enige publieke oppervlak: nginx serveert de SPA en stuurt /api door.
      ingress: {
        external: true
        targetPort: 80
        transport: 'auto'
        traffic: [ { weight: 100, latestRevision: true } ]
        ipSecurityRestrictions: [for r in allowedIpRanges: {
          name: r.name
          description: r.name
          ipAddressRange: r.ipAddressRange
          action: 'Allow'
        }]
      }
      registries: [
        { server: acr.properties.loginServer, identity: uami.id }
      ]
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: frontendImage
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'BACKEND_URL', value: backendUrl }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

output frontendUrl string = 'https://${frontend.properties.configuration.ingress.fqdn}'
output publicUrl string = effectivePublicUrl
output backendInternalUrl string = backendUrl
output postgresHost string = '${postgres.name}:${postgresPort}'
output pgDumpJobName string = backupJobs[1].name
