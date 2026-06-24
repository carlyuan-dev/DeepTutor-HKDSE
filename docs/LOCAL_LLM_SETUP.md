# Local / On-Premise LLM Setup

DeepTutor can run **100% offline on Apple Silicon** using a local inference
engine. All three options below expose an **OpenAI-compatible** API, which the
backend talks to directly — no data leaves the machine (PDPO-friendly).

The cloud provider (DeepSeek/OpenAI/…) remains available as an option; switching
is just a config change.

## Quick switch

Use the helper script, then restart the backend:

```bash
# Apple MLX (native Apple Silicon inference)
python3 scripts/set_llm_provider.py mlx --model mlx-community/Qwen2.5-7B-Instruct-4bit

# Ollama
python3 scripts/set_llm_provider.py ollama --model qwen2.5:7b

# LM Studio
python3 scripts/set_llm_provider.py lm_studio --model qwen2.5-7b-instruct

# Back to cloud DeepSeek
python3 scripts/set_llm_provider.py deepseek --model deepseek-chat \
    --base-url https://api.deepseek.com --api-key sk-xxxxx

# Inspect the current active provider
python3 scripts/set_llm_provider.py --show
```

You can also switch from the web **Settings → Catalog** page (same underlying
`data/user/settings/model_catalog.json`).

Verify which engine is live at any time:

```bash
curl -s http://localhost:8001/api/v1/market-tools/llm-status | python3 -m json.tool
# → { "mode": "local", "is_local": true, "reachable": true, ... }
```

The Market page header shows an **Engine** badge built from this endpoint
(Local / Offline vs Cloud).

---

## Option 1 — Apple MLX (recommended on M-series Macs)

```bash
pip install mlx-lm
# Serve an OpenAI-compatible endpoint on port 8081
mlx_lm.server --model mlx-community/Qwen2.5-7B-Instruct-4bit --port 8081
```

Then: `python3 scripts/set_llm_provider.py mlx --model mlx-community/Qwen2.5-7B-Instruct-4bit`

Default endpoint: `http://localhost:8081/v1`

## Option 2 — Ollama

```bash
brew install ollama        # or download from ollama.com
ollama serve               # starts the API on :11434
ollama pull qwen2.5:7b
```

Then: `python3 scripts/set_llm_provider.py ollama --model qwen2.5:7b`

Default endpoint: `http://localhost:11434/v1`

## Option 3 — LM Studio

1. Install LM Studio (lmstudio.ai). It supports an **MLX** backend on Apple Silicon.
2. Download a model, then **Start Server** (Developer tab) → serves on `:1234`.

Then: `python3 scripts/set_llm_provider.py lm_studio --model <model-id-shown-in-lm-studio>`

Default endpoint: `http://localhost:1234/v1`

---

## Notes

- Local servers usually ignore the API key; the helper sets a placeholder.
- The provider registry (`deeptutor/services/provider_registry.py`) marks
  `mlx`, `ollama`, `lm_studio`, `llama_cpp`, `vllm` as `is_local=True`, which is
  what drives the **Local / Offline** badge.
- Embeddings (used by RAG / knowledge bases) are configured separately under
  Settings → Catalog → Embedding. For a fully-offline stack, point embeddings at
  a local model too (e.g. an Ollama embedding model).
