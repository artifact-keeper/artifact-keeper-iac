{{/*
Public backend paths shared by Ingress and HTTPRoute. Keep /metrics private.
Use Ingress path types here; HTTPRoute translates Prefix to PathPrefix.
The package-format prefixes come from artifact-keeper.backendFormatPaths
(_helpers.tpl), which the OpenShift Routes (route.yaml) also consume.
*/}}
{{- define "artifact-keeper.backendPaths" -}}
- path: /api
  pathType: Prefix
- path: /health
  pathType: Exact
- path: /ready
  pathType: Exact
- path: /v2
  pathType: Prefix
{{- range splitList " " (trim (include "artifact-keeper.backendFormatPaths" .)) }}
- path: {{ . }}
  pathType: Prefix
{{- end }}
{{- end }}

{{- define "artifact-keeper.httpRoute.policyEnabled" -}}
{{- or .Values.networkPolicy.enabled (and .Values.fleet.enabled .Values.fleet.guardrails.networkPolicy) -}}
{{- end }}

{{- define "artifact-keeper.httpRoute.validate" -}}
{{- if .Values.ingress.enabled -}}
{{- fail "httpRoute.enabled and ingress.enabled are mutually exclusive; set ingress.enabled=false" -}}
{{- end -}}
{{- if .Values.route.enabled -}}
{{- fail "httpRoute.enabled and route.enabled (OpenShift Routes) are mutually exclusive; set route.enabled=false" -}}
{{- end -}}
{{- if not .Values.backend.enabled -}}
{{- fail "httpRoute.enabled requires backend.enabled=true" -}}
{{- end -}}
{{- if not .Values.httpRoute.parentRefs -}}
{{- fail "httpRoute.enabled requires at least one httpRoute.parentRefs entry" -}}
{{- end -}}
{{- if not .Values.httpRoute.hostnames -}}
{{- fail "httpRoute.enabled requires at least one httpRoute.hostnames entry" -}}
{{- end -}}
{{- if and .Values.httpRoute.dtrack.enabled (not .Values.dependencyTrack.enabled) -}}
{{- fail "httpRoute.dtrack.enabled requires dependencyTrack.enabled=true" -}}
{{- end -}}
{{- if eq (include "artifact-keeper.httpRoute.policyEnabled" .) "true" -}}
{{- if or (not .Values.httpRoute.networkPolicy.namespace) (not .Values.httpRoute.networkPolicy.podSelector) -}}
{{- fail "HTTPRoute with chart NetworkPolicies requires httpRoute.networkPolicy.namespace and non-empty httpRoute.networkPolicy.podSelector (Gateway proxy pods)" -}}
{{- end -}}
{{- end -}}
{{- /* Gateway API requires consistent optional fields and distinct listener refs per parent. */ -}}
{{- $parents := dict -}}
{{- range .Values.httpRoute.parentRefs -}}
{{- $key := printf "%s/%s" (default $.Release.Namespace .namespace) .name -}}
{{- $fields := printf "%t/%t" (hasKey . "sectionName") (hasKey . "port") -}}
{{- $listener := printf "%s/%v" (default "" .sectionName) (default 0 .port) -}}
{{- if hasKey $parents $key -}}
{{- $parent := get $parents $key -}}
{{- if or (ne $fields $parent.fields) (has $listener $parent.listeners) -}}
{{- fail "httpRoute.parentRefs for the same Gateway must use consistent sectionName/port fields and distinct listener references" -}}
{{- end -}}
{{- $_ := set $parent "listeners" (append $parent.listeners $listener) -}}
{{- else -}}
{{- $_ := set $parents $key (dict "fields" $fields "listeners" (list $listener)) -}}
{{- end -}}
{{- end -}}
{{- end }}
