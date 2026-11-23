#!/usr/bin/env bash
set -euo pipefail

STRATEGY=${1:-}
CANDIDATE_IMAGE=${2:-}
BASELINE_IMAGE=${BASELINE_IMAGE:-$CANDIDATE_IMAGE}

case "$STRATEGY" in
  rolling|blue-green|canary|shadow|ab) ;;
  *)
    echo "Usage: $0 {rolling|blue-green|canary|shadow|ab} <candidate-image>" >&2
    exit 2
    ;;
esac

if [[ -z "$CANDIDATE_IMAGE" ]]; then
  echo "A candidate container image is required." >&2
  exit 2
fi

: "${ACEEST_SECRET_KEY:?Set ACEEST_SECRET_KEY before deployment.}"
: "${ACEEST_ADMIN_PASSWORD:?Set ACEEST_ADMIN_PASSWORD before deployment.}"

NAMESPACE="aceest-${STRATEGY}"

kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NAMESPACE" create secret generic aceest-secrets \
  --from-literal=ACEEST_SECRET_KEY="$ACEEST_SECRET_KEY" \
  --from-literal=ACEEST_ADMIN_PASSWORD="$ACEEST_ADMIN_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NAMESPACE" apply -f k8s/common/app-config.yaml

for manifest in k8s/"$STRATEGY"/*.yaml; do
  sed \
    -e "s|__BASELINE_IMAGE__|$BASELINE_IMAGE|g" \
    -e "s|__CANDIDATE_IMAGE__|$CANDIDATE_IMAGE|g" \
    "$manifest"
done | kubectl -n "$NAMESPACE" apply -f -

while IFS= read -r deployment; do
  kubectl -n "$NAMESPACE" annotate "$deployment" \
    kubernetes.io/change-cause="candidate=$CANDIDATE_IMAGE build=${BUILD_NUMBER:-manual}" \
    --overwrite
  kubectl -n "$NAMESPACE" rollout status "$deployment" --timeout=180s
done < <(
  kubectl -n "$NAMESPACE" get deployment \
    -l app.kubernetes.io/name=aceest-fitness \
    -o name
)

echo "Deployment strategy: $STRATEGY"
echo "Namespace: $NAMESPACE"
echo "Baseline image: $BASELINE_IMAGE"
echo "Candidate image: $CANDIDATE_IMAGE"
kubectl -n "$NAMESPACE" get deployment,pod,service,ingress
