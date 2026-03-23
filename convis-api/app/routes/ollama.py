import logging
from fastapi import APIRouter, HTTPException

from app.utils.ollama_utils import list_ollama_models, resolve_ollama_model

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/models")
async def get_ollama_models():
    """Fetch locally available Ollama models."""
    models = await list_ollama_models()

    if models is None:
        raise HTTPException(
            status_code=503,
            detail="Ollama is not running. Start it with: ollama serve"
        )

    result = []
    for m in models:
        name = m["name"]
        param_size = m.get("parameter_size", "")
        size_gb = m.get("size_gb", 0)

        label = name
        if param_size:
            label = f"{name} ({param_size})"
        if size_gb:
            label += f" - {size_gb}GB"

        result.append({
            "value": name,
            "label": label,
            "family": m.get("family", ""),
            "parameter_size": param_size,
            "size_gb": size_gb,
        })

    return {"success": True, "models": result}


@router.get("/models/validate")
async def validate_ollama_model(model: str):
    """
    Validate and resolve an Ollama model name.
    Returns the resolved model name that actually exists locally.
    Useful for checking before starting a call.
    """
    resolved = await resolve_ollama_model(model)
    models = await list_ollama_models()
    available_names = [m["name"] for m in models]
    found = resolved in available_names

    return {
        "requested": model,
        "resolved": resolved,
        "found": found,
        "available_models": available_names,
    }
