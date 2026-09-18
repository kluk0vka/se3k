SHELL := /bin/bash
CLUSTER ?= staybook

.PHONY: tools cluster bootstrap kafka destroy

tools:
	brew install helm ansible cilium-cli istioctl argocd yq kustomize hashicorp/tap/terraform || true
	pip3 install --user locust kubernetes

cluster:
	./infra/cluster/minikube-up.sh $(CLUSTER)

bootstrap:
	cd infra/terraform && terraform init && terraform apply -auto-approve
	kustomize build gitops/platform/argocd | kubectl apply --server-side --force-conflicts -f -
	kubectl apply -f gitops/root/root-app.yaml

kafka:
	cd infra/ansible && ansible-playbook kafka.yml

destroy:
	minikube delete -p $(CLUSTER)
