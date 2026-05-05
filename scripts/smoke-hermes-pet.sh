#!/usr/bin/env bash
set -uo pipefail

echo "== Hermes Pet smoke =="

if ! command -v hermes-pet >/dev/null 2>&1; then
  echo "hermes-pet command not found on PATH" >&2
  exit 127
fi

echo
echo "== prefs =="
hermes-pet prefs

echo
echo "== doctor =="
hermes-pet doctor || true

echo
echo "== emit bubble =="
if ! hermes-pet emit bubble "Hermes Pet smoke check"; then
  echo "emit failed; launch the overlay with: hermes-pet launch" >&2
fi

echo
echo "== wrapped success =="
hermes-pet wrap --name "smoke success" -- bash -lc 'printf "%s\n" "smoke success"'

echo
echo "== wrapped failure =="
set +e
hermes-pet wrap --name "smoke expected failure" -- bash -lc 'printf "%s\n" "smoke expected failure" >&2; exit 7'
failure_code=$?
set -e
if [ "$failure_code" -eq 7 ]; then
  echo "expected failure wrapper returned 7"
else
  echo "failure wrapper returned $failure_code (expected 7)" >&2
fi

echo
echo "== jobs --last =="
hermes-pet jobs --last

echo
echo "== brief =="
hermes-pet brief --since 24h

echo
echo "Hermes Pet smoke complete."
