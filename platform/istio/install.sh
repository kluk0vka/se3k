#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
GATEWAY_API_VERSION=${GATEWAY_API_VERSION:-v1.6.0}
kubectl kustomize "github.com/kubernetes-sigs/gateway-api/config/crd?ref=${GATEWAY_API_VERSION}" | kubectl apply --server-side -f -
istioctl install -f istio.yaml -y
kubectl apply -f peer-authentication.yaml
