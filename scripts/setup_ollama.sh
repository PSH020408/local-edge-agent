#!/usr/bin/env bash
# Install and verify Ollama on Apple Silicon macOS (terminal only, no GUI app).
# Usage: ./scripts/setup_ollama.sh [model]
set -euo pipefail

MODEL="${1:-qwen3:8b}"

info() { printf "\033[1;34m[setup]\033[0m %s\n" "$1"; }
fail() { printf "\033[1;31m[error]\033[0m %s\n" "$1"; exit 1; }

[[ "$(uname -s)" == "Darwin" ]] || fail "This script targets macOS."
[[ "$(uname -m)" == "arm64" ]]  || fail "Apple Silicon (arm64) is required."

info "Chip:   $(sysctl -n machdep.cpu.brand_string)"
info "Memory: $(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 )) GB"

# 1. Homebrew
if ! command -v brew >/dev/null 2>&1; then
  info "Homebrew not found. Installing..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi
info "Homebrew: $(brew --version | head -1)"

# 2. Ollama (CLI formula, not the desktop app)
if ! command -v ollama >/dev/null 2>&1; then
  info "Installing Ollama via Homebrew..."
  brew install ollama
fi
info "Ollama: $(ollama --version)"

# 3. Run the server as a background service
if ! curl -sf http://localhost:11434/api/version >/dev/null; then
  info "Starting Ollama service..."
  brew services start ollama
  for _ in {1..20}; do
    curl -sf http://localhost:11434/api/version >/dev/null && break
    sleep 1
  done
fi
curl -sf http://localhost:11434/api/version >/dev/null || fail "Ollama server did not start."
info "Server is up at http://localhost:11434"

# 4. Pull a model
info "Pulling model: $MODEL"
ollama pull "$MODEL"

# 5. Smoke test through the HTTP API (the same path the agent will use)
info "Running smoke test..."
curl -s http://localhost:11434/api/chat -d "{
  \"model\": \"$MODEL\",
  \"messages\": [{\"role\": \"user\", \"content\": \"Reply with exactly: OK\"}],
  \"stream\": false
}" | python3 -c 'import sys, json; r = json.load(sys.stdin); print("Model reply:", r["message"]["content"].strip()); print("Tokens/sec: %.1f" % (r["eval_count"] / (r["eval_duration"] / 1e9)))'

info "Done. Installed models:"
ollama list
