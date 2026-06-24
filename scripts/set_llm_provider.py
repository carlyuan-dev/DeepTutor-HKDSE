#!/usr/bin/env python3
"""Switch the active LLM provider in data/user/settings/model_catalog.json.

Makes it trivial to flip between local on-premise inference engines (Apple MLX,
Ollama, LM Studio, llama.cpp, vLLM) and cloud providers — supporting the
project's "100% offline on Apple Silicon" goal.

Examples
--------
    # Apple MLX via `mlx_lm.server --model <repo> --port 8081`
    python3 scripts/set_llm_provider.py mlx --model mlx-community/Qwen2.5-7B-Instruct-4bit

    # Ollama (running `ollama serve`)
    python3 scripts/set_llm_provider.py ollama --model qwen2.5:7b

    # LM Studio (local server on :1234)
    python3 scripts/set_llm_provider.py lm_studio --model qwen2.5-7b-instruct

    # Custom OpenAI-compatible endpoint
    python3 scripts/set_llm_provider.py custom --model my-model \
        --base-url http://localhost:9000/v1 --api-key sk-xxx

    # Show the current active provider
    python3 scripts/set_llm_provider.py --show

After switching, restart the backend (or POST /api/v1/settings/apply) to reload.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "data" / "user" / "settings" / "model_catalog.json"

# Sensible defaults per local provider (OpenAI-compatible endpoints).
LOCAL_DEFAULTS: dict[str, dict[str, str]] = {
    "mlx": {"base_url": "http://localhost:8081/v1", "display": "Apple MLX (Local)"},
    "ollama": {"base_url": "http://localhost:11434/v1", "display": "Ollama"},
    "lm_studio": {"base_url": "http://localhost:1234/v1", "display": "LM Studio"},
    "llama_cpp": {"base_url": "http://localhost:8080/v1", "display": "llama.cpp"},
    "vllm": {"base_url": "http://localhost:8000/v1", "display": "vLLM/Local"},
}


def _load() -> dict:
    if not CATALOG_PATH.exists():
        print(f"error: catalog not found at {CATALOG_PATH}", file=sys.stderr)
        sys.exit(1)
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _show(catalog: dict) -> None:
    llm = catalog.get("services", {}).get("llm", {})
    active = llm.get("active_profile_id")
    for p in llm.get("profiles", []):
        marker = "→" if p.get("id") == active else " "
        models = ", ".join(m.get("model", "") for m in p.get("models", []))
        print(f" {marker} {p.get('name')}  [binding={p.get('binding')}]  {p.get('base_url')}  models: {models}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Switch the active LLM provider.")
    parser.add_argument("binding", nargs="?", help="provider binding (mlx | ollama | lm_studio | llama_cpp | vllm | deepseek | openai | custom | ...)")
    parser.add_argument("--model", help="model name to use")
    parser.add_argument("--base-url", help="override base URL (OpenAI-compatible /v1 endpoint)")
    parser.add_argument("--api-key", default="local-no-key", help="API key (local servers usually ignore this)")
    parser.add_argument("--show", action="store_true", help="show current providers and exit")
    args = parser.parse_args()

    catalog = _load()
    catalog.setdefault("services", {}).setdefault("llm", {}).setdefault("profiles", [])
    llm = catalog["services"]["llm"]

    if args.show or not args.binding:
        _show(catalog)
        return

    if not args.model:
        print("error: --model is required when switching provider", file=sys.stderr)
        sys.exit(1)

    binding = args.binding.strip().lower()
    defaults = LOCAL_DEFAULTS.get(binding, {})
    base_url = args.base_url or defaults.get("base_url", "")
    display = defaults.get("display", binding.title())

    profile_id = f"llm-profile-{binding}"
    model_id = f"llm-model-{binding}"
    new_profile = {
        "id": profile_id,
        "name": display,
        "binding": binding,
        "base_url": base_url,
        "api_key": args.api_key,
        "api_version": "",
        "extra_headers": {},
        "models": [{"id": model_id, "name": args.model, "model": args.model}],
    }

    # Replace any existing profile with the same id, else append.
    profiles = [p for p in llm["profiles"] if p.get("id") != profile_id]
    profiles.append(new_profile)
    llm["profiles"] = profiles
    llm["active_profile_id"] = profile_id
    llm["active_model_id"] = model_id

    CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ Active LLM provider → {display} ({binding}), model={args.model}, base_url={base_url or '(provider default)'}")
    print("  Restart the backend (or POST /api/v1/settings/apply) to apply.")


if __name__ == "__main__":
    main()
