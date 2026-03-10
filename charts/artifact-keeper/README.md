# artifact-keeper

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 1.1.0](https://img.shields.io/badge/AppVersion-1.1.0-informational?style=flat-square)

Enterprise artifact registry supporting 45+ package formats

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
| global.imageRegistry | string | `"ghcr.io/artifact-keeper"` |  |
| global.imagePullPolicy | string | `"Always"` |  |
| global.storageClass | string | `"standard"` |  |
| global.tolerations | list | `[]` | Scheduling constraints applied to ALL workloads by default. Per-component values (e.g. backend.nodeSelector) override these.  NOTE: Per-component values fully replace global, they do not merge. Setting backend.tolerations means the backend gets only those tolerations, not global + backend combined. There is currently no way to opt a single component out of global scheduling without setting its own values. |
| global.affinity | object | `{}` |  |
| global.nodeSelector | object | `{}` |  |
| global.topologySpreadConstraints | list | `[]` |  |
| nameOverride | string | `""` |  |
| fullnameOverride | string | `""` |  |
| cosign.enabled | bool | `false` | Cosign image signature verification When enabled, an init container verifies the backend image signature before the pod starts. Uses sigstore keyless verification (GitHub OIDC). |
| cosign.image.repository | string | `"gcr.io/projectsigstore/cosign"` |  |
| cosign.image.tag | string | `"v2.4.1"` |  |
| cosign.certificateOidcIssuer | string | `"https://token.actions.githubusercontent.com"` |  |
| cosign.certificateIdentityRegexp | string | `"https://github.com/artifact-keeper/.*"` |  |
| backend.enabled | bool | `true` | Backend API server The backend handles all API requests, format-specific wire protocols, and artifact storage. It runs as a single Rust binary (Axum). |
| backend.replicaCount | int | `1` |  |
| backend.image.repository | string | `"ghcr.io/artifact-keeper/artifact-keeper-backend"` |  |
| backend.image.tag | string | `"dev"` | "dev" is a floating tag built from main. ArgoCD Image Updater pins this to a digest automatically. For manual deploys, consider using a specific version tag (e.g. 1.1.0). |
| backend.image.pullPolicy | string | `"Always"` |  |
| backend.service.type | string | `"ClusterIP"` |  |
| backend.service.httpPort | int | `8080` |  |
| backend.service.grpcPort | int | `9090` |  |
| backend.env.RUST_LOG | string | `"info,artifact_keeper=debug"` |  |
| backend.env.HOST | string | `"0.0.0.0"` |  |
| backend.env.PORT | string | `"8080"` |  |
| backend.env.STORAGE_PATH | string | `"/data/storage"` |  |
| backend.env.BACKUP_PATH | string | `"/data/backups"` |  |
| backend.env.PLUGINS_DIR | string | `"/data/plugins"` |  |
| backend.env.ENVIRONMENT | string | `"development"` |  |
| backend.env.ADMIN_PASSWORD | string | `"admin"` |  |
| backend.resources.requests.cpu | string | `"250m"` |  |
| backend.resources.requests.memory | string | `"256Mi"` |  |
| backend.resources.limits.cpu | string | `"2"` |  |
| backend.resources.limits.memory | string | `"2Gi"` |  |
| backend.persistence.enabled | bool | `true` |  |
| backend.persistence.size | string | `"10Gi"` |  |
| backend.persistence.storageClass | string | `""` |  |
| backend.scanWorkspace.enabled | bool | `true` |  |
| backend.scanWorkspace.size | string | `"2Gi"` |  |
| backend.autoscaling.enabled | bool | `false` |  |
| backend.autoscaling.minReplicas | int | `2` |  |
| backend.autoscaling.maxReplicas | int | `10` |  |
| backend.autoscaling.targetCPUUtilization | int | `70` |  |
| backend.autoscaling.targetMemoryUtilization | int | `80` |  |
| backend.podDisruptionBudget.enabled | bool | `false` |  |
| backend.podDisruptionBudget.minAvailable | int | `1` |  |
| backend.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| backend.affinity | object | `{}` |  |
| backend.nodeSelector | object | `{}` |  |
| backend.topologySpreadConstraints | list | `[]` |  |
| backend.serviceAccount.create | bool | `true` |  |
| backend.serviceAccount.annotations | object | `{}` |  |
| backend.serviceAccount.name | string | `""` |  |
| web.enabled | bool | `true` | Next.js web frontend |
| web.replicaCount | int | `1` |  |
| web.image.repository | string | `"ghcr.io/artifact-keeper/artifact-keeper-web"` |  |
| web.image.tag | string | `"dev"` |  |
| web.image.pullPolicy | string | `"Always"` |  |
| web.service.type | string | `"ClusterIP"` |  |
| web.service.port | int | `3000` |  |
| web.env.NEXT_PUBLIC_API_URL | string | `""` |  |
| web.env.NODE_ENV | string | `"production"` |  |
| web.resources.requests.cpu | string | `"250m"` |  |
| web.resources.requests.memory | string | `"256Mi"` |  |
| web.resources.limits.cpu | string | `"1"` |  |
| web.resources.limits.memory | string | `"1Gi"` |  |
| web.resources.limits.ephemeral-storage | string | `"2Gi"` |  |
| web.podDisruptionBudget.enabled | bool | `false` |  |
| web.podDisruptionBudget.minAvailable | int | `1` |  |
| web.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| web.affinity | object | `{}` |  |
| web.nodeSelector | object | `{}` |  |
| web.topologySpreadConstraints | list | `[]` |  |
| edge.enabled | bool | `false` | Edge replication service |
| edge.replicaCount | int | `1` |  |
| edge.image.repository | string | `"ghcr.io/artifact-keeper/artifact-keeper-edge"` |  |
| edge.image.tag | string | `"dev"` |  |
| edge.image.pullPolicy | string | `"Always"` |  |
| edge.service.type | string | `"ClusterIP"` |  |
| edge.service.port | int | `8081` |  |
| edge.env.RUST_LOG | string | `"info,artifact_keeper_edge=debug"` |  |
| edge.env.EDGE_HOST | string | `"0.0.0.0"` |  |
| edge.env.EDGE_PORT | string | `"8081"` |  |
| edge.env.CACHE_SIZE_MB | string | `"10240"` |  |
| edge.env.HEARTBEAT_INTERVAL_SECS | string | `"30"` |  |
| edge.resources.requests.cpu | string | `"50m"` |  |
| edge.resources.requests.memory | string | `"128Mi"` |  |
| edge.resources.limits.cpu | string | `"500m"` |  |
| edge.resources.limits.memory | string | `"512Mi"` |  |
| edge.podDisruptionBudget.enabled | bool | `false` |  |
| edge.podDisruptionBudget.minAvailable | int | `1` |  |
| edge.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| edge.affinity | object | `{}` |  |
| edge.nodeSelector | object | `{}` |  |
| edge.topologySpreadConstraints | list | `[]` |  |
| postgres.enabled | bool | `true` | PostgreSQL (in-cluster, disable for external/RDS) For production, set postgres.enabled=false and configure externalDatabase to point at a managed database (RDS, Cloud SQL, etc.). The in-cluster instance is suitable for dev/testing only. |
| postgres.image.repository | string | `"postgres"` |  |
| postgres.image.tag | string | `"16-alpine"` |  |
| postgres.auth.username | string | `"registry"` |  |
| postgres.auth.password | string | `"registry"` |  |
| postgres.auth.database | string | `"artifact_registry"` |  |
| postgres.persistence.size | string | `"20Gi"` |  |
| postgres.persistence.storageClass | string | `""` |  |
| postgres.resources.requests.cpu | string | `"250m"` |  |
| postgres.resources.requests.memory | string | `"256Mi"` |  |
| postgres.resources.limits.cpu | string | `"1"` |  |
| postgres.resources.limits.memory | string | `"1Gi"` |  |
| postgres.initDb.enabled | bool | `true` |  |
| postgres.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| postgres.affinity | object | `{}` |  |
| postgres.nodeSelector | object | `{}` |  |
| postgres.topologySpreadConstraints | list | `[]` |  |
| externalDatabase.host | string | `""` | External database (used when postgres.enabled=false) |
| externalDatabase.port | int | `5432` |  |
| externalDatabase.username | string | `""` |  |
| externalDatabase.password | string | `""` |  |
| externalDatabase.database | string | `"artifact_registry"` |  |
| externalDatabase.existingSecret | string | `""` |  |
| externalDatabase.existingSecretKey | string | `"DATABASE_URL"` |  |
| meilisearch.enabled | bool | `true` | Meilisearch (full-text search engine) Powers full-text artifact search. Uses LMDB for storage (requires vm.max_map_count >= 262144 on the host). The template hardcodes MEILI_MAX_INDEXING_THREADS=4 to limit indexing parallelism.  Memory sizing: Meilisearch spawns one actix HTTP worker per CPU core. On a 28-core host, 28 workers start up simultaneously. With the default 1Gi limit this causes immediate OOMKill. Set the limit to at least 4Gi, or higher if the search index is large.  The deployment uses Recreate strategy because the PVC-backed LMDB database cannot be opened by two pods at once. Do not change this to RollingUpdate or new pods will crash with "Resource temporarily unavailable (os error 11)". |
| meilisearch.image.repository | string | `"getmeili/meilisearch"` |  |
| meilisearch.image.tag | string | `"v1.12"` | Use a major.minor tag (e.g. v1.12) for automatic patch updates, or pin to a specific patch (e.g. v1.12.8) for stability. |
| meilisearch.masterKey | string | `"artifact-keeper-dev-key"` |  |
| meilisearch.env | string | `"development"` |  |
| meilisearch.persistence.size | string | `"5Gi"` |  |
| meilisearch.persistence.storageClass | string | `""` |  |
| meilisearch.resources.requests.cpu | string | `"250m"` |  |
| meilisearch.resources.requests.memory | string | `"512Mi"` |  |
| meilisearch.resources.limits.cpu | string | `"2"` |  |
| meilisearch.resources.limits.memory | string | `"8Gi"` | Must be >= 4Gi on multi-core nodes. 8Gi recommended for nodes with 16+ cores. See Memory sizing note above. |
| meilisearch.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| meilisearch.affinity | object | `{}` |  |
| meilisearch.nodeSelector | object | `{}` |  |
| meilisearch.topologySpreadConstraints | list | `[]` |  |
| trivy.enabled | bool | `true` | Trivy vulnerability scanner Runs as a persistent server that the backend calls for image/SBOM scans. Uses a PVC for its vulnerability database cache. Like Meilisearch, the deployment uses Recreate strategy because the cache directory uses a file lock that prevents concurrent access from two pods. |
| trivy.image.repository | string | `"aquasec/trivy"` |  |
| trivy.image.tag | string | `"latest"` |  |
| trivy.persistence.size | string | `"5Gi"` |  |
| trivy.persistence.storageClass | string | `""` |  |
| trivy.resources.requests.cpu | string | `"250m"` |  |
| trivy.resources.requests.memory | string | `"256Mi"` |  |
| trivy.resources.limits.cpu | string | `"1"` |  |
| trivy.resources.limits.memory | string | `"2Gi"` |  |
| trivy.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| trivy.affinity | object | `{}` |  |
| trivy.nodeSelector | object | `{}` |  |
| trivy.topologySpreadConstraints | list | `[]` |  |
| dependencyTrack.enabled | bool | `true` | DependencyTrack SBOM analysis Provides SBOM ingestion, license analysis, and vulnerability correlation. Requires significant memory (4Gi+) to load its internal vulnerability database on startup. The bootstrap init container creates the initial admin user and API key for backend integration. |
| dependencyTrack.image.repository | string | `"dependencytrack/apiserver"` |  |
| dependencyTrack.image.tag | string | `"4.11.4"` |  |
| dependencyTrack.adminPassword | string | `"ArtifactKeeper2026!"` |  |
| dependencyTrack.persistence.size | string | `"5Gi"` |  |
| dependencyTrack.persistence.storageClass | string | `""` |  |
| dependencyTrack.resources.requests.cpu | string | `"500m"` |  |
| dependencyTrack.resources.requests.memory | string | `"4Gi"` |  |
| dependencyTrack.resources.limits.cpu | string | `"2"` |  |
| dependencyTrack.resources.limits.memory | string | `"6Gi"` |  |
| dependencyTrack.bootstrap.enabled | bool | `true` |  |
| dependencyTrack.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| dependencyTrack.affinity | object | `{}` |  |
| dependencyTrack.nodeSelector | object | `{}` |  |
| dependencyTrack.topologySpreadConstraints | list | `[]` |  |
| ingress.enabled | bool | `true` | Ingress configuration |
| ingress.className | string | `"nginx"` |  |
| ingress.annotations | object | `{"nginx.ingress.kubernetes.io/enable-cors":"true","nginx.ingress.kubernetes.io/proxy-body-size":"1024m","nginx.ingress.kubernetes.io/proxy-read-timeout":"300","nginx.ingress.kubernetes.io/proxy-send-timeout":"300"}` |  |
| ingress.host | string | `"artifacts.example.com"` |  |
| ingress.tls.enabled | bool | `false` |  |
| ingress.tls.secretName | string | `"artifact-keeper-tls"` |  |
| secrets.jwtSecret | string | `"dev-secret-change-in-production"` | Secrets These are development defaults. For production, override via --set or use existingSecret references. Never commit real credentials here. |
| secrets.s3AccessKey | string | `"minioadmin"` |  |
| secrets.s3SecretKey | string | `"minioadmin-secret"` |  |
| externalSecrets.enabled | bool | `false` | External Secrets Operator When enabled, ExternalSecret CRDs replace the static Secret template. Requires External Secrets Operator installed on the cluster and a SecretStore or ClusterSecretStore configured for your provider. |
| externalSecrets.storeName | string | `"aws-secrets-manager"` |  |
| externalSecrets.storeKind | string | `"ClusterSecretStore"` |  |
| externalSecrets.refreshInterval | string | `"1h"` |  |
| externalSecrets.secrets.jwtSecret | string | `"artifact-keeper/${ENVIRONMENT}/jwt-secret"` |  |
| externalSecrets.secrets.dbCredentials | string | `"artifact-keeper/${ENVIRONMENT}/db-credentials"` |  |
| externalSecrets.secrets.s3Keys | string | `"artifact-keeper/${ENVIRONMENT}/s3-keys"` |  |
| externalSecrets.secrets.meilisearchKey | string | `"artifact-keeper/${ENVIRONMENT}/meilisearch-key"` |  |
| externalSecrets.secrets.dtAdminPassword | string | `"artifact-keeper/${ENVIRONMENT}/dt-admin-password"` |  |
| networkPolicy.enabled | bool | `false` | Network policies |
| serviceMonitor.enabled | bool | `false` | Prometheus ServiceMonitor |
| serviceMonitor.interval | string | `"30s"` |  |
| serviceMonitor.scrapeTimeout | string | `"10s"` |  |

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
