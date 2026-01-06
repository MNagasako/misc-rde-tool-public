from __future__ import annotations

import json
import logging
from typing import Any, Optional

from classes.core import secret_store

logger = logging.getLogger(__name__)


_KEYRING_NAMESPACE = "mail:settings"
_KEYRING_KEY = "nonsecret_settings_v1"


def _safe_json_dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _safe_json_loads(raw: str) -> Optional[dict[str, Any]]:
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            return None
        return obj
    except Exception:
        return None


def _get_nonsecret_keys() -> tuple[str, ...]:
    return (
        "mail.provider",
        "mail.gmail.from_address",
        "mail.gmail.from_name",
        "mail.gmail.remember_app_password",
        "mail.microsoft365.client_id",
        "mail.microsoft365.tenant",
        "mail.smtp.host",
        "mail.smtp.port",
        "mail.smtp.security",
        "mail.smtp.username",
        "mail.smtp.from_address",
        "mail.smtp.from_name",
        "mail.smtp.remember_password",
        "mail.test.to_address",
        "mail.test.subject",
        "mail.test.body",
    )


def snapshot_from_config(cfg: Any) -> dict[str, Any]:
    """Extract non-secret mail settings from a config-like object.

    cfg is expected to implement cfg.get(key, default).
    """
    data: dict[str, Any] = {}
    for key in _get_nonsecret_keys():
        data[key] = cfg.get(key)
    return data


def save_snapshot_to_keyring(snapshot: dict[str, Any]) -> bool:
    try:
        raw = _safe_json_dumps(snapshot)
        ok = secret_store.save_secret(namespace=_KEYRING_NAMESPACE, key=_KEYRING_KEY, secret=raw)
        if not ok:
            logger.debug("mail settings keyring save failed")
        return ok
    except Exception as e:
        logger.debug("mail settings keyring save error: %s", e)
        return False


def load_snapshot_from_keyring() -> Optional[dict[str, Any]]:
    raw = secret_store.load_secret(namespace=_KEYRING_NAMESPACE, key=_KEYRING_KEY)
    if not raw:
        return None
    return _safe_json_loads(raw)


def _is_blank_mail_config(cfg: Any) -> bool:
    """Heuristic: detect if mail settings are effectively unset."""
    provider = str(cfg.get("mail.provider", "gmail") or "gmail")

    gmail_from = str(cfg.get("mail.gmail.from_address", "") or "").strip()
    smtp_host = str(cfg.get("mail.smtp.host", "") or "").strip()
    smtp_user = str(cfg.get("mail.smtp.username", "") or "").strip()
    m365_client = str(cfg.get("mail.microsoft365.client_id", "") or "").strip()
    test_to = str(cfg.get("mail.test.to_address", "") or "").strip()

    if provider not in ("gmail", "microsoft365", "smtp"):
        provider = "gmail"

    # If all meaningful fields are empty, treat as blank.
    return (not gmail_from) and (not smtp_host) and (not smtp_user) and (not m365_client) and (not test_to)


def restore_into_config_if_needed(cfg: Any) -> bool:
    """Restore mail settings from keyring into cfg if cfg appears blank.

    Returns True if cfg was modified.
    """
    try:
        if not _is_blank_mail_config(cfg):
            return False

        snapshot = load_snapshot_from_keyring()
        if not snapshot:
            return False

        changed = False
        for key in _get_nonsecret_keys():
            if key not in snapshot:
                continue
            value = snapshot.get(key)
            if value is None:
                continue
            cfg.set(key, value)
            changed = True

        if changed:
            cfg.save()
        return changed
    except Exception as e:
        logger.debug("mail settings restore error: %s", e)
        return False
