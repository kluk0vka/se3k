#!/usr/bin/env bash
set -euo pipefail
VERSION=${RUNNER_VERSION:-2.337.0}
REPO_URL=${REPO_URL:-https://github.com/kluk0vka/se3k}
DIR=${RUNNER_DIR:-$HOME/actions-runner/se3k}
ARCHIVE=actions-runner-osx-arm64-${VERSION}.tar.gz

: "${RUNNER_TOKEN:?export RUNNER_TOKEN=<registration token from Settings > Actions > Runners > New self-hosted runner>}"

mkdir -p "$DIR"
cd "$DIR"
if [ ! -x ./config.sh ]; then
  curl -fsSLO "https://github.com/actions/runner/releases/download/v${VERSION}/${ARCHIVE}"
  expected=$(curl -fsSL "https://api.github.com/repos/actions/runner/releases/tags/v${VERSION}" |
    python3 -c "import json,sys; print([a['digest'] for a in json.load(sys.stdin)['assets'] if a['name'] == '${ARCHIVE}'][0].split(':')[1])")
  echo "${expected}  ${ARCHIVE}" | shasum -a 256 -c -
  tar xzf "$ARCHIVE"
  rm -f "$ARCHIVE"
fi

./config.sh --unattended --replace \
  --url "$REPO_URL" \
  --token "$RUNNER_TOKEN" \
  --name "$(hostname -s)-staybook" \
  --labels staybook \
  --work _work

./svc.sh install
./svc.sh start
./svc.sh status
