#!/bin/zsh
# The reader test (eval/local_vlm/reader_test.py) with Underdog-Saluki-27B on llama.cpp b11574 (text only, thinking off).
cd /Users/user/Documents/code/petey-2
export PYTHONPATH=.
L=models/llm
mkdir -p runs/local_vlm/reader
$L/llama-b11574/llama-server -m $L/Underdog-Saluki-27B-1.0-IQ2-mix.gguf -c 32768 -np 1 -ngl 99 -fa on -ctk q8_0 -ctv q8_0 \
  --jinja --host 127.0.0.1 --port 8081 > runs/local_vlm/reader/server_underdog.log 2>&1 &
SP=$!
for i in {1..120}; do curl -s --max-time 2 http://127.0.0.1:8081/health | grep -q ok && break; sleep 5; done
PETEY_LOCAL_LLM_URL=http://127.0.0.1:8081/v1 venv/bin/python eval/local_vlm/reader_test.py local-underdog-iq2-nothink 2>&1 \
  | grep -v '^warning' | tee -a runs/local_vlm/reader/run.log
kill $SP
