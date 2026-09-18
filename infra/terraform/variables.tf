variable "kubeconfig" {
  type    = string
  default = "~/.kube/config"
}

variable "kube_context" {
  type    = string
  default = "staybook"
}

variable "namespaces" {
  type    = list(string)
  default = ["staybook", "data", "kafka", "argocd", "observability", "istio-system", "edge", "ci"]
}

variable "services" {
  type    = list(string)
  default = ["catalog-service", "booking-service", "inventory-service", "payment-service", "notification-service"]
}
