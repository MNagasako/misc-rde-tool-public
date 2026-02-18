"""オフラインモード管理。

アプリ全体で共通利用するオフライン状態（有効/無効、サイト単位ブロック）を管理する。
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Dict, Optional
from urllib.parse import urlparse

from classes.managers.app_config_manager import get_config_manager

logger = logging.getLogger(__name__)

OFFLINE_SITE_RDE = "rde"
OFFLINE_SITE_DATA_PORTAL = "data_portal"
OFFLINE_SITE_DATA_PORTAL_TEST = "data_portal_test"
OFFLINE_SITE_AI_API = "ai_api"

_SITE_LABELS = {
    OFFLINE_SITE_RDE: "RDE (*.nims.go.jp)",
    OFFLINE_SITE_DATA_PORTAL: "データポータル (nanonet.go.jp / *.nanonet.go.jp)",
    OFFLINE_SITE_DATA_PORTAL_TEST: "データポータル テストサイト",
    OFFLINE_SITE_AI_API: "AI API (OpenAI/Gemini/Local LLM)",
}


def get_site_label(site_key: str) -> str:
    """サイトキーに対応する表示名を返す。"""
    return _SITE_LABELS.get(site_key, site_key)


def get_blocked_site_keys(state: Optional[OfflineRuntimeState] = None) -> list[str]:
    """現在オフラインでブロック対象になっているサイトキー一覧を返す。"""
    runtime = state or get_offline_runtime_state()
    if not runtime.enabled:
        return []
    return [key for key, blocked in runtime.sites.items() if blocked]


def get_blocked_site_labels(state: Optional[OfflineRuntimeState] = None) -> list[str]:
    """現在オフラインでブロック対象になっているサイト表示名一覧を返す。"""
    keys = get_blocked_site_keys(state)
    return [get_site_label(key) for key in keys]


def build_offline_status_message(state: Optional[OfflineRuntimeState] = None) -> str:
    """メイン画面表示用のオフライン状態メッセージを返す。"""
    runtime = state or get_offline_runtime_state()
    if not runtime.enabled:
        return "🌐 オンラインモード"
    labels = get_blocked_site_labels(runtime)
    blocked_text = " / ".join(labels) if labels else "なし"
    return f"📴 オフラインモード（対象: {blocked_text}）"


@dataclass(frozen=True)
class OfflineRuntimeState:
    enabled: bool
    sites: Dict[str, bool]


class OfflineAccessBlockedError(RuntimeError):
    """オフライン設定により外部アクセスが禁止されたことを示す例外。"""

    def __init__(self, site_key: str, url: Optional[str] = None):
        self.site_key = site_key
        self.url = url or ""
        site_name = _SITE_LABELS.get(site_key, site_key)
        msg = f"オフラインモードにより外部アクセスが無効です: {site_name}"
        if self.url:
            msg = f"{msg} ({self.url})"
        super().__init__(msg)


def _default_sites() -> Dict[str, bool]:
    return {
        OFFLINE_SITE_RDE: True,
        OFFLINE_SITE_DATA_PORTAL: True,
        OFFLINE_SITE_DATA_PORTAL_TEST: True,
        OFFLINE_SITE_AI_API: True,
    }


def get_offline_runtime_state() -> OfflineRuntimeState:
    cfg = get_config_manager()
    enabled = bool(cfg.get("offline.enabled", False))
    raw_sites = cfg.get("offline.sites", {})
    defaults = _default_sites()

    if isinstance(raw_sites, dict):
        for key in defaults.keys():
            defaults[key] = bool(raw_sites.get(key, defaults[key]))

    return OfflineRuntimeState(enabled=enabled, sites=defaults)


def is_offline_mode_enabled() -> bool:
    return get_offline_runtime_state().enabled


def is_site_offline(site_key: str) -> bool:
    state = get_offline_runtime_state()
    if not state.enabled:
        return False
    return bool(state.sites.get(site_key, False))


def set_offline_mode(enabled: bool, *, persist: bool = True) -> bool:
    cfg = get_config_manager()
    cfg.set("offline.enabled", bool(enabled))
    if persist:
        return bool(cfg.save())
    return True


def set_site_offline(site_key: str, offline: bool, *, persist: bool = True) -> bool:
    cfg = get_config_manager()
    state = get_offline_runtime_state().sites
    state[site_key] = bool(offline)
    cfg.set("offline.sites", state)
    if persist:
        return bool(cfg.save())
    return True


def set_offline_state(enabled: bool, site_states: Dict[str, bool], *, persist: bool = True) -> bool:
    cfg = get_config_manager()
    normalized = _default_sites()
    for key in normalized.keys():
        normalized[key] = bool(site_states.get(key, normalized[key]))
    cfg.set("offline.enabled", bool(enabled))
    cfg.set("offline.sites", normalized)
    if persist:
        return bool(cfg.save())
    return True


def enable_offline_mode_for_sites(site_keys: list[str], *, persist: bool = True) -> bool:
    cfg = get_config_manager()
    current = get_offline_runtime_state().sites
    for key in site_keys:
        current[key] = True
    cfg.set("offline.enabled", True)
    cfg.set("offline.sites", current)
    if persist:
        return bool(cfg.save())
    return True


def resolve_site_for_url(url: str) -> Optional[str]:
    """URLからオフライン制御対象サイトキーを判定する。"""
    try:
        parsed = urlparse(str(url or ""))
    except Exception:
        return None

    host = (parsed.netloc or "").split("@")[-1].split(":")[0].lower()
    path = (parsed.path or "").lower()

    if not host:
        return None

    if host.endswith(".nims.go.jp") or host == "nims.go.jp":
        return OFFLINE_SITE_RDE

    if host == "nanonet.go.jp" or host.endswith(".nanonet.go.jp"):
        return OFFLINE_SITE_DATA_PORTAL

    if host.endswith(".cloudfront.net") and "nanonet.go.jp" in path:
        return OFFLINE_SITE_DATA_PORTAL_TEST

    return None


def validate_online_access_or_raise(url: str) -> None:
    """現在のオフライン設定に照らし、URLアクセス可否を検証する。"""
    state = get_offline_runtime_state()
    if not state.enabled:
        return

    site_key = resolve_site_for_url(url)
    if site_key and bool(state.sites.get(site_key, False)):
        raise OfflineAccessBlockedError(site_key, url=url)


def validate_ai_access_or_raise() -> None:
    state = get_offline_runtime_state()
    if not state.enabled:
        return
    if bool(state.sites.get(OFFLINE_SITE_AI_API, False)):
        raise OfflineAccessBlockedError(OFFLINE_SITE_AI_API)


def check_rde_service_health(timeout: int = 8) -> tuple[bool, str]:
    """RDEログインページの応答を軽量チェックしてサービス健全性を判定する。"""
    try:
        from net.session_manager import create_new_proxy_session

        session = create_new_proxy_session()
        url = "https://rde.nims.go.jp/rde/"
        response = session.get(url, timeout=timeout)

        if response.status_code >= 500:
            return False, f"status={response.status_code}"

        content_type = str(response.headers.get("Content-Type", "")).lower()
        if "html" not in content_type and "text" not in content_type:
            return False, f"unexpected content-type: {content_type or 'unknown'}"

        text = (response.text or "")[:3000].lower()
        if not text:
            return False, "empty response body"

        if "rde" not in text and "login" not in text and "認証" not in text:
            return False, "unexpected response body"

        return True, "ok"
    except Exception as e:
        logger.warning("RDEサービス健全性チェック失敗: %s", e)
        return False, str(e)
