# Releasing the artifact-keeper Helm chart

This repo publishes the `artifact-keeper` Helm chart to a GitHub Pages
chart repository on every push to `main` that bumps the chart version.

## TL;DR

1. Bump `version` and `appVersion` in `charts/artifact-keeper/Chart.yaml`
   to the same value (e.g. `1.2.0`).
2. Open a PR. The `helm-ci` workflow renders the chart and verifies that
   every image reference resolves on its registry.
3. Merge to `main`. The `helm-release` workflow tags the chart, packages
   it, and uploads the artifact to the `gh-pages` branch via
   `chart-releaser-action`.

## How chart version maps to image tag

`charts/artifact-keeper/templates/*-deployment.yaml` defaults the image
tag to `.Chart.AppVersion`:

```yaml
image: "{{ .Values.backend.image.repository }}:{{ .Values.backend.image.tag | default .Chart.AppVersion }}"
```

`values.yaml` ships with `image.tag: ""` for backend, web, and edge so
the default fires unless an overlay or `--set` overrides it. This means:

- `helm install foo --version 1.2.0` always pulls image tag `1.2.0`.
- `values-staging.yaml` and `values-production.yaml` keep their existing
  floating tags (`dev`, `latest`) by overriding `image.tag` explicitly.

There is no automatic alias mapping between chart version and image
version. They stay in lockstep because the version-check job blocks the
release if `Chart.yaml` is not bumped, and the image-reference gate
(`helm-ci.yml`) blocks the merge if the rendered image tag does not
exist on the registry.

## Step-by-step

### 1. Confirm backend/web/edge images are published

The chart pulls images from `ghcr.io/artifact-keeper/artifact-keeper-{backend,web,edge}`.
Before bumping the chart, confirm the corresponding image tag has
shipped:

```bash
# Backend (replace 1.2.0 with your target tag)
docker manifest inspect ghcr.io/artifact-keeper/artifact-keeper-backend:1.2.0
docker manifest inspect ghcr.io/artifact-keeper/artifact-keeper-web:1.2.0
```

If a 404 comes back, the image has not been published yet. The backend
release workflow (`artifact-keeper/.github/workflows/release.yml`) runs
on tag push and publishes both `ghcr.io` and `docker.io` images. Wait
for that workflow to succeed.

### 2. Bump Chart.yaml

```yaml
# charts/artifact-keeper/Chart.yaml
version: 1.2.0      # chart version
appVersion: "1.2.0" # application version (drives default image tag)
```

Both fields should be the same number for normal application releases.
If you ship a chart-only fix (template change, no app change), bump
`version` only and leave `appVersion` pinned to the application release
the templates target.

### 3. Open a PR and let CI verify

The `helm-ci` workflow on PRs runs:

- `helm lint` against the chart
- `helm template` for default, staging, and production overlays
- `verify-image-references`: for every overlay, render the chart and
  probe each rendered image reference against its registry. Fails if any
  tag returns 404.

If the image-reference job fails, you bumped the chart before the image
shipped. Either wait, or revert.

### 4. Merge to main

The `helm-release` workflow:

1. Reads `version` from `Chart.yaml`.
2. Skips if the tag `artifact-keeper-<version>` already exists.
3. Otherwise runs `chart-releaser-action`, which packages the chart,
   creates a GitHub Release named `artifact-keeper-<version>` with the
   `.tgz` attached, and updates `index.yaml` on the `gh-pages` branch.

Consumers see the new chart via the GitHub Pages chart repo:

```bash
helm repo add artifact-keeper https://artifact-keeper.github.io/artifact-keeper-iac/
helm repo update
helm search repo artifact-keeper
```

### 5. Discovery

There is no "latest" alias for charts. Consumers discover new versions
through:

- `helm search repo artifact-keeper --versions`
- The [GitHub Releases list](https://github.com/artifact-keeper/artifact-keeper-iac/releases)
- The chart's `index.yaml` on the `gh-pages` branch

Pin to a specific chart version (`--version 1.2.0`) for reproducible
deploys. ArgoCD `targetRevision` follows the same convention.

## Backports to release branches

When a chart fix needs to ship on an older release line:

1. Cherry-pick the chart change onto the relevant `release/x.y` branch.
2. Bump `version` to a patch release (e.g. `1.1.0` -> `1.1.1`); leave
   `appVersion` pinned to the existing application version on that
   branch.
3. The release workflow runs the same way on `release/x.y` branches.

## Common gotchas

- **Bumping appVersion alone does not publish a new chart.** The release
  workflow keys off chart `version`. If you bump only `appVersion`, the
  chart will reinstall to the new image tag for fresh installs but no
  new chart artifact ships.
- **Chart cache.** If a consumer ran `helm repo update` before the new
  chart shipped, they need to re-run it after the release workflow
  finishes.
- **GITHUB_TOKEN does not trigger downstream workflows.** The tag push
  performed by `chart-releaser-action` will not retrigger this workflow
  or any other workflow that listens on `push` tags. This is intentional
  and matches the chart-releaser docs.
