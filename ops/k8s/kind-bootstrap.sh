#!/usr/bin/env bash
#
# kind-bootstrap.sh - Deterministic, idempotent Kind cluster setup for Leviathan
#
# This script:
# - Loads environment from ~/.leviathan/env if present
# - Validates required environment variables
# - Creates Kind cluster if missing
# - Builds and loads worker image
# - Creates namespace and secrets
# - Deploys control plane
# - Runs smoke test
#
# Usage:
#   ./ops/k8s/kind-bootstrap.sh
#
# Prerequisites:
#   - kind installed
#   - docker installed
#   - kubectl installed
#   - Environment variables set (see below)
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CLUSTER_NAME="leviathan"
NAMESPACE="leviathan"
IMAGE_NAME="leviathan-worker:local"
SECRET_NAME="leviathan-secrets"

# Helper functions
log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

fail() {
    log_error "$1"
    exit 1
}

# Load environment from ~/.leviathan/env if present
ENV_FILE="$HOME/.leviathan/env"
if [[ -f "$ENV_FILE" ]]; then
    log_info "Loading environment from $ENV_FILE"
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    log_success "Environment loaded"
else
    log_warn "No environment file found at $ENV_FILE"
    log_info "Will use existing environment variables"
fi

# Validate required environment variables
log_info "Validating required environment variables..."

REQUIRED_VARS=(
    "LEVIATHAN_CONTROL_PLANE_TOKEN"
    "GITHUB_TOKEN"
    "LEVIATHAN_CLAUDE_API_KEY"
    "LEVIATHAN_CLAUDE_MODEL"
)

MISSING_VARS=()
for var in "${REQUIRED_VARS[@]}"; do
    if [[ -z "${!var:-}" ]]; then
        MISSING_VARS+=("$var")
    fi
done

if [[ ${#MISSING_VARS[@]} -gt 0 ]]; then
    log_error "Missing required environment variables:"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    echo ""
    echo "Please set these variables in your environment or in ~/.leviathan/env"
    echo ""
    echo "Example ~/.leviathan/env:"
    echo "  export LEVIATHAN_CONTROL_PLANE_TOKEN=\$(openssl rand -hex 32)"
    echo "  export GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    echo "  export LEVIATHAN_CLAUDE_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    echo "  export LEVIATHAN_CLAUDE_MODEL=claude-3-5-sonnet-20241022"
    exit 1
fi

log_success "All required environment variables are set"

# Check prerequisites
log_info "Checking prerequisites..."

command -v kind >/dev/null 2>&1 || fail "kind is not installed. Install from https://kind.sigs.k8s.io/"
command -v docker >/dev/null 2>&1 || fail "docker is not installed"
command -v kubectl >/dev/null 2>&1 || fail "kubectl is not installed"

log_success "All prerequisites installed"

# Create Kind cluster if it doesn't exist
log_info "Checking for Kind cluster '$CLUSTER_NAME'..."

if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
    log_success "Kind cluster '$CLUSTER_NAME' already exists"
else
    log_info "Creating Kind cluster '$CLUSTER_NAME'..."
    kind create cluster --name "$CLUSTER_NAME"
    log_success "Kind cluster created"
fi

# Set kubectl context
kubectl config use-context "kind-${CLUSTER_NAME}" >/dev/null
log_success "kubectl context set to kind-${CLUSTER_NAME}"

# Build worker image
log_info "Building worker image '$IMAGE_NAME'..."
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

docker build -t "$IMAGE_NAME" -f "$REPO_ROOT/ops/executor/Dockerfile" "$REPO_ROOT"
log_success "Worker image built"

# Load image into Kind cluster
log_info "Loading image into Kind cluster..."
kind load docker-image "$IMAGE_NAME" --name "$CLUSTER_NAME"
log_success "Image loaded into cluster"

# Create namespace
log_info "Creating namespace '$NAMESPACE'..."
kubectl apply -f "$REPO_ROOT/ops/k8s/namespace.yaml"
log_success "Namespace created/updated"

# Create or update secrets
log_info "Creating/updating secrets..."

# Check if secret exists
if kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" >/dev/null 2>&1; then
    log_info "Secret '$SECRET_NAME' exists, deleting to update..."
    kubectl delete secret "$SECRET_NAME" -n "$NAMESPACE"
fi

# Create secret with actual values from environment
kubectl create secret generic "$SECRET_NAME" \
    -n "$NAMESPACE" \
    --from-literal=control-plane-token="$LEVIATHAN_CONTROL_PLANE_TOKEN" \
    --from-literal=github-token="$GITHUB_TOKEN" \
    --from-literal=claude-api-key="$LEVIATHAN_CLAUDE_API_KEY" \
    --from-literal=claude-model="$LEVIATHAN_CLAUDE_MODEL"

log_success "Secret created (values not displayed for security)"

# Deploy control plane
log_info "Deploying control plane..."
kubectl apply -f "$REPO_ROOT/ops/k8s/control-plane.yaml"
log_success "Control plane deployed"

# Wait for control plane to be ready
log_info "Waiting for control plane to be ready..."
kubectl wait --for=condition=available --timeout=120s \
    deployment/leviathan-control-plane -n "$NAMESPACE"
log_success "Control plane is ready"

# Run smoke test
log_info "Running smoke test against control plane..."

# Wait a bit for the service to be fully ready
sleep 5

# Run curl test from within the cluster
SMOKE_TEST_POD="leviathan-smoke-test-$$"
kubectl run "$SMOKE_TEST_POD" \
    --image=curlimages/curl:latest \
    --restart=Never \
    --rm \
    -i \
    -n "$NAMESPACE" \
    --command -- \
    curl -f -s http://leviathan-control-plane:8000/healthz

log_success "Smoke test passed - control plane is accessible"

# Print summary
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}✓ Kind cluster setup complete!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "Cluster: kind-${CLUSTER_NAME}"
echo "Namespace: ${NAMESPACE}"
echo "Control Plane: http://leviathan-control-plane:8000 (in-cluster)"
echo ""
echo "Next steps:"
echo "  1. Run scheduler with K8s executor:"
echo "     python3 -m leviathan.control_plane.scheduler --target <name> --once --executor k8s"
echo ""
echo "  2. Monitor jobs:"
echo "     kubectl get jobs -n ${NAMESPACE} -w"
echo ""
echo "  3. View pod logs:"
echo "     kubectl logs -f <pod-name> -n ${NAMESPACE}"
echo ""
echo "  4. Check control plane logs:"
echo "     kubectl logs -f deployment/leviathan-control-plane -n ${NAMESPACE}"
echo ""
