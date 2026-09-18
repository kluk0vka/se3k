output "namespaces" {
  value = keys(kubernetes_namespace_v1.ns)
}

output "service_accounts" {
  value = [for sa in kubernetes_service_account_v1.svc : "${sa.metadata[0].namespace}/${sa.metadata[0].name}"]
}
