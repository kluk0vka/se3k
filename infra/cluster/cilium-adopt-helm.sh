#!/usr/bin/env bash
set -euo pipefail
NS=kube-system
REL=cilium
VERSION=${CILIUM_VERSION:-1.18.6}

adopt() {
  local ns_flag=()
  [[ -n "${3:-}" ]] && ns_flag=(-n "$3")
  kubectl ${ns_flag[@]+"${ns_flag[@]}"} annotate --overwrite "$1" "$2" meta.helm.sh/release-name=$REL meta.helm.sh/release-namespace=$NS
  kubectl ${ns_flag[@]+"${ns_flag[@]}"} label --overwrite "$1" "$2" app.kubernetes.io/managed-by=Helm
}

for r in ds/cilium ds/cilium-envoy deploy/cilium-operator cm/cilium-config cm/cilium-envoy-config \
         sa/cilium sa/cilium-envoy sa/cilium-operator svc/cilium-envoy svc/hubble-peer \
         role/cilium-config-agent rolebinding/cilium-config-agent; do
  adopt "${r%%/*}" "${r#*/}" $NS
done
for r in role/cilium-operator-tlsinterception-secrets role/cilium-tlsinterception-secrets \
         rolebinding/cilium-operator-tlsinterception-secrets rolebinding/cilium-tlsinterception-secrets; do
  adopt "${r%%/*}" "${r#*/}" cilium-secrets
done
for r in namespace/cilium-secrets clusterrole/cilium clusterrole/cilium-operator clusterrolebinding/cilium clusterrolebinding/cilium-operator; do
  adopt "${r%%/*}" "${r#*/}"
done
kubectl get secret -n $NS -o name | grep -E "hubble|cilium-ca" | while read -r s; do adopt secret "${s#secret/}" $NS; done || true

helm repo add cilium https://helm.cilium.io >/dev/null 2>&1 || true
helm repo update cilium >/dev/null
helm upgrade --install $REL cilium/cilium --version "$VERSION" -n $NS \
  -f "$(dirname "$0")/../../platform/cilium/values.yaml" --server-side=true --force-conflicts --wait --timeout 10m
cilium status --wait
