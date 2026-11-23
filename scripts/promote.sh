#!/usr/bin/env bash
set -euo pipefail

STRATEGY=${1:-}

case "$STRATEGY" in
  blue-green)
    NAMESPACE=aceest-blue-green
    TARGET=${2:-green}
    if [[ "$TARGET" != "blue" && "$TARGET" != "green" ]]; then
      echo "Blue-green target must be blue or green." >&2
      exit 2
    fi
    kubectl -n "$NAMESPACE" patch service aceest-fitness \
      -p "{\"spec\":{\"selector\":{\"app.kubernetes.io/name\":\"aceest-fitness\",\"aceest.io/slot\":\"$TARGET\"}}}"
    ;;
  canary)
    NAMESPACE=aceest-canary
    kubectl -n "$NAMESPACE" scale deployment aceest-stable --replicas=0
    kubectl -n "$NAMESPACE" scale deployment aceest-canary --replicas=3
    ;;
  ab)
    NAMESPACE=aceest-ab
    echo "A/B routing is active for header X-ACEest-Version: v2."
    echo "Promote by deploying the candidate as the next baseline image."
    ;;
  *)
    echo "Usage: $0 {blue-green [blue|green]|canary|ab}" >&2
    exit 2
    ;;
esac

kubectl -n "$NAMESPACE" get deployment,service,ingress
