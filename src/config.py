"""
Config — centralized configuration with env overrides.

All pipeline parameters are configurable via environment variables.

LLM selection:
    HWB_MODEL=claude-opus-4-6   (default) → Claude via ANTHROPIC_API_KEY
    HWB_MODEL=deepseek-chat               → DeepSeek via DEEPSEEK_API_KEY
    HWB_MODEL=deepseek-reasoner           → DeepSeek reasoning via DEEPSEEK_API_KEY
"""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineConfig:
    """Immutable pipeline configuration. Env vars override defaults."""

    # Model
    model: str = os.getenv("HWB_MODEL", "claude-opus-4-6")
    max_tokens_requirements: int = int(os.getenv("HWB_TOKENS_REQ", "2000"))
    max_tokens_parts: int = int(os.getenv("HWB_TOKENS_PARTS", "8192"))
    max_tokens_pcb: int = int(os.getenv("HWB_TOKENS_PCB", "8192"))
    max_tokens_cad: int = int(os.getenv("HWB_TOKENS_CAD", "5000"))
    max_tokens_assembly: int = int(os.getenv("HWB_TOKENS_ASM", "8192"))

    # Retry
    max_retries: int = int(os.getenv("HWB_MAX_RETRIES", "3"))
    retry_base_ms: int = int(os.getenv("HWB_RETRY_BASE_MS", "1000"))

    # Cache
    cache_dir: str = os.getenv("HWB_CACHE_DIR", "/tmp/hwb_cache")
    cache_ttl_s: int = int(os.getenv("HWB_CACHE_TTL", "3600"))

    # Search
    fts_max_candidates: int = int(os.getenv("HWB_FTS_MAX", "2000"))
    bom_max_parts: int = int(os.getenv("HWB_BOM_MAX", "50"))

    # Pricing (CNY native — parts from 立创商城)
    cny_to_usd: float = float(os.getenv("HWB_CNY_USD", "0.138"))  # ~¥7.25 per $1

    # Server
    host: str = os.getenv("HWB_HOST", "0.0.0.0")
    port: int = int(os.getenv("HWB_PORT", "8000"))

    # Output
    output_dir: str = os.getenv("HWB_OUTPUT_DIR", "output")


# Singleton
CONFIG = PipelineConfig()


def _ensure_key(env_var: str, label: str):
    if not os.environ.get(env_var):
        raise RuntimeError(
            f"No {label} API key found. Set the {env_var} environment variable."
        )


def ensure_llm_key():
    """Validate that the correct API key is present for the selected model."""
    model = CONFIG.model
    if model.startswith("deepseek"):
        _ensure_key("DEEPSEEK_API_KEY", "DeepSeek")
    else:
        _ensure_key("ANTHROPIC_API_KEY", "Anthropic")


# Auto-validate on import
ensure_llm_key()
