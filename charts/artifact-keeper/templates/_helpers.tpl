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
Per-namespace guardrail sizing keyed on fleet.preset. Returns YAML with the
ResourceQuota totals and the LimitRange container defaults/bounds for the
selected preset. The quota totals sit above the summed backend+web
requests/limits to leave headroom for init containers and the bootstrap Job.
*/}}
{{- define "artifact-keeper.fleet.guardrailSpec" -}}
{{- $preset := default "small" .Values.fleet.preset -}}
{{- $table := dict
  "small" (dict
    "quota" (dict "requestsCpu" "1" "requestsMemory" "1Gi" "limitsCpu" "4" "limitsMemory" "4Gi" "pods" "12" "pvcs" "4")
    "limitRange" (dict
      "defaultRequest" (dict "cpu" "100m" "memory" "128Mi")
      "default" (dict "cpu" "500m" "memory" "512Mi")
      "max" (dict "cpu" "2" "memory" "2Gi")))
  "medium" (dict
    "quota" (dict "requestsCpu" "2" "requestsMemory" "3Gi" "limitsCpu" "8" "limitsMemory" "8Gi" "pods" "20" "pvcs" "6")
    "limitRange" (dict
      "defaultRequest" (dict "cpu" "250m" "memory" "256Mi")
      "default" (dict "cpu" "1" "memory" "1Gi")
      "max" (dict "cpu" "3" "memory" "3Gi")))
  "large" (dict
    "quota" (dict "requestsCpu" "4" "requestsMemory" "6Gi" "limitsCpu" "16" "limitsMemory" "16Gi" "pods" "30" "pvcs" "8")
    "limitRange" (dict
      "defaultRequest" (dict "cpu" "500m" "memory" "512Mi")
      "default" (dict "cpu" "2" "memory" "2Gi")
      "max" (dict "cpu" "6" "memory" "6Gi")))
  -}}
{{- $spec := index $table $preset -}}
{{- if not $spec -}}
{{- fail (printf "fleet.preset=%q is not valid; use one of small, medium, large" $preset) -}}
{{- end -}}
{{- $spec | toYaml -}}
{{- end -}}
