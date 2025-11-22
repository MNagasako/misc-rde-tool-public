"""
サブグループ作成・修正のUI関連ヘルパークラス集（リファクタリング版）

このモジュールには、サブグループの作成タブと修正タブで共通利用できるUIコンポーネントと
ビジネスロジックを処理するクラスが含まれています。
新しいデータマネージャ・バリデータクラスを使用します。
"""

import os
import json
import logging
from qt_compat.widgets import (
    QLabel, QLineEdit, QTextEdit, QGridLayout, QHBoxLayout, 
    QPushButton, QMessageBox, QDialog, QVBoxLayout, QWidget
)
from qt_compat.core import Qt
from config.common import SUBGROUP_JSON_PATH
from ..core.subgroup_data_manager import SubgroupDataManager, MemberDataProcessor
from .subgroup_validators import SubjectInputValidator, UserRoleValidator, FormValidator, UIValidator
from ..ui.subgroup_subject_widget import SubjectEntryWidget, parse_subjects_from_text, subjects_to_text
from classes.theme import get_color, ThemeKey

# ロガー設定
logger = logging.getLogger(__name__)


def _is_widget_checked_safe(widget):
    """
    QRadioButton/QCheckBoxのisChecked()を安全に呼び出すヘルパー。
    削除済みオブジェクトや想定外の例外が発生した場合はFalseを返す。
    """
    if widget is None:
        return False
    try:
        # 一般的なPyQt5ウィジェットならisCheckedを持つ
        if hasattr(widget, "isChecked"):
            return widget.isChecked()
        return False
    except RuntimeError:
        # "wrapped C/C++ object of type ... has been deleted" 等
        return False
    except Exception:
        return False


def load_user_entries():
    """
    subGroup.jsonからユーザーリストを取得
    共通関数として全ファイルで使用（新しいデータマネージャを使用）
    """
    return SubgroupDataManager.load_user_entries()


class SubgroupFormBuilder:
    """サブグループ作成・修正フォームの構築を担当するクラス"""
    
    def __init__(self, layout, create_auto_resize_button, button_style):
        self.layout = layout
        self.create_auto_resize_button = create_auto_resize_button
        self.button_style = button_style
        self.form_widgets = {}
        
    def build_manual_input_form(self, default_values=None):
        """
        手動入力フォームの構築（新しい課題入力ウィジェット使用）
        
        Args:
            default_values (dict): 初期値辞書 {"group_name": "...", "description": "...", "subjects": [...], etc.}
        """
        form_grid = QGridLayout()
        defaults = default_values or {}
        
        # 入力ウィジェット作成
        self.form_widgets['group_name_edit'] = QLineEdit()
        self.form_widgets['group_name_edit'].setPlaceholderText("グループ名")
        self.form_widgets['group_name_edit'].setText(defaults.get('group_name', ''))
        
        self.form_widgets['desc_edit'] = QLineEdit()
        self.form_widgets['desc_edit'].setPlaceholderText("説明")
        self.form_widgets['desc_edit'].setText(defaults.get('description', ''))
        
        # 新しい課題入力ウィジェット
        initial_subjects = defaults.get('subjects', [])
        # 文字列形式の場合は変換
        if isinstance(initial_subjects, str):
            initial_subjects = parse_subjects_from_text(initial_subjects)
        self.form_widgets['subjects_widget'] = SubjectEntryWidget(initial_subjects)
        
        self.form_widgets['funds_edit'] = QLineEdit()
        self.form_widgets['funds_edit'].setPlaceholderText("研究資金番号 (カンマ区切り)")
        self.form_widgets['funds_edit'].setText(defaults.get('funds', ''))
        
        # スタイル設定
        for widget_name, widget in self.form_widgets.items():
            if widget_name not in ['subjects_widget'] and hasattr(widget, 'setStyleSheet'):
                widget.setStyleSheet(f"color: {get_color(ThemeKey.TEXT_SUCCESS)};")
        
        # バリデーション設定
        self.validator = SubjectInputValidator(self.form_widgets['subjects_widget'])
        
        # ラベル作成
        labels = {
            'group': QLabel("グループ名:"),
            'desc': QLabel("説明:"),
            'subjects': QLabel("課題:"),
            'funds': QLabel("研究資金番号 (カンマ区切り):")
        }
        
        for label in labels.values():
            label.setStyleSheet("font-weight: bold;")
        
        # レイアウト配置
        form_grid.addWidget(labels['group'], 0, 0)
        form_grid.addWidget(self.form_widgets['group_name_edit'], 0, 1)
        form_grid.addWidget(labels['desc'], 1, 0)
        form_grid.addWidget(self.form_widgets['desc_edit'], 1, 1)
        form_grid.addWidget(labels['subjects'], 2, 0, Qt.AlignTop)
        form_grid.addWidget(self.form_widgets['subjects_widget'], 2, 1)
        form_grid.addWidget(labels['funds'], 3, 0)
        form_grid.addWidget(self.form_widgets['funds_edit'], 3, 1)
        
        # 幅調整
        for widget_name in ['group_name_edit', 'desc_edit', 'funds_edit']:
            self.form_widgets[widget_name].setMinimumWidth(180)
        
        self.layout.addLayout(form_grid)
        return self.form_widgets
    
    def build_button_row(self, handlers):
        """
        ボタン行の構築
        
        Args:
            handlers (dict): ボタンのハンドラー辞書 {"bulk": func1, "manual": func2}
        
        Returns:
            tuple: (button_bulk, button_manual) or (None, button_manual)
        """
        button_row = QHBoxLayout()
        button_bulk = None
        button_manual = None
        
        # 一括作成ボタン（作成タブでのみ表示）
        if 'bulk' in handlers:
            button_bulk = self.create_auto_resize_button(
                "一括作成", 200, 40, self.button_style
            )
            button_bulk.clicked.connect(handlers['bulk'])
            #button_row.addWidget(button_bulk)
        
        # サブグループ作成ボタン
        if 'manual' in handlers:
            manual_text = handlers.get('manual_text', 'サブグループ作成')
            button_manual = self.create_auto_resize_button(
                manual_text, 200, 40, self.button_style
            )
            from qt_compat.widgets import QSizePolicy
            button_manual.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            button_manual.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                    color: white;
                    font-weight: bold;
                    font-size: 13px;
                    border-radius: 6px;
                    padding: 8px 20px;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
                }}
                QPushButton:pressed {{
                    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_PRESSED)};
                }}
            """)
            button_manual.clicked.connect(handlers['manual'])
            button_row.addWidget(button_manual)
        
        self.layout.addLayout(button_row)
        return button_bulk, button_manual


class SubgroupCreateHandler:
    """サブグループ作成・修正処理を担当するクラス"""
    
    def __init__(self, widget, parent, member_selector):
        self.widget = widget
        self.parent = parent
        self.member_selector = member_selector
    
    def extract_subjects_from_widget(self, subjects_widget):
        """新しい課題ウィジェットから課題情報を抽出"""
        return subjects_widget.get_subjects_data()
    
    def extract_subjects_from_text(self, text):
        """テキストから課題情報を抽出（後方互換性用）"""
        return parse_subjects_from_text(text)
    
    def extract_user_roles(self):
        """メンバーセレクターからユーザーロール情報を抽出（安全版）"""
        selected_user_ids = []
        roles = []
        owner_id = None
        owner_count = 0

        for user_entry in self.member_selector.user_rows or []:
            # 破損したタプルがあっても続行できるように安全に展開
            try:
                user_id, owner_radio, assistant_cb, member_cb, agent_cb, viewer_cb = user_entry
            except Exception:
                continue

            try:
                if _is_widget_checked_safe(owner_radio):
                    owner_count += 1
                    owner_id = user_id
                    roles.append({
                        "userId": user_id,
                        "role": "OWNER",
                        "canCreateDatasets": True,
                        "canEditMembers": True
                    })
                elif _is_widget_checked_safe(assistant_cb):
                    selected_user_ids.append(user_id)
                    roles.append({
                        "userId": user_id,
                        "role": "ASSISTANT",
                        "canCreateDatasets": True,
                        "canEditMembers": True
                    })
                elif _is_widget_checked_safe(member_cb):
                    selected_user_ids.append(user_id)
                    roles.append({
                        "userId": user_id,
                        "role": "MEMBER",
                        "canCreateDatasets": False,
                        "canEditMembers": False
                    })
                elif _is_widget_checked_safe(agent_cb):
                    selected_user_ids.append(user_id)
                    roles.append({
                        "userId": user_id,
                        "role": "AGENT",
                        "canCreateDatasets": False,
                        "canEditMembers": False
                    })
                elif _is_widget_checked_safe(viewer_cb):
                    selected_user_ids.append(user_id)
                    roles.append({
                        "userId": user_id,
                        "role": "VIEWER",
                        "canCreateDatasets": False,
                        "canEditMembers": False
                    })
            except Exception:
                # ここでは個別行の問題を無視して続行
                continue

        return selected_user_ids, roles, owner_id, owner_count
    
    def validate_owner_selection(self, owner_count):
        """OWNER選択のバリデーション"""
        if owner_count == 0:
            QMessageBox.warning(self.widget, "OWNER未選択", "サブグループには必ずOWNERを1名選択してください。")
            return False
        elif owner_count > 1:
            QMessageBox.warning(self.widget, "OWNER重複選択", f"OWNERは1名のみ選択してください。現在{owner_count}名が選択されています。")
            return False
        return True
    
    def create_confirmation_dialog(self, payload, payload_str, operation_type="作成"):
        """
        確認ダイアログの作成
        
        Args:
            payload: APIペイロード
            payload_str: ペイロードの文字列表現
            operation_type: 操作タイプ（"作成" または "更新"）
        """
        attr = payload['data']['attributes']
        
        # ユーザーマップ作成（簡易版）
        def role_label(role):
            uid = role.get('userId', '')
            return f"{uid}({role.get('role','')})"
        
        simple_text = (
            f"本当にサブグループを{operation_type}しますか？\n\n"
            f"グループ名: {attr.get('name')}\n"
            f"説明: {attr.get('description')}\n"
            f"課題番号: {attr.get('subjects')[0]['grantNumber'] if attr.get('subjects') else ''}\n"
            f"研究資金: {', '.join(f.get('fundNumber','') for f in attr.get('funds', []))}\n"
            f"ロール: {', '.join(role_label(r) for r in attr.get('roles', []))}\n"
            f"\nこの操作はARIMデータポータルでサブグループを{operation_type}します。"
        )
        
        msg_box = QMessageBox(self.widget)
        msg_box.setWindowTitle(f"サブグループ{operation_type}の確認")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText(simple_text)
        
        yes_btn = msg_box.addButton(QMessageBox.Yes)
        no_btn = msg_box.addButton(QMessageBox.No)
        detail_btn = QPushButton("詳細表示")
        msg_box.addButton(detail_btn, QMessageBox.ActionRole)
        msg_box.setDefaultButton(no_btn)
        msg_box.setStyleSheet("QLabel{font-family: 'Consolas'; font-size: 10pt;}")
        
        def show_detail():
            dlg = QDialog(self.widget)
            dlg.setWindowTitle("Payload 全文表示")
            layout = QVBoxLayout(dlg)
            text_edit = QTextEdit(dlg)
            text_edit.setReadOnly(True)
            text_edit.setPlainText(payload_str)
            text_edit.setMinimumSize(600, 400)
            layout.addWidget(text_edit)
            dlg.setLayout(layout)
            dlg.exec()
        
        detail_btn.clicked.connect(show_detail)
        return msg_box, yes_btn


class MemberDataProcessor:
    """メンバーデータ処理を担当するクラス"""
    
    @staticmethod
    def load_member_info(member_path):
        """rde-member.txtからメンバー情報を読み込み"""
        member_info = {}
        if not os.path.exists(member_path):
            return member_info
            
        try:
            with open(member_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = [x.strip() for x in line.split(',')]
                    if len(parts) >= 4:
                        email = parts[0]
                        role = 'OWNER' if parts[1] == '1' else 'ASSISTANT'
                        canCreateDatasets = parts[2] == '1'
                        canEditMembers = parts[3] == '1'
                        member_info[email] = {
                            'role': role,
                            'canCreateDatasets': canCreateDatasets,
                            'canEditMembers': canEditMembers
                        }
        except Exception as e:
            logger.error("rde-member.txt読み込みエラー: %s", e)
        
        return member_info
    
    @staticmethod
    def create_initial_role_mapping(user_entries, member_info):
        """初期ロールマッピングの作成"""
        prechecked_user_ids = set()
        initial_roles = {}
        
        if user_entries and not isinstance(user_entries, str):
            for user in user_entries:
                attr = user.get("attributes", {})
                email = attr.get("emailAddress", "")
                user_id = user.get("id", "")
                if email in member_info:
                    prechecked_user_ids.add(user_id)
                    initial_roles[user_id] = member_info[email]['role']
        
        return prechecked_user_ids, initial_roles
    
    @staticmethod
    def extract_subjects_for_display(subjects_data):
        """課題データを表示用文字列に変換"""
        if not subjects_data:
            return ""
        
        subject_parts = []
        for subject in subjects_data:
            if isinstance(subject, dict):
                grant_number = subject.get("grantNumber", "")
                title = subject.get("title", "")
                if grant_number and title:
                    subject_parts.append(f"{grant_number}:{title}")
                elif grant_number:
                    subject_parts.append(grant_number)
            else:
                subject_parts.append(str(subject))
        
        return ", ".join(subject_parts)
    
    @staticmethod
    def extract_funds_for_display(funds_data):
        """研究資金データを表示用文字列に変換"""
        if not funds_data:
            return ""
        
        fund_parts = []
        for fund in funds_data:
            if isinstance(fund, dict):
                fund_number = fund.get("fundNumber", "")
                if fund_number:
                    fund_parts.append(fund_number)
            else:
                fund_parts.append(str(fund))
        
        return ", ".join(fund_parts)


def show_selected_user_ids(widget, checkbox_list, user_entries=None):
    """
    選択されたユーザーとロールを表示するダイアログ関数
    
    Args:
        widget: 親ウィジェット
        checkbox_list: ユーザー選択リスト [(user_id, owner_radio, assistant_cb, member_cb, agent_cb, viewer_cb), ...]
        user_entries: ユーザー情報リスト [{"id": "...", "attributes": {"userName": "...", "emailAddress": "..."}}, ...]
    """
    # user_entries: [{id, attributes:{userName, emailAddress, ...}}, ...]
    user_map = {}
    if user_entries and not isinstance(user_entries, str):
        for user in user_entries:
            # 統合形式: {"id": "...", "attributes": {...}, "roles": {...}}
            user_id = user.get("id", "")
            attr = user.get("attributes", {})
            user_map[user_id] = {
                "userName": attr.get("userName", user_id),
                "emailAddress": attr.get("emailAddress", "")
            }
    
    result_lines = []
    for entry in checkbox_list:
        user_id, owner_radio, assistant_cb, member_cb, agent_cb, viewer_cb = entry
        
        # ユーザー情報取得（デフォルト値としてuser_idを使用）
        user_info = user_map.get(user_id, {"userName": user_id, "emailAddress": "不明"})
        user_name = user_info.get("userName", user_id)
        email = user_info.get("emailAddress", "不明")
        role = []
        
        # ウィジェットが削除されていないかチェック（安全版）
        if _is_widget_checked_safe(owner_radio):
            role.append('OWNER')
            
        if _is_widget_checked_safe(assistant_cb):
            role.append('ASSISTANT')
            
        if _is_widget_checked_safe(member_cb):
            role.append('MEMBER')

        if _is_widget_checked_safe(agent_cb):
            role.append('AGENT')

        if _is_widget_checked_safe(viewer_cb):
            role.append('VIEWER')

        if role:
            # 氏名を太字、メールアドレスを表示
            result_lines.append(f"<b>{user_name}</b>（{email}）: {', '.join(role)}")
    if result_lines:
        msg = "選択されたユーザーとロール:<br>" + "<br>".join(result_lines)
        QMessageBox.information(widget, "選択結果", msg)
    else:
        QMessageBox.information(widget, "選択結果", "ユーザーが選択されていません。")


def prepare_subgroup_create_request(widget, parent, user_rows=None):
    """
    サブグループ作成リクエストの準備と実行
    
    Args:
        widget: 親ウィジェット
        parent: 親ウィンドウ
        user_rows: ユーザー選択行リスト。Noneの場合はwidget.user_rowsを使用
    """
    # user_rowsがNoneならwidget.user_rowsを参照
    if user_rows is None:
        user_rows = getattr(widget, 'user_rows', None)
    
    # OWNERが必須チェック（安全版）
    owner_count = 0
    selected_user_ids = []
    roles = []
    owner_id = None

    for user_entry in user_rows or []:
        try:
            user_id, owner_radio, assistant_cb, member_cb, agent_cb, viewer_cb = user_entry
        except Exception:
            continue

        try:
            if _is_widget_checked_safe(owner_radio):
                owner_count += 1
                owner_id = user_id
                roles.append({
                    "userId": user_id,
                    "role": "OWNER",
                    "canCreateDatasets": True,
                    "canEditMembers": True
                })
            elif _is_widget_checked_safe(assistant_cb):
                selected_user_ids.append(user_id)
                roles.append({
                    "userId": user_id,
                    "role": "ASSISTANT",
                    "canCreateDatasets": True,
                    "canEditMembers": True
                })
            elif _is_widget_checked_safe(member_cb):
                selected_user_ids.append(user_id)
                roles.append({
                    "userId": user_id,
                    "role": "MEMBER",
                    "canCreateDatasets": False,
                    "canEditMembers": False
                })
            elif _is_widget_checked_safe(agent_cb):
                selected_user_ids.append(user_id)
                roles.append({
                    "userId": user_id,
                    "role": "AGENT",
                    "canCreateDatasets": False,
                    "canEditMembers": False
                })
            elif _is_widget_checked_safe(viewer_cb):
                selected_user_ids.append(user_id)
                roles.append({
                    "userId": user_id,
                    "role": "VIEWER",
                    "canCreateDatasets": False,
                    "canEditMembers": False
                })
        except Exception:
            continue

    # OWNER必須バリデーション
    if owner_count == 0:
        QMessageBox.warning(widget, "OWNER未選択", "サブグループには必ずOWNERを1名選択してください。")
        return
    elif owner_count > 1:
        QMessageBox.warning(widget, "OWNER重複選択", f"OWNERは1名のみ選択してください。現在{owner_count}名が選択されています。")
        return
    
    if owner_id:
        selected_user_ids = [owner_id] + selected_user_ids
    if not selected_user_ids:
        QMessageBox.warning(widget, "ユーザー未選択", "サブグループに追加するユーザーを1人以上選択してください。")
        return
    widget.roles = roles
    
    # subgroup_api_helperを動的インポート（循環インポート回避）
    from . import subgroup_api_helper
    
    paths = subgroup_api_helper.check_subgroup_files()
    if paths["missing"]:
        msg = f"必要なファイルが見つかりません！: {', '.join(paths['missing'])}\n\n{paths['output_dir']} または {paths['input_dir']} に配置してください。"
        QMessageBox.warning(widget, "ファイル不足", msg)
        print(msg)
        return
    info, group_config, member_lines = subgroup_api_helper.load_subgroup_config(paths)
    if isinstance(info, str):
        QMessageBox.warning(widget, "ファイル読み込みエラー", info)
        print(info)
        return
    if isinstance(group_config, str):
        QMessageBox.warning(widget, "ファイル読み込みエラー", group_config)
        print(group_config)
        return
    if not isinstance(group_config, list):
        group_config = [group_config]
    for idx, group in enumerate(group_config):
        popup_text, payload, api_url, headers = subgroup_api_helper.build_subgroup_request(info, group_config, member_lines, idx, group, selected_user_ids)
        # --- 確認ダイアログ（1段階、詳細表示ボタンでpayload全文） ---
        payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
        attr = payload['data']['attributes']
        simple_text = (
            f"本当にサブグループを作成しますか？\n\n"
            f"グループ名: {attr.get('name')}\n"
            f"説明: {attr.get('description')}\n"
            f"課題番号: {attr.get('subjects')[0]['grantNumber'] if attr.get('subjects') else ''}\n"
            f"研究資金: {', '.join(f.get('fundNumber','') for f in attr.get('funds', []))}\n"
            f"ロール: {', '.join(f'{r['userId']}({r['role']})' for r in attr.get('roles', []))}\n"
            f"\nこの操作はRDEに新規サブグループを作成します。"
        )
        msg_box = QMessageBox(widget)
        msg_box.setWindowTitle("サブグループ作成の確認")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText(simple_text)
        yes_btn = msg_box.addButton(QMessageBox.Yes)
        no_btn = msg_box.addButton(QMessageBox.No)
        detail_btn = QPushButton("詳細表示")
        msg_box.addButton(detail_btn, QMessageBox.ActionRole)
        msg_box.setDefaultButton(no_btn)
        msg_box.setStyleSheet("QLabel{font-family: 'Consolas'; font-size: 10pt;}")
        def show_detail():
            dlg = QDialog(widget)
            dlg.setWindowTitle("Payload 全文表示")
            layout = QVBoxLayout(dlg)
            text_edit = QTextEdit(dlg)
            text_edit.setReadOnly(True)
            text_edit.setPlainText(payload_str)
            text_edit.setMinimumSize(600, 400)
            layout.addWidget(text_edit)
            dlg.setLayout(layout)
            dlg.exec()
        detail_btn.clicked.connect(show_detail)
        reply = msg_box.exec()
        if msg_box.clickedButton() == yes_btn:
            send_subgroup_request = subgroup_api_helper.send_subgroup_request
            send_subgroup_request(widget, api_url, headers, payload, group.get('group_name',''))
        else:
            logger.info("サブグループ作成処理はユーザーによりキャンセルされました。")
