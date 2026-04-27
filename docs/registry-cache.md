# Registry-cache: artifact-keeper as a Docker Hub pull-through cache

This document describes the dedicated artifact-keeper instance that runs
on the CI/CD runner cluster as a Docker Hub pull-through cache for the
ARC runners.

## Why

ARC runner pods are ephemeral: each runner's containerd cache disappears
with the pod, and the cluster's single egress IP exhausts the anonymous
Docker Hub pull quota quickly. We have a 45-format artifact registry
sitting on the same cluster; using it as a pull-through cache for
`docker.io` both removes the rate-limit pain and stress-tests the OCI
proxy in a real load profile.

## What it is and is not

It is:

- A dedicated artifact-keeper deployment in the `infra-registry-cache`
  namespace.
- A pinned, stable build (currently `1.1.8`). Manual upgrades only.
- The mirror target configured in DinD's `daemon.json` for ARC runners.

It is not:

- A general-purpose artifact registry. The `infra-registry-cache`
  namespace serves the cluster's CI plumbing only. Real artifact use
  cases (npm, maven, etc.) belong on the production-tier instance.
- HA. Single replica, single PVC, single node. HA is tracked separately.

## Storage layout

Static hostPath PVs on the runner host's persistent storage volume,
matching the convention used by every other AK deployment on the
cluster:

```
/srv/ak-cache/
  artifact-storage/   # OCI blobs and manifests; bound to ak-cache-artifact-storage-pv
  postgres-data/      # repo metadata, auth, etc.; bound to ak-cache-postgres-pv
```

`/srv/ak-cache/` is on the runner host's persistent-storage volume
(typically a dedicated large mount, NOT the root filesystem). The
default `local-path` storage class provisions on the root filesystem,
which is too small for a cache that may grow to 100G+; static PVs
avoid that. If your cluster's persistent-storage path differs, adjust
the hostPath values in `e2e/registry-cache-pvs.yaml` accordingly.

## Bootstrap

```bash
# All steps run with kubectl context pointed at the runner cluster.

# 1. Pre-stage host directories (one time, on the runner host).
#    Each component runs as its own uid: backend is 1000, postgres is 999.
sudo mkdir -p /srv/ak-cache/{artifact-storage,postgres-data}
sudo chown 1000:1000 /srv/ak-cache/artifact-storage
sudo chown 999:999  /srv/ak-cache/postgres-data

# 2. Create the namespace and apply the static PVs.
kubectl create namespace infra-registry-cache
kubectl apply -f e2e/registry-cache-pvs.yaml

# 3. Apply the ArgoCD Application that owns the deployment.
kubectl apply -f argocd/registry-cache-application.yaml

# 4. Wait for the backend pod to be ready.
kubectl -n infra-registry-cache rollout status deployment/ak-cache-backend
```

## Create the docker.io proxy repo

The cache is just an artifact-keeper instance; we still need one
remote/proxy Docker repo pointed at Docker Hub. Until we add a
declarative bootstrap, do this once via the API.

```bash
# Resolve the in-cluster service URL.
SVC=ak-cache-backend.infra-registry-cache.svc.cluster.local:8080
kubectl -n infra-registry-cache exec deploy/ak-cache-backend -- \
  cat /data/storage/admin.password

# Login as admin (use the bootstrap password from above), then create the repo:
TOKEN=$(curl -sf -X POST http://$SVC/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<from above>"}' | jq -r .access_token)

curl -sf -X POST http://$SVC/api/v1/repositories \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
        "key": "docker-hub-cache",
        "name": "docker-hub-cache",
        "format": "docker",
        "repo_type": "remote",
        "upstream_url": "https://registry-1.docker.io",
        "is_public": true,
        "allow_anonymous_access": true
      }'
```

Anonymous read access is intentional: the cache must serve unauthenticated
pulls because DinD has no credentials configured for this mirror.

## Wire ARC runners to the cache

```bash
kubectl apply -f e2e/dind-registry-mirror-configmap.yaml

helm upgrade --install ak-e2e-runners \
  --namespace arc-runners \
  -f argocd/arc-e2e-runners-values.yaml \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set
```

ARC runners scale to zero by default; the next CI job that spawns a runner
picks up the new DinD config. To validate, watch a runner pod start and
confirm `daemon.json` is mounted:

```bash
kubectl -n arc-runners logs -l app.kubernetes.io/name=actions-runner-controller -c dind | head
```

## Smoke test

Run a one-off CI job that pulls `postgres:16-alpine` (or trigger the
artifact-keeper coverage workflow). On the first pull the cache fetches
from Docker Hub and stores blobs to
`/srv/ak-cache/artifact-storage/`. On subsequent pulls
(different runner pod, same image) the cache serves from local storage,
with no Docker Hub egress.

Verify cache hits in the cache backend logs:

```bash
kubectl -n infra-registry-cache logs deploy/ak-cache-backend | grep docker-hub-cache | tail
```

You should see GET requests with `cache=hit` (or equivalent) on the second
and subsequent pulls.

## Upgrade procedure

The cache is pinned. To upgrade the version:

1. Open a PR that bumps `backend.image.tag` and `web.image.tag` in
   `charts/artifact-keeper/values-registry-cache.yaml` to the new stable
   release. NEVER pick `:dev`, `:latest`, or an rc tag.
2. After review and merge, sync the `registry-cache` ArgoCD Application
   manually. Do not enable auto-sync.
3. Run the smoke test above to confirm the new version still serves
   pulls correctly.
4. If anything regresses, revert the values change and resync. Cache
   data on the PVC is unaffected by the version rollback.

## Failure modes and mitigations

| Failure | Symptom | Mitigation |
|---|---|---|
| Cache pod down | Every CI image pull fails | Run two replicas (HA, tracked separately). DinD's mirror config supports a fallback chain to authenticated Docker Hub. |
| Cache PVC full | New pulls fail with disk-full | Bump PVC `capacity` in `e2e/registry-cache-pvs.yaml` (we have 1.6T headroom on /home). |
| New stable release introduces OCI proxy regression | Pulls succeed but data is wrong | Roll back `backend.image.tag` and resync. Cache data unaffected. |

## Tracked follow-up work

- HA: run two replicas with a shared CSI volume (RWX). Today's PV is RWO
  and pinned to one node.
- Authenticated Docker Hub fallback in DinD's `daemon.json` for resilience
  when the cache is down.
- Declarative bootstrap of the `docker-hub-cache` repo so a fresh apply
  doesn't need a manual API call.
- Metrics: cache hit rate, evictions, bytes served from cache vs. upstream.
