#!/bin/bash

set -u

failures=()

echo "=== ruff format ==="
if ! uv run ruff format --check; then
    failures+=("ruff format: files need formatting")
fi

echo ""
echo "=== ruff check ==="
if ! uv run ruff check; then
    failures+=("ruff check: lint errors found")
fi

echo ""
echo "=== yamllint ==="
if ! uv run yamllint .; then
    failures+=("yamllint: YAML lint errors found")
fi

echo ""
echo "=== pytest ==="
if ! uv run pytest; then
    failures+=("pytest: test failures")
fi

echo ""
if [ ${#failures[@]} -eq 0 ]; then
    echo "All checks passed."
else
    echo "FAILURES:"
    for msg in "${failures[@]}"; do
        echo "  - $msg"
    done
    exit 1
fi
