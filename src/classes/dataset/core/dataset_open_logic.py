
from qt_compat.widgets import QMessageBox
import os
import json
from qt_compat.widgets import QComboBox, QLabel, QVBoxLayout, QHBoxLayout, QWidget
from classes.utils.api_request_helper import api_request  # refactored to use api_request_helper
from core.bearer_token_manager import BearerTokenManager
from config.common import DATASET_JSON_PATH, OUTPUT_RDE_DATA_DIR
from classes.dataset.util.show_event_refresh import RefreshOnShowWidget

import logging

# ロガー設定
logger = logging.getLogger(__name__)


def _format_any_as_pretty_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)
    return str(value)


def _build_dataset_open_error_detail_text(payload_str: str, result) -> str:
    request_text = payload_str or ""
    response_text = _format_any_as_pretty_text(result)
    return (
        "=== Request (Payload) ===\n"
        f"{request_text}\n"
        "\n=== Response / Error ===\n"
        f"{response_text}\n"
    )


def _extract_related_datasets_resource_not_found_hint(result) -> str | None:
    """Build a user-facing hint when 422 likely comes from relatedDatasets.

    RDE API returns 422 for invalid relationships; one known case is
    providing non-existing or non-accessible dataset ids in relatedDatasets.
    """

    if not isinstance(result, dict):
        return None

    status_code = result.get("status_code")
    if status_code is not None and status_code != 422:
        return None

    response_json = result.get("response_json")
    if not isinstance(response_json, dict):
        return None

    errors = response_json.get("errors")
    if not isinstance(errors, list):
        return None

    for err in errors:
        if not isinstance(err, dict):
            continue
        detail = str(err.get("detail") or "")
        pointer = str(((err.get("source") or {}) if isinstance(err.get("source"), dict) else {}).get("pointer") or "")

        looks_like_not_found = ("resource not found" in detail.lower()) and ("type=dataset" in detail)
        points_to_related = "relatedDatasets" in pointer

        if looks_like_not_found and points_to_related:
            return (
                "（確認のお願い）関連データセット（relatedDatasets）に、存在しないデータセット、または参照権限のないデータセットIDが含まれている可能性があります。\n"
                "既存データセット読み込みから自動反映した場合も含め、関連データセットの指定内容を確認してください。"
            )

    return None


def _format_dataset_open_error_summary(result) -> str:
    if isinstance(result, dict):
        status = result.get("status_code")
        err = result.get("error")
        if status is not None and err:
            return f"HTTP {status}: {err}"
        if err:
            return str(err)
    return str(result)


def _show_dataset_open_error_dialog(parent, payload_str: str, result) -> None:
    from qt_compat.widgets import QMessageBox, QPushButton, QDialog, QVBoxLayout, QTextEdit

    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle("データセット開設エラー")
    msg_box.setIcon(QMessageBox.Critical)
    hint = _extract_related_datasets_resource_not_found_hint(result)
    summary = _format_dataset_open_error_summary(result)
    if hint:
        msg_box.setText(f"データセットの開設に失敗しました。\n{summary}\n\n{hint}")
    else:
        msg_box.setText(f"データセットの開設に失敗しました。\n{summary}")
    ok_btn = msg_box.addButton(QMessageBox.Ok)
    detail_btn = QPushButton("リクエスト/レスポンス全文表示")
    msg_box.addButton(detail_btn, QMessageBox.ActionRole)
    msg_box.setDefaultButton(ok_btn)

    detail_text = _build_dataset_open_error_detail_text(payload_str, result)

    def show_detail():
        dlg = QDialog(parent)
        dlg.setWindowTitle("リクエスト/レスポンス 全文表示")
        layout = QVBoxLayout(dlg)
        text_edit = QTextEdit(dlg)
        text_edit.setReadOnly(True)
        text_edit.setPlainText(detail_text)
        text_edit.setMinimumSize(650, 450)
        layout.addWidget(text_edit)
        dlg.setLayout(layout)
        dlg.exec_()

    detail_btn.clicked.connect(show_detail)
    msg_box.exec_()


def _load_dataset_id_set_from_dataset_json() -> set[str]:
    try:
        with open(DATASET_JSON_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return {
            str(it.get("id"))
            for it in (data or {}).get("data", []) or []
            if isinstance(it, dict) and it.get("id")
        }
    except Exception:
        return set()


def _build_template_entries(
    template_data: dict,
    instrument_map: dict,
    allowed_instrument_ids: set[str] | None,
) -> tuple[list[dict], list[str], list[tuple[str, str]]]:
    """Build template combo entries.

    Returns:
        - template_list: list of dicts (id, datasetType, nameJa, instruments)
        - template_items: list of display labels
        - combo_items: list of (label, template_id) to add to QComboBox

    Filtering:
        - allowed_instrument_ids is None: include all templates
        - otherwise: include templates that reference at least one instrument id in allowed_instrument_ids
    """
    template_list: list[dict] = []
    template_items: list[str] = []
    combo_items: list[tuple[str, str]] = []

    for item in (template_data or {}).get("data", []) or []:
        tid = item.get("id", "")
        dtype = item.get("attributes", {}).get("datasetType", "")
        name_ja = item.get("attributes", {}).get("nameJa", tid)

        insts = item.get("relationships", {}).get("instruments", {}).get("data", []) or []
        inst_labels: list[str] = []
        has_allowed_instrument = allowed_instrument_ids is None

        for inst in insts:
            inst_id = inst.get("id")
            if not inst_id:
                continue

            if allowed_instrument_ids is not None and inst_id in allowed_instrument_ids:
                has_allowed_instrument = True

            inst_info = instrument_map.get(inst_id)
            if not inst_info:
                continue

            label_parts = [inst_info.get("nameJa", "")]
            if inst_info.get("localId"):
                label_parts.append(f"[{inst_info['localId']}]")
            if inst_info.get("modelNumber"):
                label_parts.append(f"({inst_info['modelNumber']})")
            inst_label = " ".join([p for p in label_parts if p])
            if inst_label:
                inst_labels.append(inst_label)

        if not has_allowed_instrument:
            continue

        inst_label_joined = ", ".join(inst_labels) if inst_labels else ""
        label = f"{name_ja} ({dtype})"
        if inst_label_joined:
            label += f" | {inst_label_joined}"

        template_list.append({"id": tid, "datasetType": dtype, "nameJa": name_ja, "instruments": inst_labels})
        template_items.append(label)
        combo_items.append((label, tid))

    return template_list, template_items, combo_items


def filter_groups_by_role(groups, filter_type="member", user_id=None):
    """グループを役割でフィルタリング"""
    filtered_groups = []
    for group in groups:
        roles = group.get("attributes", {}).get("roles", [])
        user_role = None
        
        # ユーザーの役割を取得（user_idが指定されている場合）
        if user_id:
            for role in roles:
                if role.get("userId") == user_id:
                    user_role = role.get("role")
                    break
        
        # フィルタ条件に応じて判定
        if filter_type == "none":  # フィルタなし
            filtered_groups.append(group)
        elif filter_type == "member":  # デフォルト：何らかの役割を持つ
            if user_role:
                filtered_groups.append(group)
        elif filter_type == "owner":  # OWNER のみ
            if user_role == "OWNER":
                filtered_groups.append(group)
        elif filter_type == "assistant":  # ASSISTANT のみ
            if user_role == "ASSISTANT":
                filtered_groups.append(group)
        elif filter_type == "owner_assistant":  # OWNER または ASSISTANT
            if user_role in ["OWNER", "ASSISTANT"]:
                filtered_groups.append(group)
        elif filter_type == "all_roles":  # OWNER、ASSISTANT、MEMBER、AGENT、VIEWER
            if user_role in ["OWNER", "ASSISTANT", "MEMBER", "AGENT", "VIEWER"]:
                filtered_groups.append(group)
    
    return filtered_groups


# 事前に選択されたグループ情報を引数で受け取る形に変更
def _parse_related_links_text(related_links_text: str | None) -> list[dict]:
    related_links_text = (related_links_text or "").strip()
    related_links: list[dict] = []
    if not related_links_text:
        return related_links
    # TITLE:URL をカンマ区切りで受け付ける
    items = related_links_text.split(',')
    for item in items:
        item = item.strip()
        if not item:
            continue
        if ':' not in item:
            continue
        title, url = item.split(':', 1)
        title = title.strip()
        url = url.strip()
        if title and url:
            related_links.append({"title": title, "url": url})
    return related_links


def _build_dataset_create_payload(
    *,
    group_id: str,
    manager_id: str,
    grant_number: str,
    dataset_name: str,
    embargo_date_str: str,
    template_id: str,
    dataset_type: str,
    share_core_scope: bool,
    anonymize: bool,
    description: str | None = None,
    related_links_text: str | None = None,
    tags: list[str] | None = None,
    related_dataset_ids: list[str] | None = None,
) -> tuple[dict, str]:
    # embargoDate
    embargo_date = (embargo_date_str or "").strip() or "2026-03-31"
    embargo_date_iso = embargo_date + "T03:00:00.000Z"

    payload: dict = {
        "data": {
            "type": "dataset",
            "attributes": {
                "datasetType": (dataset_type or "ANALYSIS"),
                "name": (dataset_name or "").strip(),
                "grantNumber": (grant_number or "").strip(),
                "embargoDate": embargo_date_iso,
                "dataListingType": "GALLERY",
                "sharingPolicies": [
                    {
                        "scopeId": "4df8da18-a586-4a0d-81cb-ff6c6f52e70f",
                        "permissionToView": True,
                        "permissionToDownload": False,
                    },
                    {
                        "scopeId": "22aec474-bbf2-4826-bf63-60c82d75df41",
                        "permissionToView": bool(share_core_scope),
                        "permissionToDownload": False,
                    },
                ],
                "isAnonymized": bool(anonymize),
            },
            "relationships": {
                "group": {"data": {"type": "group", "id": group_id}},
                "manager": {"data": {"type": "user", "id": manager_id}},
                "template": {"data": {"type": "datasetTemplate", "id": template_id}},
            },
        }
    }

    # Optional metadata for "新規開設2"
    description = (description or "").strip()
    if description:
        payload["data"]["attributes"]["description"] = description

    parsed_links = _parse_related_links_text(related_links_text)
    if parsed_links:
        payload["data"]["attributes"]["relatedLinks"] = parsed_links

    if tags:
        normalized_tags = [t.strip() for t in tags if isinstance(t, str) and t.strip()]
        if normalized_tags:
            payload["data"]["attributes"]["tags"] = normalized_tags

    if related_dataset_ids:
        rel_ids = [rid for rid in related_dataset_ids if isinstance(rid, str) and rid.strip()]
        if rel_ids:
            # Prevent 422 by excluding stale/nonexistent dataset IDs.
            valid_ids = _load_dataset_id_set_from_dataset_json()
            if valid_ids:
                filtered_rel_ids = [rid for rid in rel_ids if rid in valid_ids]
                dropped = [rid for rid in rel_ids if rid not in valid_ids]
                if dropped:
                    logger.warning("relatedDatasets: dataset.json に存在しないIDを除外しました: %s", dropped)
                rel_ids = filtered_rel_ids
            if rel_ids:
                payload["data"]["relationships"]["relatedDatasets"] = {
                    "data": [{"type": "dataset", "id": rid} for rid in rel_ids]
                }

    payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
    return payload, payload_str


def run_dataset_bulk_open_logic(
    parent,
    bearer_token,
    group_info,
    bulk_items: list[dict],
    embargo_date_str: str,
    share_core_scope: bool,
    anonymize: bool,
    *,
    manager_user_id: str | None = None,
    description: str | None = None,
    related_links_text: str | None = None,
    tags: list[str] | None = None,
    related_dataset_ids: list[str] | None = None,
):
    # Bearer Token統一管理システムで取得
    if not bearer_token:
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(parent)
        if not bearer_token:
            QMessageBox.warning(parent, "認証エラー", "Bearer Tokenが取得できません。ログインを確認してください。")
            return

    if group_info is None:
        QMessageBox.warning(parent, "グループ情報エラー", "グループが選択されていません。")
        return

    group_id = group_info.get("id")
    group_attr = group_info.get("attributes", {})
    subjects = group_attr.get("subjects", [])
    grant_number = group_info.get("grantNumber") or (subjects[0].get("grantNumber") if subjects else "")

    owner_id = None
    for role in group_attr.get("roles", []):
        if role.get("role") == "OWNER":
            owner_id = role.get("userId")
            break
    manager_id = manager_user_id or owner_id
    if not (group_id and manager_id and grant_number):
        QMessageBox.warning(parent, "グループ情報エラー", "グループID/管理者/課題番号が取得できませんでした。")
        return

    # Build payloads
    items: list[dict] = [it for it in (bulk_items or []) if isinstance(it, dict)]
    if not items:
        QMessageBox.warning(parent, "入力エラー", "まとめて開設: 対象テンプレートがありません。")
        return

    payloads: list[dict] = []
    payload_strs: list[str] = []

    for it in items:
        template_id = str(it.get("template_id") or "").strip()
        dataset_name = str(it.get("dataset_name") or "").strip()
        dataset_type = str(it.get("dataset_type") or "ANALYSIS").strip() or "ANALYSIS"
        if not template_id or not dataset_name:
            QMessageBox.warning(parent, "入力エラー", "まとめて開設: テンプレート/データセット名が未入力の行があります。")
            return
        payload, payload_str = _build_dataset_create_payload(
            group_id=str(group_id),
            manager_id=str(manager_id),
            grant_number=str(grant_number),
            dataset_name=dataset_name,
            embargo_date_str=embargo_date_str,
            template_id=template_id,
            dataset_type=dataset_type,
            share_core_scope=share_core_scope,
            anonymize=anonymize,
            description=description,
            related_links_text=related_links_text,
            tags=tags,
            related_dataset_ids=related_dataset_ids,
        )
        payloads.append(payload)
        payload_strs.append(payload_str)

    # Confirmation dialog (common + variable)
    common_attr = payloads[0]["data"]["attributes"]
    count = len(payloads)
    variable_lines: list[str] = []
    for idx, it in enumerate(items, start=1):
        tlabel = str(it.get("template_text") or it.get("template_id") or "")
        dname = str(it.get("dataset_name") or "")
        variable_lines.append(f"{idx}. {dname} / {tlabel}")

    simple_text = (
        "本当にデータセットをまとめて開設しますか？\n\n"
        "【共通】\n"
        f"課題番号: {common_attr.get('grantNumber')}\n"
        f"データセットを匿名にする: {common_attr.get('isAnonymized')}\n"
        f"エンバーゴ期間終了日: {common_attr.get('embargoDate')}\n"
        f"共有範囲: {common_attr.get('sharingPolicies')}\n"
        f"説明: {'入力あり' if common_attr.get('description') else '未入力'}\n"
        f"関連情報: {len(common_attr.get('relatedLinks', []) or [])}件\n"
        f"TAG: {', '.join(common_attr.get('tags', []) or [])}\n"
        f"関連データセット: {len(payloads[0]['data'].get('relationships', {}).get('relatedDatasets', {}).get('data', []) or [])}件\n"
        "\n"
        "【可変】\n"
        f"作成件数: {count}件\n"
        + "\n".join(variable_lines[:20])
        + ("\n..." if len(variable_lines) > 20 else "")
        + "\n\nこの操作はRDEに新規データセットを作成します。"
    )

    from qt_compat.widgets import QPushButton, QDialog, QVBoxLayout, QTextEdit

    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle("データセット開設の確認")
    msg_box.setIcon(QMessageBox.Question)
    msg_box.setText(simple_text)
    yes_btn = msg_box.addButton(QMessageBox.Yes)
    no_btn = msg_box.addButton(QMessageBox.No)
    detail_btn = QPushButton("詳細表示")
    msg_box.addButton(detail_btn, QMessageBox.ActionRole)
    msg_box.setDefaultButton(no_btn)
    msg_box.setStyleSheet("QLabel{font-family: 'Consolas'; font-size: 10pt;}")

    all_payloads_str = json.dumps(payloads, ensure_ascii=False, indent=2)

    def show_detail():
        dlg = QDialog(parent)
        dlg.setWindowTitle("Payload 全文表示（全件）")
        layout = QVBoxLayout(dlg)
        text_edit = QTextEdit(dlg)
        text_edit.setReadOnly(True)
        text_edit.setPlainText(all_payloads_str)
        text_edit.setMinimumSize(700, 500)
        layout.addWidget(text_edit)
        dlg.setLayout(layout)
        dlg.exec_()

    detail_btn.clicked.connect(show_detail)

    msg_box.exec_()
    if msg_box.clickedButton() != yes_btn:
        logger.info("データセットまとめて開設処理はユーザーによりキャンセルされました。")
        return

    created_ids: list[str] = []
    first_failure: tuple[str, object] | None = None

    for payload, payload_str in zip(payloads, payload_strs, strict=False):
        success, result = create_dataset(bearer_token, payload=payload)
        if success:
            try:
                did = result.get("data", {}).get("id") if isinstance(result, dict) else None
                if did:
                    created_ids.append(str(did))
            except Exception:
                pass
            continue
        if first_failure is None:
            first_failure = (payload_str, result)

    # データセット更新通知を発火（成功が1件でもあれば）
    if created_ids:
        try:
            from classes.dataset.util.dataset_refresh_notifier import get_dataset_refresh_notifier
            dataset_notifier = get_dataset_refresh_notifier()
            dataset_notifier.notify_refresh()
            logger.info("データセットまとめて開設: 更新通知を発火")
        except Exception as e:
            logger.warning("データセット更新通知の発火に失敗: %s", e)

    # 成功時にdataset.jsonを自動再取得（完了ダイアログなし）
    try:
        if created_ids and bearer_token:
            from qt_compat.core import QTimer

            def auto_refresh():
                try:
                    from classes.basic.core.basic_info_logic import auto_refresh_dataset_json
                    from classes.utils.progress_worker import SimpleProgressWorker
                    from classes.basic.ui.ui_basic_info import show_progress_dialog

                    worker = SimpleProgressWorker(
                        task_func=auto_refresh_dataset_json,
                        task_kwargs={"bearer_token": bearer_token},
                        task_name="データセット一覧自動更新",
                    )
                    show_progress_dialog(parent, "データセット一覧自動更新", worker, show_completion_dialog=False)

                    def show_completion_and_notify():
                        try:
                            QMessageBox.information(
                                parent,
                                "データセット開設完了",
                                f"データセットを{len(created_ids)}件開設しました。\n\nデータセット一覧も更新されました。",
                            )
                            from classes.dataset.util.dataset_refresh_notifier import get_dataset_refresh_notifier
                            get_dataset_refresh_notifier().notify_refresh()
                        except Exception as e:
                            logger.warning("完了ダイアログ表示・通知発火に失敗: %s", e)

                    QTimer.singleShot(3000, show_completion_and_notify)
                except Exception as e:
                    logger.error("データセット一覧自動更新でエラー: %s", e)
                    QMessageBox.critical(parent, "自動更新エラー", f"データセット開設には成功しましたが、一覧の自動更新に失敗しました。\n{e}")

            QTimer.singleShot(1000, auto_refresh)
    except Exception as e:
        logger.warning("データセット一覧自動更新の設定に失敗: %s", e)

    if first_failure is not None:
        payload_str, result = first_failure
        _show_dataset_open_error_dialog(parent, payload_str, result)

    # Keep legacy behavior (currently stubbed)
    try:
        update_dataset(bearer_token)
    except Exception:
        pass


def run_dataset_open_logic(
    parent,
    bearer_token,
    group_info,
    dataset_name,
    embargo_date_str,
    template_id,
    dataset_type,
    share_core_scope,
    anonymize,
    *,
    manager_user_id: str | None = None,
    description: str | None = None,
    related_links_text: str | None = None,
    tags: list[str] | None = None,
    related_dataset_ids: list[str] | None = None,
):
    logger.debug("run_dataset_open_logic: dataset_name=%s, embargo_date_str=%s, template_id=%s, dataset_type=%s, bearer_token=%s, group_info=%s", dataset_name, embargo_date_str, template_id, dataset_type, '[PRESENT]' if bearer_token else '[NONE]', group_info)
    logger.debug("share_core_scope=%s, anonymize=%s", share_core_scope, anonymize)
    
    # Bearer Token統一管理システムで取得
    if not bearer_token:
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(parent)
        if not bearer_token:
            QMessageBox.warning(parent, "認証エラー", "Bearer Tokenが取得できません。ログインを確認してください。")
            return
        logger.debug("Bearer Token obtained from BearerTokenManager")
    if group_info is None:
        QMessageBox.warning(parent, "グループ情報エラー", "グループが選択されていません。")
        return
    group_id = group_info.get("id")
    group_attr = group_info.get("attributes", {})
    group_name = group_attr.get("name", "")
    group_desc = group_attr.get("description", "")
    subjects = group_attr.get("subjects", [])
    # grantNumberはgroup_info直下にあればそれを優先、なければattributes.subjects[0].grantNumber
    grant_number = group_info.get("grantNumber") or (subjects[0].get("grantNumber") if subjects else "")
    # OWNERユーザーID取得
    owner_id = None
    for role in group_attr.get("roles", []):
        if role.get("role") == "OWNER":
            owner_id = role.get("userId")
            break

    manager_id = manager_user_id or owner_id
    if not (group_id and manager_id and grant_number):
        QMessageBox.warning(parent, "グループ情報エラー", "グループID/管理者/課題番号が取得できませんでした。")
        return

    # データセット名
    name = dataset_name if dataset_name else group_name
    template_id = template_id or "ARIM-R6_TU-504_TEM-STEM_20241121"
    dataset_type = dataset_type or "ANALYSIS"

    payload, payload_str = _build_dataset_create_payload(
        group_id=str(group_id),
        manager_id=str(manager_id),
        grant_number=str(grant_number),
        dataset_name=str(name),
        embargo_date_str=str(embargo_date_str or ""),
        template_id=str(template_id),
        dataset_type=str(dataset_type),
        share_core_scope=bool(share_core_scope),
        anonymize=bool(anonymize),
        description=description,
        related_links_text=related_links_text,
        tags=tags,
        related_dataset_ids=related_dataset_ids,
    )
    logger.debug("payload sharingPolicies: %s", payload['data']['attributes']['sharingPolicies'])
    logger.debug("payload isAnonymized: %s", payload['data']['attributes']['isAnonymized'])

    # 簡易表示用テキスト
    attr = payload['data']['attributes']
    simple_text = (
        f"本当にデータセットを開設しますか？\n\n"
        f"データセット名: {attr.get('name')}\n"
        f"課題番号: {attr.get('grantNumber')}\n"
        f"データセットを匿名にする: {attr.get('isAnonymized')}\n"
        f"エンバーゴ期間終了日: {attr.get('embargoDate')}\n"
        f"共有範囲: {attr.get('sharingPolicies')}\n"
        f"説明: {'入力あり' if attr.get('description') else '未入力'}\n"
        f"関連情報: {len(attr.get('relatedLinks', []) or [])}件\n"
        f"TAG: {', '.join(attr.get('tags', []) or [])}\n"
        f"関連データセット: {len(payload['data'].get('relationships', {}).get('relatedDatasets', {}).get('data', []) or [])}件\n"
        f"\nこの操作はRDEに新規データセットを作成します。"
    )

    from qt_compat.widgets import QMessageBox, QPushButton, QDialog, QVBoxLayout, QTextEdit
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle("データセット開設の確認")
    msg_box.setIcon(QMessageBox.Question)
    msg_box.setText(simple_text)
    yes_btn = msg_box.addButton(QMessageBox.Yes)
    no_btn = msg_box.addButton(QMessageBox.No)
    detail_btn = QPushButton("詳細表示")
    msg_box.addButton(detail_btn, QMessageBox.ActionRole)
    msg_box.setDefaultButton(no_btn)
    msg_box.setStyleSheet("QLabel{font-family: 'Consolas'; font-size: 10pt;}")

    def show_detail():
        dlg = QDialog(parent)
        dlg.setWindowTitle("Payload 全文表示")
        layout = QVBoxLayout(dlg)
        text_edit = QTextEdit(dlg)
        text_edit.setReadOnly(True)
        text_edit.setPlainText(payload_str)
        text_edit.setMinimumSize(600, 400)
        layout.addWidget(text_edit)
        dlg.setLayout(layout)
        dlg.exec_()
    detail_btn.clicked.connect(show_detail)

    reply = msg_box.exec_()
    if msg_box.clickedButton() == yes_btn:
        success, result = create_dataset(bearer_token, payload=payload)
        if success:
            dataset_id = result.get('data', {}).get('id', '不明') if isinstance(result, dict) else '不明'
            
            # データセット更新通知を発火
            try:
                from classes.dataset.util.dataset_refresh_notifier import get_dataset_refresh_notifier
                dataset_notifier = get_dataset_refresh_notifier()
                dataset_notifier.notify_refresh()
                logger.info("データセット開設成功: 更新通知を発火")
            except Exception as e:
                logger.warning("データセット更新通知の発火に失敗: %s", e)
            
            # 成功時にdataset.jsonを自動再取得（完了ダイアログなし）
            try:
                from qt_compat.core import QTimer
                def auto_refresh():
                    try:
                        from classes.basic.core.basic_info_logic import auto_refresh_dataset_json
                        from classes.utils.progress_worker import SimpleProgressWorker
                        from classes.basic.ui.ui_basic_info import show_progress_dialog
                        
                        if bearer_token:
                            # プログレス表示付きで自動更新（完了ダイアログなし）
                            worker = SimpleProgressWorker(
                                task_func=auto_refresh_dataset_json,
                                task_kwargs={'bearer_token': bearer_token},
                                task_name="データセット一覧自動更新"
                            )
                            
                            # プログレス表示（完了ダイアログなし）
                            progress_dialog = show_progress_dialog(parent, "データセット一覧自動更新", worker, show_completion_dialog=False)
                            
                            # dataset.json更新完了後に統合完了ダイアログを表示
                            def show_completion_and_notify():
                                try:
                                    # 統合完了ダイアログ表示
                                    QMessageBox.information(
                                        parent, 
                                        "データセット開設完了", 
                                        f"データセットの開設に成功しました。\nID: {dataset_id}\n\nデータセット一覧も更新されました。"
                                    )
                                    
                                    # 再度通知を発火
                                    from classes.dataset.util.dataset_refresh_notifier import get_dataset_refresh_notifier
                                    dataset_notifier = get_dataset_refresh_notifier()
                                    dataset_notifier.notify_refresh()
                                    logger.info("dataset.json更新完了: 再通知を発火")
                                except Exception as e:
                                    logger.warning("完了ダイアログ表示・通知発火に失敗: %s", e)
                            
                            # 自動更新完了後に統合ダイアログ表示（3秒後）
                            QTimer.singleShot(3000, show_completion_and_notify)
                            
                    except Exception as e:
                        logger.error("データセット一覧自動更新でエラー: %s", e)
                        # エラー時は即座にエラーダイアログを表示
                        QMessageBox.critical(parent, "自動更新エラー", f"データセット開設には成功しましたが、一覧の自動更新に失敗しました。\n{e}")
                
                # 少し遅延してから自動更新実行
                QTimer.singleShot(1000, auto_refresh)
                
            except Exception as e:
                logger.warning("データセット一覧自動更新の設定に失敗: %s", e)
                # エラー時は開設成功のみを通知
                QMessageBox.information(parent, "データセット開設", f"データセットの開設に成功しました。\nID: {dataset_id}\n\n（注意: 一覧の自動更新に失敗しました）")
        else:
            _show_dataset_open_error_dialog(parent, payload_str, result)
        update_dataset(bearer_token)
    else:
        logger.info("データセット開設処理はユーザーによりキャンセルされました。")

# グループ選択UIを事前に表示する関数
def create_group_select_widget(parent=None, *, register_subgroup_notifier: bool = True, connect_open_handler: bool = True):
    from qt_compat.widgets import QCheckBox
    # データ中核拠点広域シェア チェックボックス
    share_core_scope_checkbox = QCheckBox("データ中核拠点広域シェア（RDE全体での共有）を有効にする", parent)
    share_core_scope_checkbox.setChecked(False)
    # データセット匿名 チェックボックス
    anonymize_checkbox = QCheckBox("データセットを匿名にする", parent)
    anonymize_checkbox.setChecked(False)

    from qt_compat.widgets import QWidget, QPushButton, QLineEdit, QDateEdit, QComboBox
    from qt_compat.core import QDate, Qt
    import datetime
    from config.common import (
        SUBGROUP_JSON_PATH,
        TEMPLATE_JSON_PATH,
        SELF_JSON_PATH,
        ORGANIZATION_JSON_PATH,
        INSTRUMENTS_JSON_PATH,
        SUBGROUP_DETAILS_DIR,
        SUBGROUP_REL_DETAILS_DIR,
    )
    
    logger.debug("データセット開設機能：パス確認完了")
    
    user_id = None
    self_user_attr: dict = {}
    all_team_groups = []
    data_load_failed = False
    data_warning_message = None
    team_groups_raw = []
    try:
        # ログインユーザーID取得
        with open(SELF_JSON_PATH, encoding="utf-8") as f:
            self_data = json.load(f)
        user_id = self_data.get("data", {}).get("id", None)
        self_user_attr = self_data.get("data", {}).get("attributes", {}) or {}
        if not user_id:
            logger.error("self.jsonからユーザーIDが取得できませんでした。")
        with open(SUBGROUP_JSON_PATH, encoding="utf-8") as f:
            sub_group_data = json.load(f)
        
        # 全てのTEAMグループを取得（フィルタ前）
        for item in sub_group_data.get("included", []):
            if item.get("type") == "group" and item.get("attributes", {}).get("groupType") == "TEAM":
                all_team_groups.append(item)
        
        # デフォルトフィルタを適用
        team_groups_raw = filter_groups_by_role(all_team_groups, "owner_assistant", user_id)
    except Exception as e:
        logger.error("subGroup.json/self.jsonの読み込み・フィルタに失敗: %s", e)
        data_load_failed = True
        all_team_groups = []
        team_groups_raw = []
        if isinstance(e, FileNotFoundError) or "No such file or directory" in str(e):
            data_warning_message = "サブグループ情報が見つかりません。先にデータ取得を実行してください。"
        else:
            data_warning_message = "サブグループ情報の読み込みに失敗しました。データ取得後に再試行してください。"
    
    # フィルタ選択UI
    filter_combo = QComboBox(parent)
    # 強制スタイル（OSテーマ逆転時もライト/ダークをアプリ指定通りに）
    try:
        from classes.theme.theme_keys import ThemeKey as _TK
        from classes.theme.theme_manager import get_color as _gc
        
        filter_combo.setStyleSheet(
            f"QComboBox {{  border: 1px solid {_gc(_TK.COMBO_BORDER)}; border-radius: 4px; padding: 2px 6px; }}"
        )
    except Exception:
        pass
    #filter_combo.addItem("メンバー（何らかの役割を持つ）", "member")
    
    filter_combo.addItem("管理者 または 管理者代理", "owner_assistant")
    filter_combo.addItem("管理者 のみ", "owner")
    filter_combo.addItem("管理者代理 のみ", "assistant")
    filter_combo.addItem("フィルタなし（全てのグループ）", "none")
    
    #filter_combo.addItem("管理者、管理者代理、メンバー、登録代行者、閲覧者", "all_roles")
    filter_combo.setCurrentIndex(0)  # デフォルト：管理者 または 管理者代理
    
    # 初期グループリスト設定
    team_groups = team_groups_raw
    group_names = []
    for g in team_groups_raw:
        attrs = g.get("attributes", {}) if isinstance(g, dict) else {}
        name = str(attrs.get("name") or "(no name)")
        desc = str(attrs.get("description") or "").strip()
        subjects = attrs.get("subjects", [])
        grant_count = len(subjects) if subjects else 0
        if desc:
            group_names.append(f"{name}（{desc}、{grant_count}件の課題）")
        else:
            group_names.append(f"{name}（{grant_count}件の課題）")
    
    if not team_groups and not data_load_failed:
        error_widget = QWidget(parent)
        error_layout = QVBoxLayout()
        error_layout.addWidget(QLabel("利用可能なグループが見つかりません"))
        error_layout.addWidget(QLabel("サブグループ作成機能でグループを作成してください。"))
        error_widget.setLayout(error_layout)
        return error_widget, [], None, None, None, None, None, []
    
    from qt_compat.widgets import QSizePolicy
    from qt_compat.widgets import QCompleter
    
    # UIコンポーネントを先に定義（update_group_list関数で参照するため）
    combo = QComboBox(parent)
    try:
        combo.setStyleSheet(
            f"QComboBox {{  border: 1px solid {_gc(_TK.COMBO_BORDER)}; border-radius: 4px; padding: 2px 6px; }}"
        )
    except Exception:
        pass
    combo.setMinimumWidth(200)
    combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.NoInsert)
    combo.setMaxVisibleItems(12)
    combo.view().setMinimumHeight(240)
    combo.clear()
    
    # 課題番号選択欄を先に定義（update_group_list で参照するため）
    grant_combo = QComboBox(parent)
    try:
        grant_combo.setStyleSheet(
            f"QComboBox {{border: 1px solid {_gc(_TK.COMBO_BORDER)}; border-radius: 4px; padding: 2px 6px; }}"
        )
    except Exception:
        pass
    grant_combo.setMinimumWidth(200)
    grant_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    grant_combo.setEditable(True)
    grant_combo.setInsertPolicy(QComboBox.NoInsert)
    grant_combo.setMaxVisibleItems(12)
    grant_combo.view().setMinimumHeight(240)
    grant_combo.clear()
    grant_combo.lineEdit().setPlaceholderText("先にグループを選択してください")
    grant_combo.setEnabled(False)  # 初期状態では無効

    # データセット管理者選択欄（グループ決定後に有効化）
    manager_combo = QComboBox(parent)
    try:
        manager_combo.setStyleSheet(
            f"QComboBox {{  border: 1px solid {_gc(_TK.COMBO_BORDER)}; border-radius: 4px; padding: 2px 6px; }}"
        )
    except Exception:
        pass
    manager_combo.setEditable(True)
    manager_combo.setInsertPolicy(QComboBox.NoInsert)
    manager_combo.setMaxVisibleItems(12)
    manager_combo.view().setMinimumHeight(240)
    manager_combo.setEnabled(False)
    manager_combo.setMinimumWidth(220)
    manager_combo.lineEdit().setPlaceholderText("先にグループを選択してください")
    manager_entries: list[tuple[str, str]] = []
    manager_completer = QCompleter([], manager_combo)
    manager_completer.setCaseSensitivity(Qt.CaseInsensitive)
    manager_completer.setFilterMode(Qt.MatchContains)
    manager_combo.setCompleter(manager_completer)

    # 選択中サブグループの説明（description）表示
    subgroup_desc_label = QLabel("", parent)
    subgroup_desc_label.setObjectName("selectedSubgroupDescriptionLabel")
    subgroup_desc_label.setWordWrap(True)
    try:
        from classes.theme.theme_keys import ThemeKey as _TK_DESC
        from classes.theme.theme_manager import get_color as _gc_desc

        subgroup_desc_label.setStyleSheet(f"color: {_gc_desc(_TK_DESC.TEXT_MUTED)};")
    except Exception:
        pass
    subgroup_desc_label.setVisible(False)
    
    def _normalize_group_search(text: str) -> str:
        return (text or "").strip().lower()

    def _format_group_label(group: dict) -> str:
        attrs = group.get("attributes", {}) if isinstance(group, dict) else {}
        name = str(attrs.get("name") or "(no name)")
        desc = str(attrs.get("description") or "").strip()
        subjects = attrs.get("subjects", [])
        grant_count = len(subjects) if subjects else 0
        if desc:
            return f"{name}（{desc}、{grant_count}件の課題）"
        return f"{name}（{grant_count}件の課題）"

    def _group_matches_search(group: dict, search_text: str) -> bool:
        if not search_text:
            return True
        attrs = group.get("attributes", {}) if isinstance(group, dict) else {}
        name = str(attrs.get("name", "") or "")
        desc = str(attrs.get("description", "") or "")
        return search_text in f"{name} {desc}".lower()

    _suppress_group_search_update = False

    # グループ選択コンボボックス
    def update_group_list(filter_type="member", search_text: str = "", preserve_text: str | None = None):
        """フィルタタイプ/検索文字に応じてグループリストを更新"""
        nonlocal team_groups, group_names, group_completer  # group_completer も追加

        filtered_groups = filter_groups_by_role(all_team_groups, filter_type, user_id)
        normalized_search = _normalize_group_search(search_text)
        if normalized_search:
            filtered_groups = [
                g for g in filtered_groups if _group_matches_search(g, normalized_search)
            ]

        # グループ名リスト作成
        group_names_new = [_format_group_label(g) for g in filtered_groups]

        # コンボボックス更新
        try:
            combo.blockSignals(True)
        except Exception:
            pass
        combo.clear()
        if group_names_new:
            combo.addItems(group_names_new)
            combo.setCurrentIndex(-1)  # 選択なし状態
            if combo.lineEdit():
                combo.lineEdit().setPlaceholderText("グループを選択してください")
            combo.setEnabled(True)
        else:
            combo.setEnabled(False)
            if combo.lineEdit():
                combo.lineEdit().setPlaceholderText("該当するグループがありません")

        if preserve_text is not None and combo.lineEdit():
            combo.lineEdit().setText(preserve_text)
        try:
            combo.blockSignals(False)
        except Exception:
            pass

        # グループデータも更新
        team_groups = filtered_groups
        group_names = group_names_new

        # Completer も更新（重要！）
        try:
            group_completer.setModel(group_completer.model().__class__(group_names_new, group_completer))
            logger.debug("Completer更新完了: %s件", len(group_names_new))
        except Exception as e:
            logger.warning("Completer更新に失敗: %s", e)

        # 課題番号コンボボックスをクリア
        grant_combo.clear()
        grant_combo.setEnabled(False)
        grant_combo.lineEdit().setPlaceholderText("先にグループを選択してください")

        # サブグループ説明もクリア
        try:
            subgroup_desc_label.clear()
            subgroup_desc_label.setVisible(False)
        except Exception:
            pass

        return group_names_new

    def _find_role_for_user(group: dict, target_user_id: str | None) -> str | None:
        if not target_user_id:
            return None
        for role in group.get("attributes", {}).get("roles", []):
            if role.get("userId") == target_user_id:
                return role.get("role")
        return None

    def _build_member_label(user_item: dict, group: dict) -> str:
        attr = user_item.get("attributes", {}) if isinstance(user_item, dict) else {}
        org = attr.get("organizationName") or "(組織不明)"
        name_kanji = " ".join([attr.get("familyNameKanji", ""), attr.get("givenNameKanji", "")]).strip()
        name_latin = " ".join([attr.get("familyName", ""), attr.get("givenName", "")]).strip()
        base_name = name_kanji or name_latin or attr.get("userName") or attr.get("emailAddress") or (user_item.get("id") or "")
        user_name = attr.get("userName")
        if user_name and user_name not in base_name:
            base_name = f"{base_name} ({user_name})"
        role = _find_role_for_user(group, user_item.get("id"))
        role_suffix = f" [{role}]" if role else ""
        if org:
            return f"{org} / {base_name}{role_suffix}"
        return f"{base_name}{role_suffix}"

    def _load_group_member_users(group_id: str | None) -> list[dict]:
        users: list[dict] = []
        if not group_id:
            return users
        candidate_paths = [
            os.path.join(SUBGROUP_DETAILS_DIR, f"{group_id}.json"),
            os.path.join(SUBGROUP_REL_DETAILS_DIR, f"{group_id}.json"),
        ]
        for path in candidate_paths:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                for item in (data or {}).get("included", []) or []:
                    if item.get("type") == "user":
                        users.append(item)
                if users:
                    return users
            except FileNotFoundError:
                logger.debug("グループメンバー情報が見つかりません: %s", path)
            except Exception as e:
                logger.debug("グループメンバー情報の読み込みに失敗: %s", e)
        return users

    def _populate_manager_combo(selected_group: dict | None):
        nonlocal manager_entries
        if not manager_combo:
            return
        manager_entries = []
        manager_combo.blockSignals(True)
        manager_combo.clear()
        manager_combo.setEnabled(False)
        if manager_combo.lineEdit():
            manager_combo.lineEdit().setPlaceholderText("先にグループを選択してください")
        manager_combo.blockSignals(False)

        if not selected_group:
            return

        owner_id = None
        for role in selected_group.get("attributes", {}).get("roles", []):
            if role.get("role") == "OWNER" and role.get("userId"):
                owner_id = str(role["userId"])
                break

        def _add_entry(label: str, uid: str):
            manager_entries.append((label, uid))
            manager_combo.addItem(label, uid)

        members = _load_group_member_users(selected_group.get("id"))
        for member in members:
            user_id_val = member.get("id")
            if not user_id_val:
                continue
            attr = member.get("attributes", {}) or {}
            if attr.get("isDeleted"):
                continue
            label = _build_member_label(member, selected_group)
            _add_entry(label, str(user_id_val))
            email = attr.get("emailAddress")
            if email:
                try:
                    manager_combo.setItemData(manager_combo.count() - 1, email, Qt.ToolTipRole)
                except Exception:
                    pass

        if not manager_entries and owner_id:
            _add_entry(f"グループ管理者 ({owner_id})", owner_id)

        if not manager_entries and user_id:
            pseudo_user = {"id": user_id, "attributes": self_user_attr}
            label = _build_member_label(pseudo_user, selected_group)
            _add_entry(label or f"ログインユーザー ({user_id})", str(user_id))

        if manager_entries:
            manager_combo.setEnabled(True)
            if manager_combo.lineEdit():
                manager_combo.lineEdit().setPlaceholderText("データセット管理者を選択")
            try:
                manager_completer.setModel(manager_completer.model().__class__([lbl for lbl, _ in manager_entries], manager_completer))
            except Exception:
                pass

            preferred_ids = []
            if user_id:
                preferred_ids.append(str(user_id))
            if owner_id:
                preferred_ids.append(owner_id)
            default_idx = -1
            for preferred in preferred_ids:
                for idx, (_lbl, uid) in enumerate(manager_entries):
                    if uid == preferred:
                        default_idx = idx
                        break
                if default_idx >= 0:
                    break
            if default_idx < 0:
                default_idx = 0
            if 0 <= default_idx < manager_combo.count():
                manager_combo.setCurrentIndex(default_idx)
        else:
            if manager_combo.lineEdit():
                manager_combo.lineEdit().setPlaceholderText("メンバー情報が見つかりません")
            manager_combo.setEnabled(False)

    def _resolve_selected_manager_id() -> str | None:
        try:
            if manager_combo.currentData():
                return str(manager_combo.currentData())
        except Exception:
            pass
        try:
            text = (manager_combo.lineEdit().text() or "").strip()
        except Exception:
            text = ""
        if text:
            idx = manager_combo.findText(text)
            if idx >= 0:
                data = manager_combo.itemData(idx)
                if data:
                    return str(data)
            for label, uid in manager_entries:
                if label == text:
                    return uid
        return None
    
    # グループ選択コンボボックスの設定
    combo.lineEdit().setPlaceholderText("グループ名で検索")
    
    # Completer の初期化（先に行う）
    group_completer = QCompleter([], combo)  # 空リストで初期化
    group_completer.setCaseSensitivity(Qt.CaseInsensitive)  # PySide6: 列挙型が必要
    group_completer.setFilterMode(Qt.MatchContains)
    # 検索時の補完リスト（popup）の高さを12行分に制限
    popup_view = group_completer.popup()
    popup_view.setMinimumHeight(240)
    popup_view.setMaximumHeight(240)
    combo.setCompleter(group_completer)
    
    # 初期グループリスト設定
    update_group_list("owner_assistant")  # デフォルトフィルタで初期化（フィルタコンボの初期値に合わせる）
    
    # フィルタ変更時のイベントハンドラ
    def on_filter_changed():
        filter_type = filter_combo.currentData()
        logger.debug("Filter changed to: %s", filter_type)
        current_text = combo.lineEdit().text() if combo.lineEdit() else ""
        search_text = current_text
        preserve_text = current_text
        if filter_type == "none":
            search_text = ""
            preserve_text = ""
        update_group_list(filter_type, search_text=search_text, preserve_text=preserve_text)  # update_group_list内でCompleterも更新される
        logger.debug("Groups after filter: %s groups", len(team_groups))
        _populate_manager_combo(None)
        
    filter_combo.currentTextChanged.connect(on_filter_changed)
    
    # QComboBox自体のmousePressEventをラップして全リスト表示＋popup
    orig_mouse_press = combo.mousePressEvent
    def combo_mouse_press_event(event):
        print("[DEBUG] group combo (QComboBox) click: text=", combo.lineEdit().text())
        print("[DEBUG] group_names=", len(group_names))
        print("[DEBUG] combo.count before=", combo.count())
        if not combo.lineEdit().text():
            combo.clear()
            combo.addItems(group_names)
            logger.debug("group combo: added all items")
        print("[DEBUG] combo.count after=", combo.count())
        combo.showPopup()
        orig_mouse_press(event)
    combo.mousePressEvent = combo_mouse_press_event

    def _on_group_search_text_changed(text: str) -> None:
        nonlocal _suppress_group_search_update
        if _suppress_group_search_update:
            return
        _suppress_group_search_update = True
        try:
            update_group_list(filter_combo.currentData(), search_text=text, preserve_text=text)
        finally:
            _suppress_group_search_update = False

    # グループ選択時に課題番号リストを更新
    def on_group_changed():
        current_text = combo.lineEdit().text()
        logger.debug("Group selection changed: %s", current_text)
        
        # 課題番号コンボボックスをクリア
        grant_combo.clear()
        grant_combo.setEnabled(False)
        grant_combo.lineEdit().setPlaceholderText("先にグループを選択してください")
        
        # 現在選択されているグループのインデックスを探す
        selected_group = None
        for i, name in enumerate(group_names):
            if name == current_text:
                selected_group = team_groups[i]
                break
        
        if selected_group:
            # 説明（description）
            try:
                desc = str((selected_group.get('attributes', {}) or {}).get('description') or '').strip()
            except Exception:
                desc = ''
            if desc:
                subgroup_desc_label.setText(desc)
                subgroup_desc_label.setVisible(True)
            else:
                subgroup_desc_label.clear()
                subgroup_desc_label.setVisible(False)

            subjects = selected_group.get('attributes', {}).get('subjects', [])
            if subjects:
                grant_combo.setEnabled(True)
                grant_combo.lineEdit().setPlaceholderText("課題番号を選択")
                
                grant_items = []
                for subject in subjects:
                    grant_number = subject.get('grantNumber', '')
                    title = subject.get('title', '')
                    if grant_number:
                        display_text = f"{grant_number} - {title}" if title else grant_number
                        grant_items.append(display_text)
                        grant_combo.addItem(display_text, grant_number)
                
                if grant_items:
                    # 課題番号コンボボックス用のコンプリーター設定
                    grant_completer = QCompleter(grant_items, grant_combo)
                    grant_completer.setCaseSensitivity(Qt.CaseInsensitive)  # PySide6: 列挙型が必要
                    grant_completer.setFilterMode(Qt.MatchContains)
                    grant_popup_view = grant_completer.popup()
                    grant_popup_view.setMinimumHeight(240)
                    grant_popup_view.setMaximumHeight(240)
                    grant_combo.setCompleter(grant_completer)
                    
                    # 課題番号コンボボックスのクリックイベント
                    orig_grant_mouse_press = grant_combo.mousePressEvent
                    def grant_combo_mouse_press_event(event):
                        logger.debug("grant combo click")
                        if not grant_combo.lineEdit().text():
                            grant_combo.clear()
                            for subject in subjects:
                                grant_number = subject.get('grantNumber', '')
                                title = subject.get('title', '')
                                if grant_number:
                                    display_text = f"{grant_number} - {title}" if title else grant_number
                                    grant_combo.addItem(display_text, grant_number)
                        grant_combo.showPopup()
                        orig_grant_mouse_press(event)
                    grant_combo.mousePressEvent = grant_combo_mouse_press_event
                    
                    # デフォルトで最初の課題番号を選択
                    if len(grant_items) == 1:
                        grant_combo.setCurrentIndex(0)
                    else:
                        grant_combo.setCurrentIndex(-1)
                        
                logger.debug("Added %s grant numbers to combo", len(grant_items))
            else:
                grant_combo.lineEdit().setPlaceholderText("このグループには課題が登録されていません")
            _populate_manager_combo(selected_group)
        else:
            _populate_manager_combo(None)
            grant_combo.lineEdit().setPlaceholderText("先にグループを選択してください")
            try:
                subgroup_desc_label.clear()
                subgroup_desc_label.setVisible(False)
            except Exception:
                pass
    
    # グループ選択の変更イベントを接続
    combo.lineEdit().textChanged.connect(on_group_changed)
    try:
        combo.lineEdit().textEdited.connect(_on_group_search_text_changed)
    except Exception:
        pass
    combo.currentTextChanged.connect(on_group_changed)

    # name入力欄
    name_edit = QLineEdit(parent)
    name_edit.setPlaceholderText("データセット名を入力")
    name_edit.setMinimumWidth(180)

    # embargoDate入力欄（翌年度末日をデフォルト）
    today = datetime.date.today()
    next_next_year = today.year + 2
    embargo_date = QDate(next_next_year, 3, 31)
    embargo_edit = QDateEdit(parent)
    embargo_edit.setDate(embargo_date)
    embargo_edit.setDisplayFormat("yyyy-MM-dd")
    embargo_edit.setCalendarPopup(True)
    embargo_edit.setMinimumWidth(120)

    # テンプレート選択欄（表示モード: 所属組織のみ / 全件 / 組織フィルタ）
    template_list: list[dict] = []
    template_combo = QComboBox(parent)
    try:
        template_combo.setStyleSheet(
            f"QComboBox {{ border: 1px solid {_gc(_TK.COMBO_BORDER)}; border-radius: 4px; padding: 2px 6px; }}"
        )
    except Exception:
        pass
    template_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    template_combo.setEditable(True)
    template_combo.setInsertPolicy(QComboBox.NoInsert)
    template_combo.setMaxVisibleItems(12)
    template_combo.view().setMinimumHeight(240)
    template_combo.clear()
    template_combo.lineEdit().setPlaceholderText("テンプレート名・装置名で検索")

    # テンプレート表示モード選択
    template_filter_combo = QComboBox(parent)
    try:
        template_filter_combo.setStyleSheet(
            f"QComboBox {{ border: 1px solid {_gc(_TK.COMBO_BORDER)}; border-radius: 4px; padding: 2px 6px; }}"
        )
    except Exception:
        pass
    template_filter_combo.addItem("所属組織の装置のみ", "my")
    template_filter_combo.addItem("全件", "all")
    template_filter_combo.addItem("組織でフィルタ", "org")
    template_filter_combo.setCurrentIndex(0)
    # 副次的なフィルタ項目として控えめに（右寄せ + 幅を10%縮小）
    template_filter_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    template_filter_combo.setFixedWidth(int(200 * 0.9))

    # 組織フィルタ用
    org_filter_combo = QComboBox(parent)
    try:
        org_filter_combo.setStyleSheet(
            f"QComboBox {{ border: 1px solid {_gc(_TK.COMBO_BORDER)}; border-radius: 4px; padding: 2px 6px; }}"
        )
    except Exception:
        pass
    org_filter_combo.setEditable(False)
    org_filter_combo.setInsertPolicy(QComboBox.NoInsert)
    org_filter_combo.setMaxVisibleItems(12)
    org_filter_combo.view().setMinimumHeight(240)
    org_filter_combo.setEnabled(False)
    org_filter_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    org_filter_combo.setFixedWidth(int(220 * 0.9))

    template_items: list[str] = []
    org_id_by_nameja: dict[str, str] = {}
    instrument_ids_by_org: dict[str, set[str]] = {}
    # --- 所属組織名取得 ---
    org_name = None
    try:
        with open(SELF_JSON_PATH, encoding="utf-8") as f:
            self_data = json.load(f)
        org_name = self_data.get("data", {}).get("attributes", {}).get("organizationName")
    except Exception as e:
        logger.error("self.jsonの読み込みに失敗: %s", e)
    # --- organization.json を読み込んで組織一覧 + 現在の組織IDを解決 ---
    org_id = None
    try:
        with open(ORGANIZATION_JSON_PATH, encoding="utf-8") as f:
            org_data = json.load(f)
        org_items: list[tuple[str, str]] = []
        for org in (org_data or {}).get("data", []) or []:
            oid = org.get("id")
            name_ja = org.get("attributes", {}).get("nameJa")
            if oid and name_ja:
                org_id_by_nameja[str(name_ja)] = str(oid)
                org_items.append((str(name_ja), str(oid)))

        # nameJa でソート
        org_items.sort(key=lambda x: x[0])
        org_filter_combo.clear()
        org_filter_combo.addItem("(選択してください)", "")
        for name_ja, oid in org_items:
            org_filter_combo.addItem(name_ja, oid)

        if org_name:
            org_id = org_id_by_nameja.get(str(org_name))
    except Exception as e:
        logger.error("organization.jsonの読み込みに失敗: %s", e)
    # --- instrument 一覧取得（全組織分の instrument_ids_by_org を作る） ---
    instrument_map: dict[str, dict] = {}
    try:
        with open(INSTRUMENTS_JSON_PATH, encoding="utf-8") as f:
            instruments_data = json.load(f)
        for inst in (instruments_data or {}).get("data", []) or []:
            inst_id = inst.get("id")
            attr = inst.get("attributes", {})
            name_ja = attr.get("nameJa", "")
            local_id = ""
            model_number = attr.get("modelNumber", "")
            for prog in attr.get("programs", []):
                if prog.get("localId"):
                    local_id = prog["localId"]
                    break
            if inst_id:
                inst_org_id = attr.get("organizationId")
                instrument_map[str(inst_id)] = {
                    "nameJa": name_ja,
                    "localId": local_id,
                    "modelNumber": model_number,
                    "organizationId": inst_org_id,
                }
                if inst_org_id:
                    instrument_ids_by_org.setdefault(str(inst_org_id), set()).add(str(inst_id))
    except Exception as e:
        logger.error("instruments.jsonの読み込みに失敗: %s", e)

    # --- template.json 読み込み ---
    template_data: dict = {}
    try:
        with open(TEMPLATE_JSON_PATH, encoding="utf-8") as f:
            template_data = json.load(f)
    except Exception as e:
        logger.error("template.jsonの読み込みに失敗: %s", e)
        template_data = {}

    def _reload_templates() -> None:
        nonlocal template_list, template_items
        mode = template_filter_combo.currentData()
        selected_org_id = org_filter_combo.currentData() if org_filter_combo.isEnabled() else None

        if mode == "all":
            allowed_ids = None
        elif mode == "org":
            if not selected_org_id:
                template_combo.clear()
                template_list = []
                template_items = []
                template_combo.lineEdit().setPlaceholderText("先に組織を選択してください")
                return
            allowed_ids = instrument_ids_by_org.get(str(selected_org_id), set())
        else:
            # default: my
            allowed_ids = instrument_ids_by_org.get(str(org_id), set()) if org_id else set()

        template_combo.clear()
        template_list, template_items, combo_items = _build_template_entries(template_data, instrument_map, allowed_ids)
        for label, tid in combo_items:
            template_combo.addItem(label, tid)
        template_combo.lineEdit().setPlaceholderText("テンプレート名・装置名で検索")

        try:
            # Completer の更新
            template_completer.setModel(template_completer.model().__class__(template_items, template_completer))
        except Exception:
            pass
        template_combo.setCurrentIndex(-1)

    def _on_template_filter_changed() -> None:
        mode = template_filter_combo.currentData()
        if mode == "org":
            org_filter_combo.setEnabled(True)
        else:
            org_filter_combo.setEnabled(False)
        _reload_templates()
    template_combo.setMinimumWidth(260)
    template_completer = QCompleter(template_items, template_combo)
    template_completer.setCaseSensitivity(Qt.CaseInsensitive)  # PySide6: 列挙型が必要
    template_completer.setFilterMode(Qt.MatchContains)
    t_popup_view = template_completer.popup()
    t_popup_view.setMinimumHeight(240)
    t_popup_view.setMaximumHeight(240)
    template_combo.setCompleter(template_completer)
    template_combo.setCurrentIndex(-1)

    # 初期ロード（現状互換: 所属組織のみ）
    _reload_templates()

    template_filter_combo.currentIndexChanged.connect(_on_template_filter_changed)
    org_filter_combo.currentIndexChanged.connect(lambda *_: (_reload_templates() if template_filter_combo.currentData() == "org" else None))

    from qt_compat.widgets import QFormLayout
    form_layout = QFormLayout()
    form_layout.setLabelAlignment(Qt.AlignRight)
    form_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
    # ラベル太字スタイル (共通ヘルパー使用でQSS削減)
    from classes.utils.label_style import apply_label_style
    from classes.theme import ThemeKey as _TKey
    label_filter = QLabel("ロールフィルタ:");
    #apply_label_style(label_filter, _TKey.TEXT_PRIMARY, bold=True)
    label_group = QLabel("サブグループフィルタ:");
    #apply_label_style(label_group, _TKey.TEXT_PRIMARY, bold=True)
    label_grant = QLabel("課題番号:");
    label_manager = QLabel("データセット管理者:");
    #apply_label_style(label_grant, _TKey.TEXT_PRIMARY, bold=True)
    label_name = QLabel("データセット名:"); 
    #apply_label_style(label_name, _TKey.TEXT_PRIMARY, bold=True)
    label_embargo = QLabel("エンバーゴ期間終了日:"); 
    #apply_label_style(label_embargo, _TKey.TEXT_PRIMARY, bold=True)
    label_template_filter = QLabel("テンプレートフィルタ形式:");
    label_template_org = QLabel("組織フィルタ:");
    label_template = QLabel("データセットテンプレート名:"); 
    #apply_label_style(label_template, _TKey.TEXT_PRIMARY, bold=True)
    form_layout.addRow(label_filter, filter_combo)
    form_layout.addRow(label_group, combo)
    form_layout.addRow(QLabel(""), subgroup_desc_label)
    form_layout.addRow(label_grant, grant_combo)
    form_layout.addRow(label_manager, manager_combo)
    form_layout.addRow(label_name, name_edit)
    form_layout.addRow(label_embargo, embargo_edit)
    # 右寄せ: 副次的なフィルタ項目として視認上控えめにする
    def _wrap_right_aligned_field(field_widget: QWidget) -> QWidget:
        # parent を明示しない（レイアウト追加時に適切にリペアレントされる）
        wrapper = QWidget()
        h = QHBoxLayout(wrapper)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addStretch(1)
        h.addWidget(field_widget)
        return wrapper

    form_layout.addRow(label_template_filter, _wrap_right_aligned_field(template_filter_combo))
    form_layout.addRow(label_template_org, _wrap_right_aligned_field(org_filter_combo))
    form_layout.addRow(label_template, template_combo)
    form_layout.addRow(share_core_scope_checkbox)
    form_layout.addRow(anonymize_checkbox)
    # インラインの固定色指定（例: 緑系の直書き）を撤去しテーマ統一へ移行
    # 必要なら placeholder などは ThemeKey.TEXT_PLACEHOLDER へ後続で再指定可能
    from classes.theme.theme_keys import ThemeKey
    from classes.theme.theme_manager import get_color
    open_btn = QPushButton("データセット開設", parent)
    # グローバルQSSのボタンvariantを使用
    open_btn.setProperty("variant", "primary")
    open_btn.setStyleSheet("font-size: 13px; padding: 8px 20px; border-radius: 6px;")
    form_layout.addRow(open_btn)

    warning_label = QLabel("", parent)
    warning_label.setObjectName("datasetOpenWarningLabel")
    warning_label.setWordWrap(True)
    warning_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_ERROR)}; font-weight: bold;")
    warning_label.setVisible(False)
    form_layout.addRow(warning_label)

    def _apply_warning_state(message):
        if message:
            warning_label.setText(str(message))
            warning_label.setVisible(True)
            combo.setEnabled(False)
            grant_combo.setEnabled(False)
            manager_combo.setEnabled(False)
            open_btn.setEnabled(False)
        else:
            warning_label.clear()
            warning_label.setVisible(False)
            combo.setEnabled(True)
            grant_combo.setEnabled(True)
            manager_combo.setEnabled(bool(manager_entries))
            open_btn.setEnabled(True)

    if data_warning_message:
        _apply_warning_state(data_warning_message)

    container = RefreshOnShowWidget(parent)
    # Expose checkboxes for external wrappers (e.g., 新規開設2)
    container.share_core_scope_checkbox = share_core_scope_checkbox  # type: ignore[attr-defined]
    container.anonymize_checkbox = anonymize_checkbox  # type: ignore[attr-defined]
    container.template_filter_combo = template_filter_combo  # type: ignore[attr-defined]
    container.template_org_combo = org_filter_combo  # type: ignore[attr-defined]
    container.manager_combo = manager_combo  # type: ignore[attr-defined]
    container._resolve_selected_manager_id = _resolve_selected_manager_id  # type: ignore[attr-defined]
    container._manager_entries = manager_entries  # type: ignore[attr-defined]
    container.setLayout(form_layout)

    # テーマ再適用（ダーク/ライト切替時に背景色が逆転しないよう強制再指定）
    def _refresh_theme():
        return
        try:
            from classes.theme.theme_keys import ThemeKey as _TK2
            from classes.theme.theme_manager import get_color as _gc2, ThemeManager as _TM
            combo_style = (
                f"QComboBox {{ background-color: {_gc2(_TK2.COMBO_BACKGROUND)}; color: {_gc2(_TK2.TEXT_PRIMARY)}; "
                f"border: 1px solid {_gc2(_TK2.COMBO_BORDER)}; border-radius: 4px; padding: 2px 6px; }}"
            )
            for cb in (filter_combo, combo, grant_combo, manager_combo, template_combo):
                if cb:
                    cb.setStyleSheet(combo_style)
            # LineEdit / DateEdit
            name_edit.setStyleSheet(
                f"QLineEdit {{ background-color: {_gc2(_TK2.INPUT_BACKGROUND)}; color: {_gc2(_TK2.INPUT_TEXT)}; "
                f"border: 1px solid {_gc2(_TK2.INPUT_BORDER)}; border-radius: 4px; padding: 4px 6px; }}"
                f"QLineEdit:focus {{ border-color: {_gc2(_TK2.BUTTON_INFO_BACKGROUND)}; background-color: {_gc2(_TK2.PANEL_INFO_BACKGROUND)}; }}"
            )
            embargo_edit.setStyleSheet(
                f"QDateEdit {{ background-color: {_gc2(_TK2.INPUT_BACKGROUND)}; color: {_gc2(_TK2.INPUT_TEXT)}; "
                f"border: 1px solid {_gc2(_TK2.INPUT_BORDER)}; border-radius: 4px; padding: 2px 4px; }}"
            )
            # チェックボックス
            chk_style = (
                f"QCheckBox {{ color: {_gc2(_TK2.TEXT_PRIMARY)}; }}"
                f"QCheckBox::indicator {{ width: 16px; height:16px; border:1px solid {_gc2(_TK2.INPUT_BORDER)}; "
                f"background-color: {_gc2(_TK2.INPUT_BACKGROUND)}; border-radius:3px; }}"
                f"QCheckBox::indicator:checked {{ background-color: {_gc2(_TK2.BUTTON_PRIMARY_BACKGROUND)}; border-color: {_gc2(_TK2.BUTTON_PRIMARY_BACKGROUND)}; }}"
            )
            share_core_scope_checkbox.setStyleSheet(chk_style)
            anonymize_checkbox.setStyleSheet(chk_style)
            # 開設ボタン（variant保持しつつ色をテーマに追従）
            open_btn.setStyleSheet(
                f"QPushButton {{ font-size:13px; padding:8px 20px; border-radius:6px; "
                f"background-color: {_gc2(_TK2.BUTTON_PRIMARY_BACKGROUND)}; color: {_gc2(_TK2.BUTTON_PRIMARY_TEXT)}; "
                f"border:1px solid {_gc2(_TK2.BUTTON_PRIMARY_BORDER)}; font-weight:bold; }}"
                f"QPushButton:hover {{ background-color: {_gc2(_TK2.BUTTON_PRIMARY_BACKGROUND_HOVER)}; }}"
                f"QPushButton:pressed {{ background-color: {_gc2(_TK2.BUTTON_PRIMARY_BACKGROUND_PRESSED)}; }}"
            )
            # ラベル色再適用（読みやすさ向上）
            for _lbl in [label_filter, label_group, label_grant, label_manager, label_name, label_embargo, label_template]:
                if _lbl:
                    _lbl.setStyleSheet(f"color: {_gc2(_TK2.TEXT_SECONDARY)}; font-weight:bold;")
            # コンテナ背景
            container.setStyleSheet(f"background-color: {_gc2(_TK2.WINDOW_BACKGROUND)};")
        except Exception as _e:
            logger.debug("dataset_open_widget theme refresh failed: %s", _e)

    # ThemeManagerへ接続（container破棄で自動解除されるよう QObject ブリッジ経由）
    try:
        from PySide6.QtCore import QObject, Slot
        from classes.theme.theme_manager import ThemeManager as _TM2

        _tm2 = _TM2.get_instance()

        class _ThemeChangedBridge(QObject):
            @Slot(object)
            def on_theme_changed(self, *_args):
                try:
                    _refresh_theme()
                except Exception:
                    pass

        container._rde_theme_changed_bridge = _ThemeChangedBridge(container)  # type: ignore[attr-defined]
        _tm2.theme_changed.connect(container._rde_theme_changed_bridge.on_theme_changed)  # type: ignore[attr-defined]
    except Exception as _e:
        logger.debug("Theme signal connect failed (dataset open): %s", _e)
    _refresh_theme()

    def on_open():
        idx = combo.currentIndex()
        selected_group = None
        
        # グループ名から対応するグループを検索
        current_group_text = combo.lineEdit().text()
        for i, name in enumerate(group_names):
            if name == current_group_text:
                selected_group = team_groups[i]
                break
        
        if not selected_group:
            QMessageBox.warning(parent, "グループ未選択", "グループを選択してください。")
            return
        
        # 課題番号取得
        selected_grant_number = None
        grant_text = grant_combo.lineEdit().text()
        if grant_text and grant_combo.currentData():
            selected_grant_number = grant_combo.currentData()
        elif grant_text:
            # データが無い場合は、テキストから課題番号を抽出
            parts = grant_text.split(' - ')
            if parts:
                selected_grant_number = parts[0].strip()
        
        if not selected_grant_number:
            QMessageBox.warning(parent, "課題番号未選択", "課題番号を選択してください。")
            return
        
        # 選択されたグループに課題番号情報を追加
        group_info = dict(selected_group)
        group_info['grantNumber'] = selected_grant_number
        
        # 入力値取得
        dataset_name = name_edit.text().strip()
        embargo_qdate = embargo_edit.date()
        embargo_str = embargo_qdate.toString("yyyy-MM-dd")
        template_idx = template_combo.currentIndex()
        template_id = template_list[template_idx]["id"] if 0 <= template_idx < len(template_list) else ""
        dataset_type = template_list[template_idx]["datasetType"] if 0 <= template_idx < len(template_list) else "ANALYSIS"
        
        # 入力必須チェック
        if not group_info.get('attributes', {}).get('name'):
            QMessageBox.warning(parent, "入力エラー", "グループ名は必須です。")
            return
        if not selected_grant_number:
            QMessageBox.warning(parent, "入力エラー", "課題番号は必須です。")
            return
        if not dataset_name:
            QMessageBox.warning(parent, "入力エラー", "データセット名は必須です。")
            return
        if not embargo_str:
            QMessageBox.warning(parent, "入力エラー", "エンバーゴ期間終了日は必須です。")
            return
        if template_idx < 0 or not template_id:
            QMessageBox.warning(parent, "入力エラー", "テンプレートは必須です。")
            return
        
        # チェックボックスの値取得
        share_core_scope = share_core_scope_checkbox.isChecked()
        anonymize = anonymize_checkbox.isChecked()

        manager_user_id = _resolve_selected_manager_id()
        if not manager_user_id:
            QMessageBox.warning(parent, "データセット管理者未選択", "データセット管理者を選択してください。")
            return
        
        # Bearer Token統一管理システムで取得
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(parent)
        if not bearer_token:
            QMessageBox.warning(parent, "認証エラー", "Bearer Tokenが取得できません。ログインを確認してください。")
            return
        
        logger.debug("on_open: group=%s, grant_number=%s, dataset_name=%s, embargo_str=%s, template_id=%s, dataset_type=%s, bearer_token=%s, share_core_scope=%s, anonymize=%s", group_info.get('attributes', {}).get('name'), selected_grant_number, dataset_name, embargo_str, template_id, dataset_type, '[PRESENT]' if bearer_token else '[NONE]', share_core_scope, anonymize)
        run_dataset_open_logic(
            parent,
            bearer_token,
            group_info,
            dataset_name,
            embargo_str,
            template_id,
            dataset_type,
            share_core_scope,
            anonymize,
            manager_user_id=manager_user_id,
        )
    if connect_open_handler:
        open_btn.clicked.connect(on_open)

    # サブグループ情報の更新機能を追加
    def refresh_subgroup_data():
        """サブグループ情報を再読み込みしてコンボボックスを更新"""
        try:
            # ウィジェットが破棄されていないかチェック
            if not combo or combo.parent() is None:
                logger.debug("コンボボックスが破棄されているため更新をスキップ")
                return
                
            # subGroup.jsonから最新データを読み込み
            with open(SUBGROUP_JSON_PATH, encoding="utf-8") as f:
                sub_group_data = json.load(f)
            
            # 全てのTEAMグループを再取得
            new_all_team_groups = []
            for item in sub_group_data.get("included", []):
                if item.get("type") == "group" and item.get("attributes", {}).get("groupType") == "TEAM":
                    new_all_team_groups.append(item)
            
            # グローバル変数を更新
            nonlocal all_team_groups, team_groups, group_names, data_load_failed
            all_team_groups = new_all_team_groups
            data_load_failed = False
            _apply_warning_state(None)
            
            # 現在のフィルタを適用して更新
            current_filter = filter_combo.currentData()
            update_group_list(current_filter or "owner_assistant")
            _populate_manager_combo(None)
            
            # Completer の更新 - これが重要！
            if group_completer and hasattr(group_completer, 'setModel'):
                group_completer.setModel(group_completer.model().__class__(group_names, group_completer))
            
            # コンボボックスの再構築（確実な更新のため）
            if combo and hasattr(combo, 'blockSignals'):
                combo.blockSignals(True)
                combo.clear()
                if group_names:
                    combo.addItems(group_names)
                    combo.setCurrentIndex(-1)  # 選択なし状態
                    combo.lineEdit().setPlaceholderText("グループを選択してください")
                    combo.setEnabled(True)
                else:
                    combo.setEnabled(False)
                    combo.lineEdit().setPlaceholderText("該当するグループがありません")
                combo.blockSignals(False)
                
                # UIの強制更新
                combo.update()
                combo.repaint()
            
            logger.info("サブグループ情報更新完了: %s件のグループ, 表示: %s件", len(new_all_team_groups), len(group_names))
            
        except Exception as e:
            logger.error("サブグループ情報更新に失敗: %s", e)
            data_load_failed = True
            message = f"サブグループ情報の更新に失敗しました: {e}"
            _apply_warning_state(message)
    
    # 外部から呼び出し可能にする（register_subgroup_notifier=False でも showEvent で追従できるように保持）
    container._refresh_subgroup_data = refresh_subgroup_data
    container.add_show_refresh_callback(refresh_subgroup_data)

    # create2等の呼び出し側が「最新の」team_groups/group_namesを参照できるようにアクセサを公開する。
    # NOTE: update_group_list 内で team_groups が再代入されるため、戻り値のリスト参照だけだと外側が古いままになる。
    try:
        container._get_current_team_groups = lambda: team_groups  # type: ignore[attr-defined]
        container._get_current_group_names = lambda: group_names  # type: ignore[attr-defined]
    except Exception:
        pass

    if register_subgroup_notifier:
        # サブグループ更新通知システムに登録
        try:
            from classes.dataset.util.dataset_refresh_notifier import get_subgroup_refresh_notifier
            subgroup_notifier = get_subgroup_refresh_notifier()
            subgroup_notifier.register_callback(refresh_subgroup_data)
            logger.info("データセット開設タブ: サブグループ更新通知に登録完了")

            # ウィジェット破棄時の通知解除用
            def cleanup_callback():
                subgroup_notifier.unregister_callback(refresh_subgroup_data)
                logger.info("データセット開設タブ: サブグループ更新通知を解除")

            container._cleanup_subgroup_callback = cleanup_callback

        except Exception as e:
            logger.warning("サブグループ更新通知への登録に失敗: %s", e)

    return (
        container,
        team_groups,
        combo,
        grant_combo,
        manager_combo,
        open_btn,
        name_edit,
        embargo_edit,
        template_combo,
        template_list,
        filter_combo,
    )

def create_dataset(bearer_token, payload, output_dir=None):
    """
    データセット開設API実行
    Bearer Token統一管理システム対応済み
    """
    if not bearer_token:
        logger.error("Bearer Tokenが指定されていません。")
        return False, "Bearer Token required"
    url = "https://rde-api.nims.go.jp/datasets"

    if 'payload' in locals():
        pass  # payloadは引数で受け取る
    else:
        logger.error("payloadが指定されていません。")
        return

    headers = {
        "Accept": "application/vnd.api+json",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Authorization": f"Bearer {bearer_token}",
        "Connection": "keep-alive",
        "Content-Type": "application/vnd.api+json",
        "Host": "rde-api.nims.go.jp",
        "Origin": "https://rde.nims.go.jp",
        "Referer": "https://rde.nims.go.jp/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }
    resp = None
    try:
        resp = api_request("POST", url, bearer_token=bearer_token, headers=headers, json_data=payload, timeout=15)  # refactored to use api_request_helper
        if resp is None:
            logger.error("データセット開設API リクエスト失敗")
            return False, None
        resp.raise_for_status()
        data = resp.json()
        target_dir = output_dir or OUTPUT_RDE_DATA_DIR
        os.makedirs(target_dir, exist_ok=True)
        with open(os.path.join(target_dir, "create_dataset.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("設備情報(create_dataset.json)の取得・保存に成功しました。")
        
        # データセット開設成功時に個別データセット情報を自動取得
        try:
            dataset_id = data.get("data", {}).get("id")
            if dataset_id:
                logger.info("データセット開設成功。個別データセット情報を自動取得中: %s", dataset_id)
                from classes.basic.core.basic_info_logic import fetch_dataset_info_respectively_from_api
                fetch_dataset_info_respectively_from_api(bearer_token, dataset_id)
                logger.info("個別データセット情報(%s.json)の自動取得完了", dataset_id)
            else:
                logger.warning("データセット開設レスポンスにIDが含まれていません")
        except Exception as e:
            logger.warning("個別データセット情報の自動取得に失敗: %s", e)
        
        return True, data
    except Exception as e:
        logger.error("設備情報の取得・保存に失敗しました: %s", e)

        # Try to include response payload for debugging (422 etc.)
        try:
            info: dict = {"error": str(e), "url": url}
            if resp is not None:
                try:
                    info["status_code"] = getattr(resp, "status_code", None)
                except Exception:
                    info["status_code"] = None
                try:
                    info["response_text"] = getattr(resp, "text", None)
                except Exception:
                    info["response_text"] = None
                try:
                    info["response_headers"] = dict(getattr(resp, "headers", {}) or {})
                except Exception:
                    info["response_headers"] = None
                try:
                    info["response_json"] = resp.json()
                except Exception:
                    info["response_json"] = None
            return False, info
        except Exception:
            return False, str(e)


    

def update_dataset(bearer_token, output_dir=None):
    """
    データセット更新処理（Bearer Token統一管理システム対応済み）
    """
    if not bearer_token:
        logger.error("Bearer Tokenが取得できません。ログイン状態を確認してください。")
        return
    #url = "https://rde-api.nims.go.jp/datasetTemplates?programId=4bbf62be-f270-4a46-9682-38cd064607ba&teamId=1e44cefd-85ba-49cb-bc7e-196a0ef379b0&sort=id&page[limit]=10000&page[offset]=0&include=instruments&fields[instrument]=nameJa%2CnameEn"
    url = "https://rde-api.nims.go.jp/datasets/5bfd6602-41c2-423a-8652-e9cbab71a172"

    return  # 一時的にAPI呼び出しを停止