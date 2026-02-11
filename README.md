# Artifact Keeper IaC

Infrastructure as Code for [Artifact Keeper](https://github.com/artifact-keeper/artifact-keeper) — production-grade Helm charts, Terraform modules, ArgoCD GitOps, and monitoring stack.

> **Note:** All files in this repository are **example configurations** provided as getting-started templates. Review and modify them to match your specific infrastructure requirements, security policies, and operational needs before use in production.

## Architecture Overview

```mermaid
graph TB
    subgraph "Developer Workflow"
        DEV["Developer"] -->|git push| GIT["GitHub<br/>artifact-keeper-iac"]
        GIT -->|watches| ARGO["ArgoCD"]
    end

    subgraph "AWS Infrastructure (Terraform)"
        VPC["VPC<br/>Public + Private Subnets<br/>NAT Gateway"]
        EKS["EKS Cluster<br/>Managed Node Groups<br/>IRSA (IAM Roles)"]
        RDS["RDS PostgreSQL 16<br/>Multi-AZ, Encrypted"]
        S3["S3 Bucket<br/>Artifact Storage<br/>Versioned, Encrypted"]
        VPC --> EKS
        VPC --> RDS
    end

    subgraph "Kubernetes Cluster (Helm)"
        ARGO -->|deploys| HELM["Helm Release"]
        HELM --> ING["Ingress<br/>nginx + TLS"]

        ING -->|/api| BE["Backend API<br/>Rust + Axum"]
        ING -->|/| WEB["Web Frontend<br/>Next.js 15"]

        BE --> PG["PostgreSQL"]
        BE --> MS["Meilisearch"]
        BE --> TV["Trivy<br/>Vulnerability Scanner"]
        BE --> DT["Dependency-Track<br/>SBOM Analysis"]
        EDGE["Edge Replication"] --> BE

        HPA["HPA"] -.->|scales| BE
        PDB["PDB"] -.->|protects| BE
    end

    subgraph "Observability (Monitoring)"
        SM["ServiceMonitor"] -.->|scrapes /metrics| BE
        SM --> PROM["Prometheus<br/>30d retention"]
        PROM --> GRAF["Grafana<br/>Custom Dashboard"]
        PROM --> ALERT["Alertmanager<br/>7 Alert Rules"]
    end

    EKS -.-> HELM
    BE -->|IRSA| S3
    BE --> RDS

    style BE fill:#e8631c,color:#fff
    style WEB fill:#0070f3,color:#fff
    style ARGO fill:#ef7b4d,color:#fff
    style PROM fill:#e6522c,color:#fff
    style GRAF fill:#f46800,color:#fff
```

## Repository Structure

```
artifact-keeper-iac/
├── helm/                          # Helm Chart
│   ├── Chart.yaml
│   ├── values.yaml                # Development defaults
│   ├── values-staging.yaml        # Staging overlay
│   ├── values-production.yaml     # Production overlay
│   └── templates/
│       ├── backend-deployment.yaml
│       ├── backend-service.yaml
│       ├── backend-hpa.yaml       # HorizontalPodAutoscaler
│       ├── backend-pdb.yaml       # PodDisruptionBudget
│       ├── backend-serviceaccount.yaml
│       ├── backend-pvc.yaml
│       ├── web-deployment.yaml
│       ├── web-service.yaml
│       ├── edge-deployment.yaml
│       ├── edge-service.yaml
│       ├── postgres-statefulset.yaml
│       ├── meilisearch-deployment.yaml
│       ├── trivy-deployment.yaml
│       ├── dtrack-deployment.yaml
│       ├── ingress.yaml
│       ├── configmap.yaml
│       ├── secrets.yaml
│       ├── networkpolicy.yaml
│       └── servicemonitor.yaml
│
├── terraform/                     # Terraform Modules
│   ├── modules/
│   │   ├── vpc/                   # VPC, subnets, NAT, routing
│   │   ├── eks/                   # EKS cluster, node groups, IRSA
│   │   ├── rds/                   # RDS PostgreSQL, security groups
│   │   └── s3/                    # S3 bucket, encryption, lifecycle
│   └── environments/
│       ├── dev/                   # t3.large, 1-3 nodes, 20GB RDS
│       ├── staging/               # t3.xlarge, 2-5 nodes, 50GB RDS
│       └── production/            # Multi-AZ, 2 node groups, 100GB RDS
│
├── argocd/                        # ArgoCD GitOps
│   ├── appproject.yaml            # Project with RBAC roles
│   ├── applicationset.yaml        # Multi-env generator
│   └── argocd-values.yaml         # ArgoCD install config
│
└── monitoring/                    # Observability Stack
    ├── kube-prometheus-values.yaml # Prometheus + Grafana config
    ├── grafana-dashboard.json      # 12-panel custom dashboard
    └── alerting-rules.yaml         # 7 PrometheusRule alerts
```

## Helm Chart

The Helm chart deploys the full Artifact Keeper stack as a single release with per-service toggles.

### Quick Start

```bash
git clone https://github.com/artifact-keeper/artifact-keeper-iac.git
cd artifact-keeper-iac

# Development (all services in-cluster)
helm install ak helm/ \
  --namespace artifact-keeper \
  --create-namespace

# Production (external RDS, TLS, autoscaling)
helm install ak helm/ \
  -f helm/values-production.yaml \
  --namespace artifact-keeper \
  --create-namespace \
  --set ingress.host=registry.example.com \
  --set secrets.jwtSecret=$(openssl rand -base64 64) \
  --set externalDatabase.host=your-rds-endpoint.amazonaws.com
```

### Environment Comparison

```mermaid
graph LR
    subgraph DEV["Development"]
        D_BE["Backend x1"]
        D_PG["PostgreSQL<br/>In-Cluster"]
        D_MS["Meilisearch"]
        D_TV["Trivy"]
        D_DT["DependencyTrack"]
    end

    subgraph STG["Staging"]
        S_BE["Backend x2<br/>+ HPA"]
        S_PG["PostgreSQL<br/>In-Cluster"]
        S_NP["NetworkPolicy"]
        S_SM["ServiceMonitor"]
    end

    subgraph PROD["Production"]
        P_BE["Backend x3<br/>+ HPA (→20)<br/>+ PDB"]
        P_RDS["RDS PostgreSQL<br/>Multi-AZ"]
        P_NP["NetworkPolicy"]
        P_SM["ServiceMonitor"]
        P_TLS["TLS + cert-manager"]
    end

    style DEV fill:#22c55e,color:#fff
    style STG fill:#eab308,color:#fff
    style PROD fill:#ef4444,color:#fff
```

| | Development | Staging | Production |
|---|---|---|---|
| **Replicas** | 1 | 2 | 3+ (HPA up to 20) |
| **PostgreSQL** | In-cluster | In-cluster | External (RDS) |
| **Autoscaling** | Disabled | Enabled | Enabled |
| **PodDisruptionBudget** | Disabled | Enabled | Enabled (min 2) |
| **NetworkPolicy** | Disabled | Enabled | Enabled |
| **Monitoring** | Disabled | Enabled | Enabled (15s) |
| **TLS** | Disabled | Optional | Required |

## Terraform Modules

Composable modules for provisioning AWS infrastructure. Each environment composes the same four modules with different parameters.

### Module Architecture

```mermaid
graph TD
    subgraph "Terraform Modules"
        VPC["vpc/<br/>VPC + Subnets + NAT"]
        EKS["eks/<br/>EKS + Node Groups + OIDC"]
        RDS["rds/<br/>PostgreSQL 16 + Encryption"]
        S3_M["s3/<br/>Bucket + Lifecycle + Policy"]
    end

    subgraph "Environment Compositions"
        DEV_E["environments/dev/<br/>t3.large · 1-3 nodes<br/>db.t3.medium · 20GB"]
        STG_E["environments/staging/<br/>t3.xlarge · 2-5 nodes<br/>db.t3.large · 50GB"]
        PRD_E["environments/production/<br/>2 node groups · Multi-AZ<br/>db.r6g.large · 100GB"]
    end

    DEV_E --> VPC
    DEV_E --> EKS
    DEV_E --> RDS
    DEV_E --> S3_M

    STG_E --> VPC
    STG_E --> EKS
    STG_E --> RDS
    STG_E --> S3_M

    PRD_E --> VPC
    PRD_E --> EKS
    PRD_E --> RDS
    PRD_E --> S3_M

    style DEV_E fill:#22c55e,color:#fff
    style STG_E fill:#eab308,color:#fff
    style PRD_E fill:#ef4444,color:#fff
```

### Usage

```bash
cd terraform/environments/dev

# Initialize and plan
terraform init
terraform plan

# Apply infrastructure
terraform apply
```

### Key Design Decisions

- **IRSA (IAM Roles for Service Accounts)** — pods get fine-grained AWS IAM permissions via ServiceAccount annotations, no static credentials
- **Non-overlapping VPC CIDRs** — `10.0.0.0/16` (dev), `10.1.0.0/16` (staging), `10.2.0.0/16` (prod) enable VPC peering if needed
- **RDS credentials in Secrets Manager** — auto-generated 32-character passwords stored in AWS Secrets Manager
- **S3 lifecycle rules** — Standard-IA after 90 days, Glacier after 365 days (production only)
- **Remote state** — S3 + DynamoDB locking per environment

## ArgoCD GitOps

Pull-based GitOps with environment-specific sync policies.

```mermaid
graph LR
    GIT["GitHub<br/>artifact-keeper-iac"] -->|watches| ARGO["ArgoCD"]
    ARGO -->|auto-sync<br/>+ self-heal| DEV["Dev<br/>Namespace"]
    ARGO -->|auto-sync| STG["Staging<br/>Namespace"]
    ARGO -->|manual sync<br/>only| PRD["Production<br/>Namespace"]

    style DEV fill:#22c55e,color:#fff
    style STG fill:#eab308,color:#fff
    style PRD fill:#ef4444,color:#fff
    style ARGO fill:#ef7b4d,color:#fff
```

| Environment | Auto-Sync | Self-Heal | Prune |
|---|---|---|---|
| Dev | Yes | Yes | Yes |
| Staging | Yes | No | No |
| Production | **Manual** | No | No |

## Monitoring Stack

Built on [kube-prometheus-stack](https://github.com/prometheus-community/helm-charts/tree/main/charts/kube-prometheus-stack) with a custom Grafana dashboard and alert rules.

### Dashboard Panels

The Grafana dashboard includes 12 panels across 4 rows:

| Row | Panels |
|---|---|
| **Overview** | Request Rate, Error Rate, Requests In-Flight |
| **Latency** | P50, P95, P99 response times |
| **Traffic** | Requests by method, Responses by status, Active connections |
| **Resources** | Pod CPU, Pod Memory, Pod Restarts |

### Alert Rules

| Alert | Severity | Condition |
|---|---|---|
| `ArtifactKeeperHighErrorRate` | Critical | 5xx rate > 5% for 5m |
| `ArtifactKeeperHighLatency` | Warning | P99 > 2s for 5m |
| `ArtifactKeeperPodRestarting` | Warning | > 3 restarts/hour |
| `ArtifactKeeperPodNotReady` | Critical | Not ready for 5m |
| `ArtifactKeeperStorageHigh` | Warning | PVC usage > 80% for 15m |
| `DependencyTrackDown` | Critical | Unreachable for 5m |
| `ArtifactKeeperDatabaseConnectionFailure` | Critical | High 503 responses |

## Security Stack Credits

The deployment includes two open-source security scanning tools:

- **[Trivy](https://trivy.dev/)** (Apache 2.0) — Vulnerability scanner by [Aqua Security](https://www.aquasec.com/)
- **[OWASP Dependency-Track](https://dependencytrack.org/)** (Apache 2.0) — SBOM analysis platform by [OWASP](https://owasp.org/)

## Related Repositories

| Repository | Description |
|---|---|
| [artifact-keeper](https://github.com/artifact-keeper/artifact-keeper) | Backend API (Rust) |
| [artifact-keeper-web](https://github.com/artifact-keeper/artifact-keeper-web) | Web frontend (Next.js) |
| [artifact-keeper-api](https://github.com/artifact-keeper/artifact-keeper-api) | OpenAPI spec + generated SDKs |
| [artifact-keeper-site](https://github.com/artifact-keeper/artifact-keeper-site) | Documentation site |
