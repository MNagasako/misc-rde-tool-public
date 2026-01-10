from __future__ import annotations

from typing import AbstractSet, Any, Callable, Iterable, Optional


# Requirement-driven portal status labels (dataset listing)
UNCHECKED_LABEL = "未確認"

# Display labels (as shown in the dataset listing UI)
# - managed: determined by logged-in portal (management) features
# - public: determined by public portal (output.json)
PUBLIC_MANAGED_LABEL = "公開"
PRIVATE_MANAGED_LABEL = "非公開"

PUBLIC_PUBLISHED_LABEL = "公開2"
NONPUBLIC_OR_UNREGISTERED_LABEL = "管理外"


def normalize_logged_in_portal_label(label: Any) -> str:
    text = str(label).strip() if label is not None else ""
    # Logged-in portal search results / CSV use "公開済" and "UP済".
    if text in {"公開済"}:
        return PUBLIC_MANAGED_LABEL
    if text in {"UP済"}:
        return PRIVATE_MANAGED_LABEL
    if text in {"未UP"}:
        return NONPUBLIC_OR_UNREGISTERED_LABEL
    return text


def is_managed_public_label(label: Any) -> bool:
    return (str(label).strip() if label is not None else "") == PUBLIC_MANAGED_LABEL


def is_managed_private_label(label: Any) -> bool:
    return (str(label).strip() if label is not None else "") == PRIVATE_MANAGED_LABEL


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


def is_unchecked_label(label: Any) -> bool:
    return (str(label).strip() if label is not None else "") == UNCHECKED_LABEL


def is_public_published_label(label: Any) -> bool:
    return (str(label).strip() if label is not None else "") == PUBLIC_PUBLISHED_LABEL


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

    existing_text = normalize_logged_in_portal_label(existing)
    cached_text = normalize_logged_in_portal_label(cached)
    dsid = str(dataset_id or "").strip()

    # 1) Managed determination takes precedence (public/private).
    if is_managed_public_label(existing_text) or is_managed_private_label(existing_text):
        return existing_text
    if is_managed_public_label(cached_text) or is_managed_private_label(cached_text):
        return cached_text

    # 2) If the dataset_id is present in public output.json, classify as 公開2.
    #    This should override negative/unregistered results.
    if dsid and dsid in public_published_dataset_ids:
        return PUBLIC_PUBLISHED_LABEL

    # 3) Cached negative determination
    if cached_text == NONPUBLIC_OR_UNREGISTERED_LABEL:
        return cached_text

    # 4) Existing confirmed values (but don't let 管理外 block future public check)
    if existing_text and not is_unchecked_label(existing_text):
        return existing_text

    # If we already know something (e.g., cached negative), keep it; otherwise unresolved.
    if cached_text:
        return cached_text

    if existing_text:
        return existing_text

    return None
