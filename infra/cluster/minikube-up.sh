#!/usr/bin/env bash
set -euo pipefail
PROFILE=${1:-staybook}
NODES=${NODES:-3}
NODE_CPUS=${NODE_CPUS:-2}
NODE_MEMORY=${NODE_MEMORY:-3800}

minikube start -p "$PROFILE" \
  --nodes "$NODES" \
  --cpus "$NODE_CPUS" --memory "$NODE_MEMORY" \
  --cni cilium \
  --kubernetes-version stable \
  --addons metrics-server,registry

cilium status --wait || true
cilium hubble enable --ui || true
kubectl get nodes -o wide
