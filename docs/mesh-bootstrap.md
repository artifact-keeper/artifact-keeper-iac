# Bootstrapping a peer mesh with the Helm chart

This guide links two Artifact Keeper instances deployed with the `artifact-keeper` chart so that artifacts uploaded to one are replicated to the other. Adding more peers repeats the same steps.

The chart deploys peers. It does not link them. Setting `backend.replicaCount` above 1 adds backend pods to one instance, which share one database and one store; it does not create peers. See [replicaCount vs peer replication](../charts/artifact-keeper/README.md#replicacount-vs-peer-replication) in the chart README for the details.

Everything below was checked against the backend source (`backend/src/api/handlers/peers.rs`, `sync_policies.rs`, `auth.rs`, `backend/src/services/sync_worker.rs`, `backend/src/config.rs`) and the backend's own mesh end-to-end scripts (`scripts/mesh-e2e/`) in [artifact-keeper/artifact-keeper](https://github.com/artifact-keeper/artifact-keeper). The API routes and env vars used here are present in backend 1.10.1, the chart's current `appVersion`.

## How it fits together

- **One Helm release per peer.** Each release has its own PostgreSQL (in-cluster or `externalDatabase`), its own artifact storage, and its own `JWT_SECRET`. Each peer can still run several backend replicas for HA.
- **Peer identity comes from env vars.** The backend reads `PEER_INSTANCE_NAME` and `PEER_PUBLIC_ENDPOINT` at startup and stores them in its database. They are reapplied on every boot, so you can change them later with a `helm upgrade`.
- **Peers are linked through the API.** An admin registers each remote peer with `POST /api/v1/peers`, passing an `api_key` that the remote peer will accept.
- **The `api_key` you register is an API token minted on the remote peer.** The local sync worker sends it as `Authorization: Bearer <api_key>` when it probes the remote (`GET /api/v1/peers`) and when it pushes artifacts. A placeholder string gets `401`, so the peer never goes `online` and sync tasks stay `pending`.
- **What gets replicated is set per repository or by policy.** Use `POST /api/v1/peers/{id}/repositories` for a single repository, or `POST /api/v1/sync-policies` to match repositories and peers by selector.

## 1. Values for each peer

Give each peer an endpoint the other peers can reach. Across clusters this is normally the peer's Ingress, HTTPRoute, or Route hostname. When every peer is in one cluster, the backend Service DNS name is enough (for example `http://<release>-backend.<namespace>.svc.cluster.local:8080`, which is what `argocd/mesh-test-applicationset.yaml` uses).

`peer-a-values.yaml`:

```yaml
backend:
  env:
    PEER_INSTANCE_NAME: "peer-a"
    # The URL other peers use to reach this instance.
    PEER_PUBLIC_ENDPOINT: "https://peer-a.example.com"
    # Only needed if peer endpoints resolve to private addresses (RFC1918,
    # e.g. in-cluster Service IPs or a private VPC). Peer registration rejects
    # private/internal endpoints unless they are allowlisted. Keep the CIDR as
    # narrow as you can.
    # AK_SSRF_ALLOW_PRIVATE_CIDRS: "10.96.0.0/12"
  environmentSecrets:
    # Keep PEER_API_KEY stable and the same for every replica of this peer.
    # When it is unset, each backend pod generates a random key at startup.
    - name: PEER_API_KEY
      secretKeyRef:
        name: peer-a-mesh
        key: PEER_API_KEY

ingress:
  host: peer-a.example.com
```

`peer-b-values.yaml` is the same file with `peer-b` in place of `peer-a`.

Everything else (database, storage, HA settings) is configured exactly as it would be for a standalone instance. The backend does not read `PEER_ENABLED`, `PEER_SECRET_KEY`, or `PEER_AUTO_REGISTER`, so leave them out (some older docs list them).

Optional tuning, read by the backend sync worker (set under `backend.env`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `PEER_HEARTBEAT_ENABLED` | `true` | Probe registered peers to mark them `online`/`offline` |
| `PEER_HEARTBEAT_INTERVAL_SECS` | `60` | How often peers are probed |
| `PEER_HEARTBEAT_TIMEOUT_SECS` | `10` | Timeout for one probe |
| `PEER_STALE_THRESHOLD_MINUTES` | `5` | When a silent peer is marked stale |
| `SYNC_PEER_CONNECT_TIMEOUT_SECS` | `10` | TCP connect timeout for transfers |
| `SYNC_CHUNKED_THRESHOLD_BYTES` | `104857600` (100 MiB) | Artifacts above this size are sent in chunks |
| `SYNC_CHUNK_SIZE_BYTES` | `52428800` (50 MiB) | Chunk size for chunked transfers |

## 2. Install each peer as its own release

```bash
kubectl create namespace ak-peer-a
kubectl -n ak-peer-a create secret generic peer-a-mesh \
  --from-literal=PEER_API_KEY="$(openssl rand -hex 32)"
helm install peer-a charts/artifact-keeper -n ak-peer-a -f peer-a-values.yaml

kubectl create namespace ak-peer-b
kubectl -n ak-peer-b create secret generic peer-b-mesh \
  --from-literal=PEER_API_KEY="$(openssl rand -hex 32)"
helm install peer-b charts/artifact-keeper -n ak-peer-b -f peer-b-values.yaml
```

These can be different clusters. Wait until both backends are ready before continuing.

## 3. Mint a peer-link token on each peer

Do this on every peer, logged in as an admin:

```bash
A=https://peer-a.example.com
B=https://peer-b.example.com

login() {
  curl -sf -X POST "$1/api/v1/auth/login" -H 'Content-Type: application/json' \
    -d "$(jq -cn --arg p "$ADMIN_PASSWORD" '{username: "admin", password: $p}')" \
    | jq -r .access_token
}
A_JWT=$(login "$A")
B_JWT=$(login "$B")

mint() {
  curl -sf -X POST "$1/api/v1/auth/tokens" -H "Authorization: Bearer $2" \
    -H 'Content-Type: application/json' \
    -d '{"name": "mesh-peer-link", "scopes": ["admin"], "expires_in_days": 90}' \
    | jq -r .token
}
A_LINK=$(mint "$A" "$A_JWT")   # peer-b uses this to talk to peer-a
B_LINK=$(mint "$B" "$B_JWT")   # peer-a uses this to talk to peer-b
```

The backend's mesh e2e mints these tokens with the `admin` scope, as shown. A narrower scope set may be enough but has not been validated. Plan for rotation before the token expires. `/api/v1/peers/{id}` supports only `GET` and `DELETE`, but `POST /api/v1/peers/announce` upserts on the peer `name` and overwrites `endpoint_url` and `api_key`, so re-announcing a peer under the same name with a fresh token updates it in place (step 4).

## 4. Register the peers with each other

Register peer-b on peer-a:

```bash
B_ID_ON_A=$(curl -sf -X POST "$A/api/v1/peers" -H "Authorization: Bearer $A_JWT" \
  -H 'Content-Type: application/json' \
  -d "$(jq -cn --arg url "$B" --arg key "$B_LINK" \
        '{name: "peer-b", endpoint_url: $url, region: "us-west-2", api_key: $key}')" \
  | jq -r .id)
```

Then make peer-a known to peer-b. Either register it the same way with `POST $B/api/v1/peers` and `A_LINK`, or announce it under its own identity, which is what the backend e2e does:

```bash
A_PEER_ID=$(curl -sf "$A/api/v1/peers/identity" -H "Authorization: Bearer $A_JWT" | jq -r .peer_id)

curl -sf -X POST "$B/api/v1/peers/announce" -H "Authorization: Bearer $B_JWT" \
  -H 'Content-Type: application/json' \
  -d "$(jq -cn --arg id "$A_PEER_ID" --arg url "$A" --arg key "$A_LINK" \
        '{peer_id: $id, name: "peer-a", endpoint_url: $url, api_key: $key}')"
```

Registration and announce both require an admin caller. A `400` that mentions a private or internal network means the endpoint resolved to a private address; set `AK_SSRF_ALLOW_PRIVATE_CIDRS` as described in step 1.

Within one heartbeat interval, `GET /api/v1/peers` on each side should show the other peer with `"status": "online"`.

## 5. Choose what to replicate

The repository has to exist on the receiving peer as well, so create it on both peers with the same key (`POST /api/v1/repositories`) before you start syncing.

**One repository to one peer.** Subscribe peer-b to a repository on peer-a:

```bash
REPO_ID=$(curl -sf "$A/api/v1/repositories" -H "Authorization: Bearer $A_JWT" \
  | jq -r '.items[] | select(.key == "my-repo") | .id')

curl -sf -X POST "$A/api/v1/peers/$B_ID_ON_A/repositories" -H "Authorization: Bearer $A_JWT" \
  -H 'Content-Type: application/json' \
  -d "{\"repository_id\": \"$REPO_ID\", \"replication_mode\": \"push\", \"sync_enabled\": true}"
```

`replication_mode` accepts `push`, `pull`, `mirror`, or `none`. You can also pass an optional `replication_schedule` and a `replication_filter` (`{"include_patterns": [...], "exclude_patterns": [...]}`).

**By policy.** Have a sync policy match repositories and peers by selector:

```bash
curl -sf -X POST "$A/api/v1/sync-policies" -H "Authorization: Bearer $A_JWT" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "replicate-generic",
    "enabled": true,
    "repo_selector": {"match_formats": ["generic"]},
    "peer_selector": {"all": true},
    "replication_mode": "push",
    "priority": 0
  }'

curl -sf -X POST "$A/api/v1/sync-policies/evaluate" -H "Authorization: Bearer $A_JWT"
```

`repo_selector` accepts `match_labels`, `match_formats`, `match_pattern`, and `match_repos`. `peer_selector` accepts `all`, `match_labels`, `match_region`, and `match_peers`. `POST /api/v1/sync-policies/preview` shows what a policy would match before you create it.

## 6. Verify

```bash
curl -sf "$A/api/v1/peers" -H "Authorization: Bearer $A_JWT" | jq '.items[] | {name, status, last_sync_at}'
curl -sf "$A/api/v1/peers/$B_ID_ON_A/sync/tasks" -H "Authorization: Bearer $A_JWT" | jq
```

After an upload to a subscribed repository on peer-a, a sync task appears and finishes, and the artifact can then be downloaded from peer-b. To backfill artifacts that existed before the subscription, `POST /api/v1/peers/{id}/repositories/{repo_id}/sync` queues one sync task per artifact in that repository straight away instead of waiting for the next scheduled run.

## GitOps

`argocd/mesh-test-applicationset.yaml` and the `values-mesh-main.yaml` / `values-mesh-peer.yaml` overlays show the multi-release layout under ArgoCD: one Application per peer, each in its own namespace, with `PEER_INSTANCE_NAME` and `PEER_PUBLIC_ENDPOINT` passed as Helm parameters. They deploy the peers only. Steps 3 to 5 still have to run afterwards, for example from a post-sync Job or your own automation. The chart does not ship a mesh bootstrap feature yet.

## Further reading

- Chart README: [replicaCount vs peer replication](../charts/artifact-keeper/README.md#replicacount-vs-peer-replication)
- Backend docs: [Peer Replication](https://artifactkeeper.com/docs/advanced/edge-nodes/)
- Backend source: [peer and sync-policy handlers](https://github.com/artifact-keeper/artifact-keeper/tree/main/backend/src/api/handlers) and the [mesh e2e scripts](https://github.com/artifact-keeper/artifact-keeper/tree/main/scripts/mesh-e2e)
