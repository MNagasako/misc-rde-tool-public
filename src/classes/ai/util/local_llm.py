"""Helpers for local LLM provider configuration and endpoint resolution."""

from __future__ import annotations

from functools import lru_cache
import ipaddress
import socket
from typing import Any, Dict, List
from urllib.parse import urlsplit


LOCAL_LLM_PROVIDER_OLLAMA = "ollama"
LOCAL_LLM_PROVIDER_LM_STUDIO = "lm_studio"

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/api/generate"
DEFAULT_LM_STUDIO_BASE_URL = "http://localhost:1234/v1"


@lru_cache(maxsize=64)
def _resolve_host_to_ipv4(host: str) -> str:
    normalized = str(host or "").strip()
    if not normalized:
        return normalized
    try:
        ipaddress.ip_address(normalized)
        return normalized
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(normalized, None, socket.AF_INET, socket.SOCK_STREAM)
    except Exception:
        return normalized

    for info in infos:
        sockaddr = info[4] if len(info) > 4 else None
        if isinstance(sockaddr, tuple) and sockaddr:
            candidate = str(sockaddr[0] or "").strip()
            if candidate:
                return candidate
    return normalized


def _compose_endpoint_url(endpoint: Dict[str, Any], provider_type: str | None = None, *, resolve_host: bool = False) -> str:
    materialized = dict(endpoint or {})
    if resolve_host:
        host = str(materialized.get("host") or "").strip()
        if host:
            materialized["host"] = _resolve_host_to_ipv4(host)
    return compose_local_llm_base_url(materialized, provider_type)


def default_local_llm_endpoint_parts(provider_type: str, host: str = "localhost") -> Dict[str, Any]:
    normalized_provider = provider_type if provider_type == LOCAL_LLM_PROVIDER_LM_STUDIO else LOCAL_LLM_PROVIDER_OLLAMA
    normalized_host = str(host or "localhost").strip() or "localhost"
    if normalized_provider == LOCAL_LLM_PROVIDER_LM_STUDIO:
        return {
            "protocol": "http",
            "host": normalized_host,
            "port": 1234,
            "base_path": "/v1",
        }
    return {
        "protocol": "http",
        "host": normalized_host,
        "port": 11434,
        "base_path": "/api/generate",
    }


def compose_local_llm_base_url(parts: Dict[str, Any] | None, provider_type: str | None = None) -> str:
    endpoint = dict(parts or {})
    normalized_provider = provider_type or get_local_llm_provider_type(endpoint)
    defaults = default_local_llm_endpoint_parts(normalized_provider, host=str(endpoint.get("host") or "localhost"))

    protocol_value = endpoint.get("protocol")
    host_value = endpoint.get("host")
    base_path_value = endpoint.get("base_path")

    protocol = str(protocol_value if protocol_value not in (None, "") else defaults["protocol"]).strip().lower() or defaults["protocol"]
    host = str(host_value if host_value not in (None, "") else defaults["host"]).strip() or defaults["host"]
    try:
        port = int(endpoint.get("port") or defaults["port"])
    except Exception:
        port = int(defaults["port"])

    base_path = str(base_path_value if base_path_value is not None else defaults["base_path"]).strip()
    if not base_path:
        return f"{protocol}://{host}:{port}"
    if not base_path.startswith("/"):
        base_path = "/" + base_path
    return f"{protocol}://{host}:{port}{base_path}"


def parse_local_llm_base_url(provider_config: Dict[str, Any] | None) -> Dict[str, Any]:
    config = provider_config or {}
    provider_type = get_local_llm_provider_type(config)
    host_seed = str(config.get("host") or "localhost").strip() or "localhost"
    parts = default_local_llm_endpoint_parts(provider_type, host=host_seed)

    raw_url = str(config.get("base_url") or "").strip()
    protocol = str(config.get("protocol") or "").strip().lower()
    host = str(config.get("host") or "").strip()
    base_path = str(config.get("base_path") or "").strip()
    port_value = config.get("port")

    if raw_url:
        candidate = raw_url if "://" in raw_url else f"{parts['protocol']}://{raw_url}"
        parsed = urlsplit(candidate)
        if parsed.scheme:
            parts["protocol"] = parsed.scheme.lower()
        if parsed.hostname:
            parts["host"] = parsed.hostname
        if parsed.port:
            parts["port"] = parsed.port
        parsed_path = str(parsed.path or "").strip()
        if parsed_path:
            parts["base_path"] = parsed_path if parsed_path.startswith("/") else f"/{parsed_path}"
        elif not any(config.get(key) not in (None, "") for key in ("protocol", "host", "port", "base_path")):
            # 後方互換: host-only / host:port は OpenAI互換ベースURLとして扱う
            parts["base_path"] = ""

    if protocol:
        parts["protocol"] = protocol
    if host:
        parts["host"] = host
    if base_path:
        parts["base_path"] = base_path if base_path.startswith("/") else f"/{base_path}"
    try:
        if port_value not in (None, ""):
            parts["port"] = int(port_value)
    except Exception:
        pass

    parts["provider_type"] = provider_type
    parts["base_url"] = compose_local_llm_base_url(parts, provider_type)
    return parts


def get_local_llm_provider_type(provider_config: Dict[str, Any] | None) -> str:
    raw = ""
    if isinstance(provider_config, dict):
        raw = str(provider_config.get("provider_type") or provider_config.get("provider") or "").strip().lower()
    if raw == LOCAL_LLM_PROVIDER_LM_STUDIO:
        return LOCAL_LLM_PROVIDER_LM_STUDIO
    return LOCAL_LLM_PROVIDER_OLLAMA


def get_local_llm_provider_label(provider_config: Dict[str, Any] | None) -> str:
    provider_type = get_local_llm_provider_type(provider_config)
    if provider_type == LOCAL_LLM_PROVIDER_LM_STUDIO:
        return "LM Studio"
    return "Ollama"


def get_local_llm_host(provider_config: Dict[str, Any] | None) -> str:
    endpoint = parse_local_llm_base_url(provider_config)
    return str(endpoint.get("host") or "localhost").strip() or "localhost"


def get_local_llm_provider_entries(provider_config: Dict[str, Any] | None) -> List[Dict[str, str]]:
    host = get_local_llm_host(provider_config)
    return [
        {
            "id": LOCAL_LLM_PROVIDER_OLLAMA,
            "display_name": f"Ollama ({host})",
            "host": host,
            "provider_type": LOCAL_LLM_PROVIDER_OLLAMA,
        },
        {
            "id": LOCAL_LLM_PROVIDER_LM_STUDIO,
            "display_name": f"LM Studio ({host})",
            "host": host,
            "provider_type": LOCAL_LLM_PROVIDER_LM_STUDIO,
        },
    ]


def get_local_llm_api_key(provider_config: Dict[str, Any] | None) -> str:
    if not isinstance(provider_config, dict):
        return ""
    return str(provider_config.get("api_key") or "").strip()


def get_local_llm_base_url(provider_config: Dict[str, Any] | None) -> str:
    provider_type = get_local_llm_provider_type(provider_config)
    default_url = DEFAULT_LM_STUDIO_BASE_URL if provider_type == LOCAL_LLM_PROVIDER_LM_STUDIO else DEFAULT_OLLAMA_BASE_URL
    if not isinstance(provider_config, dict):
        return default_url
    endpoint = parse_local_llm_base_url(provider_config)
    raw = str(endpoint.get("base_url") or "").strip()
    return raw or default_url


def get_local_llm_request_base_url(provider_config: Dict[str, Any] | None) -> str:
    provider_type = get_local_llm_provider_type(provider_config)
    default_url = DEFAULT_LM_STUDIO_BASE_URL if provider_type == LOCAL_LLM_PROVIDER_LM_STUDIO else DEFAULT_OLLAMA_BASE_URL
    if not isinstance(provider_config, dict):
        return default_url
    endpoint = parse_local_llm_base_url(provider_config)
    return _compose_endpoint_url(endpoint, provider_type, resolve_host=True) or default_url


def uses_ollama_native_generate(provider_config: Dict[str, Any] | None) -> bool:
    provider_type = get_local_llm_provider_type(provider_config)
    if provider_type != LOCAL_LLM_PROVIDER_OLLAMA:
        return False
    base_url = get_local_llm_base_url(provider_config).lower()
    return "/api/generate" in base_url


def _strip_known_suffix(url: str) -> str:
    normalized = (url or "").strip().rstrip("/")
    suffixes = (
        "/api/generate",
        "/api/tags",
        "/v1/chat/completions",
        "/v1/responses",
        "/v1/models",
        "/chat/completions",
        "/responses",
        "/models",
    )
    lower = normalized.lower()
    for suffix in suffixes:
        if lower.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def get_local_llm_server_root(provider_config: Dict[str, Any] | None) -> str:
    base_url = get_local_llm_request_base_url(provider_config)
    root = _strip_known_suffix(base_url)
    if uses_ollama_native_generate(provider_config):
        return root or "http://localhost:11434"
    provider_type = get_local_llm_provider_type(provider_config)
    if provider_type == LOCAL_LLM_PROVIDER_LM_STUDIO:
        return root or "http://localhost:1234"
    return root or "http://localhost:11434"


def get_local_llm_openai_base(provider_config: Dict[str, Any] | None) -> str:
    base_url = get_local_llm_request_base_url(provider_config)
    stripped = _strip_known_suffix(base_url)
    if not stripped:
        stripped = DEFAULT_LM_STUDIO_BASE_URL if get_local_llm_provider_type(provider_config) == LOCAL_LLM_PROVIDER_LM_STUDIO else "http://localhost:11434/v1"
    if not stripped.rstrip("/").lower().endswith("/v1"):
        stripped = stripped.rstrip("/") + "/v1"
    return stripped.rstrip("/")


def get_local_llm_chat_url(provider_config: Dict[str, Any] | None) -> str:
    if uses_ollama_native_generate(provider_config):
        base_url = get_local_llm_request_base_url(provider_config)
        if "/api/generate" in base_url.lower():
            return base_url
        return get_local_llm_server_root(provider_config).rstrip("/") + "/api/generate"
    return get_local_llm_openai_base(provider_config) + "/chat/completions"


def get_local_llm_models_url(provider_config: Dict[str, Any] | None) -> str:
    if get_local_llm_provider_type(provider_config) == LOCAL_LLM_PROVIDER_LM_STUDIO:
        return get_local_llm_openai_base(provider_config) + "/models"
    return get_local_llm_server_root(provider_config).rstrip("/") + "/api/tags"


def build_local_llm_headers(provider_config: Dict[str, Any] | None) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    api_key = get_local_llm_api_key(provider_config)
    if api_key and not uses_ollama_native_generate(provider_config):
        headers["Authorization"] = f"Bearer {api_key}"
    return headers