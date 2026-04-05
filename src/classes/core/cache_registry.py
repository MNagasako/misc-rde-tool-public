from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional


@dataclass(frozen=True)
class CacheRuntimeContext:
    settings_widget: object | None = None
    browser: object | None = None


@dataclass(frozen=True)
class CacheSnapshot:
    cache_id: str
    name: str
    feature: str
    cache_type: str
    storage_path: str
    created_at: datetime | None
    updated_at: datetime | None
    size_bytes: int
    item_count: int | None
    active: bool
    clearable: bool
    refreshable: bool = False
    refresh_reason: str = ""
    notes: str = ""
    safe_bulk_clear: bool = True


@dataclass(frozen=True)
class CacheClearResult:
    cleared: bool
    message: str


@dataclass(frozen=True)
class CacheRefreshResult:
    refreshed: bool
    message: str


@dataclass(frozen=True)
class CacheEntry:
    cache_id: str
    snapshot_provider: Callable[[CacheRuntimeContext], CacheSnapshot]
    clear_callback: Callable[[CacheRuntimeContext], CacheClearResult]
    refresh_callback: Optional[Callable[[CacheRuntimeContext, Optional[Callable[[int, int, str], None]]], CacheRefreshResult]] = None
    refresh_reason: str = ""


def build_cache_runtime_context(settings_widget=None, browser=None) -> CacheRuntimeContext:
    resolved_browser = browser
    if resolved_browser is None and settings_widget is not None:
        resolved_browser = getattr(settings_widget, "parent_widget", None)
        if resolved_browser is None:
            try:
                resolved_browser = settings_widget.window()
            except Exception:
                resolved_browser = None
    return CacheRuntimeContext(settings_widget=settings_widget, browser=resolved_browser)


def _join_paths(paths: Iterable[str]) -> str:
    cleaned = [str(path).strip() for path in paths if str(path or "").strip()]
    return "\n".join(cleaned)


def _max_datetime(*values: datetime | None) -> datetime | None:
    candidates = [value for value in values if value is not None]
    return max(candidates) if candidates else None


def _file_datetime(path: str) -> datetime | None:
    try:
        if path and os.path.exists(path):
            return datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
    except Exception:
        pass
    return None


def _file_size(path: str) -> int:
    try:
        if path and os.path.exists(path):
            return int(os.path.getsize(path))
    except Exception:
        pass
    return 0


def _directory_json_metadata(path: str) -> tuple[int, int, datetime | None]:
    count = 0
    size_bytes = 0
    updated_at = None
    try:
        root = Path(path)
        if not root.exists() or not root.is_dir():
            return 0, 0, None
        for entry in root.glob("*.json"):
            try:
                stat = entry.stat()
            except Exception:
                continue
            count += 1
            size_bytes += int(stat.st_size)
            candidate = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            updated_at = candidate if updated_at is None or candidate > updated_at else updated_at
    except Exception:
        pass
    return count, size_bytes, updated_at


def _ttl_cache_snapshot(namespace: str, *, cache_id: str, name: str, feature: str, notes: str) -> CacheSnapshot:
    from classes.core.ttl_cache import TTLCache

    cache = TTLCache(namespace)
    path = getattr(cache, "_path", "")
    keys = cache.keys()
    return CacheSnapshot(
        cache_id=cache_id,
        name=name,
        feature=feature,
        cache_type="TTL永続キャッシュ",
        storage_path=str(path or ""),
        created_at=None,
        updated_at=_file_datetime(str(path or "")),
        size_bytes=_file_size(str(path or "")),
        item_count=len(keys),
        active=bool(keys),
        clearable=True,
        notes=notes,
    )


def _resolve_ui_controller(context: CacheRuntimeContext):
    browser = context.browser
    if browser is None:
        return None
    return getattr(browser, "ui_controller", None)


def _resolve_ai_test_widget(context: CacheRuntimeContext):
    controller = _resolve_ui_controller(context)
    if controller is None:
        return None
    ai_controller = getattr(controller, "ai_controller", None)
    if ai_controller is not None and getattr(ai_controller, "current_ai_test_widget", None) is not None:
        return ai_controller.current_ai_test_widget
    return getattr(controller, "ai_test_widget", None)


def _resolve_data_fetch2_widget(context: CacheRuntimeContext):
    controller = _resolve_ui_controller(context)
    if controller is None:
        return None
    widget = getattr(controller, "_data_fetch2_widget", None)
    if widget is not None:
        return widget
    return getattr(context.browser, "data_fetch2_widget", None)


def _browser_blob_hash_snapshot(context: CacheRuntimeContext) -> CacheSnapshot:
    browser = context.browser
    blob_hashes = getattr(browser, "_recent_blob_hashes", None) if browser is not None else None
    count = len(blob_hashes) if isinstance(blob_hashes, set) else 0
    return CacheSnapshot(
        cache_id="browser_blob_hashes",
        name="blob画像ハッシュキャッシュ",
        feature="Browser/画像取得",
        cache_type="メモリ",
        storage_path="memory://Browser._recent_blob_hashes",
        created_at=None,
        updated_at=None,
        size_bytes=0,
        item_count=count,
        active=bool(count),
        clearable=browser is not None,
        notes="blob URL 重複検知の一時キャッシュ",
    )


def _clear_browser_blob_hashes(context: CacheRuntimeContext) -> CacheClearResult:
    browser = context.browser
    if browser is None or not isinstance(getattr(browser, "_recent_blob_hashes", None), set):
        return CacheClearResult(False, "対象の実行中キャッシュが見つかりません")
    browser._recent_blob_hashes.clear()
    return CacheClearResult(True, "blob画像ハッシュキャッシュをクリアしました")


def _browser_image_count_snapshot(context: CacheRuntimeContext) -> CacheSnapshot:
    browser = context.browser
    counts = getattr(browser, "_data_id_image_counts", None) if browser is not None else None
    count = len(counts) if isinstance(counts, dict) else 0
    return CacheSnapshot(
        cache_id="browser_image_counts",
        name="画像件数キャッシュ",
        feature="Browser/画像取得",
        cache_type="メモリ",
        storage_path="memory://Browser._data_id_image_counts",
        created_at=None,
        updated_at=None,
        size_bytes=0,
        item_count=count,
        active=bool(count),
        clearable=browser is not None,
        notes="data_id ごとの画像枚数を保持",
    )


def _clear_browser_image_counts(context: CacheRuntimeContext) -> CacheClearResult:
    browser = context.browser
    if browser is None or not isinstance(getattr(browser, "_data_id_image_counts", None), dict):
        return CacheClearResult(False, "対象の実行中キャッシュが見つかりません")
    browser._data_id_image_counts.clear()
    return CacheClearResult(True, "画像件数キャッシュをクリアしました")


def _data_fetch2_runtime_snapshot(context: CacheRuntimeContext) -> CacheSnapshot:
    widget = _resolve_data_fetch2_widget(context)
    dataset_count = 0
    bulk_rde_count = 0
    bulk_dp_count = 0
    filter_count = 0
    notes: list[str] = []

    if widget is not None:
        dataset_widget = getattr(widget, "data_fetch_widget", None)
        dataset_map = getattr(dataset_widget, "dataset_map", None) if dataset_widget is not None else None
        if isinstance(dataset_map, dict):
            dataset_count = len(dataset_map)

        bulk_rde_widget = getattr(widget, "bulk_rde_widget", None)
        if bulk_rde_widget is not None:
            bulk_rde_count += len(getattr(bulk_rde_widget, "_dataset_items_cache", []) or [])
            bulk_rde_count += len(getattr(bulk_rde_widget, "_entry_items_cache", {}) or {})
            bulk_rde_count += len(getattr(bulk_rde_widget, "_subgroup_info_cache", {}) or {})
            bulk_rde_count += len(getattr(bulk_rde_widget, "_sample_info_cache", {}) or {})
            bulk_rde_count += len(getattr(bulk_rde_widget, "_instrument_info_cache", {}) or {})

        bulk_dp_widget = getattr(widget, "bulk_dp_widget", None)
        if bulk_dp_widget is not None:
            bulk_dp_count += len(getattr(bulk_dp_widget, "_entry_enrichment_cache", {}) or {})
            bulk_dp_count += len(getattr(bulk_dp_widget, "_search_result_cache", {}) or {})
            bulk_dp_count += len(getattr(bulk_dp_widget, "_search_result_ts", {}) or {})

    try:
        from classes.data_fetch2.ui.file_filter_widget import FileFilterWidget

        filter_count = len(getattr(FileFilterWidget, "_CACHED_EXTS", []) or []) + len(getattr(FileFilterWidget, "_CACHED_MEDIA", []) or [])
    except Exception:
        filter_count = 0

    total = dataset_count + bulk_rde_count + bulk_dp_count + filter_count
    if dataset_count:
        notes.append(f"dataset={dataset_count}")
    if bulk_rde_count:
        notes.append(f"bulk_rde={bulk_rde_count}")
    if bulk_dp_count:
        notes.append(f"bulk_dp={bulk_dp_count}")
    if filter_count:
        notes.append(f"filter={filter_count}")

    return CacheSnapshot(
        cache_id="data_fetch2_runtime",
        name="データ取得2ランタイムキャッシュ",
        feature="データ取得2",
        cache_type="メモリ",
        storage_path="memory://DataFetch2TabWidget",
        created_at=None,
        updated_at=None,
        size_bytes=0,
        item_count=total,
        active=bool(total),
        clearable=True,
        notes=", ".join(notes) or "dataset/bulk/filter の実行中キャッシュ",
    )


def _clear_data_fetch2_runtime(context: CacheRuntimeContext) -> CacheClearResult:
    widget = _resolve_data_fetch2_widget(context)
    try:
        from classes.data_fetch2.ui import bulk_dp_tab as bulk_dp_module

        bulk_dp_module._BULK_DP_BOOTSTRAP_CACHE = None
    except Exception:
        pass
    try:
        from classes.data_fetch2.ui.file_filter_widget import FileFilterWidget

        FileFilterWidget._CACHED_EXTS = []
        FileFilterWidget._CACHED_MEDIA = []
    except Exception:
        pass

    cleared = False
    if widget is not None:
        dataset_widget = getattr(widget, "data_fetch_widget", None)
        if dataset_widget is not None and hasattr(dataset_widget, "clear_cache"):
            dataset_widget.clear_cache()
            cleared = True

        bulk_rde_widget = getattr(widget, "bulk_rde_widget", None)
        if bulk_rde_widget is not None:
            setattr(bulk_rde_widget, "_dataset_items_cache", [])
            setattr(bulk_rde_widget, "_entry_items_cache", {})
            setattr(bulk_rde_widget, "_subgroup_info_cache", None)
            setattr(bulk_rde_widget, "_sample_info_cache", None)
            setattr(bulk_rde_widget, "_instrument_info_cache", None)
            cleared = True

        bulk_dp_widget = getattr(widget, "bulk_dp_widget", None)
        if bulk_dp_widget is not None:
            setattr(bulk_dp_widget, "_entry_enrichment_cache", {})
            setattr(bulk_dp_widget, "_search_result_cache", {})
            setattr(bulk_dp_widget, "_search_result_ts", {})
            setattr(bulk_dp_widget, "_last_search_cache_key", None)
            cleared = True

    return CacheClearResult(True if cleared or widget is None else False, "データ取得2のメモリキャッシュをクリアしました")


def _ai_runtime_snapshot(context: CacheRuntimeContext) -> CacheSnapshot:
    widget = _resolve_ai_test_widget(context)
    template_count = 0
    static_count = 0
    source_count = 0
    active = False
    if widget is not None:
        template_count = len(getattr(widget, "_cached_templates", {}) or {})
        static_count = len(getattr(widget, "_cached_static_data", {}) or {})
        source_count = len(getattr(widget, "_data_source_cache", {}) or {})
        active = bool(template_count or static_count or source_count or getattr(widget, "_cached_experiment_data", None) is not None or getattr(widget, "_cached_arim_data", None) is not None)
    total = template_count + static_count + source_count
    return CacheSnapshot(
        cache_id="ai_runtime",
        name="AI分析ランタイムキャッシュ",
        feature="AI",
        cache_type="メモリ",
        storage_path="memory://UIAITestWidget",
        created_at=None,
        updated_at=None,
        size_bytes=0,
        item_count=total,
        active=active,
        clearable=widget is not None,
        notes=f"templates={template_count}, static={static_count}, source={source_count}",
    )


def _clear_ai_runtime(context: CacheRuntimeContext) -> CacheClearResult:
    widget = _resolve_ai_test_widget(context)
    if widget is None or not hasattr(widget, "clear_cache"):
        return CacheClearResult(False, "実行中のAI分析ウィジェットが見つかりません")
    widget.clear_cache()
    return CacheClearResult(True, "AI分析ランタイムキャッシュをクリアしました")


class CacheRegistry:
    def __init__(self, entries: list[CacheEntry]):
        self._entries = list(entries)

    def get_snapshots(self, context: CacheRuntimeContext) -> list[CacheSnapshot]:
        snapshots: list[CacheSnapshot] = []
        for entry in self._entries:
            try:
                snapshot = entry.snapshot_provider(context)
                snapshots.append(
                    replace(
                        snapshot,
                        refreshable=bool(entry.refresh_callback),
                        refresh_reason=str(snapshot.refresh_reason or entry.refresh_reason or ""),
                    )
                )
            except Exception as exc:
                snapshots.append(
                    CacheSnapshot(
                        cache_id=entry.cache_id,
                        name=entry.cache_id,
                        feature="診断",
                        cache_type="不明",
                        storage_path="",
                        created_at=None,
                        updated_at=None,
                        size_bytes=0,
                        item_count=None,
                        active=False,
                        clearable=False,
                        refreshable=False,
                        refresh_reason="",
                        notes=f"メタデータ取得失敗: {exc}",
                        safe_bulk_clear=False,
                    )
                )
        return sorted(snapshots, key=lambda item: (item.feature, item.name))

    def clear_cache(self, cache_id: str, context: CacheRuntimeContext) -> CacheClearResult:
        for entry in self._entries:
            if entry.cache_id != cache_id:
                continue
            return entry.clear_callback(context)
        return CacheClearResult(False, f"cache_id={cache_id} は未登録です")

    def clear_safe_caches(self, context: CacheRuntimeContext) -> list[CacheClearResult]:
        results: list[CacheClearResult] = []
        for snapshot in self.get_snapshots(context):
            if not snapshot.safe_bulk_clear or not snapshot.clearable:
                continue
            results.append(self.clear_cache(snapshot.cache_id, context))
        return results

    def refresh_cache(
        self,
        cache_id: str,
        context: CacheRuntimeContext,
        *,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> CacheRefreshResult:
        for entry in self._entries:
            if entry.cache_id != cache_id:
                continue
            if entry.refresh_callback is None:
                return CacheRefreshResult(False, f"cache_id={cache_id} は更新不可です")
            return entry.refresh_callback(context, progress_callback)
        return CacheRefreshResult(False, f"cache_id={cache_id} は未登録です")


def _build_registry() -> CacheRegistry:
    def _emit_progress(progress_callback, current: int, total: int, message: str) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(int(current), int(total), str(message))
        except Exception:
            pass

    def dataset_listing_snapshot(_context: CacheRuntimeContext) -> CacheSnapshot:
        from classes.dataset.util.dataset_list_table_records import get_dataset_list_cache_metadata

        meta = get_dataset_list_cache_metadata()
        return CacheSnapshot(
            cache_id="dataset_listing",
            name="データセット一覧キャッシュ",
            feature="データセット",
            cache_type="メモリ+JSON",
            storage_path=_join_paths(meta.get("paths", [])),
            created_at=meta.get("created_at"),
            updated_at=meta.get("updated_at"),
            size_bytes=int(meta.get("size_bytes") or 0),
            item_count=int(meta.get("item_count") or 0),
            active=bool(meta.get("active")),
            clearable=True,
            notes=f"memory={int(meta.get('memory_count') or 0)}, persisted={int(meta.get('persisted_count') or 0)}",
        )

    def clear_dataset_listing(_context: CacheRuntimeContext) -> CacheClearResult:
        from classes.dataset.util.dataset_list_table_records import clear_dataset_list_cache_storage

        clear_dataset_list_cache_storage(include_persisted=True)
        return CacheClearResult(True, "データセット一覧キャッシュをクリアしました")

    def subgroup_listing_snapshot(_context: CacheRuntimeContext) -> CacheSnapshot:
        from classes.subgroup.util.subgroup_list_table_records import get_subgroup_list_cache_metadata

        meta = get_subgroup_list_cache_metadata()
        return CacheSnapshot(
            cache_id="subgroup_listing",
            name="サブグループ一覧キャッシュ",
            feature="サブグループ",
            cache_type="メモリ+JSON",
            storage_path=_join_paths(meta.get("paths", [])),
            created_at=meta.get("created_at"),
            updated_at=meta.get("updated_at"),
            size_bytes=int(meta.get("size_bytes") or 0),
            item_count=int(meta.get("item_count") or 0),
            active=bool(meta.get("active")),
            clearable=True,
            notes=f"memory={int(meta.get('memory_count') or 0)}, detail_users={int(meta.get('detail_user_count') or 0)}",
        )

    def clear_subgroup_listing(_context: CacheRuntimeContext) -> CacheClearResult:
        from classes.subgroup.util.subgroup_list_table_records import clear_subgroup_list_cache_storage

        clear_subgroup_list_cache_storage(include_persisted=True)
        return CacheClearResult(True, "サブグループ一覧キャッシュをクリアしました")

    def registration_status_snapshot(_context: CacheRuntimeContext) -> CacheSnapshot:
        from classes.data_entry.core.registration_status_service import get_cache_metadata

        entries = get_cache_metadata()
        paths = [str(entry.get("path") or "") for entry in entries if str(entry.get("path") or "").strip()]
        updated_at = None
        size_bytes = 0
        item_count = 0
        notes: list[str] = []
        for entry in entries:
            size_bytes += int(entry.get("size") or 0)
            item_count += int(entry.get("count") or 0)
            updated_at = _max_datetime(updated_at, entry.get("updated_at"))
            notes.append(f"{entry.get('type')}={int(entry.get('count') or 0)}")
        return CacheSnapshot(
            cache_id="registration_status",
            name="登録状況キャッシュ",
            feature="データ登録",
            cache_type="JSON",
            storage_path=_join_paths(paths),
            created_at=None,
            updated_at=updated_at,
            size_bytes=size_bytes,
            item_count=item_count,
            active=bool(item_count),
            clearable=True,
            notes=", ".join(notes),
        )

    def clear_registration_status(_context: CacheRuntimeContext) -> CacheClearResult:
        from classes.data_entry.core.registration_status_service import clear_cache

        clear_cache()
        return CacheClearResult(True, "登録状況キャッシュをクリアしました")

    def refresh_registration_status(
        _context: CacheRuntimeContext,
        progress_callback: Optional[Callable[[int, int, str], None]],
    ) -> CacheRefreshResult:
        from classes.data_entry.core import registration_status_service as regsvc

        _emit_progress(progress_callback, 0, 0, "登録状況一覧を再取得中...")
        entries = regsvc.fetch_all(default_chunk=5000, use_cache=False)
        _emit_progress(progress_callback, 1, 1, f"登録状況一覧を更新しました: {len(entries)} 件")
        return CacheRefreshResult(True, f"登録状況キャッシュを更新しました（{len(entries)} 件）")

    def portal_status_snapshot(_context: CacheRuntimeContext) -> CacheSnapshot:
        from classes.data_portal.core.portal_entry_status import get_portal_entry_status_cache_metadata

        meta = get_portal_entry_status_cache_metadata()
        return CacheSnapshot(
            cache_id="portal_entry_status",
            name="データポータル状態キャッシュ",
            feature="データポータル",
            cache_type="JSON",
            storage_path=_join_paths(meta.get("paths", [])),
            created_at=None,
            updated_at=meta.get("updated_at"),
            size_bytes=int(meta.get("size_bytes") or 0),
            item_count=int(meta.get("item_count") or 0),
            active=bool(meta.get("active")),
            clearable=True,
            notes="ポータル掲載状態の再参照抑制",
        )

    def clear_portal_status(_context: CacheRuntimeContext) -> CacheClearResult:
        from classes.data_portal.core.portal_entry_status import get_portal_entry_status_cache

        get_portal_entry_status_cache().clear()
        return CacheClearResult(True, "データポータル状態キャッシュをクリアしました")

    def search_query_snapshot(_context: CacheRuntimeContext) -> CacheSnapshot:
        from classes.core.rde_search_index import get_query_cache_metadata

        meta = get_query_cache_metadata()
        return CacheSnapshot(
            cache_id="search_query",
            name="検索インデックス問い合わせキャッシュ",
            feature="共通検索",
            cache_type="JSON",
            storage_path=str(meta.get("path") or ""),
            created_at=None,
            updated_at=meta.get("updated_at"),
            size_bytes=int(meta.get("size_bytes") or 0),
            item_count=int(meta.get("item_count") or 0),
            active=bool(meta.get("active")),
            clearable=True,
            notes="RDE検索条件ごとの結果キャッシュ",
        )

    def clear_search_query(_context: CacheRuntimeContext) -> CacheClearResult:
        from classes.core.rde_search_index import clear_query_cache

        clear_query_cache()
        return CacheClearResult(True, "検索問い合わせキャッシュをクリアしました")

    def remote_missing_snapshot(_context: CacheRuntimeContext) -> CacheSnapshot:
        from classes.utils.remote_resource_pruner import get_missing_cache_metadata

        meta = get_missing_cache_metadata()
        return CacheSnapshot(
            cache_id="remote_missing",
            name="削除済みID判定キャッシュ",
            feature="共通",
            cache_type="JSON+TTLメモリ",
            storage_path=str(meta.get("path") or ""),
            created_at=None,
            updated_at=meta.get("updated_at"),
            size_bytes=int(meta.get("size_bytes") or 0),
            item_count=int(meta.get("item_count") or 0),
            active=bool(meta.get("active")),
            clearable=True,
            notes=f"dataset={int(meta.get('dataset_count') or 0)}, group={int(meta.get('group_count') or 0)}, ttl={int(meta.get('ttl_memory_count') or 0)}",
        )

    def clear_remote_missing(_context: CacheRuntimeContext) -> CacheClearResult:
        from classes.utils.remote_resource_pruner import clear_marked_missing

        clear_marked_missing(include_existence_cache=True)
        return CacheClearResult(True, "削除済みID判定キャッシュをクリアしました")

    def public_detail_snapshot(_context: CacheRuntimeContext) -> CacheSnapshot:
        from classes.utils.data_portal_public import get_public_detail_cache_metadata

        meta = get_public_detail_cache_metadata()
        return CacheSnapshot(
            cache_id="public_detail",
            name="公開ポータル詳細キャッシュ",
            feature="データポータル",
            cache_type="JSONディレクトリ",
            storage_path=_join_paths(meta.get("paths", [])),
            created_at=None,
            updated_at=meta.get("updated_at"),
            size_bytes=int(meta.get("size_bytes") or 0),
            item_count=int(meta.get("item_count") or 0),
            active=bool(meta.get("active")),
            clearable=True,
            notes="公開データポータル詳細JSON",
        )

    def clear_public_detail(_context: CacheRuntimeContext) -> CacheClearResult:
        from classes.utils.data_portal_public import clear_public_detail_cache

        clear_public_detail_cache()
        return CacheClearResult(True, "公開ポータル詳細キャッシュをクリアしました")

    def public_output_ids_snapshot(_context: CacheRuntimeContext) -> CacheSnapshot:
        from classes.utils.data_portal_public import get_public_output_dataset_id_cache_metadata

        meta = get_public_output_dataset_id_cache_metadata()
        return CacheSnapshot(
            cache_id="public_output_ids",
            name="公開output.json IDキャッシュ",
            feature="データポータル",
            cache_type="メモリ",
            storage_path=str(meta.get("path") or ""),
            created_at=None,
            updated_at=meta.get("updated_at"),
            size_bytes=int(meta.get("size_bytes") or 0),
            item_count=int(meta.get("item_count") or 0),
            active=bool(meta.get("active")),
            clearable=True,
            notes="公開output.json 由来の dataset_id 集合",
        )

    def clear_public_output_ids(_context: CacheRuntimeContext) -> CacheClearResult:
        from classes.utils.data_portal_public import clear_public_output_dataset_id_cache

        clear_public_output_dataset_id_cache()
        return CacheClearResult(True, "公開output.json IDキャッシュをクリアしました")

    def refresh_public_output_ids(
        _context: CacheRuntimeContext,
        progress_callback: Optional[Callable[[int, int, str], None]],
    ) -> CacheRefreshResult:
        from classes.utils.data_portal_public import get_public_published_dataset_ids

        _emit_progress(progress_callback, 0, 0, "公開output.json から dataset_id を再読込中...")
        dataset_ids = get_public_published_dataset_ids(use_cache=False)
        _emit_progress(progress_callback, 1, 1, f"公開output.json ID を更新しました: {len(dataset_ids)} 件")
        return CacheRefreshResult(True, f"公開output.json IDキャッシュを更新しました（{len(dataset_ids)} 件）")

    def public_listing_ids_snapshot(_context: CacheRuntimeContext) -> CacheSnapshot:
        from classes.utils.data_portal_public import get_public_listing_dataset_id_cache_metadata

        meta = get_public_listing_dataset_id_cache_metadata()
        return CacheSnapshot(
            cache_id="public_listing_ids",
            name="公開一覧IDキャッシュ",
            feature="データポータル",
            cache_type="メモリ",
            storage_path=str(meta.get("path") or ""),
            created_at=None,
            updated_at=meta.get("updated_at"),
            size_bytes=int(meta.get("size_bytes") or 0),
            item_count=int(meta.get("item_count") or 0),
            active=bool(meta.get("active")),
            clearable=True,
            notes="公開一覧ページから抽出した dataset_id 集合",
        )

    def clear_public_listing_ids(_context: CacheRuntimeContext) -> CacheClearResult:
        from classes.utils.data_portal_public import clear_public_listing_dataset_id_cache

        clear_public_listing_dataset_id_cache()
        return CacheClearResult(True, "公開一覧IDキャッシュをクリアしました")

    def refresh_public_listing_ids(
        _context: CacheRuntimeContext,
        progress_callback: Optional[Callable[[int, int, str], None]],
    ) -> CacheRefreshResult:
        from classes.utils.data_portal_public import get_public_listing_dataset_ids

        dataset_ids = get_public_listing_dataset_ids(
            environment="production",
            force_refresh=True,
            page_max_workers=1,
            progress_callback=progress_callback,
        )
        _emit_progress(progress_callback, 1, 1, f"公開一覧 ID を更新しました: {len(dataset_ids)} 件")
        return CacheRefreshResult(True, f"公開一覧IDキャッシュを更新しました（production: {len(dataset_ids)} 件）")

    def prompt_dictionary_snapshot(_context: CacheRuntimeContext) -> CacheSnapshot:
        from classes.ai.util.prompt_assembly import get_prompt_dictionary_cache_metadata

        meta = get_prompt_dictionary_cache_metadata()
        return CacheSnapshot(
            cache_id="prompt_dictionary",
            name="プロンプト辞書キャッシュ",
            feature="AI",
            cache_type="メモリ+JSON",
            storage_path=str(meta.get("path") or ""),
            created_at=None,
            updated_at=meta.get("updated_at"),
            size_bytes=int(meta.get("size_bytes") or 0),
            item_count=int(meta.get("item_count") or 0),
            active=bool(meta.get("active")),
            clearable=True,
            notes="エイリアス設定と summary の再読込キャッシュ",
        )

    def clear_prompt_dictionary(_context: CacheRuntimeContext) -> CacheClearResult:
        from classes.ai.util.prompt_assembly import clear_prompt_dictionary_caches

        clear_prompt_dictionary_caches(remove_summary_file=True)
        return CacheClearResult(True, "プロンプト辞書キャッシュをクリアしました")

    def refresh_prompt_dictionary(
        _context: CacheRuntimeContext,
        progress_callback: Optional[Callable[[int, int, str], None]],
    ) -> CacheRefreshResult:
        from classes.ai.util.prompt_assembly import clear_prompt_dictionary_caches, get_prompt_dictionary_summary

        _emit_progress(progress_callback, 0, 0, "プロンプト辞書サマリーを再集計中...")
        clear_prompt_dictionary_caches(remove_summary_file=True)
        summary = get_prompt_dictionary_summary()
        candidate_count = int(summary.get("candidate_count") or 0)
        _emit_progress(progress_callback, 1, 1, f"プロンプト辞書を更新しました: 候補 {candidate_count} 件")
        return CacheRefreshResult(True, f"プロンプト辞書キャッシュを更新しました（候補 {candidate_count} 件）")

    def material_index_snapshot(_context: CacheRuntimeContext) -> CacheSnapshot:
        from classes.ai.extensions.utils.data_loaders import MaterialIndexLoader

        meta = MaterialIndexLoader.get_cache_metadata()
        return CacheSnapshot(
            cache_id="material_index_loader",
            name="MIローダーキャッシュ",
            feature="AI",
            cache_type="メモリ",
            storage_path=str(meta.get("path") or ""),
            created_at=None,
            updated_at=meta.get("updated_at"),
            size_bytes=int(meta.get("size_bytes") or 0),
            item_count=int(meta.get("item_count") or 0),
            active=bool(meta.get("active")),
            clearable=True,
            notes="AI拡張用 MI.json 読込結果",
        )

    def clear_material_index(_context: CacheRuntimeContext) -> CacheClearResult:
        from classes.ai.extensions.utils.data_loaders import MaterialIndexLoader

        MaterialIndexLoader.clear_cache()
        return CacheClearResult(True, "MIローダーキャッシュをクリアしました")

    def refresh_material_index(
        _context: CacheRuntimeContext,
        progress_callback: Optional[Callable[[int, int, str], None]],
    ) -> CacheRefreshResult:
        from classes.ai.extensions.utils.data_loaders import MaterialIndexLoader

        _emit_progress(progress_callback, 0, 0, "MI.json を再読込中...")
        MaterialIndexLoader.clear_cache()
        payload = MaterialIndexLoader.load_material_index()
        _emit_progress(progress_callback, 1, 1, f"MI.json を再読込しました: {len(payload)} 件")
        return CacheRefreshResult(True, f"MIローダーキャッシュを更新しました（{len(payload)} 件）")

    def equipment_loader_snapshot(_context: CacheRuntimeContext) -> CacheSnapshot:
        from classes.ai.extensions.utils.data_loaders import EquipmentLoader

        meta = EquipmentLoader.get_cache_metadata()
        return CacheSnapshot(
            cache_id="equipment_loader",
            name="設備ローダーキャッシュ",
            feature="AI",
            cache_type="メモリ",
            storage_path=str(meta.get("path") or ""),
            created_at=None,
            updated_at=meta.get("updated_at"),
            size_bytes=int(meta.get("size_bytes") or 0),
            item_count=int(meta.get("item_count") or 0),
            active=bool(meta.get("active")),
            clearable=True,
            notes="AI拡張用 EQUIPMENTS 読込結果",
        )

    def clear_equipment_loader(_context: CacheRuntimeContext) -> CacheClearResult:
        from classes.ai.extensions.utils.data_loaders import EquipmentLoader

        EquipmentLoader.clear_cache()
        return CacheClearResult(True, "設備ローダーキャッシュをクリアしました")

    def refresh_equipment_loader(
        _context: CacheRuntimeContext,
        progress_callback: Optional[Callable[[int, int, str], None]],
    ) -> CacheRefreshResult:
        from classes.ai.extensions.utils.data_loaders import EquipmentLoader

        _emit_progress(progress_callback, 0, 0, "設備 JSON を再読込中...")
        EquipmentLoader.clear_cache()
        payload = EquipmentLoader.load_equipment_data()
        _emit_progress(progress_callback, 1, 1, f"設備 JSON を再読込しました: {len(payload)} 件")
        return CacheRefreshResult(True, f"設備ローダーキャッシュを更新しました（{len(payload)} 件）")

    entries = [
        CacheEntry(
            "dataset_listing",
            dataset_listing_snapshot,
            clear_dataset_listing,
            refresh_reason="設定タブから安全に再構築する入口がないため更新不可",
        ),
        CacheEntry(
            "subgroup_listing",
            subgroup_listing_snapshot,
            clear_subgroup_listing,
            refresh_reason="設定タブから安全に再構築する入口がないため更新不可",
        ),
        CacheEntry(
            "registration_status",
            registration_status_snapshot,
            clear_registration_status,
            refresh_callback=refresh_registration_status,
            refresh_reason="RDE Entry API から再取得可能",
        ),
        CacheEntry(
            "portal_entry_status",
            portal_status_snapshot,
            clear_portal_status,
            refresh_reason="対象 dataset_id 群の再探索条件が必要なため更新不可",
        ),
        CacheEntry(
            "search_query",
            search_query_snapshot,
            clear_search_query,
            refresh_reason="問い合わせ結果キャッシュは検索実行時に再生成されるため更新不可",
        ),
        CacheEntry(
            "remote_missing",
            remote_missing_snapshot,
            clear_remote_missing,
            refresh_reason="対象リソースの再走査条件が必要なため更新不可",
        ),
        CacheEntry(
            "public_detail",
            public_detail_snapshot,
            clear_public_detail,
            refresh_reason="環境・認証条件を伴うため設定タブからは更新不可",
        ),
        CacheEntry(
            "public_output_ids",
            public_output_ids_snapshot,
            clear_public_output_ids,
            refresh_callback=refresh_public_output_ids,
            refresh_reason="output.json から再読込可能",
        ),
        CacheEntry(
            "public_listing_ids",
            public_listing_ids_snapshot,
            clear_public_listing_ids,
            refresh_callback=refresh_public_listing_ids,
            refresh_reason="公開一覧ページから再取得可能（production）",
        ),
        CacheEntry(
            "ttl_data_entry",
            lambda _context: _ttl_cache_snapshot(
                "data_entry",
                cache_id="ttl_data_entry",
                name="データエントリーTTLキャッシュ",
                feature="基本情報",
                notes="Basic Info の個別エントリー再取得抑制",
            ),
            lambda _context: (lambda cache: (cache.clear(), CacheClearResult(True, "データエントリーTTLキャッシュをクリアしました")))(
                __import__("classes.core.ttl_cache", fromlist=["TTLCache"]).TTLCache("data_entry")
            )[1],
            refresh_reason="利用時に再生成される TTL キャッシュのため更新不可",
        ),
        CacheEntry(
            "ttl_terminal_entries",
            lambda _context: _ttl_cache_snapshot(
                "terminal_entries",
                cache_id="ttl_terminal_entries",
                name="終端エントリーキャッシュ",
                feature="データ登録",
                notes="完了済みエントリーの再取得抑制",
            ),
            lambda _context: (lambda cache: (cache.clear(), CacheClearResult(True, "終端エントリーキャッシュをクリアしました")))(
                __import__("classes.core.ttl_cache", fromlist=["TTLCache"]).TTLCache("terminal_entries")
            )[1],
            refresh_reason="利用時に再生成される TTL キャッシュのため更新不可",
        ),
        CacheEntry(
            "browser_blob_hashes",
            _browser_blob_hash_snapshot,
            _clear_browser_blob_hashes,
            refresh_reason="実行時メモリのみのため更新不可",
        ),
        CacheEntry(
            "browser_image_counts",
            _browser_image_count_snapshot,
            _clear_browser_image_counts,
            refresh_reason="実行時メモリのみのため更新不可",
        ),
        CacheEntry(
            "data_fetch2_runtime",
            _data_fetch2_runtime_snapshot,
            _clear_data_fetch2_runtime,
            refresh_reason="画面内状態に依存するため設定タブからは更新不可",
        ),
        CacheEntry(
            "ai_runtime",
            _ai_runtime_snapshot,
            _clear_ai_runtime,
            refresh_reason="画面内状態に依存するため設定タブからは更新不可",
        ),
        CacheEntry(
            "prompt_dictionary",
            prompt_dictionary_snapshot,
            clear_prompt_dictionary,
            refresh_callback=refresh_prompt_dictionary,
            refresh_reason="設定ファイルから再集計可能",
        ),
        CacheEntry(
            "material_index_loader",
            material_index_snapshot,
            clear_material_index,
            refresh_callback=refresh_material_index,
            refresh_reason="入力 JSON から再読込可能",
        ),
        CacheEntry(
            "equipment_loader",
            equipment_loader_snapshot,
            clear_equipment_loader,
            refresh_callback=refresh_equipment_loader,
            refresh_reason="入力 JSON から再読込可能",
        ),
    ]
    return CacheRegistry(entries)


_CACHE_REGISTRY_SINGLETON: CacheRegistry | None = None


def get_cache_registry() -> CacheRegistry:
    global _CACHE_REGISTRY_SINGLETON
    if _CACHE_REGISTRY_SINGLETON is None:
        _CACHE_REGISTRY_SINGLETON = _build_registry()
    return _CACHE_REGISTRY_SINGLETON