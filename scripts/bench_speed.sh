#!/usr/bin/env bash
# Measure load / prompt / generation speed for local Ollama models.
# Usage: ./scripts/bench_speed.sh [model ...]
set -euo pipefail

MODELS=("$@")
[[ ${#MODELS[@]} -eq 0 ]] && MODELS=(qwen3:8b qwen3:14b)
PROMPT="${PROMPT:-Explain what an AI agent is in about 100 words.}"

for m in "${MODELS[@]}"; do
  curl -s http://localhost:11434/api/chat -d "{
    \"model\": \"$m\",
    \"messages\": [{\"role\": \"user\", \"content\": \"$PROMPT\"}],
    \"think\": false,
    \"stream\": false
  }" | python3 -c "
import sys, json
r = json.load(sys.stdin)
print('$m')
print('  load time  : %.1f s' % (r['load_duration']/1e9))
print('  prompt     : %.1f tok/s (%d tokens)' % (r['prompt_eval_count']/(r['prompt_eval_duration']/1e9), r['prompt_eval_count']))
print('  generation : %.1f tok/s (%d tokens)' % (r['eval_count']/(r['eval_duration']/1e9), r['eval_count']))
print('  total      : %.1f s' % (r['total_duration']/1e9))
"
done
