#!/bin/zsh
# MiniCPM-V 4.5 (OpenBMB Q6_K + f16 vision add-on, llama.cpp b11574) classifies the three new single-page forms.
cd /Users/user/Documents/code/petey-2
export PYTHONPATH=.
L=models/llm
HF=https://huggingface.co/openbmb/MiniCPM-V-4_5-gguf/resolve/main
log() { echo "$(date '+%H:%M:%S') $*" | tee -a runs/local_vlm/progress.log; }
for f in MiniCPM-V-4_5-Q6_K.gguf mmproj-model-f16.gguf; do
  out=$L/minicpm-v-4.5__$f
  [ -s $out ] || { log "download $f"; curl -sSL --fail -o $out.part $HF/$f && mv $out.part $out || { log "download $f FAILED"; exit 1; }; }
done
while pgrep -f "before_copies_jev_2026-10-13|granite_three.sh" > /dev/null; do sleep 20; done
$L/llama-b11574/llama-server -m $L/minicpm-v-4.5__MiniCPM-V-4_5-Q6_K.gguf --mmproj $L/minicpm-v-4.5__mmproj-model-f16.gguf \
  -c 16384 -np 1 -ngl 99 -fa on --jinja --host 127.0.0.1 --port 8084 > runs/local_vlm/server_minicpm.log 2>&1 &
SP=$!
for i in {1..120}; do curl -s --max-time 2 http://127.0.0.1:8084/health | grep -q ok && break; sleep 5; done
curl -s --max-time 2 http://127.0.0.1:8084/health | grep -q ok || { log "minicpm server did not come up (server_minicpm.log)"; kill $SP; exit 1; }
log "server up; MiniCPM-V 4.5 on dd1155, ia_1, osha_301"
PETEY_LOCAL_LLM_URL=http://127.0.0.1:8084/v1 venv/bin/python eval/local_vlm/classify_run.py local-minicpm-v-4.5-q6k-nothink >> runs/local_vlm/progress.log 2>&1
kill $SP
log "DONE minicpm"
