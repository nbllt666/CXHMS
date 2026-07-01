# vLLM 启动脚本 (单卡 + FP8 W8A8 量化 + 128K 上下文)
# RTX 3080 (Ampere sm_86) 无原生 FP8 硬件，vLLM 使用 Marlin kernel 做 weight-only FP8
# 双卡无 P2P 且 PCIe 速率低，单卡避免 inter-GPU 通信开销
# 模型原生支持 131072 (128K) 上下文，KV cache ~1.8GB（sliding window 优化），20GB 显存充足
docker run -d --name vllm-gemma4 --gpus "device=0" -p 8002:8000 -v gemma4-models:/models:rw -e NCCL_ALGO=Ring -e NCCL_DEBUG=WARN -e NCCL_P2P_DISABLE=1 -e NCCL_SHM_DISABLE=0 -e TRITON_CACHE_DIR=/root/.cache/triton vllm/vllm-openai:latest --model /models/gemma-4-e4b-it --quantization fp8 --load-format auto --dtype float16 --max-model-len 131072 --gpu-memory-utilization 0.90 --tensor-parallel-size 1 --max-num-seqs 8 --host 0.0.0.0 --port 8000 --served-model-name gemma4-e4b --attention-backend triton_attn --enable-auto-tool-choice --tool-call-parser gemma4 --reasoning-parser gemma4
