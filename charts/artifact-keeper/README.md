# artifact-keeper

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 1.1.0](https://img.shields.io/badge/AppVersion-1.1.0-informational?style=flat-square)

Enterprise artifact registry supporting 45+ package formats

## TL;DR

```bash
helm repo add artifact-keeper https://artifact-keeper.github.io/artifact-keeper-iac/
helm repo update
helm install my-artifact-keeper artifact-keeper/artifact-keeper
```

## Introduction

This chart bootstraps an [Artifact Keeper](https://github.com/artifact-keeper/artifact-keeper) deployment on a [Kubernetes](https://kubernetes.io) cluster using the [Helm](https://helm.sh) package manager.

Artifact Keeper is an enterprise artifact registry supporting 45+ package formats including:
- Container images (Docker, OCI)
- Language packages (npm, Maven, PyPI, NuGet, etc.)
- Binaries and generic artifacts
- Integrated security scanning (Trivy, DependencyTrack)

## Prerequisites

- Kubernetes 1.24+
- Helm 3.8+
- PV provisioner support in the underlying infrastructure (for persistent storage)
- **Host kernel requirement**: `vm.max_map_count >= 262144` (required by Meilisearch)

```bash
# On cluster nodes:
sysctl -w vm.max_map_count=262144
echo "vm.max_map_count = 262144" >> /etc/sysctl.d/99-meilisearch.conf
```

## Installing the Chart

### From Helm Repository

```bash
helm repo add artifact-keeper https://artifact-keeper.github.io/artifact-keeper-iac/
helm repo update
helm install my-artifact-keeper artifact-keeper/artifact-keeper
```

### From Source

```bash
git clone https://github.com/artifact-keeper/artifact-keeper-iac.git
cd artifact-keeper-iac
helm install my-artifact-keeper ./charts/artifact-keeper
```

### With Custom Values

```bash
helm install my-artifact-keeper artifact-keeper/artifact-keeper \
  --set ingress.host=artifacts.mycompany.com \
  --set backend.replicaCount=3 \
  --set postgres.enabled=false \
  --set externalDatabase.host=postgres.example.com
```

Or using a values file:

```bash
helm install my-artifact-keeper artifact-keeper/artifact-keeper -f my-values.yaml
```

## Uninstalling the Chart

```bash
helm uninstall my-artifact-keeper
```

This removes all the Kubernetes resources associated with the chart and deletes the release.

**Note**: PersistentVolumeClaims are not automatically deleted. To remove them:

```bash
kubectl delete pvc -l app.kubernetes.io/instance=my-artifact-keeper
```

## Configuration

The following table lists the configurable parameters of the Artifact Keeper chart and their default values.

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend | object | `{"affinity":{},"autoscaling":{"enabled":false,"maxReplicas":10,"minReplicas":2,"targetCPUUtilization":70,"targetMemoryUtilization":80},"enabled":true,"env":{"ADMIN_PASSWORD":"admin","BACKUP_PATH":"/data/backups","ENVIRONMENT":"development","HOST":"0.0.0.0","PLUGINS_DIR":"/data/plugins","PORT":"8080","RUST_LOG":"info,artifact_keeper=debug","STORAGE_PATH":"/data/storage"},"image":{"pullPolicy":"Always","repository":"ghcr.io/artifact-keeper/artifact-keeper-backend","tag":"dev"},"nodeSelector":{},"persistence":{"enabled":true,"size":"10Gi","storageClass":""},"podDisruptionBudget":{"enabled":false,"minAvailable":1},"replicaCount":1,"resources":{"limits":{"cpu":"2","memory":"2Gi"},"requests":{"cpu":"250m","memory":"256Mi"}},"scanWorkspace":{"enabled":true,"size":"2Gi"},"service":{"grpcPort":9090,"httpPort":8080,"type":"ClusterIP"},"serviceAccount":{"annotations":{},"create":true,"name":""},"tolerations":[],"topologySpreadConstraints":[]}` | Backend API server The backend handles all API requests, format-specific wire protocols, and artifact storage. It runs as a single Rust binary (Axum). |
| backend.image.tag | string | `"dev"` | "dev" is a floating tag built from main. ArgoCD Image Updater pins this to a digest automatically. For manual deploys, consider using a specific version tag (e.g. 1.1.0). |
| backend.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| cosign | object | `{"certificateIdentityRegexp":"https://github.com/artifact-keeper/.*","certificateOidcIssuer":"https://token.actions.githubusercontent.com","enabled":false,"image":{"repository":"gcr.io/projectsigstore/cosign","tag":"v2.4.1"}}` | Cosign image signature verification When enabled, an init container verifies the backend image signature before the pod starts. Uses sigstore keyless verification (GitHub OIDC). |
| dependencyTrack | object | `{"adminPassword":"ArtifactKeeper2026!","affinity":{},"bootstrap":{"enabled":true},"enabled":true,"image":{"repository":"dependencytrack/apiserver","tag":"4.11.4"},"nodeSelector":{},"persistence":{"size":"5Gi","storageClass":""},"resources":{"limits":{"cpu":"2","memory":"6Gi"},"requests":{"cpu":"500m","memory":"4Gi"}},"tolerations":[],"topologySpreadConstraints":[]}` | DependencyTrack SBOM analysis Provides SBOM ingestion, license analysis, and vulnerability correlation. Requires significant memory (4Gi+) to load its internal vulnerability database on startup. The bootstrap init container creates the initial admin user and API key for backend integration. |
| dependencyTrack.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| edge | object | `{"affinity":{},"enabled":false,"env":{"CACHE_SIZE_MB":"10240","EDGE_HOST":"0.0.0.0","EDGE_PORT":"8081","HEARTBEAT_INTERVAL_SECS":"30","RUST_LOG":"info,artifact_keeper_edge=debug"},"image":{"pullPolicy":"Always","repository":"ghcr.io/artifact-keeper/artifact-keeper-edge","tag":"dev"},"nodeSelector":{},"podDisruptionBudget":{"enabled":false,"minAvailable":1},"replicaCount":1,"resources":{"limits":{"cpu":"500m","memory":"512Mi"},"requests":{"cpu":"50m","memory":"128Mi"}},"service":{"port":8081,"type":"ClusterIP"},"tolerations":[],"topologySpreadConstraints":[]}` | Edge replication service |
| edge.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| externalDatabase | object | `{"database":"artifact_registry","existingSecret":"","existingSecretKey":"DATABASE_URL","host":"","password":"","port":5432,"username":""}` | External database (used when postgres.enabled=false) |
| externalSecrets | object | `{"enabled":false,"refreshInterval":"1h","secrets":{"dbCredentials":"artifact-keeper/${ENVIRONMENT}/db-credentials","dtAdminPassword":"artifact-keeper/${ENVIRONMENT}/dt-admin-password","jwtSecret":"artifact-keeper/${ENVIRONMENT}/jwt-secret","meilisearchKey":"artifact-keeper/${ENVIRONMENT}/meilisearch-key","s3Keys":"artifact-keeper/${ENVIRONMENT}/s3-keys"},"storeKind":"ClusterSecretStore","storeName":"aws-secrets-manager"}` | External Secrets Operator When enabled, ExternalSecret CRDs replace the static Secret template. Requires External Secrets Operator installed on the cluster and a SecretStore or ClusterSecretStore configured for your provider. |
| fullnameOverride | string | `""` |  |
| global.affinity | object | `{}` |  |
| global.imagePullPolicy | string | `"Always"` |  |
| global.imageRegistry | string | `"ghcr.io/artifact-keeper"` |  |
| global.nodeSelector | object | `{}` |  |
| global.storageClass | string | `"standard"` |  |
| global.tolerations | list | `[]` | Scheduling constraints applied to ALL workloads by default. Per-component values (e.g. backend.nodeSelector) override these.  NOTE: Per-component values fully replace global, they do not merge. Setting backend.tolerations means the backend gets only those tolerations, not global + backend combined. There is currently no way to opt a single component out of global scheduling without setting its own values. |
| global.topologySpreadConstraints | list | `[]` |  |
| ingress | object | `{"annotations":{"nginx.ingress.kubernetes.io/enable-cors":"true","nginx.ingress.kubernetes.io/proxy-body-size":"1024m","nginx.ingress.kubernetes.io/proxy-read-timeout":"300","nginx.ingress.kubernetes.io/proxy-send-timeout":"300"},"className":"nginx","enabled":true,"host":"artifacts.example.com","tls":{"enabled":false,"secretName":"artifact-keeper-tls"}}` | Ingress configuration |
| meilisearch | object | `{"affinity":{},"enabled":true,"env":"development","image":{"repository":"getmeili/meilisearch","tag":"v1.12"},"masterKey":"artifact-keeper-dev-key","nodeSelector":{},"persistence":{"size":"5Gi","storageClass":""},"resources":{"limits":{"cpu":"2","memory":"8Gi"},"requests":{"cpu":"250m","memory":"512Mi"}},"tolerations":[],"topologySpreadConstraints":[]}` | Meilisearch (full-text search engine) Powers full-text artifact search. Uses LMDB for storage (requires vm.max_map_count >= 262144 on the host). The template hardcodes MEILI_MAX_INDEXING_THREADS=4 to limit indexing parallelism.  Memory sizing: Meilisearch spawns one actix HTTP worker per CPU core. On a 28-core host, 28 workers start up simultaneously. With the default 1Gi limit this causes immediate OOMKill. Set the limit to at least 4Gi, or higher if the search index is large.  The deployment uses Recreate strategy because the PVC-backed LMDB database cannot be opened by two pods at once. Do not change this to RollingUpdate or new pods will crash with "Resource temporarily unavailable (os error 11)". |
| meilisearch.image.tag | string | `"v1.12"` | Use a major.minor tag (e.g. v1.12) for automatic patch updates, or pin to a specific patch (e.g. v1.12.8) for stability. |
| meilisearch.resources.limits.memory | string | `"8Gi"` | Must be >= 4Gi on multi-core nodes. 8Gi recommended for nodes with 16+ cores. See Memory sizing note above. |
| meilisearch.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| nameOverride | string | `""` |  |
| networkPolicy | object | `{"enabled":false}` | Network policies |
| postgres | object | `{"affinity":{},"auth":{"database":"artifact_registry","password":"registry","username":"registry"},"enabled":true,"image":{"repository":"postgres","tag":"16-alpine"},"initDb":{"enabled":true},"nodeSelector":{},"persistence":{"size":"20Gi","storageClass":""},"resources":{"limits":{"cpu":"1","memory":"1Gi"},"requests":{"cpu":"250m","memory":"256Mi"}},"tolerations":[],"topologySpreadConstraints":[]}` | PostgreSQL (in-cluster, disable for external/RDS) For production, set postgres.enabled=false and configure externalDatabase to point at a managed database (RDS, Cloud SQL, etc.). The in-cluster instance is suitable for dev/testing only. |
| postgres.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| secrets | object | `{"jwtSecret":"dev-secret-change-in-production","s3AccessKey":"minioadmin","s3SecretKey":"minioadmin-secret"}` | Secrets These are development defaults. For production, override via --set or use existingSecret references. Never commit real credentials here. |
| serviceMonitor | object | `{"enabled":false,"interval":"30s","scrapeTimeout":"10s"}` | Prometheus ServiceMonitor |
| trivy | object | `{"affinity":{},"enabled":true,"image":{"repository":"aquasec/trivy","tag":"latest"},"nodeSelector":{},"persistence":{"size":"5Gi","storageClass":""},"resources":{"limits":{"cpu":"1","memory":"2Gi"},"requests":{"cpu":"250m","memory":"256Mi"}},"tolerations":[],"topologySpreadConstraints":[]}` | Trivy vulnerability scanner Runs as a persistent server that the backend calls for image/SBOM scans. Uses a PVC for its vulnerability database cache. Like Meilisearch, the deployment uses Recreate strategy because the cache directory uses a file lock that prevents concurrent access from two pods. |
| trivy.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| web | object | `{"affinity":{},"enabled":true,"env":{"NEXT_PUBLIC_API_URL":"","NODE_ENV":"production"},"image":{"pullPolicy":"Always","repository":"ghcr.io/artifact-keeper/artifact-keeper-web","tag":"dev"},"nodeSelector":{},"podDisruptionBudget":{"enabled":false,"minAvailable":1},"replicaCount":1,"resources":{"limits":{"cpu":"1","ephemeral-storage":"2Gi","memory":"1Gi"},"requests":{"cpu":"250m","memory":"256Mi"}},"service":{"port":3000,"type":"ClusterIP"},"tolerations":[],"topologySpreadConstraints":[]}` | Next.js web frontend |
| web.tolerations | list | `[]` | Per-component scheduling (overrides global) |

## Deployment Profiles

The chart includes several pre-configured value files for different deployment scenarios:

### Development (values.yaml)
- Single replica deployments
- In-cluster PostgreSQL
- Minimal resource requests
- Suitable for local testing

```bash
helm install my-artifact-keeper artifact-keeper/artifact-keeper
```

### Staging (values-staging.yaml)
- 2 replicas for HA testing
- External database recommended
- Moderate resource limits
- Monitoring enabled

```bash
helm install my-artifact-keeper artifact-keeper/artifact-keeper -f values-staging.yaml
```

### Production (values-production.yaml)
- High availability (3+ replicas)
- External managed database required
- Production-grade resource limits
- Full monitoring and security features
- Pod Disruption Budgets enabled
- HorizontalPodAutoscaler configured

```bash
helm install my-artifact-keeper artifact-keeper/artifact-keeper -f values-production.yaml
```

### Mesh Networking
For multi-region or edge deployments:

**Main Hub (values-mesh-main.yaml)**:
```bash
helm install artifact-keeper-main artifact-keeper/artifact-keeper -f values-mesh-main.yaml
```

**Peer/Edge Node (values-mesh-peer.yaml)**:
```bash
helm install artifact-keeper-peer artifact-keeper/artifact-keeper -f values-mesh-peer.yaml
```

## Architecture

The chart deploys the following components:

- **Backend**: Core API server handling artifact storage and retrieval (Rust/Axum)
- **Web**: Next.js frontend for the web UI
- **PostgreSQL**: Metadata and configuration database (optional, external database recommended for production)
- **Meilisearch**: Full-text search engine for artifact discovery
- **Trivy**: Vulnerability scanner for containers and SBOMs
- **DependencyTrack**: SBOM analysis and license compliance
- **Edge** (optional): Edge replication service for distributed deployments

## Storage

The chart creates PersistentVolumeClaims for:

- **Backend artifacts**: Default 10Gi (configurable via `backend.persistence.size`)
- **PostgreSQL data**: Default 20Gi (configurable via `postgres.persistence.size`)
- **Meilisearch index**: Default 5Gi (configurable via `meilisearch.persistence.size`)
- **Trivy cache**: Default 5Gi (configurable via `trivy.persistence.size`)
- **DependencyTrack data**: Default 5Gi (configurable via `dependencyTrack.persistence.size`)

Specify a custom `storageClass` globally or per-component:

```yaml
global:
  storageClass: "fast-ssd"

# Or per-component:
backend:
  persistence:
    storageClass: "fast-ssd"
```

## Ingress

The chart includes an Ingress resource that can be enabled:

```yaml
ingress:
  enabled: true
  className: nginx
  host: artifacts.example.com
  tls:
    enabled: true
    secretName: artifact-keeper-tls
```

For TLS, create the secret before installing:

```bash
kubectl create secret tls artifact-keeper-tls \
  --cert=path/to/tls.crt \
  --key=path/to/tls.key
```

## Security

### Image Signature Verification

Enable Cosign verification to validate signed images:

```yaml
cosign:
  enabled: true
  certificateOidcIssuer: "https://token.actions.githubusercontent.com"
  certificateIdentityRegexp: "https://github.com/artifact-keeper/.*"
```

### Network Policies

Enable network policies to restrict pod-to-pod communication:

```yaml
networkPolicy:
  enabled: true
```

### Secrets Management

For production, use Kubernetes secrets or external secret managers:

```yaml
secrets:
  jwtSecret: "your-secure-jwt-secret"
 
externalDatabase:
  existingSecret: "postgres-credentials"
  existingSecretKey: "DATABASE_URL"
```

## Monitoring

Enable Prometheus ServiceMonitor for metrics collection:

```yaml
serviceMonitor:
  enabled: true
  interval: 30s
```

Metrics are exposed on `/metrics` endpoint for each service.

## High Availability

For production HA deployments:

```yaml
backend:
  replicaCount: 3
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10
    targetCPUUtilization: 70
  podDisruptionBudget:
    enabled: true
    minAvailable: 2
 
  affinity:
    podAntiAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 100
          podAffinityTerm:
            labelSelector:
              matchExpressions:
                - key: app.kubernetes.io/name
                  operator: In
                  values:
                    - artifact-keeper
            topologyKey: kubernetes.io/hostname
```

## Upgrading

### Upgrading the Chart

```bash
helm repo update
helm upgrade my-artifact-keeper artifact-keeper/artifact-keeper
```

### Upgrading with New Values

```bash
helm upgrade my-artifact-keeper artifact-keeper/artifact-keeper -f updated-values.yaml
```

### Rolling Back

```bash
helm rollback my-artifact-keeper
```

## Troubleshooting

### Meilisearch OOMKilled

If Meilisearch pods are killed due to OOM:

```yaml
meilisearch:
  resources:
    limits:
      memory: 8Gi  # Increase based on node CPU cores
```

### Backend Storage Issues

Check PVC status:

```bash
kubectl get pvc -l app.kubernetes.io/instance=my-artifact-keeper
kubectl describe pvc <pvc-name>
```

### Database Connection Issues

Verify database connectivity:

```bash
kubectl logs -l app.kubernetes.io/component=backend -f
```

### Viewing Logs

```bash
# Backend logs
kubectl logs -l app.kubernetes.io/component=backend -f

# Web frontend logs
kubectl logs -l app.kubernetes.io/component=web -f

# All components
kubectl logs -l app.kubernetes.io/instance=my-artifact-keeper --all-containers -f
```

## Development

### Local Testing

```bash
# Lint the chart
helm lint charts/artifact-keeper/

# Template and verify
helm template my-artifact-keeper charts/artifact-keeper/ --debug

# Dry-run install
helm install my-artifact-keeper charts/artifact-keeper/ --dry-run --debug

# Install in a test namespace
kubectl create namespace artifact-keeper-test
helm install my-artifact-keeper charts/artifact-keeper/ -n artifact-keeper-test
```

### Updating Documentation

This README is auto-generated using [helm-docs](https://github.com/norwoodj/helm-docs).

To regenerate after changing values:

```bash
# Install helm-docs
brew install norwoodj/tap/helm-docs  # macOS
# or
go install github.com/norwoodj/helm-docs/cmd/helm-docs@latest

# Generate documentation
helm-docs charts/artifact-keeper/
```

The documentation is automatically generated on PR by GitHub Actions.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes to the `charts/artifact-keeper/` directory
4. **Bump the version** in `charts/artifact-keeper/Chart.yaml` (required for releases)
5. Run `helm-docs charts/artifact-keeper/` to update the README
6. Test your changes locally
7. Submit a pull request

All PRs undergo:
- Helm lint validation
- Chart installation testing in kind
- Security scanning
- Version bump verification

**Homepage:** <https://artifactkeeper.com>

## Source Code

* <https://github.com/artifact-keeper/artifact-keeper>

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| brandonrc |  |  |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
