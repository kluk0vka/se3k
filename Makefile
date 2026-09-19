SHELL := /bin/bash
CLUSTER ?= staybook
KAFKA_PROFILE ?= local
TAG ?= 0.2.1

.PHONY: all tools cluster cilium bootstrap data kafka platform autoscaler observability images apps edge destroy

tools:
	brew install helm ansible cilium-cli istioctl argocd yq kustomize hashicorp/tap/terraform || true
	pip3 install --user locust kubernetes

all: cluster cilium bootstrap data kafka platform observability images apps edge

cluster:
	./infra/cluster/minikube-up.sh $(CLUSTER)

cilium:
	./infra/cluster/cilium-adopt-helm.sh

bootstrap:
	kustomize build platform/storage | kubectl apply -f -
	kubectl annotate sc standard storageclass.kubernetes.io/is-default-class=false --overwrite
	cd infra/terraform && terraform init && terraform apply -auto-approve
	kustomize build gitops/platform/argocd | kubectl apply --server-side --force-conflicts -f -

data:
	kubectl apply -f platform/data/valkey/valkey.yaml -f platform/data/postgres/postgres.yaml -f platform/data/mongo/mongo.yaml

kafka:
	cd infra/ansible && ansible-playbook kafka.yml -e @profiles/$(KAFKA_PROFILE).yml

platform:
	./platform/istio/install.sh
	kubectl apply -f platform/gateway/gateway.yaml -f platform/ratelimit/ratelimit.yaml -f platform/ratelimit/envoyfilter.yaml

autoscaler:
	./platform/autoscaler/install.sh

observability:
	./platform/observability/install.sh

images:
	for s in catalog-service booking-service inventory-service payment-service notification-service; do \
	  docker build --build-arg SERVICE=$$s -t localhost:5000/staybook/$$s:$(TAG) services && \
	  docker push localhost:5000/staybook/$$s:$(TAG); \
	done

apps:
	kubectl apply -f gitops/root/root-app.yaml

edge:
	cd platform/edge-lb && docker compose up -d --build

destroy:
	minikube delete -p $(CLUSTER)
