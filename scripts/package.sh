#!/usr/bin/env bash
# Build dist/<name>-<version>.difypkg, check what went into it, and run the
# Marketplace validator when a dify-marketplace-toolkit checkout is given.
#
#   DIFY=/path/to/dify-plugin-cli PYTHON=.venv/bin/python \
#   TOOLKIT=/path/to/dify-marketplace-toolkit scripts/package.sh
#
# DIFY defaults to `dify` on PATH, PYTHON to python3. TOOLKIT is optional.
set -euo pipefail

cd "$(dirname "$0")/.."
DIFY="${DIFY:-dify}"
PYTHON="${PYTHON:-python3}"

name=$(sed -n 's/^name: *//p' manifest.yaml)
version=$(sed -n 's/^version: *//p' manifest.yaml)
out="dist/${name}-${version}.difypkg"

mkdir -p dist
if [ -f "$out" ]; then
  rm -f -- "$out"
fi

"$DIFY" plugin package . -o "$out"
echo "Built $out ($(wc -c < "$out" | tr -d ' ') bytes)"

"$PYTHON" -m pytest -p no:cacheprovider tests/test_package.py

if [ -n "${TOOLKIT:-}" ]; then
  "$PYTHON" "$TOOLKIT/validator/validate-difypkg.py" "$out" --output-dir dist/validation
fi
