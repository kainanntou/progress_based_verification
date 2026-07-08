#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

run_step() {
  local name="$1"
  shift
  printf "\n==> %s\n" "$name"
  "$@"
}

clean_workspace() {
  find "$PROJECT_ROOT" \
    \( -type d \( -name "__pycache__" -o -name ".pytest_cache" -o -name ".mypy_cache" -o -name ".ruff_cache" \) -prune -exec rm -rf {} + \) \
    -o \( -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete \)
}

create_venv_and_install() {
  rm -rf "$PROJECT_ROOT/.venv"

  if command -v python3.12 >/dev/null 2>&1; then
    python3.12 -m venv .venv
  elif command -v python3.11 >/dev/null 2>&1; then
    python3.11 -m venv .venv
  elif command -v python3.10 >/dev/null 2>&1; then
    python3.10 -m venv .venv
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m venv .venv
  elif command -v python >/dev/null 2>&1; then
    python -m venv .venv
  else
    printf "No Python interpreter found. Install Python 3.10 or newer.\n" >&2
    exit 1
  fi

  local venv_python="$PROJECT_ROOT/.venv/bin/python"
  "$venv_python" -m pip install --upgrade pip
  "$venv_python" -m pip install ".[dev]"
}

build_package() {
  rm -rf "$PROJECT_ROOT/dist"
  "$PROJECT_ROOT/.venv/bin/python" -m hatch build

  compgen -G "$PROJECT_ROOT/dist/*.whl" >/dev/null || {
    printf "Expected wheel (*.whl) in dist/.\n" >&2
    exit 1
  }
  compgen -G "$PROJECT_ROOT/dist/*.tar.gz" >/dev/null || {
    printf "Expected source distribution (*.tar.gz) in dist/.\n" >&2
    exit 1
  }
}

initialize_git_and_commit() {
  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git init
  fi

  git add -A
  if git diff --cached --quiet; then
    printf "No staged changes to commit.\n"
  else
    git commit -m "chore: initial production-ready package structure with fair chain complex verification"
  fi
}

run_step "Phase 1: clean local caches and compiled Python artifacts" clean_workspace
run_step "Phase 2: create isolated virtual environment and install dependencies" create_venv_and_install
run_step "Phase 3a: ruff format check" "$PROJECT_ROOT/.venv/bin/python" -m ruff format --check .
run_step "Phase 3b: ruff lint with safe fixes" "$PROJECT_ROOT/.venv/bin/python" -m ruff check . --fix
run_step "Phase 3c: mypy strict type check" "$PROJECT_ROOT/.venv/bin/python" -m mypy --strict src tests
run_step "Phase 3d: pytest full suite" "$PROJECT_ROOT/.venv/bin/python" -m pytest
run_step "Phase 4: build wheel and source distribution with Hatch" build_package
run_step "Phase 5: initialize Git repository and create first commit" initialize_git_and_commit

printf "\nSetup, verification, build, and Git registration completed successfully.\n"
