#!/bin/bash
docker run -d --name vllm-gemma4 \
  --gpus '"device=0"' \
  -p 8002:8000 \
  -v gemma4-models:/models:rw \
  -v /run/desktop/mnt/host/c/vllm-gemma4/triton-cache:/root/.cache/triton:rw \
  -e NCCL_ALGO=Ring \
  -e NCCL_DEBUG=WARN \
  -e NCCL_P2P_DISABLE=1 \
  -e NCCL_SHM_DISABLE=0 \
  -e TRITON_CACHE_DIR=/root/.cache/triton \
  vllm/vllm-openai:latest \
  --model /models/gemma-4-e4b-it \
  --quantization bitsandbytes \
  --load-format bitsandbytes \
  --dtype float16 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.90 \
  --host 0.0.0.0 \
  --port 8000 \
  --served-model-name gemma4-e4b \
  --attention-backend triton_attn \
  --limit-mm-per-prompt '{"image": 999, "video": 999, "audio": 999}' \
  --enable-auto-tool-choice \
  --tool-call-parser hermes
