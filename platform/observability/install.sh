#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
helm repo add vm https://victoriametrics.github.io/helm-charts/ >/dev/null 2>&1 || true
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts >/dev/null 2>&1 || true
helm repo update vm open-telemetry >/dev/null
helm upgrade --install vm vm/victoria-metrics-k8s-stack -n observability --version 0.92.1 \
  -f values-vm-stack.yaml --wait --timeout 15m
helm upgrade --install otel-collector open-telemetry/opentelemetry-collector -n observability --version 0.173.1 \
  -f values-otel-collector.yaml --wait
kubectl apply -f alert-webhook-logger.yaml -f scrapes.yaml -f alerts.yaml
kubectl apply -k dashboards
