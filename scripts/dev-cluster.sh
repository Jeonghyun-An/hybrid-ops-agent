#!/usr/bin/env bash
# 로컬 티어 kind 개발 클러스터 — 만들기·지우기·장애 주입·복구·MCP용 읽기 전용 kubeconfig.
# 사용: bash scripts/dev-cluster.sh <up|down|fault <image-pull|bad-config>|reset|mcp-kubeconfig>
# 모든 kubectl 호출은 --context kind-hoa 를 명시한다 — 다른 클러스터(회사 서버 등)를 건드리지 않는다.
# Windows Git Bash는 '/'로 시작하는 인자를 Windows 경로로 바꾸므로, 저장소 루트로 옮겨 가서 상대 경로만 쓴다.
set -euo pipefail

CLUSTER=hoa
CONTEXT="kind-${CLUSTER}"
KIND_VERSION=v0.33.0
NODE_IMAGE="kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5"
DEMO_IMAGE=hoa-demo:0.1.0
DEMO_DEPLOYMENTS=(inventory orders gateway)
MCP_KUBECONFIG="${HOA_MCP_KUBECONFIG:-${HOME}/.kube/hoa-kind-mcp-read.kubeconfig}"

cd "$(dirname "${BASH_SOURCE[0]}")/.."

k() {
  kubectl --context "${CONTEXT}" "$@"
}

usage() {
  echo "사용: bash scripts/dev-cluster.sh <up|down|fault <image-pull|bad-config>|reset|mcp-kubeconfig>" >&2
}

check_kind_version() {
  local installed
  installed="$(kind version | awk '{print $2}')"
  if [[ "${installed}" != "${KIND_VERSION}" ]]; then
    echo "kind ${KIND_VERSION}이 필요하다(설치된 버전: ${installed})" >&2
    exit 1
  fi
}

wait_rollouts() {
  local name
  for name in "${DEMO_DEPLOYMENTS[@]}"; do
    k -n demo rollout status "deployment/${name}" --timeout=180s
  done
}

cmd_up() {
  local existed=true
  check_kind_version
  if ! kind get clusters | grep -qx "${CLUSTER}"; then
    existed=false
    kind create cluster --name "${CLUSTER}" --image "${NODE_IMAGE}" \
      --config deploy/kind/kind-config.yaml --wait 120s
  fi
  docker build -f demo_app/Dockerfile -t "${DEMO_IMAGE}" .
  kind load docker-image "${DEMO_IMAGE}" --name "${CLUSTER}"
  k apply -f deploy/kind/demo/
  k apply -f deploy/kind/rbac/
  if [[ "${existed}" == true ]]; then
    # 태그가 같아 apply만으로는 새로 넣은 이미지로 파드가 바뀌지 않는다
    k -n demo rollout restart deployment
  fi
  wait_rollouts
  cmd_mcp_kubeconfig
}

cmd_down() {
  kind delete cluster --name "${CLUSTER}"
}

cmd_fault() {
  local name="${1:-}" target
  case "${name}" in
    image-pull) target=orders ;;
    bad-config) target=inventory ;;
    *)
      usage
      exit 2
      ;;
  esac
  k -n demo patch "deployment/${target}" --type strategic \
    --patch-file "deploy/kind/faults/${name}.yaml"
  echo "장애 ${name}을(를) deployment/${target}에 넣었다 — 되돌리기: bash scripts/dev-cluster.sh reset"
}

cmd_reset() {
  k apply -f deploy/kind/demo/
  wait_rollouts
}

cmd_mcp_kubeconfig() {
  local server ca token
  server="$(k config view --minify --raw -o jsonpath='{.clusters[0].cluster.server}')"
  ca="$(k config view --minify --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')"
  token="$(k -n hoa-system create token hoa-mcp-read --duration=12h)"
  mkdir -p "$(dirname "${MCP_KUBECONFIG}")"
  (
    umask 077
    cat >"${MCP_KUBECONFIG}" <<EOF
apiVersion: v1
kind: Config
clusters:
  - name: ${CONTEXT}
    cluster:
      server: ${server}
      certificate-authority-data: ${ca}
users:
  - name: hoa-mcp-read
    user:
      token: ${token}
contexts:
  - name: hoa-mcp-read@${CONTEXT}
    context:
      cluster: ${CONTEXT}
      user: hoa-mcp-read
      namespace: demo
current-context: hoa-mcp-read@${CONTEXT}
EOF
  )
  echo "MCP용 읽기 전용 kubeconfig: ${MCP_KUBECONFIG} (토큰 12시간 유효)"
}

case "${1:-}" in
  up) cmd_up ;;
  down) cmd_down ;;
  fault)
    shift
    cmd_fault "$@"
    ;;
  reset) cmd_reset ;;
  mcp-kubeconfig) cmd_mcp_kubeconfig ;;
  *)
    usage
    exit 2
    ;;
esac
