"""LLM generation parameter handling.

This module centralizes:
- UI metadata for editable generation parameters
- Config normalization (backward-compatible)
- Provider/model specific request mapping (Gemini/OpenAI)

Note: For "use default" behavior, parameters are omitted from the request payload.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union
import json


@dataclass(frozen=True)
class GenerationParamSpec:
    key: str
    label: str
    description: str
    value_type: str  # "float" | "int" | "str_list"
    default_value: Any
    min_value: Optional[float] = None
    max_value: Optional[float] = None


GENERATION_PARAM_SPECS: List[GenerationParamSpec] = [
    GenerationParamSpec(
        key="temperature",
        label="Temperature",
        description="出力のランダム性（高いほど多様）",
        value_type="float",
        default_value=0.7,
        min_value=0.0,
        max_value=2.0,
    ),
    GenerationParamSpec(
        key="top_p",
        label="Top-P",
        description="確率質量によるサンプリング（nucleus sampling）",
        value_type="float",
        default_value=0.95,
        min_value=0.0,
        max_value=1.0,
    ),
    GenerationParamSpec(
        key="top_k",
        label="Top-K",
        description="上位K候補からサンプリング（主にGeminiで利用）",
        value_type="int",
        default_value=40,
        min_value=1,
        max_value=1000,
    ),
    GenerationParamSpec(
        key="max_output_tokens",
        label="Max Output Tokens",
        description="生成する最大トークン数（OpenAIではmax_tokens/max_completion_tokensへ変換）",
        value_type="int",
        default_value=1000,
        min_value=1,
        max_value=100000,
    ),
    GenerationParamSpec(
        key="stop_sequences",
        label="Stop Sequences",
        description="生成停止文字列（複数指定可）",
        value_type="str_list",
        default_value=[],
    ),
    GenerationParamSpec(
        key="candidate_count",
        label="Candidate Count",
        description="候補生成数（OpenAIではn、GeminiではcandidateCount）",
        value_type="int",
        default_value=1,
        min_value=1,
        max_value=20,
    ),
    GenerationParamSpec(
        key="presence_penalty",
        label="Presence Penalty",
        description="既出トークンの再出現を抑制（OpenAI向け）",
        value_type="float",
        default_value=0.0,
        min_value=-2.0,
        max_value=2.0,
    ),
    GenerationParamSpec(
        key="frequency_penalty",
        label="Frequency Penalty",
        description="頻出トークンの繰り返しを抑制（OpenAI向け）",
        value_type="float",
        default_value=0.0,
        min_value=-2.0,
        max_value=2.0,
    ),
]


def _spec_by_key() -> Dict[str, GenerationParamSpec]:
    return {spec.key: spec for spec in GENERATION_PARAM_SPECS}


def default_generation_params_config() -> Dict[str, Dict[str, Any]]:
    """Return the default config structure for generation params.

    Format:
    {
      "temperature": {"use_custom": True/False, "value": ...},
      ...
    }
    """
    return {spec.key: {"use_custom": False, "value": spec.default_value} for spec in GENERATION_PARAM_SPECS}


def normalize_ai_config_inplace(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize AI config in-place (backward compatible).

    - Ensures `generation_params` exists.
    - If legacy `temperature`/`max_tokens` are present and `generation_params` is missing,
      carry them into `generation_params` with use_custom=True (to preserve behavior).
    - Keeps legacy keys as-is for compatibility with older code.
    """
    if not isinstance(config, dict):
        return config

    if "generation_params" not in config or not isinstance(config.get("generation_params"), dict):
        gen = default_generation_params_config()

        # Preserve old behavior if legacy values exist.
        if "temperature" in config:
            gen["temperature"]["value"] = config.get("temperature")
            gen["temperature"]["use_custom"] = True
        if "max_tokens" in config:
            gen["max_output_tokens"]["value"] = config.get("max_tokens")
            gen["max_output_tokens"]["use_custom"] = True

        config["generation_params"] = gen

    # Fill missing keys with defaults.
    specs = _spec_by_key()
    gen_params = config.get("generation_params", {})
    for key, spec in specs.items():
        if key not in gen_params or not isinstance(gen_params.get(key), dict):
            gen_params[key] = {"use_custom": False, "value": spec.default_value}
        else:
            gen_params[key].setdefault("use_custom", False)
            gen_params[key].setdefault("value", spec.default_value)
    config["generation_params"] = gen_params

    return config


def parse_stop_sequences(raw: Any) -> List[str]:
    if raw is None:
        return []

    if isinstance(raw, list):
        return [str(x) for x in raw if str(x).strip()]

    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        # Accept JSON array string.
        if text.startswith("["):
            try:
                value = json.loads(text)
                if isinstance(value, list):
                    return [str(x) for x in value if str(x).strip()]
            except Exception:
                pass
        # Fallback: split by comma/newline.
        parts: List[str] = []
        for chunk in text.replace("\n", ",").split(","):
            v = chunk.strip()
            if v:
                parts.append(v)
        return parts

    return [str(raw)]


def selected_generation_params(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return only custom-selected generation params (key -> value)."""
    normalize_ai_config_inplace(config)

    result: Dict[str, Any] = {}
    gen_params = config.get("generation_params", {})
    for spec in GENERATION_PARAM_SPECS:
        entry = gen_params.get(spec.key, {})
        if not entry.get("use_custom", False):
            continue
        value = entry.get("value")
        if spec.value_type == "str_list":
            value = parse_stop_sequences(value)
            if not value:
                continue
        result[spec.key] = value

    return result


def _openai_supports_generation_params(model: str) -> bool:
    # Existing behavior in this repo: GPT-5系は追加パラメータなしが安全。
    return not model.startswith("gpt-5")


def build_openai_chat_completions_payload(
    *,
    prompt: str,
    model: str,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """Build OpenAI /chat/completions payload with safe parameter mapping."""
    payload: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }

    if not _openai_supports_generation_params(model):
        return payload

    params = selected_generation_params(config)

    # max_output_tokens mapping depends on model family.
    if "max_output_tokens" in params:
        max_out = int(params["max_output_tokens"])
        if model.startswith("gpt-4.1"):
            payload["max_completion_tokens"] = max_out
        else:
            payload["max_tokens"] = max_out

    if "temperature" in params:
        payload["temperature"] = float(params["temperature"])

    if "top_p" in params:
        payload["top_p"] = float(params["top_p"])

    # top_k: not supported by OpenAI chat completions -> ignore.

    if "stop_sequences" in params:
        stops = parse_stop_sequences(params["stop_sequences"])
        if stops:
            payload["stop"] = stops

    if "candidate_count" in params:
        payload["n"] = int(params["candidate_count"])

    if "presence_penalty" in params:
        payload["presence_penalty"] = float(params["presence_penalty"])

    if "frequency_penalty" in params:
        payload["frequency_penalty"] = float(params["frequency_penalty"])

    return payload


# Gemini generationConfig keys (camelCase)
_GEMINI_CONFIG_MAP: Dict[str, str] = {
    "temperature": "temperature",
    "top_p": "topP",
    "top_k": "topK",
    "max_output_tokens": "maxOutputTokens",
    "stop_sequences": "stopSequences",
    "candidate_count": "candidateCount",
    # Penalties are treated as optional/experimental. If the API rejects them, caller may drop and retry.
    "presence_penalty": "presencePenalty",
    "frequency_penalty": "frequencyPenalty",
}

# Fields that may not be supported across all Gemini models/endpoints.
_GEMINI_EXPERIMENTAL_FIELDS = {"presence_penalty", "frequency_penalty"}


def build_gemini_generate_content_body(
    *,
    prompt: str,
    model: str,  # unused but kept for future per-model handling
    config: Dict[str, Any],
    drop_experimental: bool = False,
) -> Dict[str, Any]:
    """Build Gemini :generateContent body.

    - Puts generation parameters under generationConfig.
    - Omits params when 'use default' is selected.
    - If drop_experimental=True, removes experimental fields to avoid API errors.
    """
    params = selected_generation_params(config)
    generation_config: Dict[str, Any] = {}

    for key, value in params.items():
        if key in _GEMINI_EXPERIMENTAL_FIELDS and drop_experimental:
            continue

        mapped = _GEMINI_CONFIG_MAP.get(key)
        if not mapped:
            continue

        if key == "stop_sequences":
            value = parse_stop_sequences(value)
            if not value:
                continue

        generation_config[mapped] = value

    body: Dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
    }

    if generation_config:
        body["generationConfig"] = generation_config

    return body
