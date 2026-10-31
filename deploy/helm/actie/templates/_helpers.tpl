{{/* Names and labels shared by every object. */}}
{{- define "actie.fullname" -}}actie{{- end }}

{{- define "actie.labels" -}}
app.kubernetes.io/part-of: actie
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end }}

{{/* A pod's labels: the common ones plus its component (which the selector matches). */}}
{{- define "actie.podLabels" -}}
{{- $root := index . 0 -}}
{{ include "actie.labels" $root }}
app.kubernetes.io/component: {{ index . 1 }}
{{- end }}

{{- define "actie.selector" -}}
app.kubernetes.io/part-of: actie
app.kubernetes.io/component: {{ . }}
{{- end }}

{{/* An image of ours: registry/name:tag, or name:tag for local images. */}}
{{- define "actie.image" -}}
{{- $root := index . 0 -}}{{- $name := index . 1 -}}
{{- if $root.Values.image.registry -}}
{{ printf "%s/%s:%s" $root.Values.image.registry $name $root.Values.image.tag }}
{{- else -}}
{{ printf "%s:%s" $name $root.Values.image.tag }}
{{- end -}}
{{- end }}

{{/* Pod Security Standard "restricted": our images already run as non-root users. */}}
{{- define "actie.podSecurity" -}}
runAsNonRoot: true
seccompProfile:
  type: RuntimeDefault
{{- end }}

{{- define "actie.containerSecurity" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: [ALL]
{{- end }}

{{/* How a process reaches the database: the API and both jobs. */}}
{{- define "actie.databaseEnv" -}}
{{- if .Values.postgres.enabled }}
- name: POSTGRES_PASSWORD
  valueFrom: { secretKeyRef: { name: {{ .Values.secretName }}, key: POSTGRES_PASSWORD } }
- name: DATABASE_URL
  value: postgresql://{{ .Values.postgres.user }}:$(POSTGRES_PASSWORD)@{{ include "actie.fullname" . }}-postgres:5432/{{ .Values.postgres.database }}
{{- else }}
- name: DATABASE_URL
  valueFrom: { secretKeyRef: { name: {{ .Values.secretName }}, key: DATABASE_URL } }
{{- end }}
{{- end }}

{{/* A short-lived process from the API image (the jobs): database only, no model key. */}}
{{- define "actie.jobContainer" -}}
image: {{ include "actie.image" (list . "actie-api") }}
imagePullPolicy: {{ .Values.image.pullPolicy }}
env:
  {{- include "actie.databaseEnv" . | nindent 2 }}
securityContext:
  {{- include "actie.containerSecurity" . | nindent 2 }}
resources:
  requests: { cpu: 50m, memory: 128Mi }
  limits: { memory: 256Mi }
volumeMounts:
  - { name: tmp, mountPath: /tmp }
{{- end }}
