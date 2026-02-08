#!/usr/bin/env bash
set -euo pipefail

MODE="${MODE:-}"

echo "[runner] MODE=${MODE}"

case "${MODE}" in
  generate)
    exec python3 -X utf8 "/app/runner_generate.py"
    ;;
  test)
    exec python3 -X utf8 "/app/runner_test.py"
    ;;
  *)
    echo "[runner] invalid MODE: ${MODE}" >&2
    exit 2
    ;;
esac

