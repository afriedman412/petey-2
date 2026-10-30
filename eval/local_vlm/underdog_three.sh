#!/bin/zsh
# Underdog (IQ2 + Q8 vision add-on, llama.cpp b11574) classifies the three new single-page forms.
cd /Users/user/Documents/code/petey-2
export PYTHONPATH=.
L=models/llm
log() { echo "$(date '+%H:%M:%S') $*" | tee -a runs/local_vlm/progress.log; }
$L/llama-b11574/llama-server -m $L/Underdog-Saluki-27B-1.0-IQ2-mix.gguf --mmproj $L/mmproj-Underdog-Saluki-27B-1.0-Q8_0.gguf \
  -c 32768 -np 1 -ngl 99 -fa on -ctk q8_0 -ctv q8_0 --jinja --reasoning-budget 0 --host 127.0.0.1 --port 8081 \
  > runs/local_vlm/server_underdog.log 2>&1 &
SP=$!
for i in {1..120}; do curl -s --max-time 2 http://127.0.0.1:8081/health | grep -q ok && break; sleep 5; done
log "server up; Underdog, thinking off, on dd1155, ia_1, osha_301"
PETEY_LOCAL_LLM_URL=http://127.0.0.1:8081/v1 venv/bin/python eval/local_vlm/classify_run.py local-underdog-iq2-q8vision-nothink >> runs/local_vlm/progress.log 2>&1
kill $SP
log "DONE"
