"""共通情報取得2: 選択状態に基づく取得実行ロジック

- UIは classes.basic.ui.common_info_selection_dialog に分離
- 既存「共通情報のみ取得」とは別経路として、取得対象を事前選択できる

取得モード:
- overwrite: 常に取得（上書き）
- older: 古い場合のみ取得
- missing: ローカルに無い場合のみ取得
- skip: 取得しない

古い判定(outdated_policy):
- bca: JSON内日時 → 取得記録 → mtime の順で「最終更新時刻」を決定
- ca: 取得記録 → mtime
- a: mtimeのみ

注意:
- HTTPアクセスは net.http_helpers 経由（api_request_helperも内部で委譲）
- パスは config.common の定数/ヘルパーを優先
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from dateutil.parser import parse as parse_datetime

from config.common import (
    DATASET_JSON_CHUNKS_DIR,
    DATASET_JSON_PATH,
    GROUP_DETAIL_JSON_PATH,
    GROUP_JSON_PATH,
    GROUP_ORGNIZATION_DIR,
    GROUP_PROJECT_DIR,
    INFO_JSON_PATH,
    INSTRUMENT_JSON_CHUNKS_DIR,
    INSTRUMENTS_JSON_PATH,
    INSTRUMENT_TYPE_JSON_PATH,
    LICENSES_JSON_PATH,
    ORGANIZATION_JSON_PATH,
    OUTPUT_RDE_DATA_DIR,
    SAMPLES_DIR,
    SELF_JSON_PATH,
    SUBGROUP_DETAILS_DIR,
    SUBGROUP_JSON_PATH,
    SUBGROUP_REL_DETAILS_DIR,
    TEMPLATE_JSON_CHUNKS_DIR,
    TEMPLATE_JSON_PATH,
    get_dynamic_file_path,
)

logger = logging.getLogger(__name__)


class CommonInfo2Keys:
    TARGET_GROUP_PIPELINE = "group_pipeline"
    TARGET_SELF = "self"
    TARGET_ORGANIZATION = "organization"
    TARGET_INSTRUMENT_TYPE = "instrument_type"
    TARGET_TEMPLATE = "template"
    TARGET_INSTRUMENTS = "instruments"
    TARGET_LICENSES = "licenses"
    TARGET_INVOICE_SCHEMAS = "invoiceSchemas"
    TARGET_SAMPLES = "samples"
    TARGET_DATASET_LIST = "dataset_list"
    TARGET_INFO_GENERATE = "info_generate"
    TARGET_DATASET_DETAILS = "dataset_details"


@dataclass(frozen=True)
class CommonInfo2TargetSpec:
    target_id: str
    label: str
    kind: str  # list | dir | composite | generated
    kind_label: str
    primary_list_path: Optional[str] = None
    list_paths: tuple[str, ...] = ()
    dir_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class LocalStatus:
    status_label: str
    list_count: Optional[int]
    file_count: Optional[int]


def build_common_info2_target_specs(include_dataset_details: bool) -> list[CommonInfo2TargetSpec]:
    specs: list[CommonInfo2TargetSpec] = [
        CommonInfo2TargetSpec(
            target_id=CommonInfo2Keys.TARGET_SELF,
            label="ユーザー情報 (self.json)",
            kind="list",
            kind_label="一覧JSON",
            primary_list_path=SELF_JSON_PATH,
            list_paths=(SELF_JSON_PATH,),
        ),
        CommonInfo2TargetSpec(
            target_id=CommonInfo2Keys.TARGET_GROUP_PIPELINE,
            label="グループ階層 (group/groupDetail/subGroup + 個別subGroups等)",
            kind="composite",
            kind_label="複合",
            primary_list_path=GROUP_JSON_PATH,
            list_paths=(GROUP_JSON_PATH, GROUP_DETAIL_JSON_PATH, SUBGROUP_JSON_PATH),
            dir_paths=(GROUP_PROJECT_DIR, GROUP_ORGNIZATION_DIR, SUBGROUP_DETAILS_DIR, SUBGROUP_REL_DETAILS_DIR),
        ),
        CommonInfo2TargetSpec(
            target_id=CommonInfo2Keys.TARGET_ORGANIZATION,
            label="組織情報 (organization.json)",
            kind="list",
            kind_label="一覧JSON",
            primary_list_path=ORGANIZATION_JSON_PATH,
            list_paths=(ORGANIZATION_JSON_PATH,),
        ),
        CommonInfo2TargetSpec(
            target_id=CommonInfo2Keys.TARGET_INSTRUMENT_TYPE,
            label="装置タイプ (instrumentType.json)",
            kind="list",
            kind_label="一覧JSON",
            primary_list_path=INSTRUMENT_TYPE_JSON_PATH,
            list_paths=(INSTRUMENT_TYPE_JSON_PATH,),
        ),
        CommonInfo2TargetSpec(
            target_id=CommonInfo2Keys.TARGET_TEMPLATE,
            label="テンプレート一覧 (template.json)",
            kind="composite",
            kind_label="一覧+チャンク",
            primary_list_path=TEMPLATE_JSON_PATH,
            list_paths=(TEMPLATE_JSON_PATH,),
            dir_paths=(TEMPLATE_JSON_CHUNKS_DIR,),
        ),
        CommonInfo2TargetSpec(
            target_id=CommonInfo2Keys.TARGET_INVOICE_SCHEMAS,
            label="インボイススキーマ (invoiceSchemas/*.json)",
            kind="dir",
            kind_label="個別JSON",
            dir_paths=(get_dynamic_file_path("output/rde/data/invoiceSchemas"),),
        ),
        CommonInfo2TargetSpec(
            target_id=CommonInfo2Keys.TARGET_SAMPLES,
            label="サンプル情報 (samples/*.json)",
            kind="dir",
            kind_label="個別JSON",
            dir_paths=(SAMPLES_DIR,),
        ),
        CommonInfo2TargetSpec(
            target_id=CommonInfo2Keys.TARGET_INSTRUMENTS,
            label="設備一覧 (instruments.json)",
            kind="composite",
            kind_label="一覧+チャンク",
            primary_list_path=INSTRUMENTS_JSON_PATH,
            list_paths=(INSTRUMENTS_JSON_PATH,),
            dir_paths=(INSTRUMENT_JSON_CHUNKS_DIR,),
        ),
        CommonInfo2TargetSpec(
            target_id=CommonInfo2Keys.TARGET_LICENSES,
            label="利用ライセンス (licenses.json)",
            kind="list",
            kind_label="一覧JSON",
            primary_list_path=LICENSES_JSON_PATH,
            list_paths=(LICENSES_JSON_PATH,),
        ),
        CommonInfo2TargetSpec(
            target_id=CommonInfo2Keys.TARGET_DATASET_LIST,
            label="データセット一覧 (dataset.json)",
            kind="composite",
            kind_label="一覧+チャンク",
            primary_list_path=DATASET_JSON_PATH,
            list_paths=(DATASET_JSON_PATH,),
            dir_paths=(DATASET_JSON_CHUNKS_DIR,),
        ),
        CommonInfo2TargetSpec(
            target_id=CommonInfo2Keys.TARGET_INFO_GENERATE,
            label="統合情報生成 (info.json)",
            kind="generated",
            kind_label="生成",
            primary_list_path=INFO_JSON_PATH,
            list_paths=(INFO_JSON_PATH,),
        ),
    ]

    if include_dataset_details:
        specs.append(
            CommonInfo2TargetSpec(
                target_id=CommonInfo2Keys.TARGET_DATASET_DETAILS,
                label="個別データセット詳細 (datasets/*.json)",
                kind="dir",
                kind_label="個別JSON",
                dir_paths=(get_dynamic_file_path("output/rde/data/datasets"),),
            )
        )

    return specs


def _iter_json_files(dir_path: str) -> list[Path]:
    p = Path(dir_path)
    if not p.exists() or not p.is_dir():
        return []

    files = []
    for fp in p.glob("*.json"):
        name = fp.name
        if name in {"summary.json"}:
            continue
        if name.endswith(".backup"):
            continue
        if name.startswith("dataset_chunk_") or name.startswith("template_chunk_") or name.startswith("instrument_chunk_"):
            # チャンクファイルは一覧生成用なので個別JSON数から除外
            continue
        files.append(fp)
    return files


def compute_local_timestamp_for_target(spec: CommonInfo2TargetSpec) -> Optional[datetime]:
    """対象のローカル最新タイムスタンプ（UTC）を返す。

    - list_paths: 最大mtime
    - dir_paths: *.json（_iter_json_filesで除外規則を統一）の最大mtime
    """

    latest_ts: Optional[float] = None

    for p in spec.list_paths:
        dt = _mtime_utc(p)
        if dt is None:
            continue
        ts = dt.timestamp()
        latest_ts = ts if latest_ts is None else max(latest_ts, ts)

    for d in spec.dir_paths:
        for fp in _iter_json_files(d):
            try:
                ts = fp.stat().st_mtime
            except OSError:
                continue
            latest_ts = ts if latest_ts is None else max(latest_ts, ts)

    return datetime.fromtimestamp(latest_ts, tz=timezone.utc) if latest_ts is not None else None


def _count_list_elements(path: str) -> Optional[int]:
    try:
        fp = Path(path)
        if not fp.exists():
            return None
        with fp.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        if isinstance(payload, list):
            return len(payload)
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                return len(data)
            included = payload.get("included")
            if isinstance(included, list):
                return len(included)
            return len(payload)
        return 1
    except Exception:
        return None


def compute_local_status_for_target(spec: CommonInfo2TargetSpec) -> LocalStatus:
    list_count = _count_list_elements(spec.primary_list_path) if spec.primary_list_path else None

    file_count: Optional[int] = None
    if spec.dir_paths:
        total = 0
        any_dir = False
        for d in spec.dir_paths:
            any_dir = True
            total += len(_iter_json_files(d))
        file_count = total if any_dir else None

    # ステータス: 有/無/一部
    exists_flags: list[bool] = []
    for p in spec.list_paths:
        exists_flags.append(Path(p).exists())
    for d in spec.dir_paths:
        exists_flags.append(Path(d).exists() and bool(list(Path(d).glob("*.json"))))

    if not exists_flags:
        status = "-"
    elif all(exists_flags):
        status = "取得済"
    elif any(exists_flags):
        status = "一部"
    else:
        status = "未取得"

    return LocalStatus(status_label=status, list_count=list_count, file_count=file_count)


def _meta_path_for_target(target_id: str) -> str:
    return get_dynamic_file_path(f"output/rde/data/.fetch_meta/{target_id}.json")


def _load_fetch_meta(target_id: str) -> Optional[Dict[str, Any]]:
    meta_path = Path(_meta_path_for_target(target_id))
    if not meta_path.exists():
        return None
    try:
        with meta_path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _save_fetch_meta(target_id: str, elapsed_seconds: Optional[float] = None) -> None:
    meta_path = Path(_meta_path_for_target(target_id))
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if elapsed_seconds is not None:
        try:
            payload["elapsed_seconds"] = float(elapsed_seconds)
        except Exception:
            pass
    try:
        with meta_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=False, indent=2)
    except Exception:
        pass


def save_fetch_meta(target_id: str, elapsed_seconds: Optional[float] = None) -> None:
    """指定 target_id の fetch_meta を保存する（fetched_at + 任意で elapsed_seconds）。"""
    _save_fetch_meta(target_id, elapsed_seconds=elapsed_seconds)


def _extract_datetime_from_json(path: str) -> Optional[datetime]:
    """JSON内の日時っぽいフィールドを探してUTC datetimeにする（見つからなければNone）"""
    try:
        fp = Path(path)
        if not fp.exists():
            return None
        with fp.open("r", encoding="utf-8") as f:
            payload = json.load(f)

        candidates: list[str] = []
        if isinstance(payload, dict):
            meta = payload.get("meta")
            if isinstance(meta, dict):
                for k in ("updatedAt", "generatedAt", "createdAt", "fetchedAt"):
                    v = meta.get(k)
                    if isinstance(v, str) and v:
                        candidates.append(v)

            data = payload.get("data")
            if isinstance(data, dict):
                attr = data.get("attributes")
                if isinstance(attr, dict):
                    for k in ("modified", "updated", "created"):
                        v = attr.get(k)
                        if isinstance(v, str) and v:
                            candidates.append(v)
            elif isinstance(data, list) and data:
                # 先頭要素のattributesを軽く見る
                first = data[0]
                if isinstance(first, dict):
                    attr = first.get("attributes")
                    if isinstance(attr, dict):
                        for k in ("modified", "updated", "created"):
                            v = attr.get(k)
                            if isinstance(v, str) and v:
                                candidates.append(v)

        for raw in candidates:
            try:
                dt = parse_datetime(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:
                continue

        return None
    except Exception:
        return None


def _mtime_utc(path: str) -> Optional[datetime]:
    try:
        ts = os.path.getmtime(path)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    except Exception:
        return None


def _is_stale(target_id: str, anchor_path: str, policy: str, stale_days: int) -> bool:
    """ローカル情報から「古い」を判定する（olderモード用）"""
    threshold = datetime.now(timezone.utc) - timedelta(days=max(stale_days, 0))

    dt: Optional[datetime] = None

    def pick_b() -> Optional[datetime]:
        return _extract_datetime_from_json(anchor_path)

    def pick_c() -> Optional[datetime]:
        meta = _load_fetch_meta(target_id)
        if isinstance(meta, dict):
            fetched_at = meta.get("fetched_at")
            if isinstance(fetched_at, str) and fetched_at:
                try:
                    v = parse_datetime(fetched_at)
                    if v.tzinfo is None:
                        v = v.replace(tzinfo=timezone.utc)
                    return v.astimezone(timezone.utc)
                except Exception:
                    return None
        return None

    def pick_a() -> Optional[datetime]:
        return _mtime_utc(anchor_path)

    if policy == "bca":
        dt = pick_b() or pick_c() or pick_a()
    elif policy == "ca":
        dt = pick_c() or pick_a()
    else:
        dt = pick_a()

    if dt is None:
        # 情報が無ければ古い扱い（安全側）
        return True

    return dt < threshold


def _mode_for(selection_state: Dict[str, Any], target_id: str) -> str:
    targets = selection_state.get("targets")
    if isinstance(targets, dict):
        row = targets.get(target_id)
        if isinstance(row, dict):
            mode = row.get("mode")
            if isinstance(mode, str) and mode:
                return mode
    return "older"


def _enabled_for(selection_state: Dict[str, Any], target_id: str) -> bool:
    targets = selection_state.get("targets")
    if isinstance(targets, dict):
        row = targets.get(target_id)
        if isinstance(row, dict):
            enabled = row.get("enabled")
            if isinstance(enabled, bool):
                return enabled
    return True


def fetch_common_info_with_selection_logic(
    bearer_token: str,
    parent,
    webview,
    selection_state: Dict[str, Any],
    progress_callback=None,
):
    """選択状態に基づいて共通情報を取得する（ProgressWorkerから呼ばれる）"""
    from .basic_info_logic import (
        _make_headers,
        _subgroups_folder_complete,
        extract_users_and_subgroups,
        fetch_dataset_list_only,
        fetch_invoice_schemas,
        fetch_instrument_type_info_from_api,
        fetch_instruments_info_from_api,
        fetch_licenses_info_from_api,
        fetch_organization_info_from_api,
        fetch_sample_info_only,
        fetch_self_info_from_api,
        fetch_template_info_from_api,
        fetch_all_dataset_info,
        run_group_hierarchy_pipeline,
    )

    include_dataset_details = bool(selection_state.get("include_dataset_details"))
    outdated_policy = str(selection_state.get("outdated_policy") or "bca")
    stale_days = int(selection_state.get("stale_days") or 0)

    specs = {s.target_id: s for s in build_common_info2_target_specs(include_dataset_details)}

    ordered_ids = [
        CommonInfo2Keys.TARGET_SELF,
        CommonInfo2Keys.TARGET_GROUP_PIPELINE,
        CommonInfo2Keys.TARGET_SAMPLES,
        CommonInfo2Keys.TARGET_ORGANIZATION,
        CommonInfo2Keys.TARGET_INSTRUMENT_TYPE,
        CommonInfo2Keys.TARGET_DATASET_LIST,
        CommonInfo2Keys.TARGET_TEMPLATE,
        CommonInfo2Keys.TARGET_INVOICE_SCHEMAS,
        CommonInfo2Keys.TARGET_INSTRUMENTS,
        CommonInfo2Keys.TARGET_LICENSES,
        CommonInfo2Keys.TARGET_INFO_GENERATE,
        CommonInfo2Keys.TARGET_DATASET_DETAILS,
    ]

    total_steps = sum(1 for tid in ordered_ids if tid in specs and _enabled_for(selection_state, tid))
    total_steps = max(total_steps, 1)
    current_step = 0

    def emit(step_message: str, pct_in_step: int = 0) -> bool:
        if not progress_callback:
            return True
        overall = int((current_step / total_steps) * 100)
        overall = max(0, min(100, overall))
        return progress_callback(overall, 100, step_message)

    def should_fetch_target(spec: CommonInfo2TargetSpec, mode: str) -> bool:
        if mode == "skip":
            return False
        if mode == "overwrite":
            return True

        anchor = spec.primary_list_path
        if not anchor and spec.dir_paths:
            # dir/compositeの場合は、ローカル最新ファイルをアンカーにする（stale判定の精度向上）
            anchor = None
            for d in spec.dir_paths:
                files = _iter_json_files(d)
                if not files:
                    continue
                try:
                    latest = max(files, key=lambda x: x.stat().st_mtime)
                    anchor = str(latest)
                    break
                except Exception:
                    continue
            if not anchor:
                # フォールバック: ディレクトリ自体
                anchor = spec.dir_paths[0]
        if not anchor:
            return mode != "skip"

        exists = Path(anchor).exists() and (Path(anchor).is_file() or any(Path(anchor).glob("*.json")))

        if mode == "missing":
            return not exists
        if mode == "older":
            if not exists:
                return True
            return _is_stale(spec.target_id, anchor, outdated_policy, stale_days)
        return True

    # 実行
    import time

    for tid in ordered_ids:
        spec = specs.get(tid)
        if not spec:
            continue
        if not _enabled_for(selection_state, tid):
            continue

        mode = _mode_for(selection_state, tid)
        current_step += 1

        if not emit(f"準備中: {spec.label}"):
            return "キャンセルされました"

        if not should_fetch_target(spec, mode):
            logger.info("共通情報取得2: スキップ（条件未満）: %s mode=%s", tid, mode)
            continue

        # ---- 各ターゲット実行 ----
        if tid == CommonInfo2Keys.TARGET_SELF:
            emit("ユーザー情報取得中...")
            t0 = time.perf_counter()
            fetch_self_info_from_api(bearer_token, parent_widget=parent)
            save_fetch_meta(tid, elapsed_seconds=(time.perf_counter() - t0))

        elif tid == CommonInfo2Keys.TARGET_GROUP_PIPELINE:
            emit("グループ階層取得中...")

            group_files_ready = all(Path(p).exists() for p in (GROUP_JSON_PATH, GROUP_DETAIL_JSON_PATH, SUBGROUP_JSON_PATH))
            subgroups_complete = _subgroups_folder_complete() if group_files_ready else False
            use_cache = (mode != "overwrite") and group_files_ready and subgroups_complete

            if use_cache:
                logger.info("共通情報取得2: グループ階層はキャッシュを再利用します")
            else:
                # force_downloadはoverwrite時に強制
                force_download = mode == "overwrite"
                t0 = time.perf_counter()
                run_group_hierarchy_pipeline(
                    bearer_token=bearer_token,
                    parent_widget=parent,
                    preferred_program_id=None,
                    progress_callback=progress_callback,
                    force_download=force_download,
                )
                save_fetch_meta(tid, elapsed_seconds=(time.perf_counter() - t0))

        elif tid == CommonInfo2Keys.TARGET_SAMPLES:
            emit("サンプル情報取得中...")
            if not Path(SUBGROUP_JSON_PATH).exists():
                raise Exception("サンプル情報取得には subGroup.json が必要です（グループ階層取得を先に実行してください）")
            t0 = time.perf_counter()
            fetch_sample_info_only(bearer_token, output_dir=get_dynamic_file_path("output/rde/data"), progress_callback=progress_callback)
            save_fetch_meta(tid, elapsed_seconds=(time.perf_counter() - t0))

        elif tid == CommonInfo2Keys.TARGET_ORGANIZATION:
            emit("組織情報取得中...")
            t0 = time.perf_counter()
            fetch_organization_info_from_api(bearer_token, ["output", "rde", "data", "organization.json"])
            save_fetch_meta(tid, elapsed_seconds=(time.perf_counter() - t0))

        elif tid == CommonInfo2Keys.TARGET_INSTRUMENT_TYPE:
            emit("装置タイプ情報取得中...")
            t0 = time.perf_counter()
            fetch_instrument_type_info_from_api(bearer_token, ["output", "rde", "data", "instrumentType.json"])
            save_fetch_meta(tid, elapsed_seconds=(time.perf_counter() - t0))

        elif tid == CommonInfo2Keys.TARGET_DATASET_LIST:
            emit("データセット一覧取得中...")
            t0 = time.perf_counter()
            fetch_dataset_list_only(bearer_token, output_dir=get_dynamic_file_path("output/rde/data"))
            save_fetch_meta(tid, elapsed_seconds=(time.perf_counter() - t0))

        elif tid == CommonInfo2Keys.TARGET_TEMPLATE:
            emit("テンプレート一覧取得中...")
            t0 = time.perf_counter()
            fetch_template_info_from_api(bearer_token)
            save_fetch_meta(tid, elapsed_seconds=(time.perf_counter() - t0))

        elif tid == CommonInfo2Keys.TARGET_INVOICE_SCHEMAS:
            emit("インボイススキーマ取得中...")
            if not Path(TEMPLATE_JSON_PATH).exists():
                raise Exception("インボイススキーマ取得には template.json が必要です（テンプレート一覧取得を先に実行してください）")
            if not Path(SUBGROUP_JSON_PATH).exists():
                raise Exception("インボイススキーマ取得には subGroup.json が必要です（グループ階層取得を先に実行してください）")
            t0 = time.perf_counter()
            fetch_invoice_schemas(bearer_token, output_dir=get_dynamic_file_path("output/rde/data"), progress_callback=progress_callback)
            save_fetch_meta(tid, elapsed_seconds=(time.perf_counter() - t0))

        elif tid == CommonInfo2Keys.TARGET_INSTRUMENTS:
            emit("設備一覧取得中...")
            t0 = time.perf_counter()
            fetch_instruments_info_from_api(bearer_token)
            save_fetch_meta(tid, elapsed_seconds=(time.perf_counter() - t0))

        elif tid == CommonInfo2Keys.TARGET_LICENSES:
            emit("ライセンス情報取得中...")
            t0 = time.perf_counter()
            fetch_licenses_info_from_api(bearer_token)
            save_fetch_meta(tid, elapsed_seconds=(time.perf_counter() - t0))

        elif tid == CommonInfo2Keys.TARGET_INFO_GENERATE:
            emit("info.json生成中...")
            # info.json生成は subGroup.json が必要
            if not Path(SUBGROUP_JSON_PATH).exists():
                raise Exception("info.json生成には subGroup.json が必要です（グループ階層取得を先に実行してください）")

            t0 = time.perf_counter()

            with open(SUBGROUP_JSON_PATH, "r", encoding="utf-8") as f:
                sub_group_data = json.load(f)
            users, subgroups = extract_users_and_subgroups(sub_group_data)

            group_id = None
            if Path(GROUP_DETAIL_JSON_PATH).exists():
                try:
                    with open(GROUP_DETAIL_JSON_PATH, "r", encoding="utf-8") as gf:
                        group_detail = json.load(gf)
                    group_id = (group_detail.get("data") or {}).get("id") if isinstance(group_detail, dict) else None
                except Exception:
                    group_id = None

            info = {
                'group_id': group_id,
                'project_group_id': (sub_group_data.get('data', {}) if isinstance(sub_group_data, dict) else {}).get('id'),
                'users': users,
                'subgroups': subgroups,
            }
            save_path = get_dynamic_file_path("output/rde/data/info.json")
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as fp:
                json.dump(info, fp, ensure_ascii=False, indent=2)
            save_fetch_meta(tid, elapsed_seconds=(time.perf_counter() - t0))

        elif tid == CommonInfo2Keys.TARGET_DATASET_DETAILS:
            emit("個別データセット詳細取得中...")
            # dataset.jsonが無ければ先に取得
            if not Path(DATASET_JSON_PATH).exists():
                t0_list = time.perf_counter()
                fetch_dataset_list_only(bearer_token, output_dir=get_dynamic_file_path("output/rde/data"))
                save_fetch_meta(CommonInfo2Keys.TARGET_DATASET_LIST, elapsed_seconds=(time.perf_counter() - t0_list))

            t0 = time.perf_counter()

            if mode == "overwrite":
                # 全件取得（既存を問わず上書き）
                dataset_json_path = get_dynamic_file_path("output/rde/data/dataset.json")
                with open(dataset_json_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                datasets = payload.get("data", []) if isinstance(payload, dict) else []
                detail_dir = get_dynamic_file_path("output/rde/data/datasets")
                Path(detail_dir).mkdir(parents=True, exist_ok=True)
                # 進捗を大雑把に更新
                total = max(len(datasets), 1)
                for idx, ds in enumerate(datasets, 1):
                    ds_id = ds.get("id") if isinstance(ds, dict) else None
                    if not ds_id:
                        continue
                    if progress_callback:
                        progress_callback(int((idx / total) * 100), 100, f"データセット詳細取得 {idx}/{total}")
                    from .basic_info_logic import fetch_dataset_info_respectively_from_api
                    fetch_dataset_info_respectively_from_api(bearer_token, ds_id, output_dir=detail_dir)
            else:
                # older/missing は既存のロジック（modified比較）を活用
                fetch_all_dataset_info(
                    bearer_token=bearer_token,
                    output_dir=get_dynamic_file_path("output/rde/data"),
                    onlySelf=False,
                    searchWords=None,
                    searchWordsBatch=None,
                    progress_callback=progress_callback,
                )
            save_fetch_meta(tid, elapsed_seconds=(time.perf_counter() - t0))

    return "共通情報取得2が正常に完了しました"
