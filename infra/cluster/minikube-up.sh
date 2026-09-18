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
kubectl taint node "$PROFILE" node-role.kubernetes.io/control-plane=:NoSchedule --overwrite
kubectl -n kube-system delete ds registry-proxy --ignore-not-found
kubectl apply -f "$(dirname "$0")/../../platform/registry/node-proxy.yaml"
docker rm -f registry-fwd >/dev/null 2>&1 || true
docker run -d --name registry-fwd --restart unless-stopped --network=host \
  alpine/socat TCP-LISTEN:5000,reuseaddr,fork "TCP:$(minikube -p "$PROFILE" ip):5000"
kubectl get nodes -o wide
