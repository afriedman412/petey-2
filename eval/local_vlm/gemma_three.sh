#!/bin/zsh
# Gemma 4 26B-A4B (unsloth UD-IQ2_M + F16 vision add-on, llama.cpp b11574) classifies the three new single-page forms.
cd /Users/user/Documents/code/petey-2
export PYTHONPATH=.
L=models/llm
HF=https://huggingface.co/unsloth/gemma-4-26B-A4B-it-GGUF/resolve/main
log() { echo "$(date '+%H:%M:%S') $*" | tee -a runs/local_vlm/progress.log; }
for f in gemma-4-26B-A4B-it-UD-IQ2_M.gguf mmproj-F16.gguf; do
  out=$L/gemma4-26b-a4b__$f
  [ -s $out ] || { log "download $f"; curl -sSL --fail -o $out.part $HF/$f && mv $out.part $out || { log "download $f FAILED"; exit 1; }; }
done
$L/llama-b11574/llama-server -m $L/gemma4-26b-a4b__gemma-4-26B-A4B-it-UD-IQ2_M.gguf --mmproj $L/gemma4-26b-a4b__mmproj-F16.gguf \
  -c 16384 -np 1 -ngl 99 --cpu-moe -ub 512 --no-mmproj-offload -fa on -ctk q8_0 -ctv q8_0 --jinja --host 127.0.0.1 --port 8082 \
  > runs/local_vlm/server_gemma.log 2>&1 &
SP=$!
for i in {1..120}; do curl -s --max-time 2 http://127.0.0.1:8082/health | grep -q ok && break; sleep 5; done
curl -s --max-time 2 http://127.0.0.1:8082/health | grep -q ok || { log "gemma server did not come up (server_gemma.log)"; kill $SP; exit 1; }
log "server up; Gemma 4 26B-A4B, thinking off, on dd1155, ia_1, osha_301"
PETEY_LOCAL_LLM_URL=http://127.0.0.1:8082/v1 venv/bin/python eval/local_vlm/classify_run.py local-gemma4-26b-a4b-iq2m-f16vision-nothink >> runs/local_vlm/progress.log 2>&1
kill $SP
log "DONE gemma"
