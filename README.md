# StayBook

Event-driven платформа бронирования отелей на Kubernetes.

Пять микросервисов на Python (FastAPI) обмениваются событиями через Kafka (сага бронирования, transactional outbox). Платформа включает service mesh, GitOps, CI/CD, observability, rate limiting, отказоустойчивую точку входа и холодный архив событий.

## Стек

| Область | Технологии |
|---|---|
| Кластер | minikube, Kubernetes 1.35, Cilium 1.18 (CNI, сетевые политики, Hubble) |
| IaC и GitOps | Terraform, Ansible, ArgoCD (App of Apps), Helm |
| Service mesh и вход | Istio 1.31 (mTLS, circuit breaking, retry), Gateway API, HAProxy + Keepalived, envoyproxy/ratelimit |
| Данные | Kafka 4.3 (Strimzi), Kafka Connect, PostgreSQL 17, MongoDB 7, Valkey 8, MinIO |
| Observability | OpenTelemetry Collector, VictoriaMetrics, VictoriaLogs, VictoriaTraces, Grafana, vmalert, Alertmanager |
| CI/CD | GitHub Actions (self-hosted runner), Kaniko, локальный registry |
| Тесты | Locust, e2e smoke-тест, chaos-сценарии |
