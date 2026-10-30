#!/bin/zsh
# Granite Vision 4.1 4B (IBM Q8_0 + f16 vision add-on, llama.cpp b11574) classifies the three new single-page forms.
cd /Users/user/Documents/code/petey-2
export PYTHONPATH=.
L=models/llm
HF=https://huggingface.co/ibm-granite/granite-vision-4.1-4b-GGUF/resolve/main
log() { echo "$(date '+%H:%M:%S') $*" | tee -a runs/local_vlm/progress.log; }
for f in granite-vision-4.1-4b-Q8_0.gguf mmproj-model-f16.gguf; do
  out=$L/granite-vision-4.1-4b__$f
  [ -s $out ] || { log "download $f"; curl -sSL --fail -o $out.part $HF/$f && mv $out.part $out || { log "download $f FAILED"; exit 1; }; }
done
while pgrep -f before_copies_jev_2026-10-13 > /dev/null; do sleep 20; done
$L/llama-b11574/llama-server -m $L/granite-vision-4.1-4b__granite-vision-4.1-4b-Q8_0.gguf --mmproj $L/granite-vision-4.1-4b__mmproj-model-f16.gguf \
  -c 16384 -np 1 -ngl 99 -fa on --jinja --host 127.0.0.1 --port 8083 > runs/local_vlm/server_granite.log 2>&1 &
SP=$!
for i in {1..120}; do curl -s --max-time 2 http://127.0.0.1:8083/health | grep -q ok && break; sleep 5; done
curl -s --max-time 2 http://127.0.0.1:8083/health | grep -q ok || { log "granite server did not come up (server_granite.log)"; kill $SP; exit 1; }
log "server up; Granite Vision 4.1 4B on dd1155, ia_1, osha_301"
PETEY_LOCAL_LLM_URL=http://127.0.0.1:8083/v1 venv/bin/python eval/local_vlm/classify_run.py local-granite-vision-4.1-4b-q8 >> runs/local_vlm/progress.log 2>&1
kill $SP
log "DONE granite"
