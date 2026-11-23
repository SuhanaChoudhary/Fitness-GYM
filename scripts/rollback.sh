#!/usr/bin/env bash
set -euo pipefail

STRATEGY=${1:-}

case "$STRATEGY" in
  rolling)
    NAMESPACE=aceest-rolling
    kubectl -n "$NAMESPACE" rollout undo deployment/aceest-fitness
    kubectl -n "$NAMESPACE" rollout status deployment/aceest-fitness --timeout=180s
    ;;
  blue-green)
    NAMESPACE=aceest-blue-green
    ACTIVE=$(kubectl -n "$NAMESPACE" get service aceest-fitness \
      -o jsonpath='{.spec.selector.aceest\.io/slot}')
    if [[ "$ACTIVE" == "green" ]]; then TARGET=blue; else TARGET=green; fi
    kubectl -n "$NAMESPACE" patch service aceest-fitness \
      -p "{\"spec\":{\"selector\":{\"app.kubernetes.io/name\":\"aceest-fitness\",\"aceest.io/slot\":\"$TARGET\"}}}"
    ;;
  canary)
    NAMESPACE=aceest-canary
    kubectl -n "$NAMESPACE" scale deployment aceest-canary --replicas=0
    kubectl -n "$NAMESPACE" scale deployment aceest-stable --replicas=3
    ;;
  shadow)
    NAMESPACE=aceest-shadow
    kubectl -n "$NAMESPACE" scale deployment aceest-shadow --replicas=0
    ;;
  ab)
    NAMESPACE=aceest-ab
    kubectl -n "$NAMESPACE" delete ingress aceest-v2 --ignore-not-found
    kubectl -n "$NAMESPACE" scale deployment aceest-v2 --replicas=0
    ;;
  *)
    echo "Usage: $0 {rolling|blue-green|canary|shadow|ab}" >&2
    exit 2
    ;;
esac

kubectl -n "$NAMESPACE" get deployment,service,ingress
