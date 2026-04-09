#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-daily}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

load_theinfo_env() {
  local line
  while IFS= read -r line; do
    [[ -n "${line}" ]] || continue
    export "${line}"
  done < <(bash -ic 'env | grep "^THEINFO_"' 2>/dev/null || true)
}

load_theinfo_env

if [[ -z "${THEINFO_USERNAME:-}" || -z "${THEINFO_PASSWORD:-}" ]]; then
  echo "Missing THEINFO_USERNAME or THEINFO_PASSWORD" >&2
  exit 1
fi

cd "${SCRIPT_DIR}"
"${SCRIPT_DIR}/.venv/bin/python" "${SCRIPT_DIR}/automate_rss.py" --mode "${MODE}"
