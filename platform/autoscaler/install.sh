#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
helm repo add kwok https://kwok.sigs.k8s.io/charts/ >/dev/null 2>&1 || true
helm repo update kwok >/dev/null
helm upgrade --install kwok kwok/kwok -n kube-system --version 0.3.0 --wait
helm upgrade --install kwok-stage-fast kwok/stage-fast -n kube-system --version 0.3.0
kustomize build --enable-helm . | kubectl apply -f -
kubectl -n kube-system rollout status deploy -l app.kubernetes.io/name=clusterapi-cluster-autoscaler --timeout=5m 2>/dev/null \
  || kubectl -n kube-system rollout status deploy/cluster-autoscaler-kwok-cluster-autoscaler --timeout=5m
