# Releasing the Helm chart

This document describes how chart releases relate to backend releases on the
[`artifact-keeper`](https://github.com/artifact-keeper/artifact-keeper) repo,
and how to cut a chart release that pairs cleanly with a specific backend
version.

Tracked under [Hardening Core](https://github.com/orgs/artifact-keeper/projects/2)
issue [#74](https://github.com/artifact-keeper/artifact-keeper-iac/issues/74).

## Two version numbers, one chart

The chart's `Chart.yaml` declares two distinct versions:

- `version` — the chart's own SemVer. Bumps independently of the backend.
- `appVersion` — the backend release this chart is intended to deploy.

The chart-releaser action tags each release as `artifact-keeper-<version>`
(e.g. `artifact-keeper-0.2.0`), which is the standard Helm-repository
convention. To make it easy to find "the chart that pairs with backend
1.1.9," every release also produces an alias tag named `chart-<appVersion>`
pointing at the same commit (e.g. `chart-1.1.9`).

Both tag names point at the same chart artifact:

```
artifact-keeper-0.2.0   <-- chart-releaser convention
chart-1.1.9             <-- backend-pairing alias
```

## Cutting a release

The flow assumes a backend release has just shipped.

1. **Bump `appVersion`** in `charts/artifact-keeper/Chart.yaml` to the new
   backend version (no `v` prefix), e.g. `appVersion: "1.1.9"`.
2. **Bump `version`** in the same file according to chart-side SemVer rules.
   Bump `patch` for value-only changes, `minor` for additive template
   changes, `major` for breaking template changes.
3. **Update default image tags** in `charts/artifact-keeper/values.yaml` for
   `backend`, `web`, and `openscap` to the new backend version. Real
   deployments should pin via their own values overlay, not rely on the
   chart default, but the default is what new operators reach for first.
4. **Verify image references resolve** by running `helm template` locally
   against the updated values and confirming each `image: ...:tag` exists
   on `ghcr.io` and `docker.io`. CI runs the same check on every PR via
   the `verify-image-references` job in `helm-ci.yml`.
5. **Open a PR** with the version bump. CI runs lint, kubeconform, image
   verification, and the install-test against k3d.
6. **Merge to `main`**. The `helm-release` workflow detects the version
   change, packages the chart, and creates two tags:
   - `artifact-keeper-<chart-version>` (e.g. `artifact-keeper-0.2.0`)
   - `chart-<appVersion>` (e.g. `chart-1.1.9`)

## Pulling a specific chart release

Once the chart is published to the gh-pages Helm repo:

```bash
helm repo add artifact-keeper https://artifact-keeper.github.io/artifact-keeper-iac/
helm repo update
helm pull artifact-keeper/artifact-keeper --version <chart-version>
```

Or, by backend pairing, against the source repo directly:

```bash
git fetch --tags
git checkout chart-1.1.9
helm package charts/artifact-keeper/
```

## What goes wrong if `appVersion` is not bumped

The release workflow's "Tag chart-${appVersion} alias" step refuses to
silently overwrite an existing `chart-<X>` tag pointing at a different
commit. If you forget to bump `appVersion` between releases, the alias
step fails with a clear error and the chart-releaser tag still gets
created (so the chart is published), but the backend-pairing alias is
left alone. Fix by either:

- Bumping `appVersion` to the actually-new backend version (most cases), or
- Manually removing the stale alias tag and re-running the release.

## What about backend `v1.1.9-rc.1`?

The same convention applies. `appVersion: "1.1.9-rc.1"` produces alias
`chart-1.1.9-rc.1`. Pre-release backend versions get pre-release chart
tags by default.

## Future automation

The current process is manual: an operator opens a PR with the version
bumps when a backend release ships. A future workflow can listen for a
`repository_dispatch` event from the backend release pipeline and open
the bump PR automatically. Tracked separately.
