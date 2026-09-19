#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
helm repo add vm https://victoriametrics.github.io/helm-charts/ >/dev/null 2>&1 || true
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts >/dev/null 2>&1 || true
helm repo update vm open-telemetry >/dev/null
CRD_DIR=$(mktemp -d)
helm pull vm/victoria-metrics-k8s-stack --version 0.92.1 --untar --untardir "$CRD_DIR" >/dev/null
python3 - "$CRD_DIR" <<'PY'
import glob, os, sys, yaml
base = sys.argv[1]
src = glob.glob(f"{base}/**/crds/crd.yaml", recursive=True)[0]
for doc in yaml.safe_load_all(open(src)):
    if doc:
        yaml.safe_dump(doc, open(f"{base}/{doc['metadata']['name']}.crd.yaml", "w"))
PY
for f in "$CRD_DIR"/*.crd.yaml; do
  kubectl get crd "$(basename "$f" .crd.yaml)" >/dev/null 2>&1 || kubectl create -f "$f" --request-timeout=300s >/dev/null
done
rm -rf "$CRD_DIR"
helm upgrade --install vm vm/victoria-metrics-k8s-stack -n observability --version 0.92.1 \
  -f values-vm-stack.yaml --skip-crds --wait --timeout 15m
helm upgrade --install otel-collector open-telemetry/opentelemetry-collector -n observability --version 0.173.1 \
  -f values-otel-collector.yaml --wait
kubectl apply -f alert-webhook-logger.yaml -f scrapes.yaml -f alerts.yaml
kubectl apply -k dashboards
