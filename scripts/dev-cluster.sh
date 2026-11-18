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

# rollout status는 새 파드만 기다린다 — 종료 중인 옛 파드가 남으면 바로 뒤의 장애 주입·조사에 섞인다
wait_settled() {
  local left="" i
  for ((i = 0; i < 40; i++)); do
    left="$(k -n demo get pods -o jsonpath='{range .items[?(@.metadata.deletionTimestamp)]}{.metadata.name}{" "}{end}')"
    if [[ -z "${left}" ]]; then
      return 0
    fi
    sleep 3
  done
  echo "복구 뒤에도 종료 중인 파드가 남았다: ${left}" >&2
  return 1
}

cmd_up() {
  local existed=true clusters
  check_kind_version
  # 목록을 먼저 받아 둔다 — kind get clusters | grep -q 는 pipefail 아래에서 SIGPIPE로 실패할 수 있다
  clusters="$(kind get clusters)"
  if grep -qx "${CLUSTER}" <<<"${clusters}"; then
    # 클러스터는 있는데 kubeconfig에 컨텍스트가 없을 때를 대비해 다시 써 둔다
    kind export kubeconfig --name "${CLUSTER}"
  else
    existed=false
    # 새로 만들면 사용자 kubeconfig의 current-context가 kind-hoa로 바뀐다(이 스크립트는 컨텍스트를 명시해서 쓴다)
    kind create cluster --name "${CLUSTER}" --image "${NODE_IMAGE}" \
      --config deploy/kind/kind-config.yaml --wait 120s
  fi
  docker build -f deploy/docker/Dockerfile --build-arg PACKAGE=hoa-demo --build-arg MEMBER=demo_app \
    -t "${DEMO_IMAGE}" .
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

# 기준 매니페스트를 다시 적용한다. client-side apply는 패치가 새로 더한 필드(매니페스트에 없는 환경변수 등)를
# 지우지 않으므로, 장애 패치는 기준 매니페스트에 이미 있는 필드만 바꾼다.
cmd_reset() {
  k apply -f deploy/kind/demo/
  # 진행 기한(progressDeadlineSeconds)을 넘긴 장애도 rollout status가 실패하지 않게 새 ReplicaSet으로 다시 시작한다
  k -n demo rollout restart deployment
  wait_rollouts
  wait_settled
}

cmd_mcp_kubeconfig() {
  local server ca token
  server="$(k config view --minify --raw -o jsonpath='{.clusters[0].cluster.server}')"
  ca="$(k config view --minify --raw -o jsonpath='{.clusters[0].cluster.certificate-authority-data}')"
  token="$(k -n hoa-system create token hoa-mcp-read --duration=12h)"
  local tmp
  mkdir -p "$(dirname "${MCP_KUBECONFIG}")"
  tmp="${MCP_KUBECONFIG}.tmp"
  (
    umask 077
    cat >"${tmp}" <<EOF
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
  # 이미 있던 파일을 덮어써도 권한이 600이 되도록 새 파일에 쓰고 옮긴다
  chmod 600 "${tmp}"
  mv -f "${tmp}" "${MCP_KUBECONFIG}"
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
