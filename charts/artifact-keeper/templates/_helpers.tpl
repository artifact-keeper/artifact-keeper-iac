{{/*
=============================================================================
EXAMPLE CONFIGURATION - Getting Started Template
=============================================================================
This file is provided as a starting point for deployments. It should be
reviewed and modified to match your specific infrastructure requirements,
security policies, and operational needs before use in production.
=============================================================================
*/}}

{{/*
Expand the name of the chart.
*/}}
{{- define "artifact-keeper.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Render an image from its image values and the root context.
An optional defaultTag preserves component-specific appVersion fallbacks.
*/}}
{{- define "artifact-keeper.image" -}}
{{- $repository := required "image.repository must not be empty" .image.repository -}}
{{- $registry := .context.Values.global.imageRegistry | default "" | trim -}}
{{- if $registry -}}
  {{- $registry = regexReplaceAll "/+" (trimAll "/" $registry) "/" -}}
  {{- $host := first (splitList "/" $registry) -}}
  {{- $validRegistry := regexMatch `^(\[[0-9a-fA-F:]+\]|[^/:@[:space:]]+)(:[0-9]+)?(/[^/:@[:space:]]+)*$` $registry -}}
  {{- $qualifiedHost := or (contains "." $host) (contains ":" $host) (eq $host "localhost") -}}
  {{- if not (and $validRegistry $qualifiedHost) -}}
    {{- fail "global.imageRegistry must be a registry host (optionally with port and path), without a URL scheme, tag or digest" -}}
  {{- end -}}
  {{- $repository = regexReplaceAll "/+" (trimAll "/" (trim $repository)) "/" -}}
  {{- if not $repository -}}
    {{- fail "image.repository must not be empty" -}}
  {{- end -}}
  {{- /* Repositories already under a destination proxy path must not gain it twice. */ -}}
  {{- if not (and (contains "/" $registry) (hasPrefix (printf "%s/" $registry) $repository)) -}}
    {{- $parts := splitList "/" $repository -}}
    {{- $first := first $parts -}}
    {{- $dockerHub := true -}}
    {{- if and (gt (len $parts) 1) (or (contains "." $first) (contains ":" $first) (eq $first "localhost")) -}}
      {{- $dockerHub = has $first (list "docker.io" "index.docker.io" "registry-1.docker.io") -}}
      {{- $repository = join "/" (rest $parts) -}}
    {{- end -}}
    {{- if and $dockerHub (not (contains "/" $repository)) -}}
      {{- $repository = printf "library/%s" $repository -}}
    {{- end -}}
    {{- $repository = printf "%s/%s" $registry $repository -}}
  {{- end -}}
{{- end -}}
{{- /* A complete reference takes precedence over the separate tag, including tag@digest pins. */ -}}
{{- if or (contains "@" $repository) (contains ":" (last (splitList "/" $repository))) -}}
  {{- $repository -}}
{{- else -}}
  {{- $tag := get .image "tag" -}}
  {{- if hasKey . "defaultTag" -}}
    {{- $tag = $tag | default .defaultTag -}}
  {{- end -}}
  {{- printf "%s:%v" $repository $tag -}}
{{- end -}}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "artifact-keeper.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "artifact-keeper.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "artifact-keeper.labels" -}}
helm.sh/chart: {{ include "artifact-keeper.chart" . }}
{{ include "artifact-keeper.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: artifact-keeper
{{- end }}

{{/*
Selector labels
*/}}
{{- define "artifact-keeper.selectorLabels" -}}
app.kubernetes.io/name: {{ include "artifact-keeper.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Backend selector labels
*/}}
{{- define "artifact-keeper.backend.selectorLabels" -}}
{{ include "artifact-keeper.selectorLabels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{/*
Scan-worker selector labels
*/}}
{{- define "artifact-keeper.scanWorker.selectorLabels" -}}
{{ include "artifact-keeper.selectorLabels" . }}
app.kubernetes.io/component: scan-worker
{{- end }}

{{/*
Web selector labels
*/}}
{{- define "artifact-keeper.web.selectorLabels" -}}
{{ include "artifact-keeper.selectorLabels" . }}
app.kubernetes.io/component: web
{{- end }}

{{/*
Edge selector labels
*/}}
{{- define "artifact-keeper.edge.selectorLabels" -}}
{{ include "artifact-keeper.selectorLabels" . }}
app.kubernetes.io/component: edge
{{- end }}

{{/*
PostgreSQL selector labels
*/}}
{{- define "artifact-keeper.postgres.selectorLabels" -}}
{{ include "artifact-keeper.selectorLabels" . }}
app.kubernetes.io/component: postgres
{{- end }}

{{/*
OpenSearch selector labels
*/}}
{{- define "artifact-keeper.opensearch.selectorLabels" -}}
{{ include "artifact-keeper.selectorLabels" . }}
app.kubernetes.io/component: opensearch
{{- end }}

{{/*
OpenSearch initial cluster manager nodes (comma-separated list of pod names)
Used only when replicaCount > 1 to bootstrap a multi-node cluster.
*/}}
{{- define "artifact-keeper.opensearch.initialMasterNodes" -}}
{{- $fullName := include "artifact-keeper.fullname" . -}}
{{- $replicaCount := int .Values.opensearch.replicaCount -}}
{{- $nodes := list -}}
{{- range $i, $_ := until $replicaCount -}}
{{- $nodes = append $nodes (printf "%s-opensearch-%d" $fullName $i) -}}
{{- end -}}
{{- join "," $nodes -}}
{{- end }}

{{/*
Trivy selector labels
*/}}
{{- define "artifact-keeper.trivy.selectorLabels" -}}
{{ include "artifact-keeper.selectorLabels" . }}
app.kubernetes.io/component: trivy
{{- end }}

{{/*
Scanner-adapter selector labels
*/}}
{{- define "artifact-keeper.scannerAdapter.selectorLabels" -}}
{{ include "artifact-keeper.selectorLabels" . }}
app.kubernetes.io/component: scanner-adapter
{{- end }}

{{/*
Image builder (buildkitd) selector labels
*/}}
{{- define "artifact-keeper.imageBuilder.selectorLabels" -}}
{{ include "artifact-keeper.selectorLabels" . }}
app.kubernetes.io/component: image-builder
{{- end }}

{{/*
DependencyTrack selector labels
*/}}
{{- define "artifact-keeper.dtrack.selectorLabels" -}}
{{ include "artifact-keeper.selectorLabels" . }}
app.kubernetes.io/component: dependency-track
{{- end }}

{{/*
Whether the Ingress gets the nginx proxy annotations: "true" for className
`nginx`, or for any class when ingress.nginxAnnotations is true.
*/}}
{{- define "artifact-keeper.ingress.rendersNginxAnnotations" -}}
{{- if or (eq (default "" .Values.ingress.className) "nginx") .Values.ingress.nginxAnnotations -}}true{{- end -}}
{{- end -}}

{{/*
The nginx proxy annotations derived from ingress.maxBodySize,
proxyReadTimeoutSeconds and proxySendTimeoutSeconds, as YAML.
*/}}
{{- define "artifact-keeper.ingress.nginxAnnotations" -}}
{{- $derived := dict -}}
{{- with .Values.ingress.maxBodySize -}}
{{- $_ := set $derived "nginx.ingress.kubernetes.io/proxy-body-size" (toString .) -}}
{{- end -}}
{{- if not (kindIs "invalid" .Values.ingress.proxyReadTimeoutSeconds) -}}
{{- $_ := set $derived "nginx.ingress.kubernetes.io/proxy-read-timeout" (toString .Values.ingress.proxyReadTimeoutSeconds) -}}
{{- end -}}
{{- if not (kindIs "invalid" .Values.ingress.proxySendTimeoutSeconds) -}}
{{- $_ := set $derived "nginx.ingress.kubernetes.io/proxy-send-timeout" (toString .Values.ingress.proxySendTimeoutSeconds) -}}
{{- end -}}
{{- toYaml $derived -}}
{{- end -}}

{{/*
Database URL helper — returns the full DATABASE_URL string
*/}}
{{- define "artifact-keeper.databaseUrl" -}}
{{- if .Values.postgres.enabled -}}
postgresql://{{ .Values.postgres.auth.username }}:{{ include "artifact-keeper.postgresPassword" . }}@{{ include "artifact-keeper.fullname" . }}-postgres:5432/{{ .Values.postgres.auth.database }}
{{- else -}}
postgresql://{{ .Values.externalDatabase.username }}:{{ .Values.externalDatabase.password }}@{{ .Values.externalDatabase.host }}:{{ .Values.externalDatabase.port }}/{{ .Values.externalDatabase.database }}
{{- end -}}
{{- end }}

{{/*
ServiceAccount name
*/}}
{{- define "artifact-keeper.serviceAccountName" -}}
{{- if .Values.backend.serviceAccount.create }}
{{- default (printf "%s-backend" (include "artifact-keeper.fullname" .)) .Values.backend.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.backend.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Name of the Secret holding core application credentials (JWT_SECRET and, when
applicable, DATABASE_URL/POSTGRES_PASSWORD). When secrets.existingSecret is set
the chart does not render its own Secret and workloads read from the
operator-supplied Secret; otherwise this is the chart-managed
"<fullname>-secrets" (the same name used by the externalSecrets target).
*/}}
{{- define "artifact-keeper.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- printf "%s-secrets" (include "artifact-keeper.fullname" .) -}}
{{- end -}}
{{- end -}}

{{/*
A credential the chart generates when the operator leaves it empty. Takes a dict
with root (the chart context), key (the key in the chart's Secret) and length.

Resolution order, and the order matters:

  1. The value stored under that key in the chart's Secret, read back with
     lookup. This is what keeps it stable across "helm upgrade".
  2. A value already generated during this render. randAlphaNum differs on every
     call, and DATABASE_URL and POSTGRES_PASSWORD must hold the same password,
     so the first result is kept in .Values for the rest of the render. Helm
     does not store this: a release stores only the values the operator passed.
  3. A freshly generated alphanumeric value. Alphanumeric because the password
     goes into DATABASE_URL unencoded.

lookup returns nothing under "helm template" and client-side "--dry-run", so
those renders produce a new value every time. A GitOps engine that deploys by
running "helm template" would rotate these on every sync, so such operators must
set the values or use secrets.existingSecret. See the README, "Generated
credentials".
*/}}
{{- define "artifact-keeper.generatedSecret" -}}
{{- $values := .root.Values -}}
{{- if not (hasKey $values "_generatedSecrets") -}}
{{- $_ := set $values "_generatedSecrets" dict -}}
{{- end -}}
{{- if not (hasKey $values._generatedSecrets .key) -}}
{{- $existing := "" -}}
{{- $secret := lookup "v1" "Secret" .root.Release.Namespace (include "artifact-keeper.secretName" .root) -}}
{{- if and $secret $secret.data -}}
{{- $existing = index $secret.data .key | default "" | b64dec -}}
{{- end -}}
{{- $_ := set $values._generatedSecrets .key (default (randAlphaNum .length) $existing) -}}
{{- end -}}
{{- index $values._generatedSecrets .key -}}
{{- end -}}

{{/*
JWT signing secret: secrets.jwtSecret if set, otherwise generated. 64 alphanumeric
characters clears the backend's checks (32 characters, 128 estimated bits).
*/}}
{{- define "artifact-keeper.jwtSecret" -}}
{{- if .Values.secrets.jwtSecret -}}
{{- .Values.secrets.jwtSecret -}}
{{- else -}}
{{- include "artifact-keeper.generatedSecret" (dict "root" . "key" "JWT_SECRET" "length" 64) -}}
{{- end -}}
{{- end -}}

{{/*
In-chart Postgres password: postgres.auth.password if set, otherwise generated.
*/}}
{{- define "artifact-keeper.postgresPassword" -}}
{{- if .Values.postgres.auth.password -}}
{{- .Values.postgres.auth.password -}}
{{- else -}}
{{- include "artifact-keeper.generatedSecret" (dict "root" . "key" "POSTGRES_PASSWORD" "length" 32) -}}
{{- end -}}
{{- end -}}

{{/*
Whether generation is off. Only an explicit false turns it off: "helm upgrade
--reuse-values" from a chart without secrets.generate leaves the key unset.
*/}}
{{- define "artifact-keeper.secretGenerationDisabled" -}}
{{- if eq (toString .Values.secrets.generate) "false" -}}true{{- end -}}
{{- end -}}

{{/*
Comma-separated values the chart is generating or preserving for this release,
empty when every credential is supplied or the chart renders no Secret.
*/}}
{{- define "artifact-keeper.generatedSecretNames" -}}
{{- $names := list -}}
{{- if and (not .Values.externalSecrets.enabled) (not .Values.secrets.existingSecret) (ne (include "artifact-keeper.secretGenerationDisabled" .) "true") -}}
{{- if not .Values.secrets.jwtSecret -}}{{- $names = append $names "secrets.jwtSecret" -}}{{- end -}}
{{- if and .Values.postgres.enabled (not .Values.postgres.auth.password) -}}{{- $names = append $names "postgres.auth.password" -}}{{- end -}}
{{- end -}}
{{- join ", " $names -}}
{{- end -}}

{{/*
Dependency-Track admin password.

Resolution order, and the order matters:

  1. An explicit dependencyTrack.adminPassword, if set.
  2. The password already stored in the chart's Secret, read back with lookup.
  3. A freshly generated 32-character password.

Step 2 is what makes this safe across "helm upgrade". Without it, randAlphaNum
would mint a new password on every render, the Secret would change, and the
bootstrap Job would then try to log in to a Dependency-Track that still has the
old one. The lookup keeps the first generated password stable for the life of
the release.

Note that lookup returns nothing during "helm template" and "--dry-run", since
there is no cluster to read. For a one-off render that is harmless: the
manifest simply shows a throwaway value. It matters a great deal under GitOps
engines that deploy by re-running "helm template" (Argo CD): there, step 2 never
fires and every sync would generate a fresh password, silently desyncing the
Secret from the password Dependency-Track actually holds. With such an engine, set
dependencyTrack.adminPassword explicitly or use secrets.existingSecret, as the dev
element of this repo's ApplicationSet does (values-dev.yaml).

Previously this defaulted to an empty string, which the bootstrap script then
passed to forceChangePassword; Dependency-Track rejects an empty password with
406 and the integration never completed (iac issue 202).
*/}}
{{- define "artifact-keeper.dtrackAdminPassword" -}}
{{- if .Values.dependencyTrack.adminPassword -}}
{{- .Values.dependencyTrack.adminPassword -}}
{{- else -}}
{{- $secret := lookup "v1" "Secret" .Release.Namespace (include "artifact-keeper.secretName" .) -}}
{{- $existing := "" -}}
{{- if and $secret $secret.data -}}
{{- $existing = index $secret.data "DEPENDENCY_TRACK_ADMIN_PASSWORD" | default "" -}}
{{- end -}}
{{- if $existing -}}
{{- $existing | b64dec -}}
{{- else -}}
{{- randAlphaNum 32 -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Space-separated Dependency-Track permission names the bootstrap Job grants to
the Automation team (dependencyTrack.bootstrap.automationPermissions). Each
entry must be an uppercase permission identifier such as BOM_UPLOAD; anything
else fails the render, because the names are interpolated into the bootstrap
script and a request path. `dig` falls back to the chart default for
`helm upgrade --reuse-values` from a chart that predates the key.
*/}}
{{- define "artifact-keeper.dtrackAutomationPermissions" -}}
{{- $default := list "BOM_UPLOAD" "PROJECT_CREATION_UPLOAD" "PORTFOLIO_MANAGEMENT" "VIEW_PORTFOLIO" "VIEW_VULNERABILITY" "VULNERABILITY_ANALYSIS" -}}
{{- $perms := dig "bootstrap" "automationPermissions" $default .Values.dependencyTrack -}}
{{- if not (kindIs "slice" $perms) -}}
{{- fail "dependencyTrack.bootstrap.automationPermissions must be a list of Dependency-Track permission names, e.g. [BOM_UPLOAD, VIEW_PORTFOLIO]" -}}
{{- end -}}
{{- range $perms -}}
{{- if not (and (kindIs "string" .) (regexMatch "^[A-Z][A-Z0-9_]*$" .)) -}}
{{- fail (printf "dependencyTrack.bootstrap.automationPermissions entry %q is not a Dependency-Track permission name (uppercase letters, digits and underscores, e.g. BOM_UPLOAD)" (toString .)) -}}
{{- end -}}
{{- end -}}
{{- join " " (uniq $perms) -}}
{{- end -}}

{{/*
Whether the Dependency-Track API key travels through the shared-config volume.
False when dependencyTrack.existingApiKeySecret supplies it instead: the volume,
its mount, DEPENDENCY_TRACK_API_KEY_FILE and the claim are all skipped, and the
backend reads DEPENDENCY_TRACK_API_KEY.

The claim is ReadWriteOnce and has no accessModes knob, so on block storage it
attaches to one node and pins every backend replica there, which is what stops
backend.replicaCount > 1 from spreading. The backend's resolve_api_key prefers
DEPENDENCY_TRACK_API_KEY over the file (dependency_track_service.rs), so the file
is not required when the key is supplied directly. See iac issue 313.
*/}}
{{- define "artifact-keeper.dtrackApiKeyFile" -}}
{{- if and .Values.dependencyTrack.enabled (not .Values.dependencyTrack.existingApiKeySecret) -}}true{{- end -}}
{{- end -}}

{{/*
Name of the shared-config claim mounted by the backend and the
Dependency-Track bootstrap Job: backend.sharedConfig.existingClaim when set,
otherwise the chart-managed <fullname>-shared-config PVC.
*/}}
{{- define "artifact-keeper.sharedConfigClaimName" -}}
{{- .Values.backend.sharedConfig.existingClaim | default (printf "%s-shared-config" (include "artifact-keeper.fullname" .)) -}}
{{- end -}}

{{/*
Reject existingClaim values the chart cannot honor. An existingClaim replaces a
chart-managed PVC, so it only makes sense while that volume is persistent.
*/}}
{{- define "artifact-keeper.validateExistingClaims" -}}
{{- if and .Values.backend.enabled .Values.backend.persistence.existingClaim -}}
{{- if .Values.backend.persistence.ephemeral.enabled -}}
{{- fail "backend.persistence.existingClaim cannot be combined with backend.persistence.ephemeral.enabled: the ephemeral mode creates a per-pod PVC, so there is no shared claim to replace. Unset one of them." -}}
{{- end -}}
{{- if not .Values.backend.persistence.enabled -}}
{{- fail "backend.persistence.existingClaim requires backend.persistence.enabled=true (with persistence disabled the backend uses an emptyDir and would ignore the claim)" -}}
{{- end -}}
{{- end -}}
{{- if and .Values.backend.enabled .Values.backend.scanWorkspace.existingClaim (not .Values.backend.scanWorkspace.enabled) -}}
{{- fail "backend.scanWorkspace.existingClaim requires backend.scanWorkspace.enabled=true (with it disabled each backend pod gets an emptyDir and would ignore the claim)" -}}
{{- end -}}
{{- if and .Values.opensearch.enabled .Values.opensearch.persistence.existingClaim -}}
{{- if not .Values.opensearch.persistence.enabled -}}
{{- fail "opensearch.persistence.existingClaim requires opensearch.persistence.enabled=true (with persistence disabled OpenSearch uses an emptyDir and would ignore the claim)" -}}
{{- end -}}
{{- if gt (int .Values.opensearch.replicaCount) 1 -}}
{{- fail "opensearch.persistence.existingClaim is only supported with opensearch.replicaCount=1: a multi-node cluster is a StatefulSet whose volumeClaimTemplates give each node its own PVC, and one claim cannot back several nodes" -}}
{{- end -}}
{{- end -}}
{{- if and .Values.imageBuilder.enabled .Values.imageBuilder.persistence.existingClaim (not .Values.imageBuilder.persistence.enabled) -}}
{{- fail "imageBuilder.persistence.existingClaim requires imageBuilder.persistence.enabled=true (with persistence disabled the build cache is an emptyDir and would ignore the claim)" -}}
{{- end -}}
{{- end -}}

{{/*
Database Dependency-Track connects to (dependencyTrack.database). An empty value
falls back to dependency_track rather than rendering a JDBC URL ending in "/"
and an init script with "CREATE DATABASE ;".
*/}}
{{- define "artifact-keeper.dtrackDatabase" -}}
{{- .Values.dependencyTrack.database | default "dependency_track" -}}
{{- end -}}

{{/*
Whether Dependency-Track reads its database password from
externalDatabase.existingSecret instead of the chart's app Secret (secretName).

Only with an external database and externalDatabase.existingSecret set, and then
only when one of these holds:
- externalDatabase.existingPasswordKey is set: the operator says where it is.
- The chart renders its own Secret (no externalSecrets.enabled, no
  secrets.existingSecret). secrets.yaml leaves POSTGRES_PASSWORD out of that
  Secret whenever externalDatabase.existingSecret is set, so secretName has
  nothing to offer.
With External Secrets (which syncs POSTGRES_PASSWORD) or secrets.existingSecret,
the app Secret keeps supplying it, as before.
*/}}
{{- define "artifact-keeper.dtrackDbPasswordFromExistingSecret" -}}
{{- $ext := .Values.externalDatabase -}}
{{- if and (not .Values.postgres.enabled) $ext.existingSecret -}}
{{- if or $ext.existingPasswordKey (and (not .Values.externalSecrets.enabled) (not .Values.secrets.existingSecret)) -}}true{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Whether Dependency-Track's JDBC host and port come from externalDatabase.existingSecret
(keys existingHostKey / existingPortKey) instead of values. Only with an external
database, existingSecret set and externalDatabase.host empty: a host set in values
always wins, together with externalDatabase.port, so a Secret holding only
DATABASE_URL keeps working.
*/}}
{{- define "artifact-keeper.dtrackDbHostFromExistingSecret" -}}
{{- $ext := .Values.externalDatabase -}}
{{- if and (not .Values.postgres.enabled) $ext.existingSecret (not $ext.host) -}}true{{- end -}}
{{- end -}}

{{- define "artifact-keeper.validateSecrets" -}}
{{- if or .Values.externalSecrets.enabled .Values.secrets.existingSecret -}}
{{- /* Secrets are supplied externally; no chart-owned Secret to validate. */ -}}
{{- else -}}
{{- if eq (include "artifact-keeper.secretGenerationDisabled" .) "true" -}}
{{- if eq .Values.secrets.jwtSecret "" -}}
{{- fail "secrets.jwtSecret is required when externalSecrets is not enabled and secrets.generate is false. Set it with --set secrets.jwtSecret=<value>" -}}
{{- end -}}
{{- if and .Values.postgres.enabled (eq .Values.postgres.auth.password "") -}}
{{- fail "postgres.auth.password is required when postgres is enabled and secrets.generate is false. Set it with --set postgres.auth.password=<value>" -}}
{{- end -}}
{{- end -}}
{{- if and .Values.opensearch.enabled (not .Values.opensearch.disableSecurityPlugin) (eq .Values.opensearch.auth.password "") -}}
{{- fail "opensearch.auth.password is required when opensearch is enabled and disableSecurityPlugin is false. Set it with --set opensearch.auth.password=<value>" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Credential-like keys set to a non-empty value in backend.env, as a
comma-separated string ("" when there are none). backend.env is rendered
verbatim into the pod spec, so a value there is readable by anyone who can get
the Deployment or its pods, or read the Helm release Secret (#375).
Credentials belong in backend.environmentSecrets (secretKeyRef). DATABASE_URL
counts only when it carries a password. Empty values are placeholders and pass.
*/}}
{{- define "artifact-keeper.backendEnvCredentials" -}}
{{- $env := .Values.backend.env | default dict -}}
{{- $secretEnv := list -}}
{{- range .Values.backend.environmentSecrets -}}
{{- $secretEnv = append $secretEnv .name -}}
{{- end -}}
{{- $env = deepCopy $env -}}
{{- range $secretEnv -}}
{{- $_ := unset $env . -}}
{{- end -}}
{{- $found := list -}}
{{- range $key := list
    "ADMIN_PASSWORD" "INITIAL_ADMIN_PASSWORD" "JWT_SECRET"
    "S3_SECRET_KEY" "S3_SECRET_ACCESS_KEY" "S3_PRESIGN_SECRET_ACCESS_KEY"
    "AZURE_STORAGE_ACCESS_KEY" "AZURE_CLIENT_SECRET" "GCS_PRIVATE_KEY" "CLOUDFRONT_PRIVATE_KEY"
    "DEPENDENCY_TRACK_API_KEY" "DTRACK_HTTP_PROXY_PASSWORD" "OPENSEARCH_PASSWORD"
    "OIDC_CLIENT_SECRET" "LDAP_BIND_PASSWORD" "SMTP_PASSWORD" "GITHUB_TOKEN"
    "PEER_API_KEY" "EDGE_API_KEY"
    "SSO_ENCRYPTION_KEY" "MIGRATION_ENCRYPTION_KEY" "AK_WEBHOOK_SECRET_KEY" -}}
{{- if toString (get $env $key) -}}
{{- $found = append $found $key -}}
{{- end -}}
{{- end -}}
{{- if regexMatch "^[A-Za-z][A-Za-z0-9+.-]*://[^/?#@]*:[^/?#@]+@" (toString (get $env "DATABASE_URL")) -}}
{{- $found = append $found "DATABASE_URL" -}}
{{- end -}}
{{- join ", " $found -}}
{{- end -}}

{{/*
Fail the render when backend.env carries credentials, unless
backend.allowCredentialsInEnv acknowledges it (NOTES.txt then warns).
*/}}
{{- define "artifact-keeper.validateBackendEnvCredentials" -}}
{{- /* dig: `helm upgrade --reuse-values` keeps the previous chart's defaults, which lack this key. */ -}}
{{- $allow := dig "allowCredentialsInEnv" false .Values.backend -}}
{{- if not (kindIs "bool" $allow) -}}
{{- fail "backend.allowCredentialsInEnv must be a boolean" -}}
{{- end -}}
{{- $found := include "artifact-keeper.backendEnvCredentials" . -}}
{{- if and $found (not $allow) -}}
{{- fail (printf "backend.env sets %s. backend.env is rendered in plaintext into the pod spec, where anyone who can read the Deployment, its pods or the Helm release can recover it. Move each one to backend.environmentSecrets (a secretKeyRef to a Secret you manage; see values.yaml) and rotate the exposed value, or set backend.allowCredentialsInEnv=true to accept the exposure (throwaway test installs only)." $found) -}}
{{- end -}}
{{- end -}}

{{/*
Returns "true" when the chart Secret carries SMTP_PASSWORD, so the backend
should reference it. Mirrors the encryption-key wiring below: with
externalSecrets.enabled the ExternalSecret maps the key whenever
externalSecrets.secrets.smtpPassword is set, so secrets.smtpPassword (which
then has nowhere to go) is not consulted; otherwise a nonempty
secrets.smtpPassword enables the reference (into the chart-rendered Secret, or
into secrets.existingSecret for compatibility).
*/}}
{{- define "artifact-keeper.smtpPasswordManaged" -}}
{{- if .Values.externalSecrets.enabled -}}
{{- if .Values.externalSecrets.secrets.smtpPassword -}}true{{- end -}}
{{- else if .Values.secrets.smtpPassword -}}true{{- end -}}
{{- end -}}

{{/*
Optional backend encryption keys. Flags opt into conventional keys in an
operator-managed Secret without putting credential-shaped placeholders in values.
Validate only these env names; other backend environment wiring is independent.
*/}}
{{- define "artifact-keeper.encryptionKeyEnv" -}}
{{- $root := . -}}
{{- range $key := list
    (dict "value" "migrationEncryptionKey" "flag" "migrationEncryptionKeyEnabled" "env" "MIGRATION_ENCRYPTION_KEY")
    (dict "value" "webhookSecretKey" "flag" "webhookSecretKeyEnabled" "env" "AK_WEBHOOK_SECRET_KEY")
    (dict "value" "ssoEncryptionKey" "flag" "ssoEncryptionKeyEnabled" "env" "SSO_ENCRYPTION_KEY") -}}
{{- $enabled := get $root.Values.secrets $key.flag -}}
{{- if not (kindIs "bool" $enabled) -}}
{{- fail (printf "secrets.%s must be a boolean" $key.flag) -}}
{{- end -}}
{{- if and $enabled (or (not $root.Values.secrets.existingSecret) $root.Values.externalSecrets.enabled) -}}
{{- fail (printf "secrets.%s requires secrets.existingSecret and externalSecrets.enabled=false" $key.flag) -}}
{{- end -}}
{{- $managed := or $enabled
    (and $root.Values.externalSecrets.enabled (get $root.Values.externalSecrets.secrets $key.value))
    (and (not $root.Values.externalSecrets.enabled) (get $root.Values.secrets $key.value)) -}}
{{- $sources := 0 -}}
{{- if $managed -}}{{- $sources = add $sources 1 -}}{{- end -}}
{{- if hasKey $root.Values.backend.env $key.env -}}{{- $sources = add $sources 1 -}}{{- end -}}
{{- range $root.Values.backend.environmentSecrets -}}
{{- if eq .name $key.env -}}{{- $sources = add $sources 1 -}}{{- end -}}
{{- end -}}
{{- if gt $sources 1 -}}
{{- fail (printf "%s has multiple definitions; use only one of chart secret wiring, backend.env, or backend.environmentSecrets" $key.env) -}}
{{- end -}}
{{- if $managed }}
- name: {{ $key.env }}
  valueFrom:
    secretKeyRef:
      name: {{ include "artifact-keeper.secretName" $root }}
      key: {{ $key.env }}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Optional backend tuning variables from backend.logging (LOG_FORMAT, LOG_ANSI,
#387) and backend.stuckScan (STUCK_SCAN_THRESHOLD_SECS,
STUCK_SCAN_CHECK_INTERVAL_SECS, #101). Each renders only when its value
differs from the backend's own default, so an install that leaves them alone
renders no new variables. Invalid values fail the render.

As with METRICS_PORT (#381), each name is rendered at most once. A
backend.env entry with the same name wins when the chart value is left at its
default, and must agree with it otherwise; a backend.environmentSecrets entry
with the same name conflicts with a non-default chart value.
*/}}
{{- define "artifact-keeper.backendTuningEnv" -}}
{{- $backend := .Values.backend -}}
{{- $env := $backend.env | default dict -}}
{{- /* dig: `helm upgrade --reuse-values` keeps the previous chart's
       defaults, which lack these keys. */ -}}
{{- $logging := dig "logging" dict $backend -}}
{{- $stuck := dig "stuckScan" dict $backend -}}
{{- if kindIs "invalid" $logging -}}{{- $logging = dict -}}{{- end -}}
{{- if kindIs "invalid" $stuck -}}{{- $stuck = dict -}}{{- end -}}
{{- if not (kindIs "map" $logging) -}}
{{- fail "backend.logging must be a map" -}}
{{- end -}}
{{- if not (kindIs "map" $stuck) -}}
{{- fail "backend.stuckScan must be a map" -}}
{{- end -}}
{{- $vars := list -}}
{{- /* hasKey, not `default`: `default` would turn an explicit false into the
       default and hide a mistyped value. */ -}}
{{- $format := "text" -}}
{{- if hasKey $logging "format" -}}{{- $format = get $logging "format" -}}{{- end -}}
{{- if not (and (kindIs "string" $format) (has $format (list "text" "json"))) -}}
{{- fail (printf "backend.logging.format must be \"text\" or \"json\"; got %v" $format) -}}
{{- end -}}
{{- if ne $format "text" -}}
{{- $vars = append $vars (dict "name" "LOG_FORMAT" "value" $format "path" "backend.logging.format") -}}
{{- end -}}
{{- $ansi := "auto" -}}
{{- if hasKey $logging "ansi" -}}{{- $ansi = get $logging "ansi" -}}{{- end -}}
{{- if not (or (kindIs "bool" $ansi) (and (kindIs "string" $ansi) (has $ansi (list "auto" "true" "false")))) -}}
{{- fail (printf "backend.logging.ansi must be \"auto\", \"true\" or \"false\"; got %v" $ansi) -}}
{{- end -}}
{{- $ansi = toString $ansi -}}
{{- if ne $ansi "auto" -}}
{{- $vars = append $vars (dict "name" "LOG_ANSI" "value" $ansi "path" "backend.logging.ansi") -}}
{{- end -}}
{{- range $item := list
    (dict "key" "thresholdSecs" "name" "STUCK_SCAN_THRESHOLD_SECS")
    (dict "key" "checkIntervalSecs" "name" "STUCK_SCAN_CHECK_INTERVAL_SECS") -}}
{{- $path := printf "backend.stuckScan.%s" $item.key -}}
{{- if and (hasKey $stuck $item.key) (not (kindIs "invalid" (get $stuck $item.key))) -}}
{{- $value := get $stuck $item.key -}}
{{- $valid := false -}}
{{- if or (kindIs "int" $value) (kindIs "int64" $value) (kindIs "float64" $value) -}}
{{- $valid = and (gt (float64 $value) 0.0) (eq (float64 (int64 $value)) (float64 $value)) -}}
{{- else if kindIs "string" $value -}}
{{- $valid = regexMatch "^[1-9][0-9]{0,9}$" $value -}}
{{- end -}}
{{- if not $valid -}}
{{- fail (printf "%s must be a positive integer number of seconds or null; got %v" $path $value) -}}
{{- end -}}
{{- $vars = append $vars (dict "name" $item.name "value" (printf "%d" (int64 $value)) "path" $path) -}}
{{- end -}}
{{- end -}}
{{- $secretEnv := list -}}
{{- range $backend.environmentSecrets -}}
{{- $secretEnv = append $secretEnv .name -}}
{{- end -}}
{{- range $vars -}}
{{- if has .name $secretEnv -}}
{{- fail (printf "%s is set by %s and also by backend.environmentSecrets; remove one" .name .path) -}}
{{- end -}}
{{- if hasKey $env .name -}}
{{- if ne (toString (get $env .name)) .value -}}
{{- fail (printf "backend.env.%s (%v) conflicts with %s (%s): remove the backend.env entry or set both to the same value" .name (get $env .name) .path .value) -}}
{{- end -}}
{{- else }}
- name: {{ .name }}
  value: {{ .value | quote }}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Returns "true" when the chart should inject ALLOW_HTTP_INTEGRATIONS=1 into
the backend, "" otherwise. An explicit ALLOW_HTTP_INTEGRATIONS entry in
backend.env wins over backend.allowHttpIntegrations entirely (the chart
renders nothing in that case). Invalid modes fail the render.
*/}}
{{- define "artifact-keeper.allowHttpIntegrations" -}}
{{- if hasKey .Values.backend.env "ALLOW_HTTP_INTEGRATIONS" -}}
{{- else -}}
{{- /* Do not use `default "auto"` here: helm's default treats a boolean
   false (--set backend.allowHttpIntegrations=false) as empty and would
   silently fall back to auto. */ -}}
{{- $mode := "auto" -}}
{{- if not (kindIs "invalid" .Values.backend.allowHttpIntegrations) -}}
{{- $mode = toString .Values.backend.allowHttpIntegrations -}}
{{- end -}}
{{- if eq $mode "true" -}}
true
{{- else if eq $mode "false" -}}
{{- else if eq $mode "auto" -}}
{{- if .Values.dependencyTrack.enabled -}}true{{- end -}}
{{- else -}}
{{- fail (printf "backend.allowHttpIntegrations must be one of \"auto\", \"true\", or \"false\"; got %q" $mode) -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
=============================================================================
Fleet mode helpers
=============================================================================
Fleet mode runs many instances per cluster, one Helm release per instance,
sharing external database, search, scanning, and object storage. Every helper
below is gated on fleet.enabled. When fleet mode is off (the default) each
helper falls back to the existing per-component values, so rendered output is
unchanged from a standard single-instance install.
*/}}

{{/*
Returns the string "true" when this release runs in fleet mode.
Callers gate on: eq (include "artifact-keeper.fleet.enabled" .) "true"
*/}}
{{- define "artifact-keeper.fleet.enabled" -}}
{{- if and .Values.fleet .Values.fleet.enabled -}}true{{- end -}}
{{- end -}}

{{/*
Returns "true" when a fleet instance is hibernated. Hibernated instances scale
their backend and web workloads to zero replicas.
*/}}
{{- define "artifact-keeper.fleet.hibernate" -}}
{{- if and (eq (include "artifact-keeper.fleet.enabled" .) "true") .Values.fleet.hibernate -}}true{{- end -}}
{{- end -}}

{{/*
PostgreSQL identifier for an instance (role and database share the name).
Instance ids may use dashes; PostgreSQL identifiers use underscores, so the id
is normalized and prefixed with ak_ to give a stable role/database name.
*/}}
{{- define "artifact-keeper.fleet.dbIdentifier" -}}
{{- printf "ak_%s" (.Values.fleet.instanceId | replace "-" "_") -}}
{{- end -}}

{{/*
Preset sizing table keyed on fleet.preset (small|medium|large). Returns YAML
for the selected preset with backend/web replica counts and resource blocks.
Presets are chart-owned so an instance spec only carries the preset name.
An empty preset falls back to small; any other value fails the render.

Every preset gives the backend a 16Gi ephemeral-storage limit, matching the
non-fleet backend.resources default raised in #116: with persistence off the
backend's scratch volumes can grow to about 12Gi, and a smaller limit gets the
pod evicted mid-operation (#350). Requests stay small so scheduling is not
affected; the web limits are unchanged.
*/}}
{{- define "artifact-keeper.fleet.presetSpec" -}}
{{- $preset := default "small" .Values.fleet.preset -}}
{{- $table := dict
  "small" (dict
    "backendReplicas" 1
    "webReplicas" 1
    "backend" (dict
      "requests" (dict "cpu" "250m" "memory" "512Mi" "ephemeral-storage" "256Mi")
      "limits" (dict "cpu" "1" "memory" "1Gi" "ephemeral-storage" "16Gi"))
    "web" (dict
      "requests" (dict "cpu" "100m" "memory" "128Mi" "ephemeral-storage" "128Mi")
      "limits" (dict "cpu" "500m" "memory" "512Mi" "ephemeral-storage" "1Gi")))
  "medium" (dict
    "backendReplicas" 2
    "webReplicas" 2
    "backend" (dict
      "requests" (dict "cpu" "500m" "memory" "1Gi" "ephemeral-storage" "512Mi")
      "limits" (dict "cpu" "2" "memory" "2Gi" "ephemeral-storage" "16Gi"))
    "web" (dict
      "requests" (dict "cpu" "250m" "memory" "256Mi" "ephemeral-storage" "256Mi")
      "limits" (dict "cpu" "1" "memory" "1Gi" "ephemeral-storage" "2Gi")))
  "large" (dict
    "backendReplicas" 3
    "webReplicas" 2
    "backend" (dict
      "requests" (dict "cpu" "1" "memory" "2Gi" "ephemeral-storage" "1Gi")
      "limits" (dict "cpu" "4" "memory" "4Gi" "ephemeral-storage" "16Gi"))
    "web" (dict
      "requests" (dict "cpu" "500m" "memory" "512Mi" "ephemeral-storage" "512Mi")
      "limits" (dict "cpu" "2" "memory" "2Gi" "ephemeral-storage" "2Gi")))
  -}}
{{- $spec := index $table $preset -}}
{{- if not $spec -}}
{{- fail (printf "fleet.preset=%q is not valid; use one of small, medium, large" $preset) -}}
{{- end -}}
{{- $spec | toYaml -}}
{{- end -}}

{{/*
Renders the body of a Deployment's .spec.strategy from a component's `strategy`
value. Call with a dict of the value and the values-path it came from (the path
is only used to make a validation failure point at the right key):

  {{- include "artifact-keeper.deploymentStrategy" (dict "strategy" .Values.backend.strategy "path" "backend.strategy") | nindent 4 }}

An unset or empty value renders `type: Recreate`, which is what every
PVC-backed component in this chart shipped hardcoded before the value existed.
`rollingUpdate` is passed through verbatim but only when the type is actually
RollingUpdate -- the Deployment API rejects a rollingUpdate block under
`type: Recreate`.
*/}}
{{- define "artifact-keeper.deploymentStrategy" -}}
{{- $strategy := .strategy | default dict -}}
{{- $type := $strategy.type | default "Recreate" -}}
{{- if not (has $type (list "Recreate" "RollingUpdate")) -}}
{{- fail (printf "%s.type=%q is not valid; use \"Recreate\" or \"RollingUpdate\"" .path $type) -}}
{{- end -}}
type: {{ $type }}
{{- if eq $type "RollingUpdate" }}
{{- with $strategy.rollingUpdate }}
rollingUpdate:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}
{{- end -}}

{{/*
Backend replica count. Zero when hibernated, the preset count in fleet mode,
otherwise the per-component value.
*/}}
{{- define "artifact-keeper.backend.replicaCount" -}}
{{- if eq (include "artifact-keeper.fleet.hibernate" .) "true" -}}
0
{{- else if eq (include "artifact-keeper.fleet.enabled" .) "true" -}}
{{- (fromYaml (include "artifact-keeper.fleet.presetSpec" .)).backendReplicas -}}
{{- else -}}
{{- .Values.backend.replicaCount -}}
{{- end -}}
{{- end -}}

{{/*
Web replica count. Zero when hibernated, the preset count in fleet mode,
otherwise the per-component value.
*/}}
{{- define "artifact-keeper.web.replicaCount" -}}
{{- if eq (include "artifact-keeper.fleet.hibernate" .) "true" -}}
0
{{- else if eq (include "artifact-keeper.fleet.enabled" .) "true" -}}
{{- (fromYaml (include "artifact-keeper.fleet.presetSpec" .)).webReplicas -}}
{{- else -}}
{{- .Values.web.replicaCount -}}
{{- end -}}
{{- end -}}

{{/*
Backend resources. Preset block in fleet mode, otherwise the per-component
value (identical output to the previous direct toYaml of backend.resources).
*/}}
{{- define "artifact-keeper.backend.resources" -}}
{{- if eq (include "artifact-keeper.fleet.enabled" .) "true" -}}
{{- (fromYaml (include "artifact-keeper.fleet.presetSpec" .)).backend | toYaml -}}
{{- else -}}
{{- toYaml .Values.backend.resources -}}
{{- end -}}
{{- end -}}

{{/*
Web resources. Preset block in fleet mode, otherwise the per-component value.
*/}}
{{- define "artifact-keeper.web.resources" -}}
{{- if eq (include "artifact-keeper.fleet.enabled" .) "true" -}}
{{- (fromYaml (include "artifact-keeper.fleet.presetSpec" .)).web | toYaml -}}
{{- else -}}
{{- toYaml .Values.web.resources -}}
{{- end -}}
{{- end -}}

{{/*
Ingress host. Fleet instances derive it from fleet.host; otherwise ingress.host.
*/}}
{{- define "artifact-keeper.ingressHost" -}}
{{- if and .Values.fleet .Values.fleet.host -}}
{{- .Values.fleet.host -}}
{{- else -}}
{{- .Values.ingress.host -}}
{{- end -}}
{{- end -}}

{{/*
Formats an integer millicore count as a Kubernetes CPU quantity. Whole cores
render bare (4000 -> "4"); anything else renders in millicores (9500 -> "9500m").
*/}}
{{- define "artifact-keeper.fleet.fmtCpu" -}}
{{- $m := int . -}}
{{- if eq (mod $m 1000) 0 -}}{{- div $m 1000 -}}{{- else -}}{{- printf "%dm" $m -}}{{- end -}}
{{- end -}}

{{/*
Formats an integer Mi count as a Kubernetes memory quantity. Whole gibibytes
render in Gi (4096 -> "4Gi"); anything else renders in Mi (3840 -> "3840Mi").
*/}}
{{- define "artifact-keeper.fleet.fmtMem" -}}
{{- $mi := int . -}}
{{- if eq (mod $mi 1024) 0 -}}{{- printf "%dGi" (div $mi 1024) -}}{{- else -}}{{- printf "%dMi" $mi -}}{{- end -}}
{{- end -}}

{{/*
Per-namespace guardrail sizing keyed on fleet.preset. Returns YAML with the
ResourceQuota totals and the LimitRange container defaults/bounds for the
selected preset. The quota totals sit above the summed backend+web
requests/limits to leave headroom for init containers and the bootstrap Job.

The base preset is expressed in canonical integer units (CPU in millicores,
memory in Mi, pods and PVCs as counts) and formatted back to Kubernetes
quantities at the end, so a preset with no optional components enabled renders
exactly as the previous hardcoded table did.

Enabled optional components (trivy, scannerAdapter, opensearch, dependencyTrack)
add their own workload footprint to the totals so the quota can actually admit
those pods (and PVCs). Without this, a preset sized only for backend+web leaves
scanner and search pods (and the bootstrap Job) unschedulable behind the quota.

fleet.guardrails.quotaOverrides replaces any individual computed total outright;
only the keys present there take effect, the rest stay component-aware.
*/}}
{{- define "artifact-keeper.fleet.guardrailSpec" -}}
{{- $preset := default "small" .Values.fleet.preset -}}
{{- $table := dict
  "small" (dict
    "requestsCpu" 1000 "requestsMemory" 1024 "limitsCpu" 4000 "limitsMemory" 4096 "pods" 12 "pvcs" 4
    "limitRange" (dict
      "defaultRequest" (dict "cpu" "100m" "memory" "128Mi")
      "default" (dict "cpu" "500m" "memory" "512Mi")
      "max" (dict "cpu" "2" "memory" "2Gi")))
  "medium" (dict
    "requestsCpu" 2000 "requestsMemory" 3072 "limitsCpu" 8000 "limitsMemory" 8192 "pods" 20 "pvcs" 6
    "limitRange" (dict
      "defaultRequest" (dict "cpu" "250m" "memory" "256Mi")
      "default" (dict "cpu" "1" "memory" "1Gi")
      "max" (dict "cpu" "3" "memory" "3Gi")))
  "large" (dict
    "requestsCpu" 4000 "requestsMemory" 6144 "limitsCpu" 16000 "limitsMemory" 16384 "pods" 30 "pvcs" 8
    "limitRange" (dict
      "defaultRequest" (dict "cpu" "500m" "memory" "512Mi")
      "default" (dict "cpu" "2" "memory" "2Gi")
      "max" (dict "cpu" "6" "memory" "6Gi")))
  -}}
{{- $spec := index $table $preset -}}
{{- if not $spec -}}
{{- fail (printf "fleet.preset=%q is not valid; use one of small, medium, large" $preset) -}}
{{- end -}}
{{/* Start from the base preset totals and add each enabled component's
     footprint. requests.cpu must grow too: the base preset covers only the
     core workload, so enabling an optional component otherwise wedges the
     namespace (new pods forbidden by the quota; observed live when search
     was enabled on a medium tenant). limits.cpu increments match each
     component's actual pod limit, plus headroom for ONE backend pod and
     ONE web pod: a RollingUpdate surge otherwise exceeds the quota
     mid-rollout and wedges the deployment (observed live on the same
     tenant once it could finally schedule OpenSearch). */}}
{{- $requestsCpu := $spec.requestsCpu -}}
{{- $limitsCpu := add $spec.limitsCpu 3000 -}}
{{- $limitsMemory := $spec.limitsMemory -}}
{{- $requestsMemory := $spec.requestsMemory -}}
{{- $pods := add $spec.pods 2 -}}
{{- $pvcs := $spec.pvcs -}}
{{- if .Values.trivy.enabled -}}
{{- $requestsCpu = add $requestsCpu 250 -}}
{{- $limitsCpu = add $limitsCpu 1000 -}}
{{- $limitsMemory = add $limitsMemory 2048 -}}
{{- $requestsMemory = add $requestsMemory 512 -}}
{{- $pods = add $pods 2 -}}
{{- end -}}
{{- if .Values.scannerAdapter.enabled -}}
{{- $requestsCpu = add $requestsCpu 100 -}}
{{- $limitsCpu = add $limitsCpu 1000 -}}
{{- $limitsMemory = add $limitsMemory 1024 -}}
{{- $requestsMemory = add $requestsMemory 256 -}}
{{- $pods = add $pods 2 -}}
{{- end -}}
{{- if .Values.opensearch.enabled -}}
{{- $requestsCpu = add $requestsCpu 250 -}}
{{- $limitsCpu = add $limitsCpu 2000 -}}
{{- $limitsMemory = add $limitsMemory 2048 -}}
{{- $requestsMemory = add $requestsMemory 1024 -}}
{{- $pods = add $pods 2 -}}
{{- $pvcs = add $pvcs 1 -}}
{{- end -}}
{{- if .Values.dependencyTrack.enabled -}}
{{- $requestsCpu = add $requestsCpu 500 -}}
{{- $limitsCpu = add $limitsCpu 2000 -}}
{{- $limitsMemory = add $limitsMemory 4096 -}}
{{- $requestsMemory = add $requestsMemory 1024 -}}
{{- $pods = add $pods 3 -}}
{{- $pvcs = add $pvcs 1 -}}
{{- end -}}
{{- $quota := dict
    "requestsCpu" (include "artifact-keeper.fleet.fmtCpu" $requestsCpu)
    "requestsMemory" (include "artifact-keeper.fleet.fmtMem" $requestsMemory)
    "limitsCpu" (include "artifact-keeper.fleet.fmtCpu" $limitsCpu)
    "limitsMemory" (include "artifact-keeper.fleet.fmtMem" $limitsMemory)
    "pods" $pods
    "pvcs" $pvcs -}}
{{- $ov := default dict .Values.fleet.guardrails.quotaOverrides -}}
{{- range $k := list "requestsCpu" "requestsMemory" "limitsCpu" "limitsMemory" "pods" "pvcs" -}}
{{- if hasKey $ov $k -}}
{{- $_ := set $quota $k (index $ov $k) -}}
{{- end -}}
{{- end -}}
{{- (dict "quota" $quota "limitRange" $spec.limitRange) | toYaml -}}
{{- end -}}

{{/*
The native package-format path prefixes that route to the backend, as a
space-separated string. Consumed by artifact-keeper.backendPaths (_routing.tpl,
which feeds the Ingress and the Gateway API HTTPRoute) and by the OpenShift
Routes (route.yaml) via `splitList " " (trim ...)`, so they never drift out of
sync. Does NOT include /api, /v2, /health, or /ready — those carry their own
pathType/handling (see artifact-keeper.backendPaths and route.yaml).

Keep this in step with the `format_routes` nests in the backend's
backend/src/api/routes.rs. /lxc is the incus alias, /general the generic
format, and /t the rattler/pixi conda-token prefix (/t/<token>/conda/...).
tests/test_httproute.py holds an independent copy of this inventory.

backend.extraFormatPaths (#359) appends operator-supplied prefixes, for example
for a backend plugin, after the built-in list so every consumer picks them up.
Each must be a single path segment ("/" plus lowercase letters, digits and
inner hyphens): the OpenShift Route for a path is named after it. Built-in
prefixes, the other backend paths, /metrics (kept private), /dtrack and
duplicates fail the render.
*/}}
{{- define "artifact-keeper.backendFormatPaths" -}}
{{- $builtin := list "/general" "/maven" "/npm" "/pypi" "/nuget" "/cargo" "/gems" "/go" "/helm" "/debian" "/rpm" "/alpine" "/pacman" "/composer" "/conan" "/conda" "/t" "/swift" "/terraform" "/cocoapods" "/hex" "/pub" "/lfs" "/ivy" "/chef" "/puppet" "/ansible" "/cran" "/bazel" "/huggingface" "/jetbrains" "/vscode" "/proto" "/incus" "/lxc" "/ext" -}}
{{- /* dig: `helm upgrade --reuse-values` keeps the previous chart's
       defaults, which lack this key. */ -}}
{{- $extra := dig "extraFormatPaths" list .Values.backend -}}
{{- if kindIs "invalid" $extra -}}{{- $extra = list -}}{{- end -}}
{{- if not (kindIs "slice" $extra) -}}
{{- fail "backend.extraFormatPaths must be a list of path prefixes such as \"/myplugin\"" -}}
{{- end -}}
{{- $reserved := concat $builtin (list "/" "/api" "/v2" "/health" "/ready" "/metrics" "/dtrack") -}}
{{- $paths := $builtin -}}
{{- range $extra -}}
{{- if not (and (kindIs "string" .) (regexMatch "^/[a-z0-9]([-a-z0-9]*[a-z0-9])?$" .)) -}}
{{- fail (printf "backend.extraFormatPaths entry %q must be a single path segment: \"/\" followed by lowercase letters, digits and inner hyphens, with no spaces or further \"/\"" (toString .)) -}}
{{- end -}}
{{- if has . $reserved -}}
{{- fail (printf "backend.extraFormatPaths entry %q is reserved: it is a built-in backend path, /metrics (kept private) or /dtrack; remove it" .) -}}
{{- end -}}
{{- if has . $paths -}}
{{- fail (printf "backend.extraFormatPaths lists %q more than once" .) -}}
{{- end -}}
{{- $paths = append $paths . -}}
{{- end -}}
{{- join " " $paths -}}
{{- end -}}

{{/*
Render one OpenShift Route. An OpenShift Route targets a single Service, so the
single-host/many-paths Ingress is expressed as one Route per path; the HAProxy
router does longest-path-prefix matching, so specific backend paths win over the
"/" web catch-all. Call with a dict:
  root        - the top-level "." (for labels)
  name        - metadata.name
  host        - shared external hostname (required; see route.yaml)
  path        - spec.path prefix
  service     - target Service name
  targetPort  - service port name or number
  annotations - route annotations map
  tls         - .Values.route.tls (enabled/termination/insecureEdgeTerminationPolicy)
*/}}
{{- define "artifact-keeper.routeObject" -}}
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: {{ .name }}
  labels:
    {{- include "artifact-keeper.labels" .root | nindent 4 }}
    app.kubernetes.io/component: route
  {{- with .annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  host: {{ .host | quote }}
  path: {{ .path }}
  to:
    kind: Service
    name: {{ .service }}
    weight: 100
  port:
    targetPort: {{ .targetPort }}
  {{- if .tls.enabled }}
  tls:
    termination: {{ .tls.termination }}
    insecureEdgeTerminationPolicy: {{ .tls.insecureEdgeTerminationPolicy }}
  {{- end }}
  wildcardPolicy: None
{{- end -}}

{{/*
NetworkPolicy `from` peers for the ingress controller (backend, web and edge
policies). networkPolicy.ingressPeers, when non-empty, is rendered verbatim so
non-nginx controllers (the OpenShift router, Traefik, a Gateway) can be
admitted. Empty keeps the historical ingress-nginx peer, namespace-pinned via
networkPolicy.ingressNamespace.
*/}}
{{- define "artifact-keeper.networkPolicy.ingressPeers" -}}
{{- if .Values.networkPolicy.ingressPeers -}}
{{- toYaml .Values.networkPolicy.ingressPeers -}}
{{- else -}}
{{- if .Values.networkPolicy.ingressNamespace }}
- namespaceSelector:
    matchLabels:
      kubernetes.io/metadata.name: {{ .Values.networkPolicy.ingressNamespace | quote }}
{{- else }}
# Explicit empty selector = ALL namespaces. It must be `{}` and not an
# omitted/null value: a nil namespaceSelector means "this namespace
# only", which would deny the ingress controller and take the instance
# offline.
- namespaceSelector: {}
{{- end }}
  podSelector:
    matchLabels:
      app.kubernetes.io/name: ingress-nginx
{{- end -}}
{{- end -}}

{{/*
NetworkPolicy `from` peers admitted to the Prometheus scrape ports of the
backend, web and edge policies. networkPolicy.monitoringPeers, when non-empty,
is rendered verbatim (for example a podSelector for the Prometheus pods).
Empty keeps the namespace peer: every pod in networkPolicy.monitoringNamespace,
matched on the kubernetes.io/metadata.name label Kubernetes stamps on every
namespace (a bare `name` label matches nothing).
*/}}
{{- define "artifact-keeper.networkPolicy.monitoringPeers" -}}
{{- /* dig: `helm upgrade --reuse-values` keeps the previous chart's defaults, which lack these keys. */ -}}
{{- $namespace := dig "monitoringNamespace" "monitoring" .Values.networkPolicy -}}
{{- if .Values.networkPolicy.monitoringPeers -}}
{{- toYaml .Values.networkPolicy.monitoringPeers -}}
{{- else -}}
{{- if not $namespace -}}
{{- fail "networkPolicy.monitoringNamespace must name the namespace Prometheus runs in (default monitoring), or set networkPolicy.monitoringPeers" -}}
{{- end }}
- namespaceSelector:
    matchLabels:
      kubernetes.io/metadata.name: {{ $namespace | quote }}
{{- end -}}
{{- end -}}

{{/*
DNS egress ports (UDP and TCP for each entry of networkPolicy.dnsPorts). An
empty list would leave the DNS egress rule with no ports, which allows ALL
egress, so it is rejected. OpenShift needs 5353: dns-default maps service port 53 to pod port
5353, and NetworkPolicy matches the post-DNAT pod port.
*/}}
{{- define "artifact-keeper.networkPolicy.dnsPorts" -}}
{{- $ports := .Values.networkPolicy.dnsPorts -}}
{{- if not $ports -}}
{{- fail "networkPolicy.dnsPorts must list at least one port (default [53])" -}}
{{- end -}}
{{- range $p := $ports }}
- port: {{ $p }}
  protocol: UDP
- port: {{ $p }}
  protocol: TCP
{{- end -}}
{{- end -}}

{{/*
=============================================================================
Egress proxy helpers
=============================================================================
*/}}

{{/*
Returns "true" when the bare "backend" ExternalName alias
(backend-alias-service.yaml) renders: backend and web enabled and
web.backendAlias.enabled not false. `dig` keeps the alias for
`helm upgrade --reuse-values` from a chart that predates the knob.
*/}}
{{- define "artifact-keeper.backendAlias.enabled" -}}
{{- $enabled := dig "backendAlias" "enabled" true .Values.web -}}
{{- if not (kindIs "bool" $enabled) -}}
{{- fail "web.backendAlias.enabled must be a boolean" -}}
{{- end -}}
{{- if and .Values.backend.enabled .Values.web.enabled $enabled -}}true{{- end -}}
{{- end -}}

{{/*
NO_PROXY defaults: loopback, in-cluster DNS suffixes, and the short Service name
of every enabled component. The bare names matter — a ".svc"/".cluster.local"
suffix match misses "artifact-keeper-backend", which is how components call each
other, so those hops would otherwise take the proxy. The bare "backend" entry is
the ExternalName alias from backend-alias-service.yaml (web images before 1.1.0
bake http://backend:8080 into their rewrites), rendered under the same condition.
Fleet mode: the shared search/scan/DB Services live outside the release; add
them via noProxy, as you must any in-cluster S3 endpoint (e.g. MinIO).
*/}}
{{- define "artifact-keeper.noProxyDefaults" -}}
{{- $full := include "artifact-keeper.fullname" . -}}
{{- $n := list "localhost" "127.0.0.1" ".svc" ".svc.cluster.local" ".cluster.local" -}}
{{- $n = append $n (printf "%s-backend" $full) -}}
{{- if eq (include "artifact-keeper.backendAlias.enabled" .) "true" -}}{{- $n = append $n "backend" -}}{{- end -}}
{{- $n = append $n (printf "%s-web" $full) -}}
{{- if .Values.edge.enabled -}}{{- $n = append $n (printf "%s-edge" $full) -}}{{- end -}}
{{- if .Values.opensearch.enabled -}}{{- $n = append $n (printf "%s-opensearch" $full) -}}{{- end -}}
{{- if .Values.trivy.enabled -}}{{- $n = append $n (printf "%s-trivy" $full) -}}{{- end -}}
{{- if .Values.scannerAdapter.enabled -}}{{- $n = append $n (printf "%s-scanner-adapter" $full) -}}{{- end -}}
{{- if .Values.dependencyTrack.enabled -}}{{- $n = append $n (printf "%s-dtrack" $full) -}}{{- end -}}
{{- if .Values.imageBuilder.enabled -}}{{- $n = append $n (printf "%s-buildkitd" $full) -}}{{- end -}}
{{- if .Values.postgres.enabled -}}{{- $n = append $n (printf "%s-postgres" $full) -}}{{- else if .Values.externalDatabase.host -}}{{- $n = append $n .Values.externalDatabase.host -}}{{- end -}}
{{- join "," $n -}}
{{- end -}}

{{/*
Effective proxy settings for one component, resolved field by field: a value
under <component>.proxy wins over the same field of global.proxy. Returns YAML:
  enabled        false when the component opted out (proxy.enabled: false) or
                 nothing resolves (no literal URL and no existingSecret)
  httpProxy      literal HTTP_PROXY URL, "" when unset
  httpsProxy     literal HTTPS_PROXY URL, "" when unset
  existingSecret Secret whose HTTP_PROXY / HTTPS_PROXY keys supply whichever
                 of the two has no literal URL, "" when unset
  noProxy        noProxyDefaults + global.proxy.noProxy + <component>.proxy.noProxy
                 (the component list extends the global one, it does not replace it)
Call: include "artifact-keeper.proxyConfig" (dict "proxy" .Values.<component>.proxy "ctx" $) | fromYaml
*/}}
{{- define "artifact-keeper.proxyConfig" -}}
{{- $svc := .proxy | default dict -}}
{{- $global := dict -}}
{{- if .ctx.Values.global -}}{{- $global = .ctx.Values.global.proxy | default dict -}}{{- end -}}
{{- $httpProxy := or $svc.httpProxy $global.httpProxy "" -}}
{{- $httpsProxy := or $svc.httpsProxy $global.httpsProxy "" -}}
{{- $secret := or $svc.existingSecret $global.existingSecret "" -}}
{{- $enabled := and (ne (toString $svc.enabled) "false") (or $httpProxy $httpsProxy $secret) -}}
{{- $noProxy := list (include "artifact-keeper.noProxyDefaults" .ctx) -}}
{{- with $global.noProxy -}}{{- $noProxy = append $noProxy . -}}{{- end -}}
{{- with $svc.noProxy -}}{{- $noProxy = append $noProxy . -}}{{- end -}}
{{- dict "enabled" (not (empty $enabled)) "httpProxy" $httpProxy "httpsProxy" $httpsProxy "existingSecret" $secret "noProxy" (join "," $noProxy) | toYaml -}}
{{- end -}}

{{/*
The env var names artifact-keeper.proxyEnv emits for a component, space
separated ("" when it emits nothing). Templates that also render a free-form
<component>.env map skip these keys so the variable is not defined twice.
Call: splitList " " (include "artifact-keeper.proxyEnvNames" (dict "proxy" .Values.<component>.proxy "ctx" $))
*/}}
{{- define "artifact-keeper.proxyEnvNames" -}}
{{- $p := include "artifact-keeper.proxyConfig" . | fromYaml -}}
{{- if $p.enabled -}}
{{- $names := list -}}
{{- if or $p.httpProxy $p.existingSecret -}}{{- $names = concat $names (list "HTTP_PROXY" "http_proxy") -}}{{- end -}}
{{- if or $p.httpsProxy $p.existingSecret -}}{{- $names = concat $names (list "HTTPS_PROXY" "https_proxy") -}}{{- end -}}
{{- $names = concat $names (list "NO_PROXY" "no_proxy") -}}
{{- join " " $names -}}
{{- end -}}
{{- end -}}

{{/*
Proxy env for a container, from artifact-keeper.proxyConfig. Emits nothing
unless the component resolves to a proxy; proxy.enabled: false opts a component
out even when global.proxy is set (with proxy-only egress that leaves it no
route out of the cluster; in-cluster + DNS still work via NO_PROXY). Emits
upper- and lower-case forms. A literal URL renders as `value`; a field that
only existingSecret supplies renders as a secretKeyRef to that key.
Call: include "artifact-keeper.proxyEnv" (dict "proxy" .Values.<component>.proxy "ctx" $)
*/}}
{{- define "artifact-keeper.proxyEnv" -}}
{{- $p := include "artifact-keeper.proxyConfig" . | fromYaml -}}
{{- if $p.enabled -}}
{{- range $pair := list (list "HTTP_PROXY" $p.httpProxy) (list "HTTPS_PROXY" $p.httpsProxy) -}}
{{- $key := index $pair 0 -}}
{{- $literal := index $pair 1 -}}
{{- if or $literal $p.existingSecret -}}
{{- range $name := list $key (lower $key) }}
- name: {{ $name }}
{{- if $literal }}
  value: {{ $literal | quote }}
{{- else }}
  valueFrom:
    secretKeyRef:
      name: {{ $p.existingSecret }}
      key: {{ $key }}
{{- end }}
{{- end }}
{{- end -}}
{{- end }}
- name: NO_PROXY
  value: {{ $p.noProxy | quote }}
- name: no_proxy
  value: {{ $p.noProxy | quote }}
{{- end -}}
{{- end -}}

{{/*
Backend container environment, shared by the backend and scan-worker
Deployments so the two cannot drift: same image, same database, storage,
scanner and upstream config. Each appends its own SCAN_QUEUE_ENABLED and
SCAN_WORKER_ENABLED.

Called with the root context, so the `.Values` references below are unchanged
from when this lived inline.
*/}}
{{- define "artifact-keeper.backend.env" }}
            {{- with (include "artifact-keeper.proxyEnv" (dict "proxy" .Values.backend.proxy "ctx" $)) }}
            {{- . | trim | nindent 12 }}
            {{- end }}
            {{- if eq (include "artifact-keeper.dtrackApiKeyFile" .) "true" }}
            # The backend reads the Dependency-Track API key from this file
            # (see resolve_api_key in dependency_track_service.rs). This replaces
            # the previous `sh -c "export ...; exec"` command wrapper, which the
            # shell-less distroless (ubi-micro) backend image cannot run
            # (CreateContainerError: exec /bin/sh: no such file — iac#199).
            - name: DEPENDENCY_TRACK_API_KEY_FILE
              value: /shared/dtrack-api-key
            {{- else if .Values.dependencyTrack.enabled }}
            # resolve_api_key gives the direct value precedence over the file, so
            # supplying it from a Secret is what lets the shared-config volume
            # stay unmounted and the backend replicas spread across nodes.
            - name: DEPENDENCY_TRACK_API_KEY
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.dependencyTrack.existingApiKeySecret }}
                  key: {{ .Values.dependencyTrack.existingApiKeySecretKey }}
            {{- end }}
            {{- /* A name defined in backend.environmentSecrets wins over the
                   same key in backend.env, so moving a credential there does
                   not need the backend.env entry removed (#375). */}}
            {{- $secretEnv := list }}
            {{- range .Values.backend.environmentSecrets }}
            {{- $secretEnv = append $secretEnv .name }}
            {{- end }}
            {{- /* Likewise the proxy helper above owns HTTP_PROXY/HTTPS_PROXY/
                   NO_PROXY (and lowercase) whenever it emits them, so a copy
                   left in backend.env does not define the variable twice. */}}
            {{- $proxyEnv := splitList " " (include "artifact-keeper.proxyEnvNames" (dict "proxy" .Values.backend.proxy "ctx" $)) }}
            {{- /* The scan flags, and on the worker every scanWorker.env key,
                   are set by the Deployment after this helper, so a copy in
                   backend.env would define the variable twice. */}}
            {{- $deploymentEnv := list }}
            {{- if .Values.scanWorker.enabled }}
            {{- $deploymentEnv = list "SCAN_QUEUE_ENABLED" "SCAN_WORKER_ENABLED" }}
            {{- if hasSuffix "scan-worker-deployment.yaml" .Template.Name }}
            {{- $deploymentEnv = concat $deploymentEnv (list "SCAN_WORKER_CONCURRENCY") (keys .Values.scanWorker.env) }}
            {{- end }}
            {{- end }}
            {{- range $key, $value := .Values.backend.env }}
            {{- if not (or (has $key $secretEnv) (has $key $proxyEnv) (has $key $deploymentEnv)) }}
            - name: {{ $key }}
              value: {{ $value | quote }}
            {{- end }}
            {{- end }}
            - name: DATABASE_URL
              {{- if and (not .Values.postgres.enabled) .Values.externalDatabase.existingSecret }}
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalDatabase.existingSecret }}
                  key: {{ .Values.externalDatabase.existingSecretKey }}
              {{- else }}
              valueFrom:
                secretKeyRef:
                  name: {{ include "artifact-keeper.secretName" . }}
                  key: DATABASE_URL
              {{- end }}
            - name: JWT_SECRET
              valueFrom:
                secretKeyRef:
                  name: {{ include "artifact-keeper.secretName" . }}
                  key: JWT_SECRET
            {{- with include "artifact-keeper.encryptionKeyEnv" . }}{{ . | trim | nindent 12 }}{{- end }}
            {{- if .Values.opensearch.enabled }}
            - name: OPENSEARCH_URL
              value: "{{ if .Values.opensearch.disableSecurityPlugin }}http{{ else }}https{{ end }}://{{ include "artifact-keeper.fullname" . }}-opensearch:9200"
            {{- if not .Values.opensearch.disableSecurityPlugin }}
            - name: OPENSEARCH_USERNAME
              valueFrom:
                secretKeyRef:
                  name: {{ include "artifact-keeper.secretName" . }}
                  key: OPENSEARCH_USERNAME
            - name: OPENSEARCH_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ include "artifact-keeper.secretName" . }}
                  key: OPENSEARCH_PASSWORD
            - name: OPENSEARCH_ALLOW_INVALID_CERTS
              value: {{ .Values.opensearch.allowInvalidCerts | quote }}
            {{- end }}
            {{- end }}
            {{- if .Values.trivy.enabled }}
            - name: TRIVY_URL
              value: "http://{{ include "artifact-keeper.fullname" . }}-trivy:8090"
            - name: SCAN_WORKSPACE_PATH
              value: "/scan-workspace"
            {{- end }}
            {{- if .Values.scannerAdapter.enabled }}
            # In-house Harbor scanner-adapter for container-image Trivy scans
            # (artifact-keeper#2091). Host must match the scanner-adapter Service
            # name. Leaves TRIVY_URL (fs/incus path) above untouched.
            - name: TRIVY_ADAPTER_URL
              value: "http://{{ include "artifact-keeper.fullname" . }}-scanner-adapter:8090"
            {{- end }}
            {{- if .Values.imageBuilder.enabled }}
            {{- /*
            Image builder: where the buildkitd daemon listens and how IT
            reaches this registry to push (in-cluster, plain HTTP). Values
            given in backend.env win over these, so an operator can point the
            backend at a daemon this chart did not deploy.
            */}}
            {{- $ib := .Values.imageBuilder }}
            {{- $env := .Values.backend.env }}
            {{- if not (hasKey $env "AK_BUILDKIT_ADDR") }}
            - name: AK_BUILDKIT_ADDR
              value: "tcp://{{ include "artifact-keeper.fullname" . }}-buildkitd:{{ $ib.service.port }}"
            {{- end }}
            {{- if not (hasKey $env "AK_IMAGE_BUILD_PUSH_REGISTRY") }}
            - name: AK_IMAGE_BUILD_PUSH_REGISTRY
              value: "{{ include "artifact-keeper.fullname" . }}-backend:{{ .Values.backend.service.httpPort }}"
            - name: AK_IMAGE_BUILD_REGISTRY_INSECURE
              value: "true"
            {{- end }}
            {{- if and $ib.policy.baseAllowlist (not (hasKey $env "AK_IMAGE_BUILD_BASE_ALLOWLIST")) }}
            - name: AK_IMAGE_BUILD_BASE_ALLOWLIST
              value: {{ $ib.policy.baseAllowlist | quote }}
            {{- end }}
            {{- if not (hasKey $env "AK_IMAGE_BUILD_ADMIN_ONLY") }}
            - name: AK_IMAGE_BUILD_ADMIN_ONLY
              value: {{ $ib.policy.adminOnly | quote }}
            {{- end }}
            {{- if not (hasKey $env "AK_IMAGE_BUILD_ALLOW_RUN") }}
            - name: AK_IMAGE_BUILD_ALLOW_RUN
              value: {{ $ib.policy.allowRun | quote }}
            {{- end }}
            {{- if not (hasKey $env "AK_IMAGE_BUILD_ALLOW_DOCKERFILE") }}
            - name: AK_IMAGE_BUILD_ALLOW_DOCKERFILE
              value: {{ $ib.policy.allowDockerfile | quote }}
            {{- end }}
            {{- if and $ib.policy.pipIndexUrl (not (hasKey $env "AK_IMAGE_BUILD_PIP_INDEX_URL")) }}
            - name: AK_IMAGE_BUILD_PIP_INDEX_URL
              value: {{ $ib.policy.pipIndexUrl | quote }}
            {{- end }}
            {{- if not (hasKey $env "AK_IMAGE_BUILD_TIMEOUT_SECS") }}
            - name: AK_IMAGE_BUILD_TIMEOUT_SECS
              value: {{ $ib.policy.timeoutSecs | quote }}
            {{- end }}
            {{- if not (hasKey $env "AK_IMAGE_BUILD_MAX_CONCURRENT") }}
            - name: AK_IMAGE_BUILD_MAX_CONCURRENT
              value: {{ $ib.policy.maxConcurrent | quote }}
            {{- end }}
            {{- end }}
            {{- if .Values.dependencyTrack.enabled }}
            - name: DEPENDENCY_TRACK_URL
              value: "http://{{ include "artifact-keeper.fullname" . }}-dtrack:8080"
            - name: DEPENDENCY_TRACK_ENABLED
              value: "true"
            {{- end }}
            {{- /*
            ALLOW_HTTP_INTEGRATIONS relaxes outbound TLS verification for all
            backend integrations. Injected only per backend.allowHttpIntegrations
            (auto/true/false); an explicit entry in backend.env overrides this.
            See values.yaml for the security trade-off.
            */}}
            {{- if eq (include "artifact-keeper.allowHttpIntegrations" .) "true" }}
            - name: ALLOW_HTTP_INTEGRATIONS
              value: "1"
            {{- end }}
            {{- if eq (include "artifact-keeper.smtpPasswordManaged" .) "true" }}
            - name: SMTP_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ include "artifact-keeper.secretName" . }}
                  key: SMTP_PASSWORD
            {{- end }}
            {{- if .Values.backend.metricsListener.enabled }}
            {{- /*
            METRICS_PORT is rendered once. A backend.env entry with the same
            key used to render a second copy, which Kubernetes accepts on
            create but a later strategic-merge patch then drops both (#381).
            An explicit backend.env entry wins, as with METRICS_BIND_IP below,
            but it must agree with metricsListener.port: the metrics Service,
            NetworkPolicy and ServiceMonitor all use that value.
            */}}
            {{- if hasKey .Values.backend.env "METRICS_PORT" }}
            {{- if ne (toString (index .Values.backend.env "METRICS_PORT")) (toString .Values.backend.metricsListener.port) }}
            {{- fail (printf "backend.env.METRICS_PORT (%v) conflicts with backend.metricsListener.port (%v): remove the backend.env entry or set both to the same port" (index .Values.backend.env "METRICS_PORT") .Values.backend.metricsListener.port) }}
            {{- end }}
            {{- else }}
            - name: METRICS_PORT
              value: {{ .Values.backend.metricsListener.port | quote }}
            {{- end }}
            {{- /*
            METRICS_BIND_IP (backend 1.11.0+). An explicit entry in backend.env
            wins, as with the image-builder variables above.
            */}}
            {{- if and .Values.backend.metricsListener.bindIP (not (hasKey .Values.backend.env "METRICS_BIND_IP")) }}
            - name: METRICS_BIND_IP
              value: {{ .Values.backend.metricsListener.bindIP | quote }}
            {{- end }}
            {{- end }}
            {{- /*
            Client-IP resolution behind a proxy (backend.clientIp). Explicit
            backend.env entries win, as with METRICS_BIND_IP above.
            */}}
            {{- $clientIp := .Values.backend.clientIp | default dict }}
            {{- if and $clientIp.trustedProxyCidrs (not (hasKey .Values.backend.env "RATE_LIMIT_TRUSTED_PROXY_CIDRS")) }}
            - name: RATE_LIMIT_TRUSTED_PROXY_CIDRS
              value: {{ $clientIp.trustedProxyCidrs | quote }}
            {{- end }}
            {{- if not (hasKey .Values.backend.env "XFF_TRUSTED_FOR_AUTHZ") }}
            {{- if not (kindIs "bool" (dig "xffTrustedForAuthz" false $clientIp)) }}
            {{- fail "backend.clientIp.xffTrustedForAuthz must be a boolean" }}
            {{- end }}
            - name: XFF_TRUSTED_FOR_AUTHZ
              value: {{ dig "xffTrustedForAuthz" false $clientIp | quote }}
            {{- end }}
            {{- with include "artifact-keeper.backendTuningEnv" . }}{{ . | trim | nindent 12 }}{{- end }}
            {{- if eq (include "artifact-keeper.fleet.enabled" .) "true" }}
            # Object storage for this instance. Artifacts share one bucket with
            # a per-instance key prefix; the non-secret settings (STORAGE_BACKEND,
            # S3_BUCKET, S3_ENDPOINT, S3_REGION and any redirect flags) come from
            # backend.env, and the prefix and access keys are injected here.
            - name: S3_PREFIX
              value: {{ .Values.fleet.instanceId | quote }}
            {{- if .Values.fleet.storage.existingSecret }}
            - name: S3_ACCESS_KEY_ID
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.fleet.storage.existingSecret }}
                  key: {{ .Values.fleet.storage.accessKeyIdKey }}
            - name: S3_SECRET_ACCESS_KEY
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.fleet.storage.existingSecret }}
                  key: {{ .Values.fleet.storage.secretAccessKeyKey }}
            {{- end }}
            {{- end }}
            {{- /*
            S3 credentials for a standard (non-fleet) install. The backend reads
            S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY; these come from the
            chart-managed Secret (secrets.s3AccessKey / secrets.s3SecretKey) or
            the ExternalSecret. Skipped when the fleet object-storage Secret
            supplies them (that path takes precedence, injected above) and when
            secrets.existingSecret is in use, since a user-managed Secret may
            store the keys under different names.
            */}}
            {{- $fleetManagedS3 := false }}
            {{- if eq (include "artifact-keeper.fleet.enabled" .) "true" }}
            {{- $fleetManagedS3 = .Values.fleet.storage.existingSecret }}
            {{- end }}
            {{- if and (not $fleetManagedS3) (eq (lower (.Values.backend.env.STORAGE_BACKEND | default "")) "s3") }}
            {{- if or .Values.externalSecrets.enabled (and (not .Values.secrets.existingSecret) .Values.secrets.s3AccessKey) }}
            - name: S3_ACCESS_KEY_ID
              valueFrom:
                secretKeyRef:
                  name: {{ include "artifact-keeper.secretName" . }}
                  key: S3_ACCESS_KEY_ID
            - name: S3_SECRET_ACCESS_KEY
              valueFrom:
                secretKeyRef:
                  name: {{ include "artifact-keeper.secretName" . }}
                  key: S3_SECRET_ACCESS_KEY
            {{- end }}
            {{- end }}
            {{- range .Values.backend.environmentSecrets }}
            - name: {{ .name }}
              valueFrom:
                secretKeyRef:
                  name: {{ .secretKeyRef.name }}
                  key: {{ .secretKeyRef.key }}
                  {{- if hasKey .secretKeyRef "optional" }}
                  optional: {{ .secretKeyRef.optional }}
                  {{- end }}
            {{- end }}
{{- end }}
