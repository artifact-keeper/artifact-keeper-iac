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
DependencyTrack selector labels
*/}}
{{- define "artifact-keeper.dtrack.selectorLabels" -}}
{{ include "artifact-keeper.selectorLabels" . }}
app.kubernetes.io/component: dependency-track
{{- end }}

{{/*
Database URL helper — returns the full DATABASE_URL string
*/}}
{{- define "artifact-keeper.databaseUrl" -}}
{{- if .Values.postgres.enabled -}}
postgresql://{{ .Values.postgres.auth.username }}:{{ .Values.postgres.auth.password }}@{{ include "artifact-keeper.fullname" . }}-postgres:5432/{{ .Values.postgres.auth.database }}
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
engines that deploy by re-running "helm template" (ArgoCD, Flux): there, step 2
never fires and every sync would generate a fresh password, silently desyncing
the Secret from the password Dependency-Track actually holds. The ArgoCD
ApplicationSet in this repo handles that with ignoreDifferences on this Secret
key plus the RespectIgnoreDifferences sync option, so the live value is kept
after first creation. If you consume this chart through another template-mode
engine, either replicate that ignore rule or set dependencyTrack.adminPassword
explicitly.

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

{{- define "artifact-keeper.validateSecrets" -}}
{{- if or .Values.externalSecrets.enabled .Values.secrets.existingSecret -}}
{{- /* Secrets are supplied externally; no chart-owned Secret to validate. */ -}}
{{- else -}}
{{- if eq .Values.secrets.jwtSecret "" -}}
{{- fail "secrets.jwtSecret is required when externalSecrets is not enabled. Set it with --set secrets.jwtSecret=<value>" -}}
{{- end -}}
{{- if and .Values.postgres.enabled (eq .Values.postgres.auth.password "") -}}
{{- fail "postgres.auth.password is required when postgres is enabled. Set it with --set postgres.auth.password=<value>" -}}
{{- end -}}
{{- if and .Values.opensearch.enabled (not .Values.opensearch.disableSecurityPlugin) (eq .Values.opensearch.auth.password "") -}}
{{- fail "opensearch.auth.password is required when opensearch is enabled and disableSecurityPlugin is false. Set it with --set opensearch.auth.password=<value>" -}}
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
*/}}
{{- define "artifact-keeper.fleet.presetSpec" -}}
{{- $preset := default "small" .Values.fleet.preset -}}
{{- $table := dict
  "small" (dict
    "backendReplicas" 1
    "webReplicas" 1
    "backend" (dict
      "requests" (dict "cpu" "250m" "memory" "512Mi" "ephemeral-storage" "256Mi")
      "limits" (dict "cpu" "1" "memory" "1Gi" "ephemeral-storage" "1Gi"))
    "web" (dict
      "requests" (dict "cpu" "100m" "memory" "128Mi" "ephemeral-storage" "128Mi")
      "limits" (dict "cpu" "500m" "memory" "512Mi" "ephemeral-storage" "1Gi")))
  "medium" (dict
    "backendReplicas" 2
    "webReplicas" 2
    "backend" (dict
      "requests" (dict "cpu" "500m" "memory" "1Gi" "ephemeral-storage" "512Mi")
      "limits" (dict "cpu" "2" "memory" "2Gi" "ephemeral-storage" "2Gi"))
    "web" (dict
      "requests" (dict "cpu" "250m" "memory" "256Mi" "ephemeral-storage" "256Mi")
      "limits" (dict "cpu" "1" "memory" "1Gi" "ephemeral-storage" "2Gi")))
  "large" (dict
    "backendReplicas" 3
    "webReplicas" 2
    "backend" (dict
      "requests" (dict "cpu" "1" "memory" "2Gi" "ephemeral-storage" "1Gi")
      "limits" (dict "cpu" "4" "memory" "4Gi" "ephemeral-storage" "4Gi"))
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
