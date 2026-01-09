from __future__ import annotations

from typing import AbstractSet, Any, Callable, Iterable, Optional


PUBLIC_MANAGED_LABEL = "公開（管理）"
PUBLIC_LABEL = "公開"


def normalize_logged_in_portal_label(label: Any) -> str:
    text = str(label).strip() if label is not None else ""
    # Logged-in portal status uses "公開済"; keep "公開" reserved for public-json fallback.
    if text in {"公開済"}:
        return PUBLIC_MANAGED_LABEL
    return text


def is_managed_public_label(label: Any) -> bool:
    return (str(label).strip() if label is not None else "") == PUBLIC_MANAGED_LABEL


def pick_best_cached_label(
    dataset_id: str,
    *,
    get_label: Callable[[str, str], Any],
    environments: Iterable[str],
) -> Optional[str]:
    """Pick first available cached label from candidate environments.

    This helps when the user operates the portal in test env while the listing
    view is environment-agnostic.
    """

    dsid = str(dataset_id or "").strip()
    if not dsid:
        return None

    for env in environments:
        env_name = str(env or "").strip()
        if not env_name:
            continue
        try:
            raw = get_label(dsid, env_name)
        except Exception:
            raw = None
        text = normalize_logged_in_portal_label(raw)
        if text:
            return text

    return None


def is_public_fallback_label(label: Any) -> bool:
    return (str(label).strip() if label is not None else "") == PUBLIC_LABEL


def resolve_portal_status_label(
    *,
    existing: Any,
    cached: Any,
    dataset_id: str,
    public_published_dataset_ids: AbstractSet[str],
) -> Optional[str]:
    """Resolve portal status label for dataset listing.

    Priority:
    1) existing UI value (already filled)
    2) cached label derived from logged-in portal access
    3) public portal output.json (no-login) -> published by other org

    Returns:
        label string, or None when unresolved.
    """

    existing_text = str(existing).strip() if existing is not None else ""
    existing_text = normalize_logged_in_portal_label(existing_text)
    if existing_text and not is_public_fallback_label(existing_text):
        return existing_text

    cached_text = normalize_logged_in_portal_label(cached)
    if cached_text:
        return cached_text

    dsid = str(dataset_id or "").strip()
    if dsid and dsid in public_published_dataset_ids:
        return PUBLIC_LABEL

    if is_public_fallback_label(existing_text):
        return existing_text

    return None
