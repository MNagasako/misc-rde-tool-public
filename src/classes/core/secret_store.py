from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


_SERVICE_PREFIX = "ARIM_RDE_Tool"


def _service_name(namespace: str) -> str:
    return f"{_SERVICE_PREFIX}:{namespace}"


def is_keyring_available() -> bool:
    try:
        import keyring

        backend = keyring.get_keyring()
        priority = getattr(backend, "priority", 0)
        try:
            return float(priority) > 0
        except Exception:
            return False
    except Exception:
        return False


def save_secret(*, namespace: str, key: str, secret: str) -> bool:
    try:
        import keyring

        keyring.set_password(_service_name(namespace), key, secret)
        return True
    except Exception as e:
        logger.warning("keyring保存失敗: %s", e)
        return False


def load_secret(*, namespace: str, key: str) -> Optional[str]:
    try:
        import keyring

        return keyring.get_password(_service_name(namespace), key)
    except Exception as e:
        logger.debug("keyring読込失敗: %s", e)
        return None


def delete_secret(*, namespace: str, key: str) -> bool:
    try:
        import keyring

        keyring.delete_password(_service_name(namespace), key)
        return True
    except Exception:
        return False
