#!/bin/bash
set -euo pipefail

# ArgoCD Image Updater setup for Rocky K8s cluster
# Prerequisites: helm, kubectl, ArgoCD already installed in argocd namespace

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Adding Argo Helm repo..."
helm repo add argo https://argoproj.github.io/argo-helm 2>/dev/null || true
helm repo update

echo "==> Creating ghcr.io credentials secret..."
if kubectl get secret ghcr-creds -n argocd &>/dev/null; then
  echo "    Secret ghcr-creds already exists, skipping"
else
  read -rp "GitHub username: " GITHUB_USER
  read -rsp "GitHub PAT (classic, read:packages scope): " GITHUB_PAT
  echo
  kubectl create secret generic ghcr-creds -n argocd \
    --from-literal=token="${GITHUB_USER}:${GITHUB_PAT}"
  echo "    Secret created"
fi

echo "==> Installing ArgoCD Image Updater..."
if helm status argocd-image-updater -n argocd &>/dev/null; then
  echo "    Already installed, upgrading..."
  helm upgrade argocd-image-updater argo/argocd-image-updater \
    -n argocd -f "${SCRIPT_DIR}/image-updater-values.yaml"
else
  helm install argocd-image-updater argo/argocd-image-updater \
    -n argocd -f "${SCRIPT_DIR}/image-updater-values.yaml"
fi

echo "==> Applying updated ApplicationSets..."
kubectl apply -f "${SCRIPT_DIR}/applicationset.yaml"
kubectl apply -f "${SCRIPT_DIR}/mesh-test-applicationset.yaml"

echo "==> Waiting for Image Updater pod..."
kubectl rollout status deployment/argocd-image-updater -n argocd --timeout=120s

echo "==> Done! Verifying..."
kubectl get pods -n argocd -l app.kubernetes.io/name=argocd-image-updater
echo
echo "Check logs with:"
echo "  kubectl logs -n argocd -l app.kubernetes.io/name=argocd-image-updater -f"
