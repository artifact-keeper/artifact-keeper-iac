# artifact-keeper

![Version: 1.7.2](https://img.shields.io/badge/Version-1.7.2-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 1.7.1](https://img.shields.io/badge/AppVersion-1.7.1-informational?style=flat-square)

## TL;DR

Install from a cloned checkout:

```bash
git clone https://github.com/artifact-keeper/artifact-keeper-iac.git
cd artifact-keeper-iac
helm install ak charts/artifact-keeper/ \
  --namespace artifact-keeper \
  --create-namespace
```

A published Helm repository at `https://artifact-keeper.github.io/artifact-keeper-iac/` is planned but not yet live. See [issue #51](https://github.com/artifact-keeper/artifact-keeper-iac/issues/51) for tracking.

## Introduction

This chart deploys [Artifact Keeper](https://github.com/artifact-keeper/artifact-keeper), an enterprise artifact registry supporting 45+ package formats (Maven, npm, PyPI, Docker/OCI, Cargo, NuGet, and many more). The chart packages the backend API, web frontend, and all supporting services into a single Helm release with per-component toggles.

All files in this chart are provided as example configurations. Review and modify them to match your specific infrastructure requirements, security policies, and operational needs before use in production.

## Compatibility Matrix

The chart and backend versions must match. The current chart on `main` deploys OpenSearch (replacing Meilisearch from v1.1.x), so it requires backend v1.2.0 or later.

| Chart version | Backend image | Search backend |
|---|---|---|
| `main` (unreleased v1.2.x) | v1.2.0+ (`:dev`, `:1.2-dev`, or `:1.2.0`+) | OpenSearch |
| tag `chart-1.1.x` (planned) | v1.1.x line | Meilisearch |

For deployments running backend v1.1.x, pin the chart to a tag matching that line. Mixing chart `main` with backend `:1.1-dev` will fail at startup because the backend will not find an OpenSearch endpoint.

Tracking issues: chart release tags are coordinated in [#74](https://github.com/artifact-keeper/artifact-keeper-iac/issues/74), and a published Helm repository is tracked in [#51](https://github.com/artifact-keeper/artifact-keeper-iac/issues/51).

## Prerequisites

- Kubernetes 1.26+
- Helm 3.12+
- PV provisioner support in the underlying infrastructure
- `vm.max_map_count >= 262144` on nodes running OpenSearch (recommended by Lucene)

To set `vm.max_map_count` on your nodes:

```bash
sysctl -w vm.max_map_count=262144
echo "vm.max_map_count = 262144" >> /etc/sysctl.d/99-opensearch.conf
```

## Installing the Chart

Install the chart from a local clone with the release name `ak`:

```bash
git clone https://github.com/artifact-keeper/artifact-keeper-iac.git
cd artifact-keeper-iac
helm install ak charts/artifact-keeper/ \
  --namespace artifact-keeper \
  --create-namespace
```

A published Helm repository at `https://artifact-keeper.github.io/artifact-keeper-iac/` is planned but not yet live (see [issue #51](https://github.com/artifact-keeper/artifact-keeper-iac/issues/51)). Once published, the equivalent install command will be `helm install ak artifact-keeper/artifact-keeper`.

If you are running backend v1.1.x, do not install from `main`. See the [Compatibility Matrix](#compatibility-matrix) above for chart/backend version pairing.

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
| backend | object | `{"affinity":{},"autoscaling":{"enabled":false,"maxReplicas":10,"minReplicas":2,"targetCPUUtilization":70,"targetMemoryUtilization":80},"containerSecurityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true},"enabled":true,"env":{"ADMIN_PASSWORD":"","BACKUP_PATH":"/data/backups","ENVIRONMENT":"development","HOST":"0.0.0.0","PLUGINS_DIR":"/data/plugins","PORT":"8080","RATE_LIMIT_TRUSTED_PROXY_CIDRS":"10.0.0.0/8,172.16.0.0/12,192.168.0.0/16","RUST_LOG":"info,artifact_keeper=debug","STORAGE_PATH":"/data/storage"},"image":{"pullPolicy":"Always","repository":"ghcr.io/artifact-keeper/artifact-keeper-backend","tag":"dev"},"initContainerSecurityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true},"metricsListener":{"enabled":false,"port":9091},"nodeSelector":{},"persistence":{"enabled":true,"size":"10Gi","storageClass":""},"podDisruptionBudget":{"enabled":false,"minAvailable":1},"podSecurityContext":{"fsGroup":0,"runAsNonRoot":true,"runAsUser":1001},"replicaCount":1,"resources":{"limits":{"cpu":"2","ephemeral-storage":"1Gi","memory":"2Gi"},"requests":{"cpu":"250m","ephemeral-storage":"256Mi","memory":"256Mi"}},"scanWorkspace":{"enabled":true,"size":"2Gi"},"service":{"grpcPort":9090,"httpPort":8080,"type":"ClusterIP"},"serviceAccount":{"annotations":{},"create":true,"name":""},"tolerations":[],"topologySpreadConstraints":[]}` | Backend API server The backend handles all API requests, format-specific wire protocols, and artifact storage. It runs as a single Rust binary (Axum). |
| backend.env.RATE_LIMIT_TRUSTED_PROXY_CIDRS | string | `"10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"` | Rate Limiting RATE_LIMIT_TRUSTED_PROXY_CIDRS — CIDR(s), comma-separated, of the reverse proxy / ingress that sits in front of the backend. The login rate limiter keys on (username, client-IP) and only believes the X-Forwarded-For header when the request's TCP peer falls inside one of these ranges; otherwise it keys on the raw TCP peer. In Kubernetes the backend is reached through an ingress controller (ingress-nginx by default), so its TCP peer is ALWAYS the ingress/proxy pod IP. Leaving this empty makes the backend key every client on that single proxy pod IP → one shared login bucket per account → a single flooding client can targeted-lock-out any user (including owner break-glass) with ~10 requests / 15 min (iac#207, ak#2298). The default trusts the standard RFC1918 private pod-network ranges so per-client keying on the real client IP works out of the box behind an in-cluster proxy. TIGHTEN this to your ingress controller's actual pod CIDR for defense-in-depth, or set it to "" only when the backend is reached directly (no proxy) so ConnectInfo already carries the real client IP. |
| backend.image.tag | string | `"dev"` | "dev" is a floating tag built from main. Leave this empty ("") to inherit the chart's appVersion instead (see the IMAGE TAGS note at the top of this file). ArgoCD Image Updater pins floating tags to a digest automatically. For manual deploys with a floating tag, consider a specific version tag (e.g. 1.1.0) or set pullPolicy: Always. |
| backend.metricsListener | object | `{"enabled":false,"port":9091}` | Unauthenticated Prometheus metrics listener. When enabled, the backend starts a second TCP listener on `metricsPort` serving only `GET /metrics` with no authentication. Intended for Prometheus scrapers that cannot present credentials. Disabled by default.  |
| backend.podSecurityContext | object | `{"fsGroup":0,"runAsNonRoot":true,"runAsUser":1001}` | Pod-level securityContext. Defaults are image-native: the backend image bakes the Grype vulnerability DB at /home/artifact/.cache/grype with ownership 1001:0 (see artifact-keeper docker/Dockerfile.backend). The pod MUST run as UID 1001 or Grype hits EACCES on the DB. fsGroup only chowns mounted volumes -- it does NOT touch the image's root filesystem -- so changing runAsUser away from 1001 will break scans even if fsGroup matches.  If you are upgrading from chart <= 1.x where this defaulted to 1000:1000, your storage/scan-workspace PVCs will be recursively chowned on first remount because fsGroup changed. That takes ~1s per GiB of artifact data. See UPGRADE-NOTES.md. |
| backend.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| cosign | object | `{"certificateIdentityRegexp":"https://github.com/artifact-keeper/.*","certificateOidcIssuer":"https://token.actions.githubusercontent.com","enabled":false,"image":{"repository":"gcr.io/projectsigstore/cosign","tag":"v2.4.1"}}` | Cosign image signature verification When enabled, an init container verifies the backend image signature before the pod starts. Uses sigstore keyless verification (GitHub OIDC). |
| dependencyTrack | object | `{"adminPassword":"","affinity":{},"bootstrap":{"containerSecurityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]}},"enabled":true,"podSecurityContext":{"fsGroup":1000,"runAsNonRoot":true,"runAsUser":1000}},"containerSecurityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true},"enabled":true,"image":{"repository":"dependencytrack/apiserver","tag":"4.11.4"},"initContainerSecurityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true},"nodeSelector":{},"persistence":{"size":"5Gi","storageClass":""},"podSecurityContext":{"fsGroup":1000,"runAsNonRoot":true,"runAsUser":1000},"resources":{"limits":{"cpu":"2","ephemeral-storage":"1Gi","memory":"6Gi"},"requests":{"cpu":"500m","ephemeral-storage":"256Mi","memory":"4Gi"}},"tmpSizeLimit":"2Gi","tolerations":[],"topologySpreadConstraints":[]}` | DependencyTrack SBOM analysis Provides SBOM ingestion, license analysis, and vulnerability correlation. Requires significant memory (4Gi+) to load its internal vulnerability database on startup. The bootstrap init container creates the initial admin user and API key for backend integration. |
| dependencyTrack.tmpSizeLimit | string | `"2Gi"` | Size limit for the `/tmp` emptyDir volume. DependencyTrack writes ~1-2Gi into /tmp during startup (NVD mirror sync, DB migrations, JVM working files), so the default is sized to fit. Operators on constrained nodes can tune this down; an empty string falls back to the 2Gi default in the deployment template. |
| dependencyTrack.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| edge | object | `{"affinity":{},"containerSecurityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true},"enabled":false,"env":{"CACHE_SIZE_MB":"10240","EDGE_HOST":"0.0.0.0","EDGE_PORT":"8081","HEARTBEAT_INTERVAL_SECS":"30","RUST_LOG":"info,artifact_keeper_edge=debug"},"image":{"pullPolicy":"Always","repository":"ghcr.io/artifact-keeper/artifact-keeper-edge","tag":"dev"},"nodeSelector":{},"podDisruptionBudget":{"enabled":false,"minAvailable":1},"podSecurityContext":{"fsGroup":1000,"runAsNonRoot":true,"runAsUser":1000},"replicaCount":1,"resources":{"limits":{"cpu":"500m","memory":"512Mi"},"requests":{"cpu":"50m","memory":"128Mi"}},"service":{"port":8081,"type":"ClusterIP"},"tolerations":[],"topologySpreadConstraints":[]}` | Edge replication service NOTE: The ghcr.io/artifact-keeper/artifact-keeper-edge image is not yet published. Setting edge.enabled: true will fail because the image cannot be pulled. Airgap operators should exclude this component from pre-pull lists until the edge image ships. Tracking: issue #56. |
| edge.image.tag | string | `"dev"` | "dev" floating tag. Kept explicit (not empty) on purpose: the edge image is not published at the chart's appVersion yet, so inheriting appVersion would reference an image that does not exist. See the edge note above and issue #56. Leave empty ("") only once edge ships at the chart's appVersion. |
| edge.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| externalDatabase | object | `{"database":"artifact_registry","existingSecret":"","existingSecretKey":"DATABASE_URL","host":"","password":"","port":5432,"username":""}` | External database (used when postgres.enabled=false) |
| externalSecrets | object | `{"enabled":false,"refreshInterval":"1h","secrets":{"dbCredentials":"artifact-keeper/${ENVIRONMENT}/db-credentials","dtAdminPassword":"artifact-keeper/${ENVIRONMENT}/dt-admin-password","jwtSecret":"artifact-keeper/${ENVIRONMENT}/jwt-secret","migrationEncryptionKey":"","opensearchAuth":"artifact-keeper/${ENVIRONMENT}/opensearch-auth","s3Keys":"artifact-keeper/${ENVIRONMENT}/s3-keys","smtpPassword":"artifact-keeper/${ENVIRONMENT}/smtp-password","webhookSecretKey":""},"storeKind":"ClusterSecretStore","storeName":"aws-secrets-manager"}` | External Secrets Operator When enabled, ExternalSecret CRDs replace the static Secret template. Requires External Secrets Operator installed on the cluster and a SecretStore or ClusterSecretStore configured for your provider. |
| fleet | object | `{"enabled":false,"externalDatabaseBootstrap":{"adminSecret":"","enabled":true,"existingSecret":"","host":"","passwordKey":"password","port":5432},"guardrails":{"databaseNamespace":"","ingressNamespace":"ingress-nginx","limitRange":false,"networkPolicy":false,"resourceQuota":false,"scannerNamespace":"","searchNamespace":""},"hibernate":false,"host":"","instanceId":"","preset":"","storage":{"accessKeyIdKey":"S3_ACCESS_KEY_ID","existingSecret":"","secretAccessKeyKey":"S3_SECRET_ACCESS_KEY"}}` | Fleet mode: many instances per cluster sharing external services. Opt-in and off by default. When fleet.enabled is false none of the fleet templates render and backend/web sizing and replica counts come from the per-component values above, so a standard single-instance install is unaffected. When enabled, one release is one instance: sizing comes from a preset, the ingress serves a single host, and the instance uses a shared PostgreSQL server and shared object storage instead of in-release services. See templates/_helpers.tpl for the preset tables. |
| fleet.enabled | bool | `false` | Enable fleet mode. Master switch for every fleet template and helper. |
| fleet.externalDatabaseBootstrap | object | `{"adminSecret":"","enabled":true,"existingSecret":"","host":"","passwordKey":"password","port":5432}` | Bootstrap of the instance role and database on a shared PostgreSQL server. Runs as a pre-install/pre-upgrade hook Job that creates the role and database (named ak_<instanceId>) if they are absent. The backend runs its own schema migrations on startup, so the Job only guarantees the empty database and its owning role exist before the backend connects. |
| fleet.externalDatabaseBootstrap.adminSecret | string | `""` | Name of an existing Secret holding superuser credentials for the shared server, used only by the bootstrap Job. Expected keys: username, password. |
| fleet.externalDatabaseBootstrap.enabled | bool | `true` | Run the bootstrap Job. |
| fleet.externalDatabaseBootstrap.existingSecret | string | `""` | Name of an existing Secret holding the instance role password. The same Secret is expected to hold the DATABASE_URL the backend consumes. |
| fleet.externalDatabaseBootstrap.host | string | `""` | Host of the shared PostgreSQL read-write service. |
| fleet.externalDatabaseBootstrap.passwordKey | string | `"password"` | Key in existingSecret holding the instance role password. |
| fleet.externalDatabaseBootstrap.port | int | `5432` | Port of the shared PostgreSQL read-write service. |
| fleet.guardrails | object | `{"databaseNamespace":"","ingressNamespace":"ingress-nginx","limitRange":false,"networkPolicy":false,"resourceQuota":false,"scannerNamespace":"","searchNamespace":""}` | Per-namespace guardrails. Each toggle is independent and off by default. ResourceQuota and LimitRange are sized from the preset; the NetworkPolicy restricts ingress to the named ingress-controller namespace and egress to the named shared-service namespaces plus DNS and outbound HTTPS. |
| fleet.guardrails.databaseNamespace | string | `""` | Namespace of the shared PostgreSQL server (NetworkPolicy egress). |
| fleet.guardrails.ingressNamespace | string | `"ingress-nginx"` | Namespace of the ingress controller allowed to reach the instance (NetworkPolicy ingress). |
| fleet.guardrails.limitRange | bool | `false` | Emit a LimitRange sized from the preset. |
| fleet.guardrails.networkPolicy | bool | `false` | Emit a NetworkPolicy scoping ingress and egress. |
| fleet.guardrails.resourceQuota | bool | `false` | Emit a ResourceQuota sized from the preset. |
| fleet.guardrails.scannerNamespace | string | `""` | Namespace of the shared scanner service (NetworkPolicy egress). |
| fleet.guardrails.searchNamespace | string | `""` | Namespace of the shared search service (NetworkPolicy egress). |
| fleet.hibernate | bool | `false` | Hibernate this instance by scaling backend and web to zero replicas. The release and its data stay in place; set back to false to resume. |
| fleet.host | string | `""` | Public hostname for this instance, used as the single ingress host. When set, TLS for the host is expected to be terminated upstream (for example by a shared wildcard certificate on the ingress controller), so the chart does not emit a per-release ingress TLS block. |
| fleet.instanceId | string | `""` | Stable identifier for this instance. Drives the derived database role and database name (ak_<instanceId>, with dashes normalized to underscores) and the object storage key prefix. |
| fleet.preset | string | `""` | Sizing preset: small, medium, or large. Selects chart-owned backend and web replica counts and resource requests/limits (see _helpers.tpl). An empty value falls back to small; any other value fails the render. |
| fleet.storage | object | `{"accessKeyIdKey":"S3_ACCESS_KEY_ID","existingSecret":"","secretAccessKeyKey":"S3_SECRET_ACCESS_KEY"}` | Object storage credentials for the shared S3-compatible backend. The non-secret settings (endpoint, bucket, region) are supplied through backend.env; the access keys are read from an existing Secret referenced here and injected into the backend as S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY. |
| fleet.storage.accessKeyIdKey | string | `"S3_ACCESS_KEY_ID"` | Key in the Secret holding the access key id. |
| fleet.storage.existingSecret | string | `""` | Name of an existing Secret holding the object storage access keys. |
| fleet.storage.secretAccessKeyKey | string | `"S3_SECRET_ACCESS_KEY"` | Key in the Secret holding the secret access key. |
| fullnameOverride | string | `""` |  |
| gke.healthCheckPolicies.backend.requestPath | string | `"/livez"` | Health-check path for the backend BackendService. |
| gke.healthCheckPolicies.dependencyTrack.requestPath | string | `"/api/version"` | Health-check path for the DependencyTrack BackendService. |
| gke.healthCheckPolicies.enabled | bool | `false` | Render a `networking.gke.io/v1` HealthCheckPolicy per Service so a GKE Gateway BackendService probes the app's real health path instead of `/` (which backend and DependencyTrack return 404 for). Leave disabled on non-GKE installs and on plain Ingress-based GKE. |
| global.affinity | object | `{}` |  |
| global.imagePullPolicy | string | `"Always"` |  |
| global.imagePullSecrets | list | `[]` | Image pull secrets applied to workloads that honor them (currently the scanner-adapter). Leave empty for public images. |
| global.imageRegistry | string | `"ghcr.io/artifact-keeper"` |  |
| global.nodeSelector | object | `{}` |  |
| global.storageClass | string | `"standard"` |  |
| global.tolerations | list | `[]` | Scheduling constraints applied to ALL workloads by default. Per-component values (e.g. backend.nodeSelector) override these.  NOTE: Per-component values fully replace global, they do not merge. Setting backend.tolerations means the backend gets only those tolerations, not global + backend combined. There is currently no way to opt a single component out of global scheduling without setting its own values. |
| global.topologySpreadConstraints | list | `[]` |  |
| ingress | object | `{"annotations":{"nginx.ingress.kubernetes.io/enable-cors":"true","nginx.ingress.kubernetes.io/proxy-body-size":"1024m","nginx.ingress.kubernetes.io/proxy-read-timeout":"300","nginx.ingress.kubernetes.io/proxy-send-timeout":"300"},"className":"nginx","enabled":true,"host":"artifacts.example.com","tls":{"enabled":true,"secretName":"artifact-keeper-tls"}}` | Ingress configuration |
| nameOverride | string | `""` |  |
| networkPolicy | object | `{"enabled":true}` | Network policies |
| opensearch | object | `{"affinity":{},"allowInvalidCerts":true,"auth":{"password":"ArtifactKeeper2026!Strong","username":"admin"},"clusterName":"artifact-keeper","containerSecurityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":false},"disableSecurityPlugin":true,"enabled":true,"fixOwnership":{"enabled":true,"securityContext":{"allowPrivilegeEscalation":false,"capabilities":{"add":["CHOWN","FOWNER"],"drop":["ALL"]},"readOnlyRootFilesystem":true,"runAsNonRoot":false,"runAsUser":0}},"image":{"repository":"opensearchproject/opensearch","tag":"2.19.1"},"initContainerSecurityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true},"javaOpts":"-Xms512m -Xmx512m","nodeSelector":{},"persistence":{"enabled":true,"size":"5Gi","storageClass":""},"podSecurityContext":{"fsGroup":1000,"runAsNonRoot":true,"runAsUser":1000},"replicaCount":1,"resources":{"limits":{"cpu":"2","ephemeral-storage":"512Mi","memory":"2Gi"},"requests":{"cpu":"250m","ephemeral-storage":"128Mi","memory":"1Gi"}},"tolerations":[],"topologySpreadConstraints":[]}` | OpenSearch (full-text search engine) Powers full-text artifact search. The backend auto-reindexes from Postgres on first boot, so there is no data migration required when enabling OpenSearch on a fresh install.  Deployment mode: - replicaCount: 1 (default) renders a single-node Deployment with   discovery.type=single-node, suitable for dev and small installs. - replicaCount: >= 2 renders a StatefulSet with per-pod PVCs and sets   cluster.initial_cluster_manager_nodes for multi-node bootstrapping.   Use this for staging/production.  Security: - disableSecurityPlugin: true is the simplest option and is the default   for the example template. The backend talks plain HTTP on port 9200. - disableSecurityPlugin: false enables the OpenSearch Security plugin.   You must then provide auth.username/auth.password and configure real   TLS certificates. The default demo config is always disabled   (DISABLE_INSTALL_DEMO_CONFIG=true) so you do not ship demo certs   into production by accident. |
| opensearch.allowInvalidCerts | bool | `true` | Backend-side TLS verification toggle. Leave true for self-signed certs in development; set to false once real certs are in place. |
| opensearch.auth | object | `{"password":"ArtifactKeeper2026!Strong","username":"admin"}` | Admin credentials used when disableSecurityPlugin is false. Ignored otherwise. Override via --set or externalSecrets in production. |
| opensearch.auth.password | string | `"ArtifactKeeper2026!Strong"` | OpenSearch 2.12+ requires a strong initial admin password. |
| opensearch.containerSecurityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":false}` | readOnlyRootFilesystem is false because OpenSearch writes config and lock files outside its data volume on startup. |
| opensearch.disableSecurityPlugin | bool | `true` | When true, the Security plugin is disabled and the backend talks plain HTTP. Set to false for staging/production (see README for cert-manager setup). |
| opensearch.image.tag | string | `"2.19.1"` | Pin to a specific patch for stability. 2.19.1 matches the version the backend is tested against. |
| opensearch.initContainerSecurityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true}` | Applies to the sysctl-check init container. The fix-ownership init container has separate root + CHOWN/FOWNER requirements, configured under `opensearch.fixOwnership.securityContext`. |
| opensearch.javaOpts | string | `"-Xms512m -Xmx512m"` | JVM heap sizing. Keep Xms == Xmx. The container memory limit should be roughly 2x the heap to leave room for off-heap and page cache. |
| opensearch.persistence.enabled | bool | `true` | When false and replicaCount == 1, data lives in an emptyDir sized according to `size`. Set to true (and configure storageClass) for any install that must survive pod restarts. |
| opensearch.resources.limits.memory | string | `"2Gi"` | Must be roughly 2x the JVM heap in javaOpts. |
| opensearch.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| postgres | object | `{"affinity":{},"auth":{"database":"artifact_registry","password":"","username":"registry"},"containerSecurityContext":{},"enabled":true,"image":{"repository":"postgres","tag":"16-alpine"},"initDb":{"enabled":true},"nodeSelector":{},"persistence":{"size":"20Gi","storageClass":""},"podSecurityContext":{"fsGroup":999,"runAsNonRoot":true,"runAsUser":999},"resources":{"limits":{"cpu":"1","ephemeral-storage":"512Mi","memory":"1Gi"},"requests":{"cpu":"250m","ephemeral-storage":"128Mi","memory":"256Mi"}},"tolerations":[],"topologySpreadConstraints":[]}` | PostgreSQL (in-cluster, disable for external/RDS) For production, set postgres.enabled=false and configure externalDatabase to point at a managed database (RDS, Cloud SQL, etc.). The in-cluster instance is suitable for dev/testing only. |
| postgres.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| scannerAdapter | object | `{"affinity":{},"cacheSizeLimit":"2Gi","containerSecurityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true},"enabled":true,"env":{"SCANNER_TRIVY_INSECURE":"true"},"image":{"pullPolicy":"IfNotPresent","repository":"ghcr.io/artifact-keeper/artifact-keeper-scanner-adapter","tag":"1"},"nodeSelector":{},"podSecurityContext":{"fsGroup":10000,"runAsNonRoot":true,"runAsUser":10000},"resources":{"limits":{"cpu":"1","ephemeral-storage":"2Gi","memory":"1Gi"},"requests":{"cpu":"100m","ephemeral-storage":"128Mi","memory":"128Mi"}},"tmpSizeLimit":"1Gi","tolerations":[],"topologySpreadConstraints":[]}` | In-house Trivy scanner-adapter Stateless Harbor-protocol scanner-adapter (image artifact-keeper-scanner-adapter) that the backend calls over HTTP via TRIVY_ADAPTER_URL for container-image Trivy scans. It pulls the target image from the AK registry per request and runs Trivy in-process, so it needs no Redis and no persistent storage — a single replica is fine. The image is multi-arch (amd64 + arm64), so there is no arch-pinned nodeSelector; leave it enabled on arm64 clusters too. Default enabled: true (recommended for amd64 and supported on arm64). This is separate from the `trivy` server above, which stays on TRIVY_URL for the fs/incus scan path. |
| scannerAdapter.cacheSizeLimit | string | `"2Gi"` | Writable scratch for image-layer extraction and the Trivy DB cache. emptyDir (no PVC) because the adapter is stateless. |
| scannerAdapter.env | object | `{"SCANNER_TRIVY_INSECURE":"true"}` | Extra environment for the adapter. SCANNER_TRIVY_INSECURE defaults to "true" because the adapter reaches the AK registry over the plain-HTTP in-cluster Service endpoint; set to "false" if the adapter pulls from a TLS-terminated registry it can verify. |
| scannerAdapter.image.tag | string | `"1"` | The scanner-adapter is versioned independently of the AK backend/web/edge images (major-only tags `1`/`1.0`/`latest`; there is no `scanner-adapter:<appVersion>`). Pin to the adapter's major tag `"1"` so the chart is decoupled from appVersion. The deployment renders the tag as `tag | default .Chart.AppVersion`, so leaving this empty ("") would fall back to appVersion and pull a non-existent tag — keep it pinned. |
| scannerAdapter.tolerations | list | `[]` | Per-component scheduling (overrides global). Do NOT arch-pin here; the image is multi-arch. |
| secrets | object | `{"existingSecret":"","jwtSecret":"","migrationEncryptionKey":"","s3AccessKey":"","s3SecretKey":"","smtpPassword":"","webhookSecretKey":""}` | Secrets These are development defaults. For production, override via --set or use existingSecret references. Never commit real credentials here. |
| secrets.existingSecret | string | `""` | Name of an existing Secret that already holds the core application credentials (JWT_SECRET, and DATABASE_URL/POSTGRES_PASSWORD when the chart would otherwise manage them). When set, the chart does not render its own Secret and all workloads read from this Secret instead, so the values under `secrets` and `postgres.auth.password` are not required. Useful for GitOps and secret-manager workflows where the Secret is provisioned out of band. |
| serviceMonitor | object | `{"enabled":false,"interval":"30s","scrapeTimeout":"10s"}` | Prometheus ServiceMonitor |
| trivy | object | `{"affinity":{},"containerSecurityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true},"db":{"javaRepository":"","preseed":{"enabled":false},"repository":"","skipUpdate":false},"enabled":true,"image":{"repository":"aquasec/trivy","tag":"0.62.1"},"initContainerSecurityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true},"nodeSelector":{},"persistence":{"size":"5Gi","storageClass":""},"podSecurityContext":{"fsGroup":10000,"runAsNonRoot":true,"runAsUser":10000},"resources":{"limits":{"cpu":"1","ephemeral-storage":"1Gi","memory":"2Gi"},"requests":{"cpu":"250m","ephemeral-storage":"128Mi","memory":"256Mi"}},"tolerations":[],"topologySpreadConstraints":[]}` | Trivy vulnerability scanner Runs as a persistent server that the backend calls for image/SBOM scans. Uses a PVC for its vulnerability database cache. The deployment uses Recreate strategy because the cache directory uses a file lock that prevents concurrent access from two pods. |
| trivy.db | object | `{"javaRepository":"","preseed":{"enabled":false},"repository":"","skipUpdate":false}` | Vulnerability database settings. Trivy downloads its vulnerability DB lazily (on first scan), pulling an OCI artifact from a registry. The upstream default (ghcr.io/aquasecurity/trivy-db) is anonymous-pull and gets rate-limited; clusters that cannot reach it (or that hit the rate limit) end up with no DB, which fails the pinned-cve-gate pre-flight. To make the fetch reliable we (a) point at a configurable mirror and (b) pre-seed the DB with an init container so it is present before the server accepts scans. |
| trivy.db.javaRepository | string | `""` | OCI repository for the Java DB (used by jar/war scanning). Same opt-in semantics as `repository` above. |
| trivy.db.preseed | object | `{"enabled":false}` | Run an init container that downloads the DB into the cache PVC before the server starts. Makes the DB present on rollout instead of on first scan. Default OFF because the preseed download from mirror.gcr.io can exceed Helm's default install timeout in some clusters, leaving the Trivy Deployment stuck at Available 0/1 (see artifact-keeper-iac #137). The server still fetches the DB lazily on first scan via TRIVY_DB_REPOSITORY, so this is opt-in for now. |
| trivy.db.repository | string | `""` | OCI repository for the vulnerability DB. Override to an internal mirror the cluster can reach. Default empty means Trivy uses its built-in ghcr.io default, which has historically been the only reliably-reachable source from our gate cluster. mirror.gcr.io was tried in #136 but caused the server to hang at Available 0/1 even with preseed off (see artifact-keeper-iac #140), so the mirror is now opt-in by override rather than the default. |
| trivy.db.skipUpdate | bool | `false` | Skip the periodic in-server DB refresh. Leave false so the server keeps the DB fresh from the configured mirror; set true for fully air-gapped clusters where the DB is seeded out of band. |
| trivy.tolerations | list | `[]` | Per-component scheduling (overrides global) |
| web | object | `{"affinity":{},"containerSecurityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true},"enabled":true,"env":{"NEXT_PUBLIC_API_URL":"","NODE_ENV":"production"},"image":{"pullPolicy":"Always","repository":"ghcr.io/artifact-keeper/artifact-keeper-web","tag":"dev"},"nodeSelector":{},"podDisruptionBudget":{"enabled":false,"minAvailable":1},"podSecurityContext":{"fsGroup":1000,"runAsNonRoot":true,"runAsUser":1000},"replicaCount":1,"resources":{"limits":{"cpu":"1","ephemeral-storage":"2Gi","memory":"1Gi"},"requests":{"cpu":"250m","ephemeral-storage":"256Mi","memory":"256Mi"}},"service":{"port":3000,"type":"ClusterIP"},"tolerations":[],"topologySpreadConstraints":[]}` | Next.js web frontend |
| web.image.tag | string | `"dev"` | "dev" floating tag for the development profile. Leave empty ("") to inherit the chart's appVersion (see backend.image.tag). |
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
  --set secrets.jwtSecret=$(openssl rand 64 | openssl base64 -A)
```

### Smoke / Release-Gate Testing

`values-smoke.yaml` is the canonical overlay for smoke installs and the release-gate test suites in [artifact-keeper-test](https://github.com/artifact-keeper/artifact-keeper-test). It pins resource requests to fit a 4 CPU / 8 Gi namespace, sets a non-default admin password, exempts the `admin` user from rate limiting, and disables every external dependency the smoke can't satisfy (Trivy, DependencyTrack, ingress, ServiceMonitor, NetworkPolicy, External Secrets, edge replication, cosign verification).

```bash
helm install ak charts/artifact-keeper/ \
  -f charts/artifact-keeper/values-smoke.yaml \
  --set backend.image.tag=dev \
  --set web.image.tag=dev \
  --namespace artifact-keeper-smoke \
  --create-namespace
```

This file is the single source of truth for smoke overrides. When the chart adds a new default-on subsystem, update `values-smoke.yaml` rather than encoding overrides as inline `--set` flags in test scripts.

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
| **OpenSearch** | Full-text search engine for artifact discovery | Enabled |
| **Trivy** | Vulnerability scanner for container images and SBOMs (fs/incus path via `TRIVY_URL`) | Enabled |
| **Scanner-adapter** | In-house Harbor scanner-adapter for container-image Trivy scans (`TRIVY_ADAPTER_URL`); stateless, multi-arch, no PVC | Enabled |
| **DependencyTrack** | SBOM analysis platform for license and vulnerability correlation | Enabled |

### Component Diagram

```
Ingress
  |
  +-- /api/* --> Backend (port 8080, gRPC 9090)
  +-- /*     --> Web (port 3000)

Backend --> PostgreSQL (port 5432)
Backend --> OpenSearch (port 9200)
Backend --> Trivy (port 8090)
Backend --> Scanner-adapter (port 8090)
Scanner-adapter --> Backend registry (pull target images)
Backend --> DependencyTrack (port 8080)
```

## Storage

Services that use PersistentVolumeClaims run with the Recreate deployment strategy (or a StatefulSet with per-pod PVCs, in the case of multi-node OpenSearch). This prevents two pods from competing for the same volume lock during rolling updates.

The backend uses two PVCs: one for artifact storage and one for scan workspace (temp files during security scans). Both can be sized independently.

| Component | Default Size | Purpose |
|-----------|-------------|---------|
| Backend storage | 10Gi | Artifact file storage |
| Backend scan workspace | 2Gi | Temporary scan files |
| PostgreSQL | 20Gi | Database files |
| OpenSearch | 5Gi | Search index (Lucene) |
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

When `networkPolicy.enabled` is set to `true`, the chart creates NetworkPolicy resources that restrict traffic between components. Only the required communication paths are allowed (for example, backend to PostgreSQL, backend to OpenSearch on port 9200, and OpenSearch-to-OpenSearch transport on port 9300).

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
- Set `opensearch.replicaCount: 3` to switch OpenSearch from single-node Deployment mode to a StatefulSet with cluster bootstrapping. The chart sets `cluster.initial_cluster_manager_nodes` automatically.
- DependencyTrack runs as a single replica due to PVC lock constraints. Plan maintenance windows for upgrades.

## Upgrading

### Image Tags

The default `dev` tag is a floating tag that always points to the latest build from main. When using ArgoCD, the Image Updater pins these to specific digests so rollouts are deterministic. For manual deployments, consider using a specific version tag (e.g. `1.1.0`).

Docker tags use semver without a `v` prefix: git tag `v1.1.0` produces Docker tag `1.1.0`.

### Container Registry

Images are published to `ghcr.io/artifact-keeper/artifact-keeper-{backend,web}` by default. Docker Hub mirrors are available at `docker.io/artifactkeeper/{backend,web}`. Change the registry via `global.imageRegistry` or per-component `image.repository` values.

## Troubleshooting

### OpenSearch OOMKill

OpenSearch JVM heap is set via `opensearch.javaOpts` (`-Xms`/`-Xmx`). The container memory limit must be roughly 2x the heap size to leave room for off-heap, Lucene page cache, and native threads. If the pod is OOMKilled, raise both values together.

### OpenSearch "max_map_count" warning

OpenSearch recommends `vm.max_map_count >= 262144`. This is a host-level sysctl and cannot be set from inside the pod. Apply it on every node:

```bash
sysctl -w vm.max_map_count=262144
echo "vm.max_map_count = 262144" >> /etc/sysctl.d/99-opensearch.conf
```

### OpenSearch cluster will not form (multi-node)

When `replicaCount >= 2`, the chart renders a StatefulSet with `cluster.initial_cluster_manager_nodes` set to the pod names (`ak-opensearch-0`, `ak-opensearch-1`, ...). If pods cannot reach each other, check that the headless service `<release>-opensearch-headless` exists and the NetworkPolicy (if enabled) allows traffic between OpenSearch pods on port 9300.

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
helm template ak charts/artifact-keeper/ -f charts/artifact-keeper/values-smoke.yaml \
  --set backend.image.tag=dev --set web.image.tag=dev > /dev/null
```

## Contributing

1. Fork the repository and create a feature branch.
2. Make your changes to `values.yaml`, templates, or overlay files.
3. Run `helm-docs` in the `charts/artifact-keeper/` directory to regenerate the README.
4. Run `helm lint` and `helm template` to validate the chart.
5. Open a pull request against the `main` branch.

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
