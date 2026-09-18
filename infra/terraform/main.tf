locals {
  app_namespace = "staybook"

  postgres_services = ["booking-service", "inventory-service", "payment-service"]
  mongo_services    = ["catalog-service", "notification-service"]
  valkey_services   = ["catalog-service", "inventory-service"]

  common_labels = {
    "app.kubernetes.io/part-of"    = "staybook"
    "app.kubernetes.io/managed-by" = "terraform"
  }
}

resource "kubernetes_namespace_v1" "ns" {
  for_each = toset(var.namespaces)
  metadata {
    name = each.value
    labels = merge(
      local.common_labels,
      each.value == local.app_namespace ? { "istio-injection" = "enabled" } : {}
    )
  }
}

resource "kubernetes_service_account_v1" "svc" {
  for_each = toset(var.services)
  metadata {
    name      = each.value
    namespace = kubernetes_namespace_v1.ns[local.app_namespace].metadata[0].name
    labels    = merge(local.common_labels, { "app.kubernetes.io/name" = each.value })
  }
  automount_service_account_token = false
}

resource "random_password" "postgres" {
  for_each = toset(local.postgres_services)
  length   = 24
  special  = false
}

resource "random_password" "mongo" {
  for_each = toset(local.mongo_services)
  length   = 24
  special  = false
}

resource "random_password" "valkey" {
  length  = 32
  special = false
}

resource "kubernetes_secret_v1" "postgres" {
  for_each = toset(local.postgres_services)
  metadata {
    name      = "${each.value}-postgres"
    namespace = kubernetes_namespace_v1.ns[local.app_namespace].metadata[0].name
    labels    = local.common_labels
  }
  data = {
    POSTGRES_USER     = replace(each.value, "-service", "")
    POSTGRES_PASSWORD = random_password.postgres[each.value].result
    POSTGRES_DB       = replace(each.value, "-service", "")
  }
}

resource "kubernetes_secret_v1" "mongo" {
  for_each = toset(local.mongo_services)
  metadata {
    name      = "${each.value}-mongo"
    namespace = kubernetes_namespace_v1.ns[local.app_namespace].metadata[0].name
    labels    = local.common_labels
  }
  data = {
    MONGO_USER     = replace(each.value, "-service", "")
    MONGO_PASSWORD = random_password.mongo[each.value].result
  }
}

resource "kubernetes_secret_v1" "valkey" {
  for_each = merge(
    { for s in local.valkey_services : s => { name = "${s}-valkey", namespace = local.app_namespace } },
    {
      valkey    = { name = "valkey-auth", namespace = "data" }
      ratelimit = { name = "ratelimit-valkey", namespace = "edge" }
    }
  )
  metadata {
    name      = each.value.name
    namespace = kubernetes_namespace_v1.ns[each.value.namespace].metadata[0].name
    labels    = local.common_labels
  }
  data = {
    VALKEY_PASSWORD = random_password.valkey.result
  }
}

resource "random_password" "grafana_admin" {
  length  = 20
  special = false
}

resource "kubernetes_secret_v1" "grafana_admin" {
  metadata {
    name      = "grafana-admin"
    namespace = kubernetes_namespace_v1.ns["observability"].metadata[0].name
    labels    = local.common_labels
  }
  data = {
    admin-user     = "admin"
    admin-password = random_password.grafana_admin.result
  }
}
