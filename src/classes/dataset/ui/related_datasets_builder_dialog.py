"""
関連データセットビルダーダイアログ - RelatedDatasetsBuilderDialog
関連データセットをコンボボックスとテーブルで管理するダイアログ
"""
import os
import json
import logging
from typing import Any

try:
    from qt_compat.widgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
        QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QCompleter,
        QTextEdit, QRadioButton, QLineEdit, QWidget,
    )
    from qt_compat.core import Qt, Signal
except Exception:
    from PySide6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
        QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QCompleter,
        QTextEdit, QRadioButton, QLineEdit, QWidget,
    )
    from PySide6.QtCore import Qt, Signal

from config.common import get_dynamic_file_path
from classes.theme.theme_keys import ThemeKey
from classes.theme.theme_manager import get_color

logger = logging.getLogger(__name__)


class RelatedDatasetsBuilderDialog(QDialog):
    """関連データセットビルダーダイアログ
    
    関連データセットをコンボボックスで選択し、テーブルで管理する。
    同じ課題番号のデータセットを全て追加する機能も提供。
    
    Signals:
        datasets_changed: 関連データセットが変更された時に発火 (list: dataset_id のリスト)
    """
    
    datasets_changed = Signal(list)
    
    def __init__(self, parent=None, current_dataset_ids=None, exclude_dataset_id=None, current_grant_number=None):
        """
        Args:
            parent: 親ウィジェット
            current_dataset_ids: 現在選択されている関連データセットIDのリスト
            exclude_dataset_id: 除外するデータセットID（編集中のデータセット）
            current_grant_number: 現在のデータセットの課題番号（同じ課題番号追加用）
        """
        super().__init__(parent)
        self.setWindowTitle("関連データセットビルダー")
        self.setMinimumWidth(800)
        self.setMinimumHeight(500)
        
        self.exclude_dataset_id = exclude_dataset_id
        self.current_grant_number = current_grant_number
        self.all_datasets = []
        self.user_grant_numbers = set()

        # サブグループ名解決用
        self._subgroup_name_by_id: dict[str, str] = {}

        # 相互関連（表示中のデータセット -> 呼び出し元データセット）判定キャッシュ
        # dataset_id -> set(related_dataset_id)
        self._related_ids_cache: dict[str, set[str]] = {}
        
        # ダイアログレイアウト
        layout = QVBoxLayout()
        
        # 説明ラベル
        desc_label = QLabel("関連データセットを選択・管理します")
        desc_label.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_SECONDARY)}; margin-bottom: 8px;")
        layout.addWidget(desc_label)
        
        # データセット選択エリア
        # 同じ課題番号の一括追加ボタン（コンボ行の上へ分離）
        add_all_row = QHBoxLayout()
        self.add_all_grant_button = QPushButton("同じ課題番号のデータセットを全て追加する")
        self.add_all_grant_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            }}
        """)
        self.add_all_grant_button.clicked.connect(self.add_all_from_grant_number)
        add_all_row.addWidget(self.add_all_grant_button)
        add_all_row.addStretch(1)
        
        # 課題番号が設定されていない場合はボタンを無効化
        if not current_grant_number:
            self.add_all_grant_button.setEnabled(False)
            self.add_all_grant_button.setToolTip("現在のデータセットに課題番号が設定されていません")
        else:
            self.add_all_grant_button.setToolTip(f"課題番号 '{current_grant_number}' の全データセットを追加")

        layout.addLayout(add_all_row)

        # フィルタ設定（閲覧・修正タブと同様: 表示データセット + 課題番号絞り込み）
        filter_widget = QWidget()
        filter_layout = QVBoxLayout()
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(4)

        filter_type_widget = QWidget()
        filter_type_layout = QHBoxLayout()
        filter_type_layout.setContentsMargins(0, 0, 0, 0)

        filter_type_label = QLabel("表示データセット:")
        filter_type_label.setMinimumWidth(120)
        filter_type_label.setStyleSheet("font-weight: bold;")

        self.filter_user_only_radio = QRadioButton("ユーザー所属のみ")
        self.filter_user_only_radio.setObjectName("related_dataset_filter_user_only_radio")
        self.filter_others_only_radio = QRadioButton("その他のみ")
        self.filter_others_only_radio.setObjectName("related_dataset_filter_others_only_radio")
        self.filter_all_radio = QRadioButton("すべて")
        self.filter_all_radio.setObjectName("related_dataset_filter_all_radio")
        self.filter_user_only_radio.setChecked(True)

        filter_type_layout.addWidget(filter_type_label)
        filter_type_layout.addWidget(self.filter_user_only_radio)
        filter_type_layout.addWidget(self.filter_others_only_radio)
        filter_type_layout.addWidget(self.filter_all_radio)
        filter_type_layout.addStretch(1)
        filter_type_widget.setLayout(filter_type_layout)
        filter_layout.addWidget(filter_type_widget)

        grant_filter_widget = QWidget()
        grant_filter_layout = QHBoxLayout()
        grant_filter_layout.setContentsMargins(0, 0, 0, 0)

        grant_filter_label = QLabel("課題番号絞り込み:")
        grant_filter_label.setMinimumWidth(120)
        grant_filter_label.setStyleSheet("font-weight: bold;")

        self.grant_number_filter_edit = QLineEdit()
        self.grant_number_filter_edit.setObjectName("related_dataset_grant_number_filter_edit")
        self.grant_number_filter_edit.setPlaceholderText("課題番号の一部を入力（部分一致検索・リアルタイム絞り込み）")
        self.grant_number_filter_edit.setMinimumWidth(400)

        grant_filter_layout.addWidget(grant_filter_label)
        grant_filter_layout.addWidget(self.grant_number_filter_edit)
        grant_filter_layout.addStretch(1)
        grant_filter_widget.setLayout(grant_filter_layout)
        filter_layout.addWidget(grant_filter_widget)

        filter_widget.setLayout(filter_layout)
        layout.addWidget(filter_widget)

        # データセット選択（選択→追加ボタンでリストに追加）
        select_layout = QHBoxLayout()
        select_layout.addWidget(QLabel("データセット選択:"))

        self.dataset_combo = QComboBox()
        self.dataset_combo.setEditable(True)
        self.dataset_combo.setInsertPolicy(QComboBox.NoInsert)
        self.dataset_combo.lineEdit().setPlaceholderText("関連データセットを検索・選択...")
        select_layout.addWidget(self.dataset_combo, 1)

        self.add_selected_button = QPushButton("関連データセットを追加")
        self.add_selected_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                font-weight: bold;
                padding: 6px 10px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            }}
        """)
        self.add_selected_button.clicked.connect(self._add_selected_dataset_from_combo)
        select_layout.addWidget(self.add_selected_button)

        layout.addLayout(select_layout)

        # フィルタ変更で即時にコンボ内容を再構築
        try:
            self.filter_user_only_radio.toggled.connect(lambda *_: self._apply_filters_to_combo())
            self.filter_others_only_radio.toggled.connect(lambda *_: self._apply_filters_to_combo())
            self.filter_all_radio.toggled.connect(lambda *_: self._apply_filters_to_combo())
            self.grant_number_filter_edit.textChanged.connect(lambda *_: self._apply_filters_to_combo())
        except Exception:
            pass

        # 選択中データセットの日時（JST）を表示
        try:
            from classes.utils.dataset_datetime_display import create_dataset_dates_label, attach_dataset_dates_label

            self.dataset_dates_label = create_dataset_dates_label(self)
            attach_dataset_dates_label(combo=self.dataset_combo, label=self.dataset_dates_label)
            layout.addWidget(self.dataset_dates_label)
        except Exception:
            self.dataset_dates_label = None
        
        # テーブル作成
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "サブグループ",
            "課題番号",
            "データセット名",
            "タイプ",
            "相互関連",
            "関連付け",
            "削除",
        ])
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)
        
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)

        # 一括: 表示中 + テーブル内を相互関連付け
        bulk_row = QHBoxLayout()
        self.bulk_link_button = QPushButton("リストされた関連データセットを全て相互関連付ける")
        self.bulk_link_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                font-weight: bold;
                padding: 8px 12px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DISABLED_TEXT)};
            }}
        """)
        self.bulk_link_button.clicked.connect(self._on_bulk_link_all_mutually)
        bulk_row.addWidget(self.bulk_link_button)
        bulk_row.addStretch(1)
        layout.addLayout(bulk_row)
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        ok_button = QPushButton("OK")
        ok_button.setMinimumWidth(100)
        ok_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
        """)
        ok_button.clicked.connect(self.accept)
        button_layout.addWidget(ok_button)
        
        cancel_button = QPushButton("キャンセル")
        cancel_button.setMinimumWidth(100)
        cancel_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
            }}
        """)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        
        # データ読み込みとセットアップ
        self._load_all_datasets()
        self._load_subgroup_names()
        self._setup_combo()
        
        # 現在のデータセットを読み込み
        if current_dataset_ids:
            self._load_current_datasets(current_dataset_ids)
        
        # コンボボックスのイベント接続（選択だけでは追加しない）
        self.dataset_combo.currentIndexChanged.connect(lambda *_: self._update_add_button_state())
        self._update_add_button_state()
        try:
            self.dataset_combo.lineEdit().returnPressed.connect(self._add_selected_dataset_from_combo)
        except Exception:
            pass
    
    def _load_all_datasets(self):
        """全データセットを読み込み"""
        try:
            datasets_file = get_dynamic_file_path("output/rde/data/dataset.json")
            if not os.path.exists(datasets_file):
                logger.error("データセットファイルが見つかりません: %s", datasets_file)
                return
            
            with open(datasets_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            all_datasets = data.get("data", [])
            
            # 除外するデータセットIDがある場合はフィルタリング
            if self.exclude_dataset_id:
                all_datasets = [ds for ds in all_datasets if ds.get("id") != self.exclude_dataset_id]
            
            self.all_datasets = all_datasets
            logger.info("全データセット読み込み完了: %s件", len(self.all_datasets))
            
            # ユーザーのgrantNumberを取得
            self._load_user_grant_numbers()
            
        except Exception as e:
            logger.error("データセット読み込みエラー: %s", e)
    
    def _load_user_grant_numbers(self):
        """ユーザーのgrantNumberを取得"""
        try:
            # サブグループファイルとセルフファイルから取得
            sub_group_path = get_dynamic_file_path('output/rde/data/subGroup.json')
            self_path = get_dynamic_file_path('output/rde/data/self.json')

            grant_numbers: set[str] = set()

            # まずは閲覧・修正タブと同様に self.json + subGroup.json(includedのTEAM/roles/subjects) を使う
            user_id: str | None = None
            if os.path.exists(self_path):
                try:
                    with open(self_path, encoding="utf-8") as f:
                        self_data = json.load(f)
                    raw_user_id = (self_data.get("data") or {}).get("id")
                    if raw_user_id is not None:
                        user_id = str(raw_user_id)
                except Exception:
                    user_id = None

            if user_id and os.path.exists(sub_group_path):
                with open(sub_group_path, encoding="utf-8") as f:
                    sub_group_data = json.load(f)

                candidates: list[dict] = []
                included = sub_group_data.get("included")
                if isinstance(included, list):
                    candidates.extend([x for x in included if isinstance(x, dict)])
                data = sub_group_data.get("data")
                if isinstance(data, list):
                    candidates.extend([x for x in data if isinstance(x, dict)])
                elif isinstance(data, dict):
                    candidates.append(data)

                for item in candidates:
                    if item.get("type") != "group":
                        continue
                    attrs = item.get("attributes") or {}
                    if not isinstance(attrs, dict):
                        continue
                    if attrs.get("groupType") != "TEAM":
                        continue

                    roles = attrs.get("roles") or []
                    if not isinstance(roles, list):
                        roles = []
                    user_in_group = False
                    for role in roles:
                        if not isinstance(role, dict):
                            continue
                        if str(role.get("userId")) != user_id:
                            continue
                        if role.get("role") in ["OWNER", "ASSISTANT"]:
                            user_in_group = True
                            break
                    if not user_in_group:
                        continue

                    subjects = attrs.get("subjects") or []
                    if not isinstance(subjects, list):
                        subjects = []
                    for subject in subjects:
                        if not isinstance(subject, dict):
                            continue
                        gn = subject.get("grantNumber")
                        if gn:
                            grant_numbers.add(str(gn))

            # フォールバック（古い形式など）: subGroup.json の data に grantNumber が直で入っているケース
            if not grant_numbers and os.path.exists(sub_group_path):
                with open(sub_group_path, encoding="utf-8") as f:
                    sub_group_data = json.load(f)
                data = sub_group_data.get("data")
                if isinstance(data, list):
                    for sg in data:
                        if not isinstance(sg, dict):
                            continue
                        gn = (sg.get("attributes") or {}).get("grantNumber")
                        if gn:
                            grant_numbers.add(str(gn))

            self.user_grant_numbers = grant_numbers
            logger.debug("ユーザー課題番号: %s", sorted(grant_numbers))
            
        except Exception as e:
            logger.debug("ユーザー課題番号取得エラー: %s", e)

    def _load_subgroup_names(self):
        """サブグループ名の解決用マップを読み込み"""
        try:
            sub_group_path = get_dynamic_file_path('output/rde/data/subGroup.json')
            if not os.path.exists(sub_group_path):
                return
            with open(sub_group_path, encoding="utf-8") as f:
                sub_group_data = json.load(f)

            # subGroup.json は included / data のいずれかに group が入る想定
            subgroup_name_by_id: dict[str, str] = {}

            candidates: list[dict] = []
            included = sub_group_data.get("included")
            if isinstance(included, list):
                candidates.extend([x for x in included if isinstance(x, dict)])
            data = sub_group_data.get("data")
            if isinstance(data, list):
                candidates.extend([x for x in data if isinstance(x, dict)])
            elif isinstance(data, dict):
                candidates.append(data)

            for item in candidates:
                if not isinstance(item, dict):
                    continue
                if item.get("type") != "group":
                    continue
                attrs = item.get("attributes") or {}
                if not isinstance(attrs, dict):
                    continue
                # TEAM を優先（サブグループとして扱う）
                if attrs.get("groupType") != "TEAM":
                    continue
                group_id = item.get("id")
                name = attrs.get("name")
                if group_id and name:
                    subgroup_name_by_id[str(group_id)] = str(name)
            self._subgroup_name_by_id = subgroup_name_by_id
        except Exception as e:
            logger.debug("サブグループ名取得エラー: %s", e)

    def _resolve_subgroup_name(self, dataset_id: str, dataset: dict) -> str:
        """dataset_id と dataset の情報からサブグループ名を推定（空欄回避）"""
        try:
            # まず詳細JSON（output / API）を優先
            detail = self._load_dataset_detail_from_output(dataset_id)
            if detail is None:
                detail = self._fetch_dataset_detail_from_api(dataset_id)

            def _extract_group_id(ds: dict) -> str | None:
                rels = ds.get("relationships") or {}
                if not isinstance(rels, dict):
                    return None
                group_data = (rels.get("group") or {}).get("data")
                if isinstance(group_data, dict) and group_data.get("id"):
                    return str(group_data.get("id"))
                sharing_data = (rels.get("sharingGroups") or {}).get("data")
                if isinstance(sharing_data, dict) and sharing_data.get("id"):
                    return str(sharing_data.get("id"))
                if isinstance(sharing_data, list):
                    for d in sharing_data:
                        if isinstance(d, dict) and d.get("id"):
                            return str(d.get("id"))
                return None

            group_id = None
            if isinstance(detail, dict) and isinstance(detail.get("data"), dict):
                group_id = _extract_group_id(detail.get("data"))
                # included に group 名があればそれも取り込む
                included = detail.get("included")
                if isinstance(included, list):
                    for inc in included:
                        if not isinstance(inc, dict):
                            continue
                        if inc.get("type") != "group":
                            continue
                        inc_id = inc.get("id")
                        attrs = inc.get("attributes") or {}
                        if inc_id and isinstance(attrs, dict) and attrs.get("name"):
                            self._subgroup_name_by_id.setdefault(str(inc_id), str(attrs.get("name")))

            if not group_id:
                group_id = _extract_group_id(dataset)

            if group_id:
                name = self._subgroup_name_by_id.get(group_id)
                if name:
                    return name
                # 最終フォールバック: IDだけでも表示（空欄は避ける）
                return group_id
        except Exception:
            return "(不明)"
        return "(不明)"

    def _load_dataset_detail_from_output(self, dataset_id: str) -> dict | None:
        try:
            detail_path = get_dynamic_file_path(f"output/rde/data/datasets/{dataset_id}.json")
            if not os.path.exists(detail_path):
                return None
            with open(detail_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _fetch_dataset_detail_from_api(self, dataset_id: str, *, bearer_token: str | None = None) -> dict | None:
        """APIからデータセット詳細を取得（相互関連の判定/関連付けトグル用）"""
        try:
            from config.site_rde import URLS
            from classes.utils.api_request_helper import api_request
            from core.bearer_token_manager import BearerTokenManager

            token = bearer_token or BearerTokenManager.get_valid_token()
            if not token:
                return None

            api_url = URLS["api"]["dataset_detail"].format(id=dataset_id)
            headers = {
                "Accept": "application/vnd.api+json",
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/vnd.api+json",
            }
            resp = api_request("GET", api_url, headers=headers, timeout=15)
            if not resp or resp.status_code != 200:
                return None
            return resp.json()
        except Exception:
            return None

    def _get_related_dataset_ids_for(self, dataset_id: str) -> set[str]:
        """dataset_id の relatedDatasets を set で返す（キャッシュ優先）"""
        if dataset_id in self._related_ids_cache:
            return self._related_ids_cache[dataset_id]

        payload = self._load_dataset_detail_from_output(dataset_id)
        if payload is None:
            payload = self._fetch_dataset_detail_from_api(dataset_id)

        related_ids: set[str] = set()
        try:
            if payload and isinstance(payload, dict):
                rels = (payload.get("data") or {}).get("relationships") or {}
                rel_data = (rels.get("relatedDatasets") or {}).get("data") or []
                if isinstance(rel_data, list):
                    for item in rel_data:
                        if isinstance(item, dict) and item.get("id"):
                            related_ids.add(str(item.get("id")))
        except Exception:
            related_ids = set()

        self._related_ids_cache[dataset_id] = related_ids
        return related_ids

    def _is_mutually_related_to_current(self, dataset_id: str) -> bool:
        """表示中 dataset_id が呼び出し元 dataset(exclude_dataset_id) を relatedDatasets に持つか"""
        if not self.exclude_dataset_id:
            return False
        return self.exclude_dataset_id in self._get_related_dataset_ids_for(dataset_id)

    def _build_patch_payload_for_related_datasets(self, dataset_detail: dict[str, Any], new_related_ids: list[str]) -> dict[str, Any]:
        """relatedDatasets のみ変更した PATCH payload を作る（他の重要 relationships は保持）"""
        data = dataset_detail.get("data") or {}
        dataset_id = str(data.get("id") or "")
        attrs = data.get("attributes") or {}
        rels = data.get("relationships") or {}

        safe_attr_keys = [
            "name",
            "grantNumber",
            "description",
            "contact",
            "taxonomyKeys",
            "relatedLinks",
            "tags",
            "citationFormat",
            "dataListingType",
            "embargoDate",
            "sharingPolicies",
            "isAnonymized",
            "isDataEntryProhibited",
            "isDataEntryDeleteProhibited",
        ]
        safe_attrs: dict[str, Any] = {}
        for k in safe_attr_keys:
            if k in attrs:
                safe_attrs[k] = attrs.get(k)

        relationships: dict[str, Any] = {
            "relatedDatasets": {
                "data": [{"type": "dataset", "id": rid} for rid in new_related_ids if rid]
            }
        }

        important_relationships = [
            "applicant",
            "dataOwners",
            "instruments",
            "manager",
            "template",
            "group",
            "license",
            "sharingGroups",
        ]
        for rel_name in important_relationships:
            if rel_name in rels:
                relationships[rel_name] = rels[rel_name]

        return {
            "data": {
                "type": "dataset",
                "id": dataset_id,
                "attributes": safe_attrs,
                "relationships": relationships,
            }
        }

    def _set_reciprocal_link(self, from_dataset_id: str, to_dataset_id: str, should_link: bool) -> bool:
        """from_dataset_id -> relatedDatasets に to_dataset_id を追加/削除（即時反映）"""
        try:
            from classes.utils.api_request_helper import api_request
            from core.bearer_token_manager import BearerTokenManager

            bearer_token = BearerTokenManager.get_token_with_relogin_prompt(self)
            if not bearer_token:
                return False

            # まず詳細を取得（payload構築に必要）
            detail = self._load_dataset_detail_from_output(from_dataset_id)
            if detail is None:
                detail = self._fetch_dataset_detail_from_api(from_dataset_id)
            if not detail:
                return False

            current_related = set(self._get_related_dataset_ids_for(from_dataset_id))
            if should_link:
                current_related.add(to_dataset_id)
            else:
                current_related.discard(to_dataset_id)

            new_related_ids = sorted(current_related)
            payload = self._build_patch_payload_for_related_datasets(detail, new_related_ids)

            api_url = f"https://rde-api.nims.go.jp/datasets/{from_dataset_id}"
            headers = {
                "Accept": "application/vnd.api+json",
                "Authorization": f"Bearer {bearer_token}",
                "Content-Type": "application/vnd.api+json",
            }
            resp = api_request("PATCH", api_url, headers=headers, json_data=payload, timeout=15)
            if not resp or resp.status_code not in (200, 201):
                return False

            # 成功したのでキャッシュ更新
            self._related_ids_cache[from_dataset_id] = set(new_related_ids)
            return True
        except Exception:
            return False

    def _find_row_by_dataset_id(self, dataset_id: str) -> int:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)  # 課題番号列に dataset_id を保持
            if item and item.data(Qt.UserRole) == dataset_id:
                return row
        return -1
    
    def _setup_combo(self):
        """コンボボックスのセットアップ"""
        self._apply_filters_to_combo()

    def _get_filtered_datasets(self) -> list[dict]:
        datasets: list[dict] = [d for d in self.all_datasets if isinstance(d, dict)]

        # 表示データセットフィルタ
        try:
            user_only = bool(self.filter_user_only_radio.isChecked())
            others_only = bool(self.filter_others_only_radio.isChecked())
        except Exception:
            user_only = True
            others_only = False

        if user_only:
            datasets = [
                d
                for d in datasets
                if str((d.get("attributes") or {}).get("grantNumber") or "") in self.user_grant_numbers
            ]
        elif others_only:
            datasets = [
                d
                for d in datasets
                if str((d.get("attributes") or {}).get("grantNumber") or "") not in self.user_grant_numbers
            ]

        # 課題番号絞り込み（部分一致）
        try:
            grant_filter = str(self.grant_number_filter_edit.text() or "").strip()
        except Exception:
            grant_filter = ""
        if grant_filter:
            datasets = [
                d
                for d in datasets
                if grant_filter in str((d.get("attributes") or {}).get("grantNumber") or "")
            ]

        # 並びは「ユーザー所属優先」
        user_datasets: list[dict] = []
        other_datasets: list[dict] = []
        for d in datasets:
            grant_number = str((d.get("attributes") or {}).get("grantNumber") or "")
            if grant_number and grant_number in self.user_grant_numbers:
                user_datasets.append(d)
            else:
                other_datasets.append(d)
        return user_datasets + other_datasets

    def _apply_filters_to_combo(self) -> None:
        # 可能なら現在選択を維持
        prev_id: str | None = None
        try:
            prev = self.dataset_combo.currentData()
            if isinstance(prev, dict) and prev.get("id"):
                prev_id = str(prev.get("id"))
        except Exception:
            prev_id = None

        filtered = self._get_filtered_datasets()

        prev_block = self.dataset_combo.blockSignals(True)
        try:
            self.dataset_combo.clear()

            display_names: list[str] = []
            for dataset in filtered:
                attrs = dataset.get("attributes", {})
                name = attrs.get("name", "名前なし")
                grant_number = attrs.get("grantNumber", "")
                dataset_type = attrs.get("datasetType", "")
                dataset_id = dataset.get("id", "")

                display_text = f"{grant_number} - {name} (ID: {dataset_id})"
                if dataset_type:
                    display_text += f" [{dataset_type}]"

                self.dataset_combo.addItem(display_text, dataset)
                display_names.append(display_text)

            completer = QCompleter(display_names, self.dataset_combo)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            self.dataset_combo.setCompleter(completer)
        finally:
            self.dataset_combo.blockSignals(prev_block)

        # 選択復元（シグナルを出して日時ラベル等も更新）
        target_idx = -1
        if prev_id:
            for idx in range(self.dataset_combo.count()):
                data = self.dataset_combo.itemData(idx)
                if isinstance(data, dict) and str(data.get("id") or "") == prev_id:
                    target_idx = idx
                    break
        if target_idx < 0 and self.dataset_combo.count() > 0:
            target_idx = 0

        try:
            self.dataset_combo.setCurrentIndex(target_idx)
        except Exception:
            pass

        try:
            self._update_add_button_state()
        except Exception:
            pass

        logger.info("コンボボックスセットアップ完了: %s件", self.dataset_combo.count())
    
    def _load_current_datasets(self, dataset_ids):
        """現在選択されているデータセットをテーブルに読み込み"""
        for dataset_id in dataset_ids:
            # all_datasetsから該当データセットを検索
            dataset = None
            for ds in self.all_datasets:
                if ds.get("id") == dataset_id:
                    dataset = ds
                    break
            
            if dataset:
                self._add_dataset_to_table(dataset)
            else:
                logger.warning("データセットID '%s' が見つかりません", dataset_id)
    
    def _add_dataset_to_table(self, dataset):
        """テーブルにデータセットを追加"""
        dataset_id = dataset.get("id", "")
        attrs = dataset.get("attributes", {})
        grant_number = attrs.get("grantNumber", "")
        name = attrs.get("name", "名前なし")
        dataset_type = attrs.get("datasetType", "")
        
        # 既に追加済みかチェック
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item and item.data(Qt.UserRole) == dataset_id:
                logger.debug("データセットは既に追加済み: %s", name)
                return False
        
        # 新しい行を追加
        row = self.table.rowCount()
        self.table.insertRow(row)

        # サブグループ
        subgroup_name = self._resolve_subgroup_name(str(dataset_id), dataset)
        subgroup_item = QTableWidgetItem(subgroup_name)
        self.table.setItem(row, 0, subgroup_item)
        
        # 課題番号（dataset_idをUserRoleに保存）
        grant_item = QTableWidgetItem(grant_number)
        grant_item.setData(Qt.UserRole, dataset_id)
        self.table.setItem(row, 1, grant_item)
        
        # データセット名
        name_item = QTableWidgetItem(name)
        self.table.setItem(row, 2, name_item)
        
        # タイプ
        type_item = QTableWidgetItem(dataset_type)
        self.table.setItem(row, 3, type_item)

        # 相互関連
        mutual_text = "あり" if self._is_mutually_related_to_current(dataset_id) else "なし"
        mutual_item = QTableWidgetItem(mutual_text)
        self.table.setItem(row, 4, mutual_item)

        # 関連付け（表示中 dataset -> 呼び出し元 dataset の関係を設定/解除）
        link_button = QPushButton()
        link_button.setMinimumWidth(90)

        def _apply_link_button_state(is_linked: bool):
            if is_linked:
                link_button.setText("解除する")
                link_button.setStyleSheet(
                    f"background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};"
                    f"color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};"
                    "font-weight: bold; padding: 4px 10px; border-radius: 4px;"
                )
            else:
                link_button.setText("関連付ける")
                link_button.setStyleSheet(
                    f"background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};"
                    f"color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};"
                    "font-weight: bold; padding: 4px 10px; border-radius: 4px;"
                )

        _apply_link_button_state(mutual_text == "あり")

        if not self.exclude_dataset_id:
            link_button.setEnabled(False)
            link_button.setToolTip("呼び出し元データセットが特定できないため設定できません")
        else:
            def on_toggle_reciprocal():
                link_button.setEnabled(False)
                try:
                    currently_linked = self._is_mutually_related_to_current(dataset_id)
                    should_link = not currently_linked

                    action_label = "関連付ける" if should_link else "解除する"

                    # 対象データセットが存在するか確認（存在しない場合は専用メッセージ）
                    detail = self._load_dataset_detail_from_output(dataset_id)
                    if detail is None:
                        detail = self._fetch_dataset_detail_from_api(dataset_id)
                    if not detail:
                        QMessageBox.warning(
                            self,
                            "エラー",
                            "対象のデータセットが存在していないため、関連付けを更新できません。\n"
                            "データ取得（dataset.json）を更新してから再度お試しください。",
                        )
                        return

                    message = (
                        f"表示中データセットから、呼び出し元データセットへの{action_label}を行います。\n\n"
                        f"実行しますか？"
                    )
                    reply = QMessageBox.question(
                        self,
                        f"{action_label}の確認",
                        message,
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No,
                    )
                    if reply != QMessageBox.Yes:
                        return

                    ok = self._set_reciprocal_link(dataset_id, self.exclude_dataset_id, should_link)
                    if not ok:
                        QMessageBox.warning(self, "エラー", "関連付けの更新に失敗しました。権限やログイン状態を確認してください。")
                        return

                    # UI即時反映
                    row_idx = self._find_row_by_dataset_id(dataset_id)
                    if row_idx >= 0:
                        self.table.setItem(row_idx, 4, QTableWidgetItem("あり" if should_link else "なし"))
                        _apply_link_button_state(should_link)
                finally:
                    link_button.setEnabled(True)

            link_button.clicked.connect(on_toggle_reciprocal)

        self.table.setCellWidget(row, 5, link_button)
        
        # 削除ボタン
        delete_button = QPushButton("削除")
        delete_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_DANGER_TEXT)};
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_DANGER_BACKGROUND_HOVER)};
            }}
        """)
        delete_button.clicked.connect(lambda checked=False, dsid=dataset_id: self._delete_dataset(dsid))
        self.table.setCellWidget(row, 6, delete_button)
        
        logger.debug("データセット追加: %s", name)
        return True
    
    def _delete_dataset(self, dataset_id: str):
        """指定された dataset_id の行を削除"""
        row = self._find_row_by_dataset_id(dataset_id)
        if row < 0:
            return
        item = self.table.item(row, 2)
        name = item.text() if item else "不明"
        self.table.removeRow(row)
        logger.debug("データセット削除: row=%s, name=%s", row, name)
    
    def _update_add_button_state(self) -> None:
        try:
            idx = self.dataset_combo.currentIndex()
            if idx < 0:
                self.add_selected_button.setEnabled(False)
                return
            data = self.dataset_combo.itemData(idx)
            enabled = isinstance(data, dict) and bool(data.get("id"))
            self.add_selected_button.setEnabled(enabled)
        except Exception:
            try:
                self.add_selected_button.setEnabled(False)
            except Exception:
                pass

    def _add_selected_dataset_from_combo(self) -> None:
        """選択中のコンボエントリをテーブルへ追加（明示的操作）。"""
        idx = self.dataset_combo.currentIndex()
        if idx < 0:
            return
        dataset = self.dataset_combo.itemData(idx)
        if not isinstance(dataset, dict) or not dataset.get("id"):
            return

        self._add_dataset_to_table(dataset)
        try:
            self.dataset_combo.setCurrentIndex(-1)
        except Exception:
            pass
        try:
            if self.dataset_combo.lineEdit():
                self.dataset_combo.lineEdit().clear()
        except Exception:
            pass
        self._update_add_button_state()

    def _show_bulk_results_dialog(self, title: str, lines: list[str]) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumWidth(760)
        dlg.setMinimumHeight(480)

        v = QVBoxLayout(dlg)
        desc = QLabel("実行結果（成功/失敗）")
        desc.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_PRIMARY)}; font-weight: bold;")
        v.addWidget(desc)

        text = QTextEdit(dlg)
        text.setReadOnly(True)
        text.setPlainText("\n".join(lines) if lines else "(結果なし)")
        v.addWidget(text)

        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("OK")
        ok.setMinimumWidth(100)
        ok.setStyleSheet(
            f"background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};"
            f"color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};"
            "font-weight: bold; padding: 8px 16px; border-radius: 4px;"
        )
        ok.clicked.connect(dlg.accept)
        row.addWidget(ok)
        v.addLayout(row)
        dlg.setLayout(v)
        dlg.exec()

    def _on_bulk_link_all_mutually(self) -> None:
        """呼び出し元 + テーブル内データセットを全て相互関連付けする。"""
        if not self.exclude_dataset_id:
            QMessageBox.warning(self, "エラー", "呼び出し元データセットが特定できないため実行できません。")
            return

        # この操作はAPI(PATCH)が必須なため、先に認証を確立しておく
        try:
            from core.bearer_token_manager import BearerTokenManager

            bearer_token = BearerTokenManager.get_token_with_relogin_prompt(self)
            if not bearer_token:
                QMessageBox.warning(self, "エラー", "認証トークンが取得できないため実行できません。")
                return
        except Exception:
            bearer_token = None

        dataset_ids = [self.exclude_dataset_id] + list(self.get_selected_dataset_ids())
        # 重複除去しつつ順序維持
        seen: set[str] = set()
        dataset_ids = [d for d in dataset_ids if d and not (d in seen or seen.add(d))]

        if len(dataset_ids) < 2:
            QMessageBox.information(self, "情報", "相互関連付けする対象がありません。")
            return

        reply = QMessageBox.question(
            self,
            "実行の確認",
            "呼び出し元データセットと、リストされたデータセットを全て相互に関連付けます。\n"
            "この操作は実行直後に反映されます。\n\n"
            "実行しますか？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        results: list[str] = []

        def _ensure_detail_exists(dataset_id: str) -> bool:
            # dataset.jsonが古く、output配下の個別jsonが残っている場合でも、
            # 実体（API上の存在）を優先してチェックする。
            api_detail = self._fetch_dataset_detail_from_api(dataset_id, bearer_token=bearer_token)
            if api_detail is not None:
                return True
            # APIで見つからない -> 削除済み等の可能性。ローカル詳細が残っていても「存在しない」扱い。
            return False

        # 実在チェック
        missing = [d for d in dataset_ids if not _ensure_detail_exists(d)]
        if missing:
            for d in missing:
                results.append(f"[失敗] 関連データセットが存在しません（削除済みかもしれません）: {d}")

            # まとめてユーザーへ案内（dataset.json更新を促す）
            try:
                preview = "\n".join(missing[:8])
                suffix = "\n..." if len(missing) > 8 else ""
                QMessageBox.warning(
                    self,
                    "関連データセットが存在しません",
                    "関連データセットが存在しません（削除済みかもしれません）。\n\n"
                    "dataset.json が古い可能性があります。\n"
                    "データセット一覧（dataset.json）を API から再取得して更新してから再実行してください。\n\n"
                    f"対象ID:\n{preview}{suffix}",
                )
            except Exception:
                pass

        # ペアごとに双方向リンク
        for i in range(len(dataset_ids)):
            for j in range(i + 1, len(dataset_ids)):
                a = dataset_ids[i]
                b = dataset_ids[j]
                if a in missing or b in missing:
                    results.append(f"[SKIP] {a} ↔ {b}（存在確認で失敗）")
                    continue
                ok1 = self._set_reciprocal_link(a, b, True)
                ok2 = self._set_reciprocal_link(b, a, True)
                if ok1 and ok2:
                    results.append(f"[成功] {a} ↔ {b}")
                else:
                    results.append(f"[失敗] {a} ↔ {b}")

        # UI即時反映（呼び出し元への相互関連の有無列を再評価）
        try:
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 1)
                dsid = item.data(Qt.UserRole) if item else None
                if dsid:
                    self.table.setItem(
                        row,
                        4,
                        QTableWidgetItem("あり" if self._is_mutually_related_to_current(str(dsid)) else "なし"),
                    )
        except Exception:
            pass

        self._show_bulk_results_dialog("相互関連付け結果", results)
    
    def add_all_from_grant_number(self):
        """同じ課題番号のデータセットを全て追加"""
        if not self.current_grant_number:
            QMessageBox.warning(self, "エラー", "課題番号が設定されていません。")
            return
        
        # 同じ課題番号のデータセットを検索
        matching_datasets = []
        for dataset in self.all_datasets:
            attrs = dataset.get("attributes", {})
            grant_number = attrs.get("grantNumber", "")
            if grant_number == self.current_grant_number:
                matching_datasets.append(dataset)
        
        if not matching_datasets:
            QMessageBox.information(self, "情報", f"課題番号 '{self.current_grant_number}' のデータセットが見つかりません。")
            return
        
        # 全て追加
        added_count = 0
        for dataset in matching_datasets:
            if self._add_dataset_to_table(dataset):
                added_count += 1
        
        if added_count > 0:
            QMessageBox.information(self, "完了", f"課題番号 '{self.current_grant_number}' のデータセット {added_count}件を追加しました。")
            logger.info("同じ課題番号のデータセット追加: %s件", added_count)
        else:
            QMessageBox.information(self, "情報", "追加可能なデータセットはありません（全て選択済みです）。")
    
    def get_selected_dataset_ids(self):
        """選択されているデータセットIDのリストを取得"""
        dataset_ids = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item:
                dataset_id = item.data(Qt.UserRole)
                if dataset_id:
                    dataset_ids.append(dataset_id)
        return dataset_ids
    
    def accept(self):
        """OKボタンが押された時の処理"""
        dataset_ids = self.get_selected_dataset_ids()
        logger.info("関連データセットビルダー完了: %s件", len(dataset_ids))
        self.datasets_changed.emit(dataset_ids)
        super().accept()
