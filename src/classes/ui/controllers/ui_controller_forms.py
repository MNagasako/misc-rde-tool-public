"""
UIコントローラーフォーム機能クラス - ARIM RDE Tool v1.13.2
UIControllerのフォーム生成・バリデーション・入力管理機能を担当
"""
import logging
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QComboBox, QLineEdit, QTextEdit, QMessageBox, QWidget
)

class UIControllerForms:
    """UIコントローラーのフォーム機能専門クラス"""
    
    def __init__(self, ui_controller):
        """
        UIControllerFormsの初期化
        Args:
            ui_controller: 親のUIControllerインスタンス
        """
        self.ui_controller = ui_controller
        self.logger = logging.getLogger("UIControllerForms")
        
        # フォーム関連の状態変数
        self.sample_form_widget = None
        self.current_form_data = {}
        self.form_validation_rules = {}
    
    def create_expand_button(self, text_widget, title):
        """
        テキストエリア用の拡大表示ボタンを作成
        Args:
            text_widget: 対象のテキストウィジェット
            title: ダイアログのタイトル
        Returns:
            QPushButton: 拡大表示ボタン
        """
        try:
            expand_btn = QPushButton("🔍")
            expand_btn.setToolTip("拡大表示")
            expand_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e3f2fd;
                    border: 1px solid #2196f3;
                    border-radius: 12px;
                    width: 24px;
                    height: 24px;
                    font-size: 12px;
                    color: #1976d2;
                }
                QPushButton:hover {
                    background-color: #bbdefb;
                }
                QPushButton:pressed {
                    background-color: #90caf9;
                }
            """)
            expand_btn.setMaximumSize(24, 24)
            expand_btn.setMinimumSize(24, 24)
            
            # クリック時の処理を設定
            def show_expanded():
                self.show_text_area_expanded(text_widget, title)
            
            expand_btn.clicked.connect(show_expanded)
            self.logger.info(f"拡大表示ボタン作成完了: {title}")
            return expand_btn
            
        except Exception as e:
            self.logger.error(f"拡大表示ボタン作成エラー: {e}")
            self.ui_controller.show_error(f"拡大表示ボタン作成エラー: {e}")
            return None
    
    def show_text_area_expanded(self, text_widget, title):
        """
        テキストエリアの拡大表示ダイアログを表示
        Args:
            text_widget: 対象のテキストウィジェット
            title: ダイアログのタイトル
        """
        try:
            # 循環参照を避けるため、直接実装を呼び出す
            # テキスト内容を取得
            content = ""
            if hasattr(text_widget, 'toPlainText'):
                content = text_widget.toPlainText()
                # QTextBrowserの場合、HTMLコンテンツも確認
                if hasattr(text_widget, 'toHtml') and not content.strip():
                    html_content = text_widget.toHtml()
                    if html_content.strip():
                        content = html_content
            elif hasattr(text_widget, 'toHtml'):
                content = text_widget.toHtml()
            else:
                content = str(text_widget)
            
            # コンテンツが空の場合のメッセージ
            if not content.strip():
                content = "（内容が空です）"
            
            # 編集可能かどうかを判定
            editable = not text_widget.isReadOnly() if hasattr(text_widget, 'isReadOnly') else False
            
            # ダイアログを表示（元のウィジェットへの参照を渡す）
            from classes.ui.dialogs.ui_dialogs import TextAreaExpandDialog
            dialog = TextAreaExpandDialog(self.ui_controller.parent, title, content, editable, text_widget)
            dialog.show()
            
        except Exception as e:
            self.logger.error(f"テキストエリア拡大表示エラー: {e}")
            try:
                # エラー時もダイアログを表示
                from classes.ui.dialogs.ui_dialogs import TextAreaExpandDialog
                dialog = TextAreaExpandDialog(self.ui_controller.parent, title, f"エラーが発生しました: {e}", False)
                dialog.show()
            except Exception as e2:
                # フォールバック：基本的なエラー表示
                self.logger.error(f"フォールバックダイアログ表示エラー: {e2}")
                if hasattr(self.ui_controller, 'show_error'):
                    self.ui_controller.show_error(f"テキストエリア拡大表示エラー: {e}")
                else:
                    print(f"テキストエリア拡大表示エラー: {e}")
    
    def update_sample_form(self, group_id, widget, layout):
        """
        グループIDに基づいて試料選択/入力フォームを動的生成
        Args:
            group_id: 選択されたグループID
            widget: 親ウィジェット
            layout: 親レイアウト
        """
        try:
            import json
            import os
            
            self.logger.info(f"試料フォーム更新開始: グループID={group_id}")
            
            # 既存の試料フォームを削除
            if hasattr(self.ui_controller, 'sample_form_widget') and self.ui_controller.sample_form_widget is not None:
                layout.removeWidget(self.ui_controller.sample_form_widget)
                self.ui_controller.sample_form_widget.deleteLater()
                self.ui_controller.sample_form_widget = None

            # 試料フォーム全体のコンテナ作成
            self.ui_controller.sample_form_widget = QFrame()
            self.ui_controller.sample_form_widget.setFrameStyle(QFrame.Box)
            self.ui_controller.sample_form_widget.setStyleSheet("""
                QFrame {
                    border: 1px solid #c0c0c0;
                    border-radius: 4px;
                    background-color: #f8f8f8;
                    margin: 5px;
                    padding: 10px;
                }
            """)
            
            sample_form_layout = QVBoxLayout()
            self.ui_controller.sample_form_widget.setLayout(sample_form_layout)
            
            # フォームの内容を構築
            self._build_sample_form_content(group_id, sample_form_layout)
            
            # 親レイアウトに追加
            layout.addWidget(self.ui_controller.sample_form_widget)
            
            self.logger.info(f"試料フォーム更新完了: グループID={group_id}")
            
        except Exception as e:
            self.logger.error(f"試料フォーム更新エラー: {e}")
            self.ui_controller.show_error(f"試料フォーム更新エラー: {e}")
    
    def _build_sample_form_content(self, group_id, layout):
        """
        試料フォームの内容を構築
        Args:
            group_id: グループID
            layout: 親レイアウト
        """
        try:
            # タイトルラベル（コンパクト化）
            title_label = QLabel("🧪 試料情報")
            title_label.setStyleSheet("""
                font-weight: bold; 
                color: #2196F3; 
                margin: 2px 0 2px 0; 
                font-size: 11pt;
            """)
            layout.addWidget(title_label)
            
            # 既存試料データを確認し、選択機能を実装
            self._create_sample_selection_area(group_id, layout)
            
            # 試料選択・入力エリア
            self._create_sample_input_area(layout)
            
            # バリデーション情報表示エリア
            self._create_validation_info_area(layout)
            
        except Exception as e:
            self.logger.error(f"試料フォーム内容構築エラー: {e}")
    
    def _create_sample_selection_area(self, group_id, layout):
        """
        試料選択エリアを作成（既存試料がある場合のみ表示）
        Args:
            group_id: グループID
            layout: 親レイアウト
        """
        try:
            import json
            import os
            from config.common import get_dynamic_file_path
            
            # グループIDに紐づく既存試料データを確認
            sample_file_path = get_dynamic_file_path(f'output/rde/data/samples/{group_id}.json')
            
            if not os.path.exists(sample_file_path):
                self.logger.info(f"試料データファイルが存在しません: {sample_file_path}")
                return
            
            with open(sample_file_path, 'r', encoding='utf-8') as f:
                sample_data = json.load(f)
            
            # 試料データが存在する場合、選択コンボボックスを作成
            samples = sample_data.get('data', [])
            if not samples:
                self.logger.info(f"グループID {group_id} に試料データがありません")
                return
            
            self.logger.info(f"グループID {group_id} に {len(samples)} 件の既存試料が見つかりました")
            
            # 選択コンボボックス作成（横並びレイアウト）
            combo_widget = QWidget()
            combo_layout = QHBoxLayout()
            combo_layout.setContentsMargins(0, 0, 0, 0)
            combo_layout.setSpacing(10)
            
            # ラベル
            combo_label = QLabel("試料選択:")
            combo_label.setFixedWidth(120)  # 他のラベルと幅を合わせる
            combo_label.setStyleSheet("color: #424242; font-weight: bold; font-size: 10pt;border:0")
            combo_layout.addWidget(combo_label)
            
            # コンボボックス
            from PyQt5.QtWidgets import QComboBox
            self.ui_controller.sample_select_combo = QComboBox()
            self.ui_controller.sample_select_combo.setStyleSheet("""
                QComboBox {
                    padding: 4px 6px;
                    border: 1px solid #cccccc;
                    border-radius: 3px;
                    background-color: white;
                    font-size: 10pt;
                    min-height: 24px;
                }
                QComboBox::drop-down {
                    border: none;
                    background: #e3f2fd;
                }
            """)
            
            # "新規入力"オプションを最初に追加
            self.ui_controller.sample_select_combo.addItem("-- 新規入力で試料情報を作成 --", None)
            
            # 既存試料をコンボボックスに追加
            for i, sample in enumerate(samples):
                attributes = sample.get('attributes', {})
                names = attributes.get('names', [])
                description = attributes.get('description', '')
                
                # 表示用のテキストを作成
                display_name = names[0] if names else f"試料 {i+1}"
                if description:
                    # 説明が長い場合は省略
                    desc_short = description[:30] + "..." if len(description) > 30 else description
                    display_text = f"{display_name} - {desc_short}"
                else:
                    display_text = display_name
                
                self.ui_controller.sample_select_combo.addItem(display_text, sample)
            
            # コンボボックスの変更イベントを設定
            self.ui_controller.sample_select_combo.currentIndexChanged.connect(
                self.ui_controller.on_sample_selection_changed
            )
            
            combo_layout.addWidget(self.ui_controller.sample_select_combo)
            combo_widget.setLayout(combo_layout)
            layout.addWidget(combo_widget)
            
            # 説明テキスト（シンプル化）
            info_text = QLabel("既存試料を選択するか、「新規入力」のまま下記に入力")
            info_text.setStyleSheet("color: #666666; font-size: 9pt; margin: 2px 0 5px 0;")
            layout.addWidget(info_text)
            
        except Exception as e:
            self.logger.error(f"試料選択エリア作成エラー: {e}")
            # エラーが発生しても、通常の入力フォームは表示する
    
    def _create_sample_input_area(self, layout):
        """
        試料入力エリアを作成
        Args:
            layout: 親レイアウト
        """
        try:
            # 試料名入力
            self._add_sample_input(layout, "試料名", "sample_names_input", "試料名を入力してください", True)
            
            # 試料の説明入力
            self._add_sample_input(layout, "試料の説明", "sample_description_input", "試料の説明を入力してください", False, True)
            
            # 組成情報入力
            self._add_sample_input(layout, "化学式・組成式・分子式", "sample_composition_input", "化学式・組成式・分子式を入力してください", False)
            
        except Exception as e:
            self.logger.error(f"試料入力エリア作成エラー: {e}")
    
    def _add_sample_input(self, layout, label_text, attr_name, placeholder, is_required=False, is_textarea=False):
        """
        試料入力フィールドを追加（横並びレイアウト）
        Args:
            layout: 親レイアウト
            label_text: ラベルテキスト
            attr_name: 属性名
            placeholder: プレースホルダー
            is_required: 必須フィールドかどうか
            is_textarea: テキストエリアかどうか
        """
        try:
            from PyQt5.QtWidgets import QHBoxLayout, QWidget
            
            # 横並び用のコンテナを作成
            row_widget = QWidget()
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(10)
            
            # ラベル作成（固定幅）
            label = QLabel(label_text + ("(必須)" if is_required else ""))
            label.setFixedWidth(120)  # ラベル幅を拡張（化学式等の長いラベル対応）
            if is_required:
                label.setStyleSheet("color: #d32f2f; font-weight: bold; font-size: 10pt;border:0")
            else:
                label.setStyleSheet("color: #424242; font-size: 10pt;border:0")

            row_layout.addWidget(label)
            
            # 入力フィールド作成（残りの幅を使用）
            if is_textarea:
                input_widget = QTextEdit()
                input_widget.setPlaceholderText(placeholder)
                input_widget.setMaximumHeight(50)  # さらに小さく
                input_widget.setMinimumHeight(50)
            else:
                input_widget = QLineEdit()
                input_widget.setPlaceholderText(placeholder)
                input_widget.setMinimumHeight(24)  # 小さく
            
            # スタイルを統一（シンプル化）
            input_widget.setStyleSheet("""
                QLineEdit, QTextEdit {
                    padding: 3px 6px;
                    border: 1px solid #cccccc;
                    border-radius: 3px;
                    background-color: white;
                    font-size: 10pt;
                }
                QLineEdit:focus, QTextEdit:focus {
                    border: 2px solid #2196F3;
                }
                QLineEdit:disabled, QTextEdit:disabled {
                    background-color: #f5f5f5;
                    color: #666666;
                }
            """)
            
            row_layout.addWidget(input_widget)
            
            # 拡大表示ボタンをテキストエリアに追加
            if is_textarea:
                expand_btn = self.create_expand_button(input_widget, f"{label_text}の拡大表示")
                expand_btn.setFixedSize(24, 24)  # 小さく
                row_layout.addWidget(expand_btn)
            
            row_widget.setLayout(row_layout)
            row_widget.setStyleSheet("margin-bottom: 2px;")  # フィールド間の間隔を最小化
            
            # UIControllerに属性として設定
            setattr(self.ui_controller, attr_name, input_widget)
            layout.addWidget(row_widget)
            
            self.logger.debug(f"試料入力フィールド追加: {attr_name}")
            
        except Exception as e:
            self.logger.error(f"試料入力フィールド追加エラー: {e}")
    
    def _create_validation_info_area(self, layout):
        """
        バリデーション情報表示エリアを作成
        Args:
            layout: 親レイアウト
        """
        try:
            info_label = QLabel("※ 試料名*は必須項目です。")
            info_label.setStyleSheet("color: #666666; font-size: 9pt; margin: 2px 0 0 0;")
            # layout.addWidget(info_label)

        except Exception as e:
            self.logger.error(f"バリデーション情報エリア作成エラー: {e}")
    
    def validate_sample_info_early(self):
        """
        データ登録前の早期バリデーション
        試料情報の入力状況をチェックし、問題があれば警告メッセージを表示
        Returns:
            bool: バリデーション成功時True、失敗時False
        """
        try:
            self.logger.info("試料情報の早期バリデーション開始")
            
            # 既存試料が選択されている場合はバリデーション不要
            if (hasattr(self.ui_controller, 'sample_combo') and 
                self.ui_controller.sample_combo.currentIndex() > 0):
                self.logger.info("既存試料が選択済み - バリデーション省略")
                return True
                
            # 新規入力時のバリデーション（試料名のみ必須）
            sample_names = ""
            
            # 試料名の取得（新しいフォーム構造）
            if (hasattr(self.ui_controller, 'sample_input_widgets') and
                'name' in self.ui_controller.sample_input_widgets):
                sample_names = self.ui_controller.sample_input_widgets['name'].text().strip()
            elif hasattr(self.ui_controller, 'sample_names_input'):
                sample_names = self.ui_controller.sample_names_input.text().strip()
            
            # 試料名のみチェック（試料の説明は任意）
            if not sample_names:
                # 警告メッセージを表示
                message = ("試料情報が不足しています。\n\n"
                          "不足項目: 試料名\n\n"
                          "以下のいずれかを行ってください:\n"
                          "・既存試料を選択する\n"
                          "・新規入力で試料名を入力する")
                
                QMessageBox.warning(None, "試料情報入力エラー", message)
                
                # 試料名入力欄にフォーカスを移動
                if (hasattr(self.ui_controller, 'sample_input_widgets') and
                    'name' in self.ui_controller.sample_input_widgets):
                    self.ui_controller.sample_input_widgets['name'].setFocus()
                elif hasattr(self.ui_controller, 'sample_names_input'):
                    self.ui_controller.sample_names_input.setFocus()
                    
                self.logger.warning("試料名が未入力のためバリデーション失敗")
                return False
                
            self.logger.info("試料情報バリデーション成功")
            return True
            
        except Exception as e:
            self.logger.error(f"試料情報バリデーションエラー: {e}")
            self.ui_controller.show_error(f"試料情報バリデーションエラー: {e}")
            return False
    
    def set_sample_inputs_enabled(self, enabled):
        """
        試料入力欄の編集可能/不可を設定
        Args:
            enabled: Trueで編集可能、Falseで編集不可
        """
        try:
            style_enabled = "background-color: white; color: black;"
            style_disabled = "background-color: #f0f0f0; color: #888888;"
            
            style = style_enabled if enabled else style_disabled
            
            # 試料入力フィールドの状態を設定
            input_fields = [
                'sample_names_input',
                'sample_description_input', 
                'sample_composition_input'
            ]
            
            for field_name in input_fields:
                if hasattr(self.ui_controller, field_name):
                    field = getattr(self.ui_controller, field_name)
                    field.setEnabled(enabled)
                    field.setStyleSheet(style)
            
            self.logger.info(f"試料入力欄の状態変更: enabled={enabled}")
            
        except Exception as e:
            self.logger.error(f"試料入力欄状態変更エラー: {e}")
            self.ui_controller.show_error(f"試料入力欄状態変更エラー: {e}")
    
    def create_image_limit_dropdown(self):
        """
        画像制限ドロップダウンレイアウトを作成
        Returns:
            QHBoxLayout: 画像制限選択用レイアウト
        """
        try:
            from PyQt5.QtWidgets import QHBoxLayout, QLabel
            
            limit_layout = QHBoxLayout()
            limit_label = QLabel("画像取得上限:")
            limit_layout.addWidget(limit_label)
            
            dropdown = QComboBox()
            dropdown.addItems(["制限なし", "1枚まで", "3枚まで", "5枚まで", "10枚まで", "20枚まで"])
            dropdown.setCurrentText("3枚まで")  # デフォルト値
            dropdown.setStyleSheet("""
                QComboBox {
                    border: 1px solid #c0c0c0;
                    border-radius: 4px;
                    padding: 5px;
                    background-color: white;
                }
                QComboBox::drop-down {
                    border: none;
                }
                QComboBox::down-arrow {
                    width: 12px;
                    height: 12px;
                }
            """)
            
            limit_layout.addWidget(dropdown)
            limit_layout.addStretch()
            
            # UIControllerに属性として保存（他のメソッドからアクセス可能にする）
            self.ui_controller.image_limit_dropdown = dropdown
            
            # 変更時のイベントハンドラーを設定
            dropdown.currentTextChanged.connect(self.update_image_limit)
            
            self.logger.info("画像制限ドロップダウンレイアウト作成完了")
            return limit_layout
            
        except Exception as e:
            self.logger.error(f"画像制限ドロップダウンレイアウト作成エラー: {e}")
            self.ui_controller.show_error(f"画像制限ドロップダウンレイアウト作成エラー: {e}")
            return None
    
    def update_image_limit(self, value):
        """
        画像取得上限を更新
        Args:
            value: 選択された値
        """
        try:
            self.logger.info(f"画像取得上限更新: {value}")
            
            # グローバル変数を直接更新
            import sys
            for module_name, module in sys.modules.items():
                if hasattr(module, 'MAX_IMAGES_PER_DATASET'):
                    if value == "制限なし":
                        setattr(module, 'MAX_IMAGES_PER_DATASET', None)
                    else:
                        # "10枚まで" -> 10 の形で数値を抽出
                        import re
                        match = re.search(r'(\d+)', value)
                        if match:
                            limit_value = int(match.group(1))
                            setattr(module, 'MAX_IMAGES_PER_DATASET', limit_value)
                        else:
                            setattr(module, 'MAX_IMAGES_PER_DATASET', 20)  # デフォルト
                    break
            
            # メッセージ表示
            if hasattr(self.ui_controller, 'parent') and hasattr(self.ui_controller.parent, 'display_manager'):
                self.ui_controller.parent.display_manager.set_message(f"画像取得上限が {value} に設定されました")
            
            self.logger.info(f"画像取得上限が {value} に設定されました")
            
        except Exception as e:
            self.logger.error(f"画像取得上限更新エラー: {e}")
            self.ui_controller.show_error(f"画像取得上限更新エラー: {e}")
    
    def get_form_data(self):
        """
        現在のフォームデータを取得
        Returns:
            dict: フォームデータ
        """
        try:
            form_data = {}
            
            # 試料情報を取得
            if hasattr(self.ui_controller, 'sample_names_input'):
                form_data['sample_names'] = self.ui_controller.sample_names_input.text().strip()
            
            if hasattr(self.ui_controller, 'sample_description_input'):
                form_data['sample_description'] = self.ui_controller.sample_description_input.toPlainText().strip()
                
            if hasattr(self.ui_controller, 'sample_composition_input'):
                form_data['sample_composition'] = self.ui_controller.sample_composition_input.text().strip()
            
            self.logger.debug(f"フォームデータ取得: {form_data}")
            return form_data
            
        except Exception as e:
            self.logger.error(f"フォームデータ取得エラー: {e}")
            return {}
    
    def clear_form_data(self):
        """
        フォームデータをクリア
        """
        try:
            # 試料入力フィールドをクリア
            input_fields = [
                'sample_names_input',
                'sample_description_input',
                'sample_composition_input'
            ]
            
            for field_name in input_fields:
                if hasattr(self.ui_controller, field_name):
                    field = getattr(self.ui_controller, field_name)
                    if hasattr(field, 'clear'):
                        field.clear()
                    elif hasattr(field, 'setText'):
                        field.setText("")
            
            self.logger.info("フォームデータクリア完了")
            
        except Exception as e:
            self.logger.error(f"フォームデータクリアエラー: {e}")
            self.ui_controller.show_error(f"フォームデータクリアエラー: {e}")
