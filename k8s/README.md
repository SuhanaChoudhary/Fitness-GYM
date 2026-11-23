# Kubernetes deployment strategy guide

These manifests demonstrate five release strategies for the ACEest Fitness application. Each strategy uses a separate namespace, readiness and liveness probes, non-root containers, resource limits, and an isolated ephemeral SQLite database. Use a public registry image for Minikube, or configure an image pull secret before deployment.

## Prerequisites

Install `kubectl` and Minikube, then start the cluster:

```bash
minikube start --cpus=4 --memory=6144
minikube addons enable ingress
kubectl cluster-info
```

Export the application secrets and select versioned registry images:

```bash
export ACEEST_SECRET_KEY="replace-with-a-long-random-value"
export ACEEST_ADMIN_PASSWORD="replace-with-a-strong-password"
export BASELINE_IMAGE="docker.io/YOUR_USER/aceest-fitness:v1.0.1"
export CANDIDATE_IMAGE="docker.io/YOUR_USER/aceest-fitness:v1.0.2"
```

The deployment script creates a Kubernetes Secret from the two environment variables. Secret values are never stored in Git.

## Rolling update

```bash
bash scripts/deploy.sh rolling "$CANDIDATE_IMAGE"
kubectl -n aceest-rolling rollout history deployment/aceest-fitness
curl "http://$(minikube ip):30080/health"
```

The Deployment uses `maxUnavailable: 0` and `maxSurge: 1`. A failed release can be reverted to its previous ReplicaSet:

```bash
bash scripts/rollback.sh rolling
```

## Blue-green deployment

The blue Deployment runs the baseline while the green Deployment runs the candidate. The Service initially selects blue.

```bash
BASELINE_IMAGE="$BASELINE_IMAGE" \
  bash scripts/deploy.sh blue-green "$CANDIDATE_IMAGE"
curl "http://$(minikube ip):30081/health"
```

Validate green directly before promotion:

```bash
kubectl -n aceest-blue-green port-forward deployment/aceest-green 5001:5000
curl http://127.0.0.1:5001/health
```

Switch traffic without recreating the Service:

```bash
bash scripts/promote.sh blue-green green
```

Switch back to the previous slot:

```bash
bash scripts/rollback.sh blue-green
```

## Canary release

Three stable Pods and one candidate Pod share a Service, producing an approximate 75/25 traffic split.

```bash
BASELINE_IMAGE="$BASELINE_IMAGE" \
  bash scripts/deploy.sh canary "$CANDIDATE_IMAGE"
curl "http://$(minikube ip):30082/health"
```

Promote the candidate or remove it immediately:

```bash
bash scripts/promote.sh canary
bash scripts/rollback.sh canary
```

## Shadow deployment

The NGINX Ingress returns the primary response and mirrors each request to the candidate. Shadow responses are ignored, and the candidate uses a separate ephemeral database.

```bash
BASELINE_IMAGE="$BASELINE_IMAGE" \
  bash scripts/deploy.sh shadow "$CANDIDATE_IMAGE"
curl -H 'Host: aceest-shadow.local' "http://$(minikube ip)/health"
kubectl -n aceest-shadow logs deployment/aceest-shadow --tail=20
```

Stop mirrored processing while leaving the primary available:

```bash
bash scripts/rollback.sh shadow
```

Shadow mirroring requires the Minikube NGINX Ingress add-on. It is intended for validation traffic; mirrored requests may execute writes in the isolated shadow environment.

## A/B testing

The primary Ingress routes to v1. Requests containing `X-ACEest-Version: v2` route to the candidate.

```bash
BASELINE_IMAGE="$BASELINE_IMAGE" \
  bash scripts/deploy.sh ab "$CANDIDATE_IMAGE"

curl -H 'Host: aceest-ab.local' "http://$(minikube ip)/health"
curl -H 'Host: aceest-ab.local' -H 'X-ACEest-Version: v2' \
  "http://$(minikube ip)/health"
```

Remove v2 routing and scale its Deployment to zero:

```bash
bash scripts/rollback.sh ab
```

## Cluster evidence and cleanup

Capture the following output for the assignment evidence:

```bash
kubectl get namespaces
kubectl get deployment,pod,service,ingress --all-namespaces
kubectl -n aceest-rolling rollout history deployment/aceest-fitness
```

Remove all demonstration environments:

```bash
kubectl delete namespace \
  aceest-rolling aceest-blue-green aceest-canary aceest-shadow aceest-ab
```

Kubernetes rolling updates and rollback behavior are documented in the [Kubernetes deployment guide](https://kubernetes.io/docs/tasks/run-application/update-deployment-rolling/). The shadow and A/B examples depend on [Ingress NGINX mirroring and canary annotations](https://kubernetes.github.io/ingress-nginx/user-guide/nginx-configuration/annotations/).
