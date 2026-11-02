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
{{- $timeouts := include "artifact-keeper.httpRoute.timeouts" . | fromYaml -}}
{{- if and $timeouts.request $timeouts.backendRequest -}}
{{- $request := include "artifact-keeper.gatewayDurationMs" $timeouts.request | int64 -}}
{{- $backendRequest := include "artifact-keeper.gatewayDurationMs" $timeouts.backendRequest | int64 -}}
{{- if and (gt $request 0) (gt $backendRequest $request) -}}
{{- fail (printf "httpRoute.timeouts.backendRequest (%s) cannot be longer than httpRoute.timeouts.request (%s) unless request is 0s" $timeouts.backendRequest $timeouts.request) -}}
{{- end -}}
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

{{/*
The non-empty httpRoute.timeouts fields as a YAML map ("{}" when none are
set), validated against the Gateway API Duration format (GEP-2257) that the
HTTPRoute CRD enforces: one to four <number><unit> groups, number up to five
digits, unit h, m, s or ms; "0s" disables the timeout. dig: `helm upgrade
--reuse-values` keeps the previous chart's defaults, which lack the key.
*/}}
{{- define "artifact-keeper.httpRoute.timeouts" -}}
{{- $values := dig "timeouts" dict .Values.httpRoute | default dict -}}
{{- $out := dict -}}
{{- range $field := list "request" "backendRequest" -}}
{{- $value := get $values $field -}}
{{- if not (kindIs "invalid" $value) -}}
{{- if not (kindIs "string" $value) -}}
{{- fail (printf "httpRoute.timeouts.%s must be a Gateway API duration string such as \"300s\" or \"0s\"; got %v" $field $value) -}}
{{- end -}}
{{- if $value -}}
{{- if not (regexMatch "^([0-9]{1,5}(h|m|s|ms)){1,4}$" $value) -}}
{{- fail (printf "httpRoute.timeouts.%s must be a Gateway API duration such as \"300s\", \"1h30m\" or \"0s\" (1-4 <number><h|m|s|ms> groups); got %q" $field $value) -}}
{{- end -}}
{{- $_ := set $out $field $value -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- toYaml $out -}}
{{- end -}}

{{/*
A validated Gateway API duration string in milliseconds.
*/}}
{{- define "artifact-keeper.gatewayDurationMs" -}}
{{- $total := 0 -}}
{{- $scale := dict "h" 3600000 "m" 60000 "s" 1000 "ms" 1 -}}
{{- range regexFindAll "[0-9]+(ms|h|m|s)" . -1 -}}
{{- $unit := regexFind "(ms|h|m|s)$" . -}}
{{- $total = add $total (mul (trimSuffix $unit . | int64) (get $scale $unit)) -}}
{{- end -}}
{{- $total -}}
{{- end }}
