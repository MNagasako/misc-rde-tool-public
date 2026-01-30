"""
サブグループ修正ウィジェット(リファクタリング版)
責務分離により保守性を向上
"""

import os
import sys
import json
import logging
import webbrowser
from typing import Iterable, List, Optional
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QGridLayout, 
    QPushButton, QMessageBox, QScrollArea, QCheckBox, QRadioButton, 
    QButtonGroup, QDialog, QTextEdit, QComboBox, QCompleter, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
)
from config.common import (
    SUBGROUP_JSON_PATH,
    SUBGROUP_DETAILS_DIR,
    SUBGROUP_REL_DETAILS_DIR,
)
from config.site_rde import URLS
from qt_compat.core import Qt
from classes.theme import get_color, ThemeKey
from classes.utils.label_style import apply_label_style

# ロガー設定
logger = logging.getLogger(__name__)
from ...dataset.util.dataset_refresh_notifier import get_subgroup_refresh_notifier
from ..util.subgroup_ui_helpers import (
    SubjectInputValidator, SubgroupFormBuilder, 
    SubgroupCreateHandler, MemberDataProcessor,
    show_selected_user_ids, load_user_entries
)
from ..util.subgroup_member_selector_common import (
    create_common_subgroup_member_selector,
    create_common_subgroup_member_selector_with_api_complement
)
from ..core import subgroup_api_helper
from ..util.related_dataset_fetcher import RelatedDatasetFetcher, RelatedDataset


DATASET_PAGE_TEMPLATE = URLS["web"].get("dataset_page", "https://rde.nims.go.jp/rde/datasets/{id}")


class SubgroupEditHandler(SubgroupCreateHandler):
    """
    サブグループ更新処理専用ハンドラー
    """
    
    def __init__(self, widget, parent, member_selector):
        super().__init__(widget, parent, member_selector)
        self.selected_group_data = None
    
    def set_selected_group(self, group_data):
        """選択されたグループデータを設定"""
        self.selected_group_data = group_data
    
    def create_update_confirmation_dialog(self, payload, payload_str):
        """更新確認ダイアログの作成"""
        return super().create_confirmation_dialog(payload, payload_str, operation_type="更新")
    
    def extract_update_payload(self, group_id, group_name, description, subjects, funds, roles):
        """更新用ペイロードの作成（PATCH用）"""
        # 選択されたグループからparent情報を取得
        parent_data = self.selected_group_data.get("relationships", {}).get("parent", {}).get("data", {})
        parent_id = parent_data.get("id", "")
        
        payload = {
            "data": {
                "type": "group",
                "id": group_id,
                "attributes": {
                    "name": group_name,
                    "description": description,
                    "subjects": subjects,
                    "funds": [{"fundNumber": f} for f in funds],
                    "roles": roles
                },
                "relationships": {
                    "parent": {
                        "data": {
                            "type": "group",
                            "id": parent_id
                        }
                    }
                }
            }
        }
        return payload
    
    def send_update_request(self, payload, group_id, group_name):
        """
        PATCHリクエストの送信
        """
        # BearerToken統一管理システムで取得
        from core.bearer_token_manager import BearerTokenManager
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(self.widget)
        if not bearer_token:
            QMessageBox.warning(self.widget, "認証エラー", "Bearerトークンが取得できません。ログイン状態を確認してください。")
            return False
        
        # API URL構築
        api_url = f"https://rde-api.nims.go.jp/groups/{group_id}"
        
        # ヘッダー準備
        headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/vnd.api+json",
            "Accept": "application/vnd.api+json"
        }
        
        logger.debug("PATCH API URL: %s", api_url)
        logger.debug("ペイロード: %s", json.dumps(payload, ensure_ascii=False, indent=2))
        
        # API送信（セッション管理されたPATCHリクエスト）
        try:
            from net.http_helpers import proxy_patch
            resp = proxy_patch(api_url, headers=headers, json=payload, timeout=15)
            
            logger.debug("レスポンス: %s", resp.status_code)
            logger.debug("レスポンス内容: %s", resp.text)
            
            if resp.status_code in (200, 201, 202):
                # 成功メッセージ表示前にsubGroup.jsonを自動再取得（スキップなし）
                refresh_success = False
                try:
                    from classes.basic.core.basic_info_logic import auto_refresh_subgroup_json
                    from classes.utils.progress_worker import SimpleProgressWorker
                    from classes.basic.ui.ui_basic_info import show_progress_dialog
                    
                    logger.info("サブグループ更新成功 - subGroup.json即座に再取得開始")
                    
                    # プログレス表示付きで自動更新（即座に実行）
                    worker = SimpleProgressWorker(
                        task_func=auto_refresh_subgroup_json,
                        task_kwargs={'bearer_token': bearer_token, 'force_refresh_subgroup': True},
                        task_name="サブグループ情報更新"
                    )
                    
                    # プログレス表示（ブロッキング実行）
                    progress_dialog = show_progress_dialog(self.widget, "サブグループ情報更新中", worker)
                    
                    refresh_success = True
                    logger.info("サブグループ情報自動更新完了")
                    
                    # サブグループ更新通知を送信
                    try:
                        from classes.dataset.util.dataset_refresh_notifier import get_subgroup_refresh_notifier
                        subgroup_notifier = get_subgroup_refresh_notifier()
                        from qt_compat.core import QTimer
                        def send_notification():
                            try:
                                subgroup_notifier.notify_refresh()
                                logger.info("サブグループ更新通知を送信しました")
                            except Exception as e:
                                logger.warning("サブグループ更新通知送信に失敗: %s", e)
                        QTimer.singleShot(500, send_notification)  # 0.5秒後に通知
                    except Exception as e:
                        logger.warning("サブグループ更新通知の設定に失敗: %s", e)
                    
                except Exception as e:
                    logger.error("サブグループ情報自動更新でエラー: %s", e)
                    QMessageBox.warning(
                        self.widget, 
                        "更新警告", 
                        f"サブグループ[{group_name}]の更新には成功しましたが、\nsubGroup.jsonの自動更新に失敗しました。\n\n"
                        f"基本情報タブで手動更新を実行してください。\n\nエラー: {e}"
                    )
                    # エラー時のみメッセージ表示（通常は自動更新のプログレスダイアログで完結）
                
                return True
            else:
                error_text = resp.text
                QMessageBox.warning(self.widget, "更新失敗", f"サブグループの更新に失敗しました。\nStatus: {resp.status_code}\n{error_text}")
                return False
                
        except Exception as e:
            QMessageBox.warning(self.widget, "通信エラー", f"API通信中にエラーが発生しました: {e}")
            return False


class EditFormManager:
    """
    編集フォーム管理専用クラス
    """
    
    def __init__(self, layout, form_builder, form_widgets):
        self.layout = layout
        self.form_builder = form_builder
        self.form_widgets = form_widgets
    
    def populate_form_from_group(self, group_data):
        """グループデータからフォームに値を設定"""
        if not group_data:
            return
        
        # 基本情報設定
        self.form_widgets['group_name_edit'].setText(group_data.get('name', ''))
        self.form_widgets['desc_edit'].setText(group_data.get('description', ''))
        
        # 課題情報設定（新しいウィジェット用）
        subjects_data = group_data.get('subjects', [])
        self.form_widgets['subjects_widget'].set_subjects_data(subjects_data)
        
        # 研究資金情報設定（新しいウィジェット用）
        funds_data = group_data.get('funds', [])
        if 'funds_widget' in self.form_widgets:
            # リスト形式に変換
            funds_list = []
            for fund in funds_data:
                if isinstance(fund, dict):
                    fund_number = fund.get("fundNumber", "")
                    if fund_number:
                        funds_list.append(fund_number)
                else:
                    funds_list.append(str(fund))
            self.form_widgets['funds_widget'].set_funding_numbers(funds_list)
    
    def get_form_values(self):
        """フォームから値を取得"""
        funds_value = []
        if 'funds_widget' in self.form_widgets:
            funds_value = self.form_widgets['funds_widget'].get_funding_numbers()
        
        return {
            'group_name': self.form_widgets['group_name_edit'].text().strip(),
            'description': self.form_widgets['desc_edit'].text().strip(),
            'subjects_data': self.form_widgets['subjects_widget'].get_subjects_data(),
            'funds_list': funds_value
        }


class EditMemberManager:
    """
    編集用メンバー選択管理専用クラス
    """
    
    def __init__(self, scroll_area, parent_widget=None):
        self.scroll_area = scroll_area
        self.current_member_selector = None
        self.parent_widget = parent_widget  # Bearer token取得用
    
    def update_member_selection(self, group_data, user_entries):
        """メンバー選択状態を既存グループに合わせて更新"""
        if not group_data:
            return None
        
        # 現在のロールマッピングを作成
        current_roles = {}
        for member in group_data.get('members', []):
            current_roles[member['id']] = member['role']
        
        # Bearer token統一管理システムで取得
        bearer_token = None
        if self.parent_widget:
            from core.bearer_token_manager import BearerTokenManager
            bearer_token = BearerTokenManager.get_valid_token()
        
        logger.debug("update_member_selection: Bearer token=%s", 'あり' if bearer_token else 'なし')
        
        # 新しいメンバーセレクターを作成（Bearer token付きでAPI補完有効化）
        new_member_selector = create_common_subgroup_member_selector_with_api_complement(
            initial_roles=current_roles,
            prechecked_user_ids=set(current_roles.keys()),
            subgroup_id=group_data.get('id'),
            bearer_token=bearer_token,
            disable_internal_scroll=True,
        )
        
        # スクロールエリアに設定
        self.scroll_area.setWidget(new_member_selector)
        self.current_member_selector = new_member_selector

        # 閲覧・修正タブは外側スクロールに集約するため、内側のスクロールを抑止
        try:
            from qt_compat.core import Qt
            self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            self.scroll_area.setWidgetResizable(True)
            self.scroll_area.setFrameStyle(0)
            self.scroll_area.setContentsMargins(0, 0, 0, 0)

            # セレクター側がコンテンツ全体の高さを持つ前提で、スクロールエリアも高さ追従
            target_h = int(new_member_selector.sizeHint().height()) if new_member_selector is not None else 0
            if target_h > 0:
                self.scroll_area.setMinimumHeight(target_h)
                self.scroll_area.setMaximumHeight(target_h)
        except Exception:
            logger.debug("member selector scroll suppression failed", exc_info=True)
        
        # Bearer tokenが取得できていない場合、後で再実行を試行
        if not bearer_token:
            logger.debug("Bearer token未取得のため、後で再実行を予約")
            from qt_compat.core import QTimer
            import weakref
            
            # 弱参照で安全にオブジェクトを保持
            weak_parent = weakref.ref(self.parent_widget) if self.parent_widget else None
            weak_self = weakref.ref(self)
            
            def safe_retry():
                self_ref = weak_self()
                parent_ref = weak_parent() if weak_parent else None
                
                if self_ref and parent_ref:
                    self_ref._retry_with_bearer_token(group_data, user_entries, parent_ref)
                else:
                    logger.debug("再実行時: オブジェクトが削除済みのためスキップ")
            
            QTimer.singleShot(2000, safe_retry)
        
        return new_member_selector
    
    def _retry_with_bearer_token(self, group_data, user_entries, parent_widget=None):
        """Bearer token取得後の再実行（安全版）"""
        target_parent = parent_widget or self.parent_widget
        
        if not target_parent:
            logger.debug("親ウィジェットが無効のため再実行をスキップ")
            return
        
        from core.bearer_token_manager import BearerTokenManager
        bearer_token = BearerTokenManager.get_valid_token()
        
        if bearer_token:
            logger.debug("Bearer token取得完了 - メンバーセレクターを再作成")
            self.update_member_selection(group_data, user_entries)
        else:
            logger.debug("Bearer token再取得失敗")
    
    def get_current_selector(self):
        """現在のメンバーセレクターを取得"""
        return self.current_member_selector


class SubgroupSelector:
    """
    既存サブグループ選択とフィルタリング専用クラス
    """
    
    def __init__(self, combo_widget, filter_combo, on_selection_changed=None, pre_filter_input: Optional[QLineEdit] = None):
        self.combo_widget = combo_widget
        self.filter_combo = filter_combo
        self.on_selection_changed = on_selection_changed
        self.pre_filter_input = pre_filter_input
        self.groups_data = []
        self.filtered_groups_data = []
        self.sample_count_cache = {}  # 試料数キャッシュ
        self._detail_user_cache: dict[str, dict] = {}
        self._last_focus_group_id: Optional[str] = None
        self._combo_completer: Optional[QCompleter] = None
        
        # イベント接続
        self.filter_combo.currentTextChanged.connect(self.apply_filter)
        if self.pre_filter_input is not None:
            self.pre_filter_input.textChanged.connect(self.apply_filter)
        self.combo_widget.currentTextChanged.connect(self._on_combo_selection_changed)
    
    def load_existing_subgroups(self):
        """既存サブグループの読み込み"""
        try:
            # subGroup.json / subGroups詳細の内容が更新され得るため、読み込み前にキャッシュを破棄
            try:
                self._detail_user_cache.clear()
            except Exception:
                pass

            if not os.path.exists(SUBGROUP_JSON_PATH):
                logger.info("サブグループファイルが見つかりません: %s", SUBGROUP_JSON_PATH)
                self._set_empty_state("サブグループファイルが見つかりません")
                return False
            
            with open(SUBGROUP_JSON_PATH, encoding="utf-8") as f:
                data = json.load(f)
            
            # データ処理
            groups = self._extract_groups_from_json(data)

            # RDE側で削除済み（404/410確認済み）のサブグループは候補から除外
            try:
                from classes.utils.remote_resource_pruner import filter_out_marked_missing_ids

                groups = filter_out_marked_missing_ids(
                    groups or [],
                    resource_type="group",
                    id_key="id",
                )
            except Exception:
                pass
            
            logger.debug("サブグループ抽出完了: %s件", len(groups))
            self.groups_data = groups
            
            # 試料数の事前読み込み（バックグラウンドで実行）
            logger.debug("関連試料数の事前読み込みを開始...")
            self._preload_sample_counts()
            logger.debug("関連試料数の事前読み込み完了")
            
            self.apply_filter()

            # 直前にフォーカス指定されたサブグループがあれば再選択
            try:
                if self._last_focus_group_id:
                    self.select_group_by_id(self._last_focus_group_id, prompt_clear_filter=True)
            except Exception:
                pass
            return True
            
        except Exception as e:
            logger.error("サブグループ読み込みエラー: %s", e)
            self._set_empty_state("読み込みエラー")
            return False
    
    def _extract_groups_from_json(self, data):
        """JSONデータからグループ情報を抽出"""
        # データ型検証
        if not isinstance(data, dict):
            logger.error("JSONデータがdict型ではありません: %s", type(data))
            return []
        
        # ユーザー情報マップ作成
        user_map = {}
        included_items = data.get("included", [])
        
        if not isinstance(included_items, list):
            logger.error("included がlist型ではありません: %s", type(included_items))
            return []
        
        for item in included_items:
            if not isinstance(item, dict):
                logger.warning("included内のitemがdict型ではありません: %s", type(item))
                continue
            if item.get("type") == "user":
                user_map[item["id"]] = item.get("attributes", {})
        
        # サブグループデータ抽出
        groups = []
        for item in included_items:
            if not isinstance(item, dict):
                logger.warning("グループitemがdict型ではありません: %s", type(item))
                continue
            if item.get("type") == "group":
                attr = item.get("attributes", {})
                if not isinstance(attr, dict):
                    logger.warning("attributes がdict型ではありません: %s", type(attr))
                    continue
                if attr.get("groupType") == "TEAM":
                    members = self._build_member_list(attr.get("roles", []), user_map, item.get("id", ""))
                    groups.append({
                        "id": item.get("id", ""),
                        "name": attr.get("name", ""),
                        "description": attr.get("description", ""),
                        "subjects": attr.get("subjects", []),
                        "funds": attr.get("funds", []),
                        "members": members,
                        "roles": attr.get("roles", [])
                    })
        
        return groups
    
    def _read_detail_user_attributes(self, subgroup_id: str) -> dict:
        """サブグループ個別ファイルからユーザー属性を読み込む（キャッシュ付き）。"""
        if not subgroup_id:
            return {}
        if subgroup_id in self._detail_user_cache:
            return self._detail_user_cache[subgroup_id]

        attr_map: dict[str, dict] = {}
        candidate_paths = [
            os.path.join(SUBGROUP_DETAILS_DIR, f"{subgroup_id}.json"),
            os.path.join(SUBGROUP_REL_DETAILS_DIR, f"{subgroup_id}.json"),
        ]
        for path in candidate_paths:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                for item in (data or {}).get("included", []) or []:
                    if item.get("type") == "user":
                        uid = item.get("id")
                        if uid:
                            attr_map[str(uid)] = item.get("attributes", {}) or {}
                if attr_map:
                    break
            except FileNotFoundError:
                logger.debug("サブグループ詳細ファイル未検出: %s", path)
            except Exception as e:
                logger.debug("サブグループ詳細読込失敗 (%s): %s", path, e)

        self._detail_user_cache[subgroup_id] = attr_map
        return attr_map

    def _build_member_list(self, roles, user_map, subgroup_id: str):
        """ロール情報からメンバーリストを構築"""
        detail_attr_map = self._read_detail_user_attributes(subgroup_id)
        members = []
        for role in roles:
            user_id = role.get("userId", "")
            role_type = role.get("role", "MEMBER")
            user_attr = detail_attr_map.get(user_id) or user_map.get(user_id, {})
            members.append({
                "id": user_id,
                "name": user_attr.get("userName", "Unknown"),
                "email": user_attr.get("emailAddress", ""),
                "role": role_type
            })
        return members
    
    def _set_empty_state(self, message):
        """空状態の設定"""
        self.groups_data = []
        self.filtered_groups_data = []
        self.combo_widget.clear()
        self.combo_widget.addItem(message, None)
    
    def _normalize_filter_text(self, text: str) -> str:
        return (text or "").strip().lower()

    def _matches_pre_filter(self, group: dict, filter_text: str) -> bool:
        if not filter_text:
            return True
        name = str((group or {}).get("name", "") or "")
        group_id = str((group or {}).get("id", "") or "")
        desc = str((group or {}).get("description", "") or "")
        haystack = f"{name} {group_id} {desc}".lower()
        return filter_text in haystack

    def _format_combo_display(self, group: dict, sample_count: int) -> tuple[str, str]:
        name = str((group or {}).get("name", "") or "")
        desc_raw = str((group or {}).get("description", "") or "")
        desc_full = desc_raw if desc_raw else "説明なし"
        group_id = str((group or {}).get("id", "") or "")
        short_id = group_id[:10] if group_id else ""
        sample_label = f"試料: {sample_count}件" if sample_count >= 0 else "試料: N/A"

        tooltip = f"{name} ({desc_full}、{sample_label}、{group_id})"

        try:
            view = self.combo_widget.view()
            view_width = int(view.viewport().width()) if view and view.viewport() else 0
        except Exception:
            view_width = 0

        if view_width <= 0:
            try:
                view_width = int(self.combo_widget.width())
            except Exception:
                view_width = 0
        if view_width <= 0:
            view_width = 400

        id_display = short_id if short_id else group_id
        prefix = f"{name} ("
        suffix = f"、{sample_label}、{id_display})"
        try:
            fm = self.combo_widget.fontMetrics()
            available = max(20, int(view_width) - fm.horizontalAdvance(prefix + suffix) - 12)
            desc_display = fm.elidedText(desc_full, Qt.ElideRight, available)
        except Exception:
            desc_display = desc_full

        display_text = f"{name} ({desc_display}、{sample_label}、{id_display})"
        return display_text, tooltip

    def apply_filter(self):
        """フィルター適用"""
        filter_value = self.filter_combo.currentData()
        current_user_id = self._get_current_user_id()
        pre_filter_text = ""
        if self.pre_filter_input is not None:
            try:
                pre_filter_text = self._normalize_filter_text(self.pre_filter_input.text())
            except Exception:
                pre_filter_text = ""
        
        if filter_value == "none":
            base_groups = self.groups_data.copy()
        else:
            base_groups = []
            for group in self.groups_data:
                if self._should_include_group(group, filter_value, current_user_id):
                    base_groups.append(group)

        if pre_filter_text:
            self.filtered_groups_data = [
                group for group in base_groups
                if self._matches_pre_filter(group, pre_filter_text)
            ]
        else:
            self.filtered_groups_data = base_groups
        
        self._update_combo_items()
    
    def _should_include_group(self, group, filter_value, current_user_id):
        """グループがフィルター条件に合致するかチェック"""
        user_roles = []
        for role in group.get("roles", []):
            if role.get("userId") == current_user_id:
                user_roles.append(role.get("role", ""))
        
        if filter_value == "owner" and "OWNER" in user_roles:
            return True
        elif filter_value == "both" and ("OWNER" in user_roles or "ASSISTANT" in user_roles):
            return True
        elif filter_value == "assistant" and "ASSISTANT" in user_roles:
            return True
        elif filter_value == "member" and "MEMBER" in user_roles:
            return True
        elif filter_value == "agent" and "AGENT" in user_roles:
            return True
        elif filter_value == "viewer" and "VIEWER" in user_roles:
            return True

        return False
    
    def _get_current_user_id(self):
        """現在のユーザーIDを取得"""
        try:
            from config.common import SELF_JSON_PATH
            with open(SELF_JSON_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("data", {}).get("id", "")
        except Exception as e:
            logger.debug("ユーザーID取得エラー: %s", e)
            return ""
    
    def _update_combo_items(self):
        """コンボボックスアイテムの更新"""
        current_group_id = None
        try:
            current_data = self.combo_widget.currentData()
            if isinstance(current_data, dict):
                current_group_id = str(current_data.get("id", "") or "")
        except Exception:
            current_group_id = None

        self.combo_widget.clear()
        
        if not self.filtered_groups_data:
            self.combo_widget.addItem("該当するサブグループがありません", None)
            return
        
        # グループ名でソート
        sorted_groups = sorted(self.filtered_groups_data, key=lambda g: g["name"])
        
        display_texts = []
        for group in sorted_groups:
            # 関連試料数の取得
            sample_count = self._get_sample_count(group['id'])
            
            display_text, tooltip = self._format_combo_display(group, sample_count)
            self.combo_widget.addItem(display_text, group)
            try:
                self.combo_widget.setItemData(self.combo_widget.count() - 1, tooltip, Qt.ToolTipRole)
            except Exception:
                pass
            display_texts.append(display_text)

        # 部分一致検索のためのCompleter設定
        try:
            completer = QCompleter(display_texts, self.combo_widget)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            popup_view = completer.popup()
            popup_view.setMinimumHeight(240)
            popup_view.setMaximumHeight(240)
            self.combo_widget.setCompleter(completer)
            self._combo_completer = completer
        except Exception:
            pass

        if current_group_id:
            try:
                for i in range(self.combo_widget.count()):
                    data = self.combo_widget.itemData(i)
                    if isinstance(data, dict) and str(data.get("id", "") or "") == current_group_id:
                        self.combo_widget.setCurrentIndex(i)
                        break
            except Exception:
                pass

    def _find_group_by_id(self, group_id: str) -> Optional[dict]:
        if not group_id:
            return None
        for g in self.groups_data or []:
            try:
                if isinstance(g, dict) and str(g.get("id", "") or "") == str(group_id):
                    return g
            except Exception:
                continue
        return None

    def _select_combo_item_by_group_id(self, group_id: str) -> bool:
        if not group_id:
            return False
        for i in range(self.combo_widget.count()):
            try:
                data = self.combo_widget.itemData(i)
                if isinstance(data, dict) and str(data.get("id", "") or "") == str(group_id):
                    self.combo_widget.setCurrentIndex(i)
                    return True
            except Exception:
                continue
        return False

    def _set_filter_none(self) -> bool:
        """フィルタコンボを 'フィルタ無し' に切り替える。"""
        try:
            for i in range(self.filter_combo.count()):
                if self.filter_combo.itemData(i) == "none":
                    self.filter_combo.setCurrentIndex(i)
                    return True
        except Exception:
            pass
        return False

    def select_group_by_id(self, group_id: str, prompt_clear_filter: bool = True) -> bool:
        """指定IDのサブグループを選択する。

        フィルタが厳しく表示できない場合は、必要時のみフィルタ解除を確認して再表示する。
        """
        group_id = str(group_id or "")
        if not group_id:
            return False

        # 現在の候補から選択を試行
        if self._select_combo_item_by_group_id(group_id):
            self._last_focus_group_id = group_id
            return True

        # そもそもデータに存在しない場合は諦める
        if not self._find_group_by_id(group_id):
            return False

        # フィルタ条件で見えない場合のみ、解除確認
        if prompt_clear_filter and self.filter_combo.currentData() != "none":
            try:
                reply = QMessageBox.question(
                    self.combo_widget,
                    "フィルタ解除の確認",
                    "更新したサブグループが現在の表示フィルタ条件では表示できません。\n"
                    "フィルタを解除して表示しますか？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if reply == QMessageBox.Yes:
                    self._set_filter_none()
                    # apply_filter は currentTextChanged 経由でも呼ばれるが、明示的に安全側で呼ぶ
                    try:
                        self.apply_filter()
                    except Exception:
                        pass
                    if self._select_combo_item_by_group_id(group_id):
                        self._last_focus_group_id = group_id
                        return True
            except Exception:
                pass

        return False
    
    def _get_sample_count(self, subgroup_id):
        """サブグループIDに対応する関連試料数を取得（キャッシュ付き）"""
        # キャッシュから取得を試行
        if subgroup_id in self.sample_count_cache:
            return self.sample_count_cache[subgroup_id]
        
        try:
            from config.common import get_samples_dir_path
            samples_dir = get_samples_dir_path()
            sample_file = os.path.join(samples_dir, f"{subgroup_id}.json")
            
            if not os.path.exists(sample_file):
                count = 0
            else:
                with open(sample_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                samples_data = data.get('data', [])
                count = len(samples_data)
            
            # キャッシュに保存
            self.sample_count_cache[subgroup_id] = count
            return count
            
        except Exception as e:
            logger.debug("試料数取得エラー (ID: %s): %s", subgroup_id, e)
            # エラーの場合もキャッシュに保存（再試行を避ける）
            self.sample_count_cache[subgroup_id] = -1
            return -1
    
    def _preload_sample_counts(self):
        """全サブグループの試料数を事前に読み込み（オプション）"""
        try:
            from config.common import get_samples_dir_path
            samples_dir = get_samples_dir_path()
            
            if not os.path.exists(samples_dir):
                return
            
            # samplesディレクトリ内の全JSONファイルを取得
            for filename in os.listdir(samples_dir):
                if filename.endswith('.json'):
                    subgroup_id = filename[:-5]  # .jsonを除去
                    
                    # 既にキャッシュされていない場合のみ読み込み
                    if subgroup_id not in self.sample_count_cache:
                        self._get_sample_count(subgroup_id)
        
        except Exception as e:
            logger.debug("試料数事前読み込みエラー: %s", e)
    
    def _on_combo_selection_changed(self, text):
        """コンボボックス選択変更時の処理"""
        current_data = self.combo_widget.currentData()

        def _running_under_pytest() -> bool:
            try:
                return bool(os.environ.get("PYTEST_CURRENT_TEST")) or ("pytest" in sys.modules)
            except Exception:
                return False

        # RDE側で削除済みのサブグループを選択してしまうケースの対策
        if not _running_under_pytest():
            try:
                if isinstance(current_data, dict):
                    group_id = str(current_data.get("id", "") or "")
                    if group_id:
                        from classes.utils.remote_resource_pruner import check_group_exists

                        check = check_group_exists(group_id, timeout=3.0)
                        if check.exists is False:
                            # groups_data から除外して再描画
                            try:
                                self.groups_data = [
                                    g
                                    for g in (self.groups_data or [])
                                    if not (isinstance(g, dict) and str(g.get("id", "") or "") == group_id)
                                ]
                            except Exception:
                                pass
                            try:
                                self.filtered_groups_data = [
                                    g
                                    for g in (self.filtered_groups_data or [])
                                    if not (isinstance(g, dict) and str(g.get("id", "") or "") == group_id)
                                ]
                            except Exception:
                                pass
                            self.apply_filter()
                            try:
                                QMessageBox.warning(
                                    self.combo_widget,
                                    "サブグループ削除検知",
                                    "選択したサブグループはRDE上で削除済みのため、候補から除外しました。\n"
                                    "基本情報タブでJSONを再取得してください。",
                                )
                            except Exception:
                                pass
                            return
            except Exception:
                pass

        if self.on_selection_changed:
            self.on_selection_changed(current_data)
    
    def get_selected_group(self):
        """選択されたグループデータを取得"""
        return self.combo_widget.currentData()


class RelatedDatasetSection:
    """Displays datasets linked to the currently selected subgroup."""

    def __init__(self, fetcher: Optional[RelatedDatasetFetcher] = None) -> None:
        import os

        self.fetcher = fetcher or RelatedDatasetFetcher()
        self._is_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST"))
        self.widget = QWidget()
        self.widget.setObjectName("relatedDatasetSection")
        if self._is_pytest:
            self.widget.setAttribute(Qt.WA_DontShowOnScreen, True)
        container = QVBoxLayout()
        container.setContentsMargins(0, 12, 0, 0)
        container.setSpacing(6)
        self.widget.setLayout(container)

        header_layout = QHBoxLayout()
        header_label = QLabel("関連データセット")
        apply_label_style(header_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
        self.count_label = QLabel("0件 / 課題 0件")
        self.count_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)}; font-weight: bold;"
        )
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        header_layout.addWidget(self.count_label)
        container.addLayout(header_layout)

        self.message_label = QLabel("サブグループを選択すると関連データセットを表示します。")
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet(
            f"color: {get_color(ThemeKey.TEXT_MUTED)};"
        )
        container.addWidget(self.message_label)

        self.table = QTableWidget()
        if self._is_pytest:
            self.table.setAttribute(Qt.WA_DontShowOnScreen, True)
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "データセット",
            "課題番号",
            "作成日",
            "更新日",
            "タイル数",
            "ブラウザ",
        ])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.setMinimumHeight(180)
        self.table.setMaximumHeight(360)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 6):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header.setStretchLastSection(False)
        try:
            self.table.horizontalHeader().setDefaultAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        except Exception:
            pass
        self.table.hide()
        self.scroll_area = self.table
        container.addWidget(self.table)

    def update_for_group(self, group_data: Optional[dict]) -> None:
        """Render datasets associated with *group_data*."""

        if not group_data:
            self.clear()
            return

        subjects = group_data.get('subjects', []) if isinstance(group_data, dict) else []
        grant_numbers = self._extract_grant_numbers(subjects)
        grant_total = len(set(grant_numbers))

        if not grant_total:
            self.clear("サブグループに課題番号が設定されていません。", grant_total=0)
            return

        datasets = self.fetcher.get_related_datasets(grant_numbers)
        if not datasets:
            dataset_path = getattr(self.fetcher, 'dataset_json_path', '')
            if dataset_path and not os.path.exists(dataset_path):
                message = "dataset.jsonが見つからないため関連データセットを表示できません。"
            else:
                message = "関連するデータセットが見つかりません。"
            self.clear(message, grant_total=grant_total)
            return

        self._render_rows(datasets, grant_total)

    def clear(self, message: Optional[str] = None, grant_total: int = 0) -> None:
        """Clear the list and show *message*."""

        self._clear_rows()
        fallback = "サブグループを選択すると関連データセットを表示します。"
        self.message_label.setText(message or fallback)
        self.message_label.show()
        self.table.hide()
        self._update_count_label(0, grant_total)

    def _render_rows(self, datasets: List[RelatedDataset], grant_total: int) -> None:
        self._clear_rows()
        self.table.setRowCount(len(datasets))

        for row_idx, dataset in enumerate(datasets):
            dataset_id = str(dataset.get("id") or "")
            title = dataset.get("name") or "名称未設定"
            grant_number = dataset.get("grant_number") or "-"

            created_raw = dataset.get("created") or dataset.get("created_at") or dataset.get("createdAt")
            modified_raw = dataset.get("modified") or dataset.get("updated") or dataset.get("updatedAt")

            created_text = self._format_datetime(created_raw)
            modified_text = self._format_datetime(modified_raw)

            tile_count = self._resolve_tile_count(dataset_id)
            tile_text = "-" if tile_count is None else str(tile_count)

            title_button = QPushButton(title)
            title_button.setObjectName("relatedDatasetLinkButton")
            title_button.setFlat(True)
            title_button.setCursor(Qt.PointingHandCursor)
            title_button.setStyleSheet(
                f"color: {get_color(ThemeKey.TEXT_LINK)}; text-align: left; border: none;"
            )
            if dataset_id:
                title_button.setToolTip(f"{title}\n{dataset_id}")
                title_button.clicked.connect(
                    lambda _checked=False, ds_id=dataset_id, ds_name=title: self._launch_dataset_edit(ds_id, ds_name)
                )
            else:
                title_button.setEnabled(False)
                title_button.setToolTip("データセットIDが見つかりません")
            self.table.setCellWidget(row_idx, 0, title_button)

            grant_item = QTableWidgetItem(grant_number)
            grant_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 1, grant_item)

            created_item = QTableWidgetItem(created_text)
            created_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 2, created_item)

            modified_item = QTableWidgetItem(modified_text)
            modified_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 3, modified_item)

            tile_item = QTableWidgetItem(tile_text)
            tile_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row_idx, 4, tile_item)

            browser_btn = QPushButton("開く")
            browser_btn.setObjectName("relatedDatasetOpenButton")
            browser_btn.setFixedWidth(64)
            browser_btn.setStyleSheet(
                f"background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};"
                f"color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)}; font-weight: bold; border-radius: 4px;"
                f"border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BORDER)};"
            )
            if dataset_id:
                browser_btn.clicked.connect(
                    lambda _checked=False, ds_id=dataset_id: self._open_dataset_page(ds_id)
                )
            else:
                browser_btn.setEnabled(False)
                browser_btn.setToolTip("データセットIDが見つかりません")
            self.table.setCellWidget(row_idx, 5, browser_btn)

        try:
            self.table.resizeRowsToContents()
        except Exception:
            pass

        self.message_label.hide()
        self.table.show()
        self._update_count_label(len(datasets), grant_total)

    def _format_datetime(self, value: Optional[str]) -> str:
        if not value:
            return "--"
        try:
            from classes.utils.dataset_datetime_display import format_iso_to_jst

            return format_iso_to_jst(str(value), with_seconds=False) or str(value)
        except Exception:
            return str(value)

    def _resolve_tile_count(self, dataset_id: str) -> Optional[int]:
        if not dataset_id:
            return None
        try:
            from config.common import get_dynamic_file_path

            path = get_dynamic_file_path(f"output/rde/data/dataEntry/{dataset_id}.json")
            if not path or not os.path.exists(path):
                return None
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            items = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(items, list):
                return len(items)
        except Exception:
            return None
        return None

    def _launch_dataset_edit(self, dataset_id: str, title: str) -> None:
        if not dataset_id:
            return
        try:
            from classes.utils.dataset_launch_manager import DatasetLaunchManager

            DatasetLaunchManager.instance().request_launch(
                target_key="dataset_edit",
                dataset_id=str(dataset_id),
                display_text=title or str(dataset_id),
                raw_dataset=None,
                source_name="subgroup_related_dataset",
            )
        except Exception:
            logger.debug("related dataset: dataset_edit launch failed", exc_info=True)

    def _open_dataset_page(self, dataset_id: str) -> None:
        url = DATASET_PAGE_TEMPLATE.format(id=dataset_id)
        try:
            webbrowser.open(url)
            logger.info("関連データセットページをブラウザで開きました: %s", url)
        except Exception as exc:
            logger.warning("関連データセットページを開けませんでした: %s", exc)

    def _update_count_label(self, dataset_count: int, grant_total: int) -> None:
        self.count_label.setText(f"{dataset_count}件 / 課題 {grant_total}件")

    def _clear_rows(self) -> None:
        try:
            self.table.setRowCount(0)
        except Exception:
            pass

    @staticmethod
    def _extract_grant_numbers(subjects: Iterable) -> List[str]:
        grant_numbers: List[str] = []
        if not isinstance(subjects, list):
            return grant_numbers
        for subject in subjects:
            if isinstance(subject, dict):
                grant = subject.get('grantNumber') or ""
                if grant:
                    grant_numbers.append(grant)
        return grant_numbers


def _create_related_dataset_section(layout: QVBoxLayout) -> RelatedDatasetSection:
    section = RelatedDatasetSection()
    layout.addWidget(section.widget)
    return section


def create_subgroup_edit_widget(parent, title, color, create_auto_resize_button):
    """
    サブグループ修正ウィジェット作成
    責務分離により保守性を向上
    """
    widget = QWidget()
    layout = QVBoxLayout()
    
    # タイトル
    title_label = QLabel(f"{title}機能")
    apply_label_style(title_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True, point_size=16)
    #layout.addWidget(title_label)
    
    button_style = f"background-color: {color}; color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)}; font-weight: bold; border-radius: 6px;"
    
    # === 1. 既存サブグループ選択UI ===
    selection_section = _create_selection_section(layout)
    filter_combo, existing_group_combo, refresh_btn, pre_filter_input = (
        selection_section['filter_combo'], 
        selection_section['combo'], 
        selection_section['refresh_btn'],
        selection_section['pre_filter_input'],
    )
    
    # === 2. メンバー選択UI ===
    member_section = _create_member_section(layout)
    scroll_area, initial_member_selector = member_section['scroll'], member_section['selector']
    
    # === 3. フォームUI ===
    form_section = _create_form_section(layout, create_auto_resize_button, button_style)
    form_widgets = form_section['widgets']
    
    # === 4. ボタンUI ===
    button_section = _create_button_section(layout, button_style, create_auto_resize_button)
    update_btn, show_selected_btn = button_section['update'], button_section['show']
    
    # === 5. 関連データセット表示 ===
    related_dataset_section = _create_related_dataset_section(layout)
    
    # === 6. 管理クラス初期化 ===
    managers = _initialize_managers(
        existing_group_combo, filter_combo, pre_filter_input, scroll_area, 
        form_section['builder'], form_widgets, widget, related_dataset_section
    )

    # 外部連携用（データ登録→サブグループ閲覧・修正ジャンプ等）
    try:
        widget._subgroup_selector = managers.get('selector')
    except Exception:
        pass
    
    # === 7. イベントハンドラー設定 ===
    _setup_event_handlers(
        widget, parent, managers, button_section, form_widgets, refresh_btn
    )
    
    # === 8. 初期化 ===
    managers['selector'].load_existing_subgroups()
    
    # 修正タブ作成時に動的ユーザーを初期化
    try:
        from ..core import subgroup_api_helper
        subgroup_api_helper.backup_and_clear_dynamic_users()
    except Exception as e:
        logger.warning("修正タブ作成時の動的ユーザー初期化エラー: %s", e)
    
    # 外部リフレッシュ用
    widget._refresh_subgroup_list = managers['selector'].load_existing_subgroups
    
    layout.addStretch()
    widget.setLayout(layout)
    return widget


def _create_selection_section(layout):
    """サブグループ選択セクションの作成"""
    selection_layout = QVBoxLayout()
    
    # フィルター部
    filter_layout = QHBoxLayout()
    filter_label = QLabel("表示フィルタ:")
    filter_combo = QComboBox()
    filter_combo.addItem("OWNER", "owner")
    filter_combo.addItem("OWNER+ASSISTANT", "both") 
    filter_combo.addItem("ASSISTANT", "assistant")
    filter_combo.addItem("MEMBER", "member")
    filter_combo.addItem("AGENT", "agent")
    filter_combo.addItem("VIEWER", "viewer")
    filter_combo.addItem("フィルタ無し", "none")
    filter_combo.setCurrentIndex(0)
    filter_layout.addWidget(filter_label)
    filter_layout.addWidget(filter_combo)
    
    # リフレッシュボタンをここで追加
    refresh_btn = QPushButton("サブグループリスト更新")
    filter_layout.addWidget(refresh_btn)
    filter_layout.addStretch()

    # 事前フィルタ（部分一致検索）
    pre_filter_layout = QHBoxLayout()
    pre_filter_label = QLabel("部分一致フィルタ:")
    pre_filter_input = QLineEdit()
    pre_filter_input.setObjectName("subgroupEditPreFilterInput")
    pre_filter_input.setPlaceholderText("サブグループ名・説明で絞り込み（部分一致）")
    pre_filter_layout.addWidget(pre_filter_label)
    pre_filter_layout.addWidget(pre_filter_input)
    pre_filter_layout.addStretch()
    
    # 選択コンボボックス
    existing_group_label = QLabel("修正するサブグループを選択:")
    existing_group_combo = QComboBox()
    existing_group_combo.setMinimumWidth(400)
    existing_group_combo.setEditable(True)
    existing_group_combo.setInsertPolicy(QComboBox.NoInsert)
    existing_group_combo.setMaxVisibleItems(12)
    existing_group_combo.view().setMinimumHeight(240)
    
    selection_layout.addWidget(existing_group_label)
    selection_layout.addLayout(filter_layout)
    selection_layout.addLayout(pre_filter_layout)
    selection_layout.addWidget(existing_group_combo)
    layout.addLayout(selection_layout)
    
    return {
        'filter_combo': filter_combo,
        'combo': existing_group_combo,
        'refresh_btn': refresh_btn,
        'pre_filter_input': pre_filter_input,
    }


def _create_member_section(layout):
    """メンバー選択セクションの作成"""
    # 初期状態では空のメンバーセレクターを作成
    member_selector = create_common_subgroup_member_selector(
        initial_roles={}, prechecked_user_ids=set(), disable_internal_scroll=True
    )
    
    # スクロールエリア設定（余白を最小化、画面サイズ対応）
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameStyle(0)  # フレームを削除
    scroll.setContentsMargins(0, 0, 0, 0)  # スクロールエリアの余白を削除

    # 閲覧・修正タブは外側スクロールに集約するため、内側のスクロールバーは表示しない
    try:
        from qt_compat.core import Qt
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    except Exception:
        pass
    
    # スクロールエリアのスタイルシートで余白を完全に削除
    scroll.setStyleSheet("""
        QScrollArea {
            border: none;
            margin: 0px;
            padding: 0px;
        }
    """)
    
    member_selector.setMinimumWidth(520)
    member_selector.setMaximumWidth(800)
    scroll.setMinimumWidth(520)  # スクロールエリア幅も調整
    scroll.setMaximumWidth(800)  # 余分な余白を削除
    
    # セレクター全体の高さに追従（スクロールは外側へ）
    try:
        calculated_height = int(member_selector.sizeHint().height())
        if calculated_height > 0:
            scroll.setMinimumHeight(calculated_height)
            scroll.setMaximumHeight(calculated_height)
        else:
            scroll.setMinimumHeight(150)
    except Exception:
        scroll.setMinimumHeight(150)
    
    # メンバーセレクターのラベルとスクロールエリアを余白なしで配置
    member_layout = QVBoxLayout()
    member_layout.setContentsMargins(0, 0, 0, 0)  # 完全に余白を削除
    member_layout.setSpacing(2)  # ラベルとテーブル間のスペースを最小化
    
    member_label = QLabel("グループメンバー選択（複数可）:")
    apply_label_style(member_label, get_color(ThemeKey.TEXT_PRIMARY), bold=True)
    member_layout.addWidget(member_label)
    member_layout.addWidget(scroll)
    
    layout.addLayout(member_layout)
    scroll.setWidget(member_selector)

    # 参照用（テスト/調整）
    try:
        scroll.setObjectName("subgroup_member_selector_scroll")
    except Exception:
        pass
    
    return {'scroll': scroll, 'selector': member_selector}


def _create_form_section(layout, create_auto_resize_button, button_style):
    """フォームセクションの作成"""
    form_builder = SubgroupFormBuilder(layout, create_auto_resize_button, button_style)
    form_widgets = form_builder.build_manual_input_form()
    return {'builder': form_builder, 'widgets': form_widgets}


def _create_button_section(layout, button_style, create_auto_resize_button):
    """ボタンセクションの作成"""
    button_layout = QHBoxLayout()
    
    # 選択ユーザー確認ボタン
    show_selected_btn = QPushButton("選択ユーザー/ロールを表示")
    button_layout.addWidget(show_selected_btn)
    
    # 関連試料抽出ボタン
    extract_samples_btn = QPushButton("関連試料抽出")
    #extract_samples_btn.setStyleSheet(button_style)
    button_layout.addWidget(extract_samples_btn)
    
    # サブグループページ表示ボタン
    #open_subgroup_page_btn = QPushButton("RDEサブグループページを開く")
    #open_subgroup_page_btn.setStyleSheet(button_style)
    open_subgroup_page_btn= create_auto_resize_button(
        "RDEサブグループページを開く", 200, 40, button_style
    )
    button_layout.addWidget(open_subgroup_page_btn)
    
    # 更新実行ボタン
    update_btn = create_auto_resize_button(
        "サブグループ更新", 200, 40, button_style
    )
    button_layout.addWidget(update_btn)
    
    layout.addLayout(button_layout)
    
    return {
        'update': update_btn,
        'show': show_selected_btn,
        'extract_samples': extract_samples_btn,
        'open_subgroup_page': open_subgroup_page_btn,
        'layout': button_layout
    }


def _initialize_managers(combo, filter_combo, pre_filter_input, scroll_area, form_builder, form_widgets, widget, dataset_section):
    """管理クラスの初期化"""
    
    def on_group_selection_changed(group_data):
        """グループ選択変更時のコールバック"""
        # 先に関連データセットを更新（Noneでも内部で初期化）
        dataset_section.update_for_group(group_data)
        if not group_data:
            return
        
        logger.info("選択されたグループ: %s", group_data['name'])
        
        # 修正タブでグループが選択された際に動的ユーザーを初期化
        try:
            from ..core import subgroup_api_helper
            subgroup_api_helper.backup_and_clear_dynamic_users()
        except Exception as e:
            logger.warning("動的ユーザー初期化エラー: %s", e)
        
        # フォーム更新
        form_manager.populate_form_from_group(group_data)
        
        # メンバー選択更新
        user_entries = load_user_entries()
        new_selector = member_manager.update_member_selection(group_data, user_entries)
        
        # ハンドラーのセレクター参照更新
        if new_selector:
            edit_handler.member_selector = new_selector
            edit_handler.set_selected_group(group_data)
    
    # 管理クラス初期化
    selector = SubgroupSelector(combo, filter_combo, on_group_selection_changed, pre_filter_input=pre_filter_input)
    form_manager = EditFormManager(None, form_builder, form_widgets)
    member_manager = EditMemberManager(scroll_area, parent_widget=widget)  # parent_widgetを追加
    edit_handler = SubgroupEditHandler(None, None, member_manager.get_current_selector())
    
    # subGroup.json更新時にコンボボックスエントリーを更新
    try:
        from classes.dataset.util.dataset_refresh_notifier import get_subgroup_refresh_notifier
        notifier = get_subgroup_refresh_notifier()
        
        # selector.load_existing_subgroupsをコールバックとして登録
        def refresh_callback():
            logger.info("サブグループ更新通知を受け取り、エントリーを更新します")
            selector.load_existing_subgroups()

            # 直前に更新したサブグループがある場合は、それを優先して再表示
            try:
                group_id = getattr(widget, "_last_updated_subgroup_id", None)
                if group_id:
                    if selector.select_group_by_id(str(group_id), prompt_clear_filter=True):
                        widget._last_updated_subgroup_id = None
            except Exception:
                pass
        
        notifier.register_callback(refresh_callback)
        logger.info("サブグループ更新通知コールバックを登録しました")
    except Exception as e:
        logger.warning("サブグループ更新通知登録エラー: %s", e)
    
    return {
        'selector': selector,
        'form': form_manager,
        'member': member_manager,
        'handler': edit_handler,
        'datasets': dataset_section,
    }


def _setup_event_handlers(widget, parent, managers, button_section, form_widgets, refresh_btn):
    """イベントハンドラーの設定"""
    
    # 管理クラス取得
    edit_handler = managers['handler'] 
    form_manager = managers['form']
    selector = managers['selector']
    member_manager = managers['member']
    
    # ハンドラーの widget, parent 設定
    edit_handler.widget = widget
    edit_handler.parent = parent
    
    def on_show_selected():
        """選択ユーザー確認"""
        current_selector = member_manager.get_current_selector()
        if current_selector and current_selector.user_rows:
            # セレクター内のuser_entriesを使用（統合メンバーリスト）
            user_entries = current_selector.user_entries if hasattr(current_selector, 'user_entries') else []
            show_selected_user_ids(widget, current_selector.user_rows, user_entries)
    
    def on_extract_samples():
        """関連試料抽出"""
        selected_group = selector.get_selected_group()
        if not selected_group:
            QMessageBox.warning(widget, "選択エラー", "関連試料を抽出するサブグループを選択してください。")
            return
        
        subgroup_id = selected_group.get('id')
        if not subgroup_id:
            QMessageBox.warning(widget, "データエラー", "選択されたサブグループのIDが取得できません。")
            return
        
        # 関連試料抽出ダイアログを表示
        from ..util.sample_extractor import show_related_samples_dialog
        show_related_samples_dialog(subgroup_id, widget)
    
    def on_open_subgroup_page():
        """サブグループページをブラウザで開く"""
        selected_group = selector.get_selected_group()
        if not selected_group:
            QMessageBox.warning(widget, "選択エラー", "開くサブグループを選択してください。")
            return
        
        subgroup_id = selected_group.get('id')
        if not subgroup_id:
            QMessageBox.warning(widget, "データエラー", "選択されたサブグループのIDが取得できません。")
            return
        
        # サブグループページのURLを生成してブラウザで開く
        url = f"https://rde.nims.go.jp/rde/datasets/groups/{subgroup_id}"
        try:
            webbrowser.open(url)
            logger.info("サブグループページをブラウザで開きました: %s", url)
        except Exception as e:
            QMessageBox.warning(widget, "エラー", f"ブラウザでページを開けませんでした: {str(e)}")
    
    def on_update_subgroup():
        """サブグループ更新処理"""
        if not edit_handler.selected_group_data:
            QMessageBox.warning(widget, "選択エラー", "修正するサブグループを選択してください。")
            return
        
        # フォーム値取得
        form_values = form_manager.get_form_values()
        
        # バリデーション
        if not form_values['group_name']:
            QMessageBox.warning(widget, "入力エラー", "グループ名を入力してください。")
            return
        
        # ユーザーロール抽出
        selected_user_ids, roles, owner_id, owner_count = edit_handler.extract_user_roles()
        
        if not edit_handler.validate_owner_selection(owner_count):
            return
        
        if not selected_user_ids and not owner_id:
            QMessageBox.warning(widget, "ユーザー未選択", "更新するユーザーを1人以上選択してください。")
            return
        
        # 更新処理実行
        _execute_update(edit_handler, form_values, roles, widget=widget, selector=selector)
    
    # イベント接続
    button_section['show'].clicked.connect(on_show_selected)
    button_section['extract_samples'].clicked.connect(on_extract_samples)
    button_section['open_subgroup_page'].clicked.connect(on_open_subgroup_page)
    button_section['update'].clicked.connect(on_update_subgroup)
    refresh_btn.clicked.connect(selector.load_existing_subgroups)


def _execute_update(edit_handler, form_values, roles, widget, selector):
    """更新処理の実行"""
    selected_group = edit_handler.selected_group_data
    group_id = selected_group['id']
    group_name = form_values['group_name']
    
    # ペイロード作成（新しい課題データ形式・研究資金番号リスト対応）
    subjects = form_values['subjects_data']  # 既にリスト形式
    funds = form_values.get('funds_list', [])  # リスト形式で取得
    
    payload = edit_handler.extract_update_payload(
        group_id, group_name, form_values['description'], subjects, funds, roles
    )
    
    # 確認ダイアログ
    payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
    msg_box, yes_btn = edit_handler.create_update_confirmation_dialog(payload, payload_str)
    reply = msg_box.exec()
    
    if msg_box.clickedButton() != yes_btn:
        return
    
    # API送信
    success = edit_handler.send_update_request(payload, group_id, group_name)
    
    if success:
        logger.info("サブグループ[%s]の更新が完了しました", group_name)

        # 更新直後は当該サブグループを再選択して再表示する
        try:
            widget._last_updated_subgroup_id = str(group_id)
        except Exception:
            pass
        try:
            selector.load_existing_subgroups()
            selector.select_group_by_id(str(group_id), prompt_clear_filter=True)
        except Exception as e:
            logger.debug("更新後の再選択に失敗: %s", e)
    else:
        logger.error("サブグループ[%s]の更新に失敗しました", group_name)
