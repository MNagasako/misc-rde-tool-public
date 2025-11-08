"""
サブグループバリデーション管理モジュール
フォームバリデーション、ユーザーロールバリデーション、入力チェックを集約
"""
import re
from qt_compat.widgets import QMessageBox
from qt_compat.gui import QColor


class SubjectInputValidator:
    """課題入力のバリデーション機能を担当するクラス（更新版）"""
    
    def __init__(self, subjects_widget):
        """
        Args:
            subjects_widget: SubjectEntryWidget インスタンス
        """
        self.subjects_widget = subjects_widget
        self.setup_validation()
    
    def setup_validation(self):
        """バリデーション機能のセットアップ"""
        # 課題ウィジェットのデータ変更時にバリデーション実行
        self.subjects_widget.dataChanged.connect(self.validate_all_subjects)
    
    def validate_all_subjects(self):
        """全課題のバリデーション実行"""
        valid_subjects, errors = self.subjects_widget.validate_subjects()
        
        if errors:
            # エラーがある場合の表示（今後必要に応じて実装）
            print(f"[WARNING] 課題バリデーションエラー: {errors}")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_subject_format(grant_number, title=""):
        """
        課題データの形式検証（静的メソッド）
        
        Args:
            grant_number (str): 課題番号
            title (str): 課題名（オプション）
            
        Returns:
            tuple: (is_valid, error_message)
        """
        if not grant_number.strip():
            return False, "課題番号が空です"
        
        # 課題番号の文字制限チェック（半角英数字、ハイフン、アンダースコア）
        if not all(c.isalnum() or c in '-_' for c in grant_number):
            return False, f"課題番号に無効な文字が含まれています: {grant_number}"
        
        return True, ""
    
    @staticmethod
    def validate_subjects_list(subjects):
        """
        課題リストの検証
        
        Args:
            subjects (list): [{"grantNumber": "", "title": ""}, ...] 形式
            
        Returns:
            tuple: (is_valid, error_messages_list, valid_subjects)
        """
        valid_subjects = []
        errors = []
        grant_numbers = set()
        
        for i, subject in enumerate(subjects):
            grant_number = subject.get("grantNumber", "").strip()
            title = subject.get("title", "").strip()
            
            if not grant_number:
                continue  # 空の課題番号はスキップ
            
            # 重複チェック
            if grant_number in grant_numbers:
                errors.append(f"課題番号が重複しています: {grant_number}")
                continue
            
            # 形式チェック
            is_valid, error_msg = SubjectInputValidator.validate_subject_format(grant_number, title)
            if not is_valid:
                errors.append(f"行{i+1}: {error_msg}")
                continue
            
            # 課題名が空の場合は課題番号を使用
            if not title:
                title = grant_number
            
            valid_subjects.append({"grantNumber": grant_number, "title": title})
            grant_numbers.add(grant_number)
        
        return len(errors) == 0, errors, valid_subjects


class UserRoleValidator:
    """ユーザーロール選択のバリデーションクラス"""
    
    @staticmethod
    def validate_user_roles(user_rows):
        """
        ユーザーロール選択のバリデーション
        
        Args:
            user_rows (list): ユーザー選択情報 [(user_id, owner_radio, assistant_cb, member_cb, agent_cb, viewer_cb), ...]
        
        Returns:
            tuple: (is_valid, error_message, roles, selected_user_ids)
        """
        owner_count = 0
        selected_user_ids = []
        roles = []
        owner_id = None

        for user_id, owner_radio, assistant_cb, member_cb, agent_cb, viewer_cb in user_rows or []:
            if owner_radio.isChecked():
                owner_count += 1
                owner_id = user_id
                roles.append({
                    "userId": user_id,
                    "role": "OWNER",
                    "canCreateDatasets": True,
                    "canEditMembers": True
                })
            elif assistant_cb.isChecked():
                selected_user_ids.append(user_id)
                roles.append({
                    "userId": user_id,
                    "role": "ASSISTANT",
                    "canCreateDatasets": True,
                    "canEditMembers": False
                })
            elif member_cb.isChecked():
                selected_user_ids.append(user_id)
                roles.append({
                    "userId": user_id,
                    "role": "MEMBER",
                    "canCreateDatasets": False,
                    "canEditMembers": False
                })
            elif agent_cb.isChecked():
                selected_user_ids.append(user_id)
                roles.append({
                    "userId": user_id,
                    "role": "AGENT",
                    "canCreateDatasets": False,
                    "canEditMembers": False
                })    
            elif viewer_cb.isChecked():
                selected_user_ids.append(user_id)
                roles.append({
                    "userId": user_id,
                    "role": "VIEWER",
                    "canCreateDatasets": False,
                    "canEditMembers": False
                })                    
        # OWNER必須バリデーション
        if owner_count == 0:
            return False, "OWNER（管理者）を1人選択してください。", [], []
        elif owner_count > 1:
            return False, "OWNERは1人のみ選択できます。", [], []
        
        if owner_id:
            selected_user_ids = [owner_id] + selected_user_ids
        
        if not selected_user_ids:
            return False, "追加するユーザーを1人以上選択してください。", [], []
        
        return True, "", roles, selected_user_ids
    
    @staticmethod
    def validate_owner_selection(owner_count):
        """OWNER選択数のバリデーション（UIメッセージ表示付き）"""
        if owner_count == 0:
            return False, "OWNER（管理者）を1人選択してください。"
        elif owner_count > 1:
            return False, "OWNERは1人のみ選択できます。"
        return True, ""


class FormValidator:
    """フォーム全体のバリデーションクラス"""
    
    @staticmethod
    def validate_required_fields(group_name, selected_user_ids):
        """
        必須フィールドのバリデーション
        
        Args:
            group_name (str): グループ名
            selected_user_ids (list): 選択ユーザーIDリスト
            
        Returns:
            tuple: (is_valid, error_message)
        """
        if not group_name:
            return False, "グループ名を入力してください。"
        
        if not selected_user_ids:
            return False, "追加するユーザーを1人以上選択してください。"
        
        return True, ""
    
    @staticmethod
    def validate_subjects_text(subjects_text):
        """
        課題テキストの検証
        
        Args:
            subjects_text (str): 課題入力テキスト
            
        Returns:
            tuple: (is_valid, error_message, parsed_subjects)
        """
        if not subjects_text.strip():
            return True, "", []
        
        # 改行チェック
        if '\n' in subjects_text or '\r' in subjects_text:
            return False, "改行は使用できません。カンマで区切ってください", []
        
        # 課題パース
        parsed_subjects = []
        parts = [p.strip() for p in subjects_text.split(',') if p.strip()]
        
        for part in parts:
            if ':' in part:
                grant_number, title = part.split(':', 1)
                grant_number = grant_number.strip()
                title = title.strip()
                
                if not grant_number or not title:
                    return False, f"課題番号または課題名が空です: {part}", []
                
                parsed_subjects.append({
                    "grantNumber": grant_number,
                    "title": title
                })
            else:
                # 課題番号のみの場合
                grant_number = part.strip()
                if grant_number:
                    parsed_subjects.append({
                        "grantNumber": grant_number,
                        "title": grant_number
                    })
        
        return True, "", parsed_subjects
    
    @staticmethod
    def validate_funds_text(funds_text):
        """
        研究資金テキストの検証
        
        Args:
            funds_text (str): 研究資金入力テキスト
            
        Returns:
            list: パースされた研究資金リスト
        """
        if not funds_text.strip():
            return []
        
        return [f.strip() for f in funds_text.split(',') if f.strip()]


class UIValidator:
    """UI表示・操作バリデーションクラス"""
    
    @staticmethod
    def show_validation_error(parent_widget, title, message):
        """
        バリデーションエラーのメッセージ表示
        
        Args:
            parent_widget: 親ウィジェット
            title (str): ダイアログタイトル
            message (str): エラーメッセージ
        """
        QMessageBox.warning(parent_widget, title, message)
    
    @staticmethod
    def show_validation_success(parent_widget, title, message):
        """
        バリデーション成功のメッセージ表示
        
        Args:
            parent_widget: 親ウィジェット
            title (str): ダイアログタイトル
            message (str): 成功メッセージ
        """
        QMessageBox.information(parent_widget, title, message)
    
    @staticmethod
    def get_row_background_color(is_owner, is_assistant, is_member, is_agent, is_viewer):
        """
        行の背景色を取得
        
        Args:
            is_owner (bool): OWNER選択状態
            is_assistant (bool): ASSISTANT選択状態
            is_member (bool): MEMBER選択状態
            is_agent (bool): AGENT選択状態
            is_viewer (bool): VIEWER選択状態

        Returns:
            QColor: 背景色
        """
        if is_owner:
            # OWNER選択時: より濃い青色
            return QColor(200, 220, 255)
        elif is_assistant:
            # ASSISTANT選択時: 薄い青色
            return QColor(230, 240, 255)
        elif is_member:
            # MEMBER選択時: 薄い緑色
            return QColor(230, 255, 230)
        elif is_agent:
            # AGENT選択時: 薄い黄色
            return QColor(255, 255, 230)
        elif is_viewer:
            # VIEWER選択時: 薄い灰色
            return QColor(240, 240, 240)
        else:
            # 未選択時: デフォルト背景色
            return QColor(255, 255, 255)


class SubgroupFilterValidator:
    """サブグループフィルタリングのバリデーションクラス"""
    
    @staticmethod
    def should_include_group(group, filter_value, current_user_id):
        """
        フィルタ条件に基づくグループ表示判定
        
        Args:
            group (dict): グループデータ
            filter_value (str): フィルタ値 ("owner", "both", "assistant", "member", "agent", "viewer", "none")
            current_user_id (str): 現在のユーザーID
            
        Returns:
            bool: 表示対象かどうか
        """
        if filter_value == "none":
            return True
        
        roles = group.get("attributes", {}).get("roles", [])
        user_role = next((r["role"] for r in roles if r["userId"] == current_user_id), None)
        
        if filter_value == "owner":
            return user_role == "OWNER"
        elif filter_value == "both":
            return user_role in ["OWNER", "ASSISTANT"]
        elif filter_value == "assistant":
            return user_role == "ASSISTANT"
        elif filter_value == "member":
            return user_role == "MEMBER"
        elif filter_value == "agent":
            return user_role == "AGENT"
        elif filter_value == "viewer":
            return user_role == "VIEWER"

        return False
    
    @staticmethod
    def get_current_user_id():
        """
        現在のユーザーIDを取得（実装は環境に依存）
        
        Returns:
            str: ユーザーID（実装により要調整）
        """
        # TODO: 実際の環境に合わせて実装
        # 現在は仮実装
        return "current_user_id"
