# artifact-keeper

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 1.1.0](https://img.shields.io/badge/AppVersion-1.1.0-informational?style=flat-square)

## TL;DR

```bash
helm repo add artifact-keeper https://artifact-keeper.github.io/artifact-keeper-iac/
helm repo update
helm install ak artifact-keeper/artifact-keeper \
  --namespace artifact-keeper \
  --create-namespace
```

## Introduction

This chart deploys [Artifact Keeper](https://github.com/artifact-keeper/artifact-keeper), an enterprise artifact registry supporting 45+ package formats (Maven, npm, PyPI, Docker/OCI, Cargo, NuGet, and many more). The chart packages the backend API, web frontend, and all supporting services into a single Helm release with per-component toggles.

All files in this chart are provided as example configurations. Review and modify them to match your specific infrastructure requirements, security policies, and operational needs before use in production.

## Prerequisites

- Kubernetes 1.26+
- Helm 3.12+
- PV provisioner support in the underlying infrastructure
- `vm.max_map_count >= 262144` on nodes running Meilisearch (required by LMDB)

To set `vm.max_map_count` on your nodes:

```bash
sysctl -w vm.max_map_count=262144
echo "vm.max_map_count = 262144" >> /etc/sysctl.d/99-meilisearch.conf
```

## Installing the Chart

Install the chart with the release name `ak`:

```bash
helm install ak artifact-keeper/artifact-keeper \
  --namespace artifact-keeper \
  --create-namespace
```

Or install from a local checkout:

```bash
git clone https://github.com/artifact-keeper/artifact-keeper-iac.git
cd artifact-keeper-iac
helm install ak charts/artifact-keeper/ \
  --namespace artifact-keeper \
  --create-namespace
```

These commands deploy Artifact Keeper with the default development configuration. See the [Values](#values) section for the full list of configurable parameters.

## Uninstalling the Chart

```bash
helm uninstall ak --namespace artifact-keeper
```

This removes all Kubernetes resources associated with the release. PersistentVolumeClaims are not deleted automatically. To remove them:

```bash
kubectl delete pvc -l app.kubernetes.io/instance=ak -n artifact-keeper
```

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| backend | object | `{"affinity":{},"autoscaling":{"enabled":false,"maxReplicas":10,"minReplicas":2,"targetCPUUtilization":70,"targetMemoryUtilization":80},"enabled":true,"env":{"ADMIN_PASSWORD":"admin","BACKUP_PATH":"/data/backups","ENVIRONMENT":"development","HOST":"0.0.0.0","PLUGINS_DIR":"/data/plugins","PORT":"8080","RUST_LOG":"info,artifact_keeper=debug","STORAGE_PATH":"/data/storage"},"image":{"pullPolicy":"Always","repository":"ghcr.io/artifact-keeper/artifact-keeper-backend","tag":"dev"},"nodeSelector":{},"persistence":{"enabled":true,"size":"10Gi","storageClass":""},"podDisruptionBudget":{"enabled":false,"minAvailable":1},"replicaCount":1,"resources":{"limits":{"cpu":"2","ephemeral-storage":"1Gi","memory":"2Gi"},"requests":{"cpu":"250m","ephemeral-storage":"256Mi","memory":"256Mi"}},"scanWorkspace":{"enabled":true,"size":"2Gi"},"service":{"grpcPort":9090,"httpPort":8080,"type":"ClusterIP"},"serviceAccount":{"annotations":{},"create":true,"name":""},"tolerations":[],"topologySpreadConstraints":[]}` | Backend API server The backend handles all API requests, format-specific wire protocols, and artifact storage. It runs as a single Rust binary (Axum). |
| backend.image.tag | string | `"dev"` | "dev" is a floating tag built from main. ArgoCD Image Updater pins this to a digest automatically. For manual deploys, consider using a specific version tag (e.g. 1.1.0). |
| backend.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| cosign | object | `{"certificateIdentityRegexp":"https://github.com/artifact-keeper/.*","certificateOidcIssuer":"https://token.actions.githubusercontent.com","enabled":false,"image":{"repository":"gcr.io/projectsigstore/cosign","tag":"v2.4.1"}}` | Cosign image signature verification When enabled, an init container verifies the backend image signature before the pod starts. Uses sigstore keyless verification (GitHub OIDC). |
| dependencyTrack | object | `{"adminPassword":"ArtifactKeeper2026!","affinity":{},"bootstrap":{"enabled":true},"enabled":true,"image":{"repository":"dependencytrack/apiserver","tag":"4.11.4"},"nodeSelector":{},"persistence":{"size":"5Gi","storageClass":""},"resources":{"limits":{"cpu":"2","ephemeral-storage":"1Gi","memory":"6Gi"},"requests":{"cpu":"500m","ephemeral-storage":"256Mi","memory":"4Gi"}},"tolerations":[],"topologySpreadConstraints":[]}` | DependencyTrack SBOM analysis Provides SBOM ingestion, license analysis, and vulnerability correlation. Requires significant memory (4Gi+) to load its internal vulnerability database on startup. The bootstrap init container creates the initial admin user and API key for backend integration. |
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
| meilisearch | object | `{"affinity":{},"enabled":true,"env":"development","image":{"repository":"getmeili/meilisearch","tag":"v1.12"},"masterKey":"artifact-keeper-dev-key","nodeSelector":{},"persistence":{"size":"5Gi","storageClass":""},"resources":{"limits":{"cpu":"2","ephemeral-storage":"512Mi","memory":"8Gi"},"requests":{"cpu":"250m","ephemeral-storage":"128Mi","memory":"512Mi"}},"tolerations":[],"topologySpreadConstraints":[]}` | Meilisearch (full-text search engine) Powers full-text artifact search. Uses LMDB for storage (requires vm.max_map_count >= 262144 on the host). The template hardcodes MEILI_MAX_INDEXING_THREADS=4 to limit indexing parallelism.  Memory sizing: Meilisearch spawns one actix HTTP worker per CPU core. On a 28-core host, 28 workers start up simultaneously. With the default 1Gi limit this causes immediate OOMKill. Set the limit to at least 4Gi, or higher if the search index is large.  The deployment uses Recreate strategy because the PVC-backed LMDB database cannot be opened by two pods at once. Do not change this to RollingUpdate or new pods will crash with "Resource temporarily unavailable (os error 11)". |
| meilisearch.image.tag | string | `"v1.12"` | Use a major.minor tag (e.g. v1.12) for automatic patch updates, or pin to a specific patch (e.g. v1.12.8) for stability. |
| meilisearch.resources.limits.memory | string | `"8Gi"` | Must be >= 4Gi on multi-core nodes. 8Gi recommended for nodes with 16+ cores. See Memory sizing note above. |
| meilisearch.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| nameOverride | string | `""` |  |
| networkPolicy | object | `{"enabled":false}` | Network policies |
| postgres | object | `{"affinity":{},"auth":{"database":"artifact_registry","password":"registry","username":"registry"},"enabled":true,"image":{"repository":"postgres","tag":"16-alpine"},"initDb":{"enabled":true},"nodeSelector":{},"persistence":{"size":"20Gi","storageClass":""},"resources":{"limits":{"cpu":"1","ephemeral-storage":"512Mi","memory":"1Gi"},"requests":{"cpu":"250m","ephemeral-storage":"128Mi","memory":"256Mi"}},"tolerations":[],"topologySpreadConstraints":[]}` | PostgreSQL (in-cluster, disable for external/RDS) For production, set postgres.enabled=false and configure externalDatabase to point at a managed database (RDS, Cloud SQL, etc.). The in-cluster instance is suitable for dev/testing only. |
| postgres.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| secrets | object | `{"jwtSecret":"dev-secret-change-in-production","s3AccessKey":"minioadmin","s3SecretKey":"minioadmin-secret"}` | Secrets These are development defaults. For production, override via --set or use existingSecret references. Never commit real credentials here. |
| serviceMonitor | object | `{"enabled":false,"interval":"30s","scrapeTimeout":"10s"}` | Prometheus ServiceMonitor |
| trivy | object | `{"affinity":{},"enabled":true,"image":{"repository":"aquasec/trivy","tag":"0.62.1"},"nodeSelector":{},"persistence":{"size":"5Gi","storageClass":""},"resources":{"limits":{"cpu":"1","ephemeral-storage":"1Gi","memory":"2Gi"},"requests":{"cpu":"250m","ephemeral-storage":"128Mi","memory":"256Mi"}},"tolerations":[],"topologySpreadConstraints":[]}` | Trivy vulnerability scanner Runs as a persistent server that the backend calls for image/SBOM scans. Uses a PVC for its vulnerability database cache. Like Meilisearch, the deployment uses Recreate strategy because the cache directory uses a file lock that prevents concurrent access from two pods. |
| trivy.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| web | object | `{"affinity":{},"enabled":true,"env":{"NEXT_PUBLIC_API_URL":"","NODE_ENV":"production"},"image":{"pullPolicy":"Always","repository":"ghcr.io/artifact-keeper/artifact-keeper-web","tag":"dev"},"nodeSelector":{},"podDisruptionBudget":{"enabled":false,"minAvailable":1},"replicaCount":1,"resources":{"limits":{"cpu":"1","ephemeral-storage":"2Gi","memory":"1Gi"},"requests":{"cpu":"250m","ephemeral-storage":"256Mi","memory":"256Mi"}},"service":{"port":3000,"type":"ClusterIP"},"tolerations":[],"topologySpreadConstraints":[]}` | Next.js web frontend |
| web.tolerations | list | `[]` | Per-component scheduling (overrides global) |

## Deployment Profiles

The chart ships with several values overlay files for common deployment scenarios.

### Development (default)

The base `values.yaml` targets a single-node dev cluster. All services run in-cluster, autoscaling and network policies are disabled, and resource requests are kept small.

```bash
helm install ak charts/artifact-keeper/ \
  --namespace artifact-keeper \
  --create-namespace
```

### Staging

Enables autoscaling, PodDisruptionBudgets, network policies, and ServiceMonitor. PostgreSQL remains in-cluster. TLS is enabled.

```bash
helm install ak charts/artifact-keeper/ \
  -f charts/artifact-keeper/values-staging.yaml \
  --namespace artifact-keeper \
  --create-namespace
```

### Production

Designed for multi-node clusters with external RDS. Enables HPA (up to 20 replicas), PDBs, network policies, TLS via cert-manager, External Secrets Operator integration, and 15-second monitoring scrape intervals. In-cluster PostgreSQL is disabled in favor of a managed database.

```bash
helm install ak charts/artifact-keeper/ \
  -f charts/artifact-keeper/values-production.yaml \
  --namespace artifact-keeper \
  --create-namespace \
  --set ingress.host=registry.example.com \
  --set externalDatabase.host=your-rds-endpoint.amazonaws.com \
  --set secrets.jwtSecret=$(openssl rand -base64 64)
```

### Mesh (Multi-Instance Replication)

Two overlay files support multi-instance mesh testing via ArgoCD:

- `values-mesh-main.yaml` configures the primary instance with peer identity and public endpoint.
- `values-mesh-peer.yaml` configures peer instances with reduced resource footprints.

Both use `fullnameOverride` for stable service names and disable non-essential components (Trivy, DependencyTrack, ingress).

## Architecture

The chart deploys the following components:

| Component | Description | Default |
|-----------|-------------|---------|
| **Backend** | Rust (Axum) API server handling all format-specific wire protocols | Enabled |
| **Web** | Next.js 15 frontend | Enabled |
| **Edge** | Edge replication service for distributed deployments | Disabled |
| **PostgreSQL** | In-cluster database (disable for external/managed DB) | Enabled |
| **Meilisearch** | Full-text search engine for artifact discovery | Enabled |
| **Trivy** | Vulnerability scanner for container images and SBOMs | Enabled |
| **DependencyTrack** | SBOM analysis platform for license and vulnerability correlation | Enabled |

### Component Diagram

```
Ingress
  |
  +-- /api/* --> Backend (port 8080, gRPC 9090)
  +-- /*     --> Web (port 3000)

Backend --> PostgreSQL (port 5432)
Backend --> Meilisearch (port 7700)
Backend --> Trivy (port 8090)
Backend --> DependencyTrack (port 8080)
```

## Storage

Services that use PersistentVolumeClaims (Meilisearch, Trivy, DependencyTrack) run with the Recreate deployment strategy. This prevents two pods from competing for the same volume lock during rolling updates. Do not change these to RollingUpdate.

The backend uses two PVCs: one for artifact storage and one for scan workspace (temp files during security scans). Both can be sized independently.

| Component | Default Size | Purpose |
|-----------|-------------|---------|
| Backend storage | 10Gi | Artifact file storage |
| Backend scan workspace | 2Gi | Temporary scan files |
| PostgreSQL | 20Gi | Database files |
| Meilisearch | 5Gi | Search index (LMDB) |
| Trivy | 5Gi | Vulnerability database cache |
| DependencyTrack | 5Gi | Internal vulnerability database |

## Ingress

The chart creates a single Ingress resource that routes traffic to the backend and web frontend. By default it uses the `nginx` IngressClass with a 1024m proxy body size limit (for large artifact uploads) and 300-second timeouts.

To enable TLS with cert-manager:

```yaml
ingress:
  host: registry.example.com
  tls:
    enabled: true
    secretName: artifact-keeper-tls
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
```

## Security

### Cosign Image Verification

When `cosign.enabled` is set to `true`, an init container verifies the backend image signature before the pod starts. This uses sigstore keyless verification with GitHub OIDC, confirming the image was built by the Artifact Keeper CI pipeline.

### Network Policies

When `networkPolicy.enabled` is set to `true`, the chart creates NetworkPolicy resources that restrict traffic between components. Only the required communication paths are allowed (for example, backend to PostgreSQL, backend to Meilisearch).

### Secrets Management

For development, secrets are stored directly in the chart's Secret template. For production, two options exist:

1. **External overrides**: Pass secrets via `--set` flags or external values files that are not committed to version control.
2. **External Secrets Operator**: Set `externalSecrets.enabled: true` to pull secrets from AWS Secrets Manager (or another provider) using ExternalSecret CRDs.

### Security Contexts

All deployments include restrictive security contexts: non-root users, read-only root filesystems where possible, and dropped capabilities.

## Monitoring

Set `serviceMonitor.enabled: true` to create a Prometheus ServiceMonitor that scrapes the backend's `/metrics` endpoint. The scrape interval defaults to 30 seconds and can be adjusted via `serviceMonitor.interval`.

The [monitoring/](../../monitoring/) directory contains a pre-built Grafana dashboard (12 panels across 4 rows) and 7 PrometheusRule alert definitions covering error rates, latency, pod health, storage usage, and database connectivity.

## High Availability

For production deployments:

- Set `backend.replicaCount: 3` (or higher) and enable `backend.autoscaling` to scale based on CPU and memory utilization.
- Enable `backend.podDisruptionBudget` to ensure at least N replicas remain available during voluntary disruptions.
- Use `backend.affinity` with pod anti-affinity to spread replicas across nodes.
- Disable in-cluster PostgreSQL (`postgres.enabled: false`) and point `externalDatabase` at a managed, multi-AZ database like Amazon RDS.
- Meilisearch and DependencyTrack run as single replicas due to PVC lock constraints. Plan maintenance windows for upgrades.

## Upgrading

### Image Tags

The default `dev` tag is a floating tag that always points to the latest build from main. When using ArgoCD, the Image Updater pins these to specific digests so rollouts are deterministic. For manual deployments, consider using a specific version tag (e.g. `1.1.0`).

Docker tags use semver without a `v` prefix: git tag `v1.1.0` produces Docker tag `1.1.0`.

### Container Registry

Images are published to `ghcr.io/artifact-keeper/artifact-keeper-{backend,web}` by default. Docker Hub mirrors are available at `docker.io/artifactkeeper/{backend,web}`. Change the registry via `global.imageRegistry` or per-component `image.repository` values.

## Troubleshooting

### Meilisearch OOMKill

Meilisearch spawns one HTTP worker per CPU core. On a 28-core node, 28 workers start simultaneously, easily exceeding a 1Gi memory limit. Set `meilisearch.resources.limits.memory` to at least 4Gi. The chart defaults to 8Gi.

### Meilisearch "Resource temporarily unavailable"

This error (os error 11) means two pods are trying to open the same LMDB database. The Meilisearch deployment uses the Recreate strategy to prevent this. Do not change it to RollingUpdate.

### DependencyTrack Slow Startup

DependencyTrack loads its vulnerability database on first boot, which requires 4Gi+ of memory and can take several minutes. The readiness probe is configured with a generous initial delay. If the pod is killed before initialization completes, increase `dependencyTrack.resources.limits.memory`.

### Backend PVC Permissions

If the backend fails to write artifacts, verify that the PVC is writable by the container user. The init container in the backend deployment sets ownership to the correct UID.

## Development

### Generating Documentation

This README is generated by [helm-docs](https://github.com/norwoodj/helm-docs). After modifying `values.yaml`, regenerate it:

```bash
cd charts/artifact-keeper
helm-docs
```

The CI pipeline verifies that the README is up to date on every pull request. If it detects a drift, the build will fail with instructions to run helm-docs locally.

### Linting

```bash
helm lint charts/artifact-keeper/
helm template ak charts/artifact-keeper/ > /dev/null
helm template ak charts/artifact-keeper/ -f charts/artifact-keeper/values-production.yaml > /dev/null
```

## Contributing

1. Fork the repository and create a feature branch.
2. Make your changes to `values.yaml`, templates, or overlay files.
3. Run `helm-docs` in the `charts/artifact-keeper/` directory to regenerate the README.
4. Run `helm lint` and `helm template` to validate the chart.
5. Open a pull request against the `main` branch.

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
