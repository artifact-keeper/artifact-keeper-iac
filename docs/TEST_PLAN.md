# Infrastructure Test Plan

## Overview

The artifact-keeper IaC repo contains Helm charts, Terraform configurations, and ArgoCD application manifests. Testing infrastructure needs to be built from scratch.

## Test Inventory

| Test Type | Framework | Count | CI Job | Status |
|-----------|-----------|-------|--------|--------|
| Helm lint | (none) | 0 | - | Missing |
| Terraform validate | (none) | 0 | - | Missing |
| Kubernetes validation | (none) | 0 | - | Missing |
| CI workflow | (none) | 0 | - | Missing |

## How to Run

### Helm
```bash
helm lint helm/artifact-keeper/
helm template artifact-keeper helm/artifact-keeper/ | kubectl apply --dry-run=client -f -
```

### Terraform
```bash
cd terraform/
terraform init
terraform validate
terraform plan
```

## Gaps and Roadmap

| Gap | Recommendation | Priority |
|-----|---------------|----------|
| No CI workflow | Create ci.yml with helm lint + terraform validate | P1 |
| No Helm testing | Add helm-unittest for chart testing | P2 |
| No Kubernetes validation | Add kubeval or kubeconform for manifest validation | P2 |
| No Terraform testing | Add terratest for infrastructure testing | P3 |
