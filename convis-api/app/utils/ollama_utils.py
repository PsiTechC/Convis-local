"""
Ollama utility functions for model discovery and validation.
"""

import os
import logging
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)


def _get_ollama_base_url() -> str:
    """Get the Ollama base URL (native API, not OpenAI-compat /v1)."""
    url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    return url.rstrip("/").removesuffix("/v1")


async def list_ollama_models() -> List[dict]:
    """
    Fetch locally available Ollama models.
    Returns list of dicts with keys: name, family, parameter_size, size_gb.
    Returns empty list if Ollama is unreachable.
    """
    base_url = _get_ollama_base_url()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()

        models = []
        for m in data.get("models", []):
            name = m.get("name", "")
            size_bytes = m.get("size", 0)
            size_gb = round(size_bytes / (1024 ** 3), 1)
            param_size = m.get("details", {}).get("parameter_size", "")
            family = m.get("details", {}).get("family", "")

            models.append({
                "name": name,
                "family": family,
                "parameter_size": param_size,
                "size_gb": size_gb,
            })

        return models

    except httpx.ConnectError:
        logger.warning("[OLLAMA] Cannot connect to Ollama — is it running?")
        return []
    except Exception as e:
        logger.error(f"[OLLAMA] Failed to list models: {e}")
        return []


async def resolve_ollama_model(requested_model: str) -> str:
    """
    Resolve a requested model name to an actual available Ollama model.

    Handles common mismatches:
      - 'llama3.2:3b' requested but only 'llama3.2:latest' is pulled
      - 'llama3.2' requested but 'llama3.2:latest' is the actual name
      - Exact match is always preferred

    Returns the resolved model name, or the original if Ollama is unreachable
    (let Ollama return its own error in that case).
    """
    models = await list_ollama_models()
    if not models:
        # Ollama unreachable — return as-is, let the actual call fail with a clear error
        return requested_model

    available_names = [m["name"] for m in models]

    # 1. Exact match
    if requested_model in available_names:
        return requested_model

    # 2. Try with :latest tag  (e.g. 'llama3.2' -> 'llama3.2:latest')
    if ":" not in requested_model:
        with_latest = f"{requested_model}:latest"
        if with_latest in available_names:
            logger.info(f"[OLLAMA] Resolved '{requested_model}' -> '{with_latest}'")
            return with_latest

    # 3. Try base name without tag  (e.g. 'llama3.2:3b' -> 'llama3.2:latest')
    base_name = requested_model.split(":")[0]
    for name in available_names:
        if name.split(":")[0] == base_name:
            logger.info(f"[OLLAMA] Resolved '{requested_model}' -> '{name}' (base name match)")
            return name

    # 4. No match found — log available models for debugging
    logger.warning(
        f"[OLLAMA] Model '{requested_model}' not found. "
        f"Available: {available_names}. Pull it with: ollama pull {requested_model}"
    )
    return requested_model
