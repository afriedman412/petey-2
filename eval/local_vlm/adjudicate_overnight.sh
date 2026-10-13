#!/bin/zsh
# The adjudicator test (eval/local_vlm/adjudicate_test.py) on three local models in turn, after Sonnet's baseline:
# Granite Vision 4.1 4B, MiniCPM-V 4.5, Underdog-Saluki-27B. Each model: download if missing, start llama-server,
# answer the cases (stopping after the first form under 75%), stop the server. Summary at the end:
# runs/local_vlm/adjudicate/summary.txt. Progress: runs/local_vlm/adjudicate/overnight.log.
cd /Users/user/Documents/code/petey-2
export PYTHONPATH=.
L=models/llm
LOG=runs/local_vlm/adjudicate/overnight.log
mkdir -p runs/local_vlm/adjudicate
log() { echo "$(date '+%H:%M:%S') $*" | tee -a $LOG; }
get() {   # repo file local_name
  [ -s $L/$3 ] || { log "download $2"; curl -sSL --fail -o $L/$3.part https://huggingface.co/$1/resolve/main/$2 && mv $L/$3.part $L/$3 || { log "download $2 FAILED"; return 1; }; }
}
serve_and_test() {   # label port model mmproj extra-flags...
  local label=$1 port=$2 model=$3 mmproj=$4; shift 4
  $L/llama-b11574/llama-server -m $L/$model --mmproj $L/$mmproj -c 16384 -np 1 -ngl 99 -fa on --jinja \
    --host 127.0.0.1 --port $port "$@" > runs/local_vlm/adjudicate/server_$label.log 2>&1 &
  local sp=$!
  for i in {1..120}; do curl -s --max-time 2 http://127.0.0.1:$port/health | grep -q ok && break; sleep 5; done
  if curl -s --max-time 2 http://127.0.0.1:$port/health | grep -q ok; then
    log "start $label"
    PETEY_LOCAL_LLM_URL=http://127.0.0.1:$port/v1 venv/bin/python eval/local_vlm/adjudicate_test.py $label 2>&1 \
      | grep -v '^warning' | tee -a $LOG
  else
    log "$label: server did not come up (server_$label.log)"
  fi
  kill $sp; sleep 3
}

while pgrep -f "adjudicate_test.py claude-sonnet-4-6" > /dev/null; do sleep 20; done
log "Sonnet baseline finished"

get ibm-granite/granite-vision-4.1-4b-GGUF granite-vision-4.1-4b-Q8_0.gguf granite-vision-4.1-4b__granite-vision-4.1-4b-Q8_0.gguf \
  && get ibm-granite/granite-vision-4.1-4b-GGUF mmproj-model-f16.gguf granite-vision-4.1-4b__mmproj-model-f16.gguf \
  && serve_and_test local-granite-vision-4.1-4b-q8 8083 granite-vision-4.1-4b__granite-vision-4.1-4b-Q8_0.gguf granite-vision-4.1-4b__mmproj-model-f16.gguf

get openbmb/MiniCPM-V-4_5-gguf MiniCPM-V-4_5-Q6_K.gguf minicpm-v-4.5__MiniCPM-V-4_5-Q6_K.gguf \
  && get openbmb/MiniCPM-V-4_5-gguf mmproj-model-f16.gguf minicpm-v-4.5__mmproj-model-f16.gguf \
  && serve_and_test local-minicpm-v-4.5-q6k-nothink 8084 minicpm-v-4.5__MiniCPM-V-4_5-Q6_K.gguf minicpm-v-4.5__mmproj-model-f16.gguf

serve_and_test local-underdog-iq2-q8vision-nothink 8081 Underdog-Saluki-27B-1.0-IQ2-mix.gguf mmproj-Underdog-Saluki-27B-1.0-Q8_0.gguf \
  -ctk q8_0 -ctv q8_0

venv/bin/python - > runs/local_vlm/adjudicate/summary.txt <<'EOF'
import json, collections, glob, os
print("adjudicator test: share of cases answered right (each form half 'current', half 'proposed': 50% = always one answer)\n")
for path in sorted(glob.glob("runs/local_vlm/adjudicate/*.jsonl")):
    rows = [json.loads(l) for l in open(path)]
    by = collections.defaultdict(list)
    for r in rows: by[r["bid"]].append(r)
    model = os.path.basename(path)[:-6]
    for bid, rs in by.items():
        secs = sorted(r["seconds"] for r in rs)
        k = collections.Counter((r["kind"], r["right"]) for r in rs)
        kinds = {x: f"{k[(x, True)]}/{k[(x, True)] + k[(x, False)]}" for x in ("slip_keep", "slip_fix", "real") if k[(x, True)] + k[(x, False)]}
        print(f"{model:40} {bid:24} {sum(r['right'] for r in rs) / len(rs):5.0%} of {len(rs):3}  {kinds}  unclear {sum(r['verdict'] == 'unclear' for r in rs)}  errors {sum(bool(r['error']) for r in rs)}  median {secs[len(secs) // 2]} s")
EOF
log "DONE (summary.txt)"
