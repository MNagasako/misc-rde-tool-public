"""
自動設定ダイアログ

データポータル修正ダイアログの各項目を自動設定するためのダイアログ
報告書ベースとAIベースの2種類の情報源から候補を取得し、ユーザーが選択して適用できる
"""

import os

from typing import Dict, Any, Optional, Callable
from qt_compat.widgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QButtonGroup, QTextEdit, QMessageBox, QGroupBox, QProgressDialog
)
from qt_compat.core import Qt

from classes.theme import get_color, ThemeKey
from classes.managers.log_manager import get_logger

logger = get_logger("DataPortal.AutoSettingDialog")


class AutoSettingDialog(QDialog):
    """
    自動設定ダイアログ
    
    機能:
    - 情報源選択（報告書/AI）
    - 候補取得と表示
    - 適用/やり直し/中止
    """
    
    def __init__(self, 
                 title: str,
                 field_name: str,
                 dataset_id: str,
                 report_fetcher: Optional[Callable] = None,
                 ai_fetcher: Optional[Callable] = None,
                 metadata: Optional[Dict[str, Any]] = None,
                 description: Optional[str] = None,
                 parent=None):
        """
        初期化
        
        Args:
            title: ダイアログのタイトル
            field_name: 対象フィールド名（例: "重要技術領域"）
            dataset_id: データセットID
            report_fetcher: 報告書ベースの候補取得関数 (dataset_id) -> Dict[str, str]
            ai_fetcher: AIベースの候補取得関数 (dataset_id) -> Dict[str, str]
            metadata: メタデータ（選択肢情報、マッピング用）
            description: ダイアログの説明文（Noneの場合は自動生成）
            parent: 親ウィジェット
        """
        super().__init__(parent)
        
        self.field_name = field_name
        self.dataset_id = dataset_id
        self.report_fetcher = report_fetcher
        self.ai_fetcher = ai_fetcher
        self.metadata = metadata or {}
        self.description = description or self._generate_description()
        
        self.selected_source = "report"  # デフォルトは報告書
        self.candidates = {}  # 取得した候補 {"main": "value", "sub": "value"}
        # QDialog の result() と名前が衝突しないようにする
        self.applied_result: Optional[Dict[str, str]] = None  # 最終的に適用する値
        
        self.setWindowTitle(f"{title} - 自動設定")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        self._init_ui()
        logger.info(f"自動設定ダイアログ初期化: field={field_name}, dataset={dataset_id}")
    
    def _generate_description(self) -> str:
        """フィールド名に基づいて説明文を自動生成"""
        descriptions = {
            "重要技術領域（主・副）": "報告書またはAIから重要技術領域の候補を取得し、主・副を設定します。",
            "横断技術領域（主・副）": "報告書から横断技術領域の候補を取得し、主・副を設定します。",
            "装置・プロセス": "報告書から利用した設備の候補を取得し、選択的置換ダイアログで適用します。",
        }
        return descriptions.get(self.field_name, f"{self.field_name}の候補を自動取得します。")
    
    def _init_ui(self):
        """UI初期化"""
        layout = QVBoxLayout(self)
        
        # 説明ラベル
        desc_label = QLabel(self.description)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(f"""
            QLabel {{
                color: {get_color(ThemeKey.TEXT_SECONDARY)};
                padding: 8px;
                background-color: {get_color(ThemeKey.PANEL_NEUTRAL_BACKGROUND)};
                border-radius: 4px;
                font-size: 11px;
            }}
        """)
        layout.addWidget(desc_label)
        
        # 情報源選択グループ
        source_group = QGroupBox("情報源選択")
        source_layout = QVBoxLayout()
        
        self.source_btn_group = QButtonGroup(self)
        
        self.report_radio = QRadioButton("報告書から取得")
        self.report_radio.setChecked(True)
        self.report_radio.toggled.connect(self._on_source_changed)
        if not self.report_fetcher:
            self.report_radio.setEnabled(False)
            self.report_radio.setToolTip("報告書取得機能が利用できません")
        self.source_btn_group.addButton(self.report_radio, 0)
        source_layout.addWidget(self.report_radio)
        
        self.ai_radio = QRadioButton("AIで推定")
        self.ai_radio.toggled.connect(self._on_source_changed)
        if not self.ai_fetcher:
            self.ai_radio.setEnabled(False)
            self.ai_radio.setToolTip("AI推定機能が利用できません")
        self.source_btn_group.addButton(self.ai_radio, 1)
        source_layout.addWidget(self.ai_radio)
        
        # デフォルト選択
        if self.report_fetcher:
            self.selected_source = "report"
        elif self.ai_fetcher:
            self.selected_source = "ai"
            self.ai_radio.setChecked(True)
        
        source_group.setLayout(source_layout)
        layout.addWidget(source_group)
        
        # 取得ボタン
        self.fetch_btn = QPushButton("候補を取得")
        self.fetch_btn.clicked.connect(self._on_fetch_candidates)
        self.fetch_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
            }}
        """)
        layout.addWidget(self.fetch_btn)
        
        # 候補表示エリア
        candidate_group = QGroupBox("取得された候補")
        candidate_layout = QVBoxLayout()
        
        self.candidate_text = QTextEdit()
        self.candidate_text.setReadOnly(True)
        self.candidate_text.setPlaceholderText("「候補を取得」ボタンを押すと、候補が表示されます")
        self.candidate_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                color: {get_color(ThemeKey.INPUT_TEXT)};
                font-size: 12px;
            }}
        """)
        candidate_layout.addWidget(self.candidate_text)
        
        candidate_group.setLayout(candidate_layout)
        layout.addWidget(candidate_group)
        
        # ボタンエリア
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_btn = QPushButton("中止")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        self.retry_btn = QPushButton("やり直し")
        self.retry_btn.clicked.connect(self._on_retry)
        self.retry_btn.setEnabled(False)
        button_layout.addWidget(self.retry_btn)
        
        self.apply_btn = QPushButton("適用")
        self.apply_btn.clicked.connect(self._on_apply)
        self.apply_btn.setEnabled(False)
        self.apply_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
            }}
            QPushButton:disabled {{
                background-color: {get_color(ThemeKey.BUTTON_DISABLED_BACKGROUND)};
            }}
        """)
        button_layout.addWidget(self.apply_btn)
        
        layout.addLayout(button_layout)
    
    def _on_source_changed(self):
        """情報源変更"""
        if self.report_radio.isChecked():
            self.selected_source = "report"
            logger.debug("情報源: 報告書")
        else:
            self.selected_source = "ai"
            logger.debug("情報源: AI")
        
        # 候補をクリア
        self.candidates = {}
        self.candidate_text.clear()
        self.apply_btn.setEnabled(False)
        self.retry_btn.setEnabled(False)
    
    def _on_fetch_candidates(self):
        """候補を取得"""
        try:
            # pytest実行中は、モーダルUI/イベント強制処理がWindows側で不安定になり得るため抑制
            progress = None
            if not os.environ.get("PYTEST_CURRENT_TEST"):
                progress = QProgressDialog("候補を取得しています...", None, 0, 0, self)
                progress.setWindowTitle("候補取得中")
                progress.setWindowModality(Qt.WindowModal)
                progress.show()

                from qt_compat.core import QCoreApplication
                QCoreApplication.processEvents()
            
            # 候補取得
            if self.selected_source == "report" and self.report_fetcher:
                logger.info("報告書から候補取得開始")
                self.candidates = self.report_fetcher(self.dataset_id)
            elif self.selected_source == "ai" and self.ai_fetcher:
                logger.info("AIで候補取得開始")
                self.candidates = self.ai_fetcher(self.dataset_id)
            else:
                raise ValueError(f"取得機能が利用できません: {self.selected_source}")
            
            if progress is not None:
                progress.close()
            
            # 候補表示
            if self.candidates:
                self._display_candidates()
                self.apply_btn.setEnabled(True)
                self.retry_btn.setEnabled(True)
                logger.info(f"候補取得成功: {self.candidates}")
            else:
                QMessageBox.warning(
                    self,
                    "候補取得失敗",
                    "候補を取得できませんでした。\n別の情報源を試すか、手動で入力してください。"
                )
                logger.warning("候補取得失敗: 空の結果")
        
        except Exception as e:
            logger.error(f"候補取得エラー: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "エラー",
                f"候補取得中にエラーが発生しました:\n{e}"
            )
    
    def _display_candidates(self):
        """候補を表示"""
        text_parts = []
        
        # 情報源
        source_name = "報告書" if self.selected_source == "report" else "AI推定"
        text_parts.append(f"【情報源】 {source_name}\n")
        
        # 候補内容（装置・プロセスリスト or 主・副形式）
        if "equipment" in self.candidates:
            # 装置・プロセスリスト形式
            equipment_list = self.candidates.get("equipment", [])
            if equipment_list:
                text_parts.append(f"【装置・プロセス一覧】 ({len(equipment_list)}件)")
                for eq in equipment_list:
                    text_parts.append(f"  • {eq}")
            else:
                text_parts.append("【装置・プロセス一覧】 候補が見つかりませんでした")
        else:
            # 主・副形式（重要技術領域、横断技術領域）
            if "main" in self.candidates:
                text_parts.append(f"【主】 {self.candidates['main']}")
            if "sub" in self.candidates:
                text_parts.append(f"【副】 {self.candidates['sub']}")

            # 参考情報: MItree（マテリアルインデックス詳細）候補があれば併記
            if "MItree" in self.candidates and isinstance(self.candidates["MItree"], list) and self.candidates["MItree"]:
                text_parts.append("\n【参考】 マテリアルインデックス（詳細）候補")
                # 上位3件まで表示（label / hierarchy / 理由）
                for i, item in enumerate(self.candidates["MItree"][:3], start=1):
                    label = item.get('label') if isinstance(item, dict) else str(item)
                    hierarchy = item.get('hierarchy') if isinstance(item, dict) else None
                    reason = item.get('reason') if isinstance(item, dict) else ''
                    text_parts.append(f"  ・{i}. {label}")
                    if hierarchy:
                        text_parts.append(f"     階層: {hierarchy}")
                    if reason:
                        text_parts.append(f"     理由: {reason}")
            
            # メタデータとのマッピング確認（あれば）
            if self.metadata:
                text_parts.append("\n【マッピング確認】")
                for key in ["main", "sub"]:
                    if key in self.candidates:
                        value = self.candidates[key]
                        if value:
                            # メタデータからラベルを検索
                            matched = self._find_metadata_label(value)
                            if matched:
                                text_parts.append(f"{key}: {value} → {matched}")
                            else:
                                text_parts.append(f"{key}: {value} (マッピングなし)")
        
        self.candidate_text.setPlainText("\n".join(text_parts))
    
    def _find_metadata_label(self, value: str) -> Optional[str]:
        """
        メタデータから値に対応するラベルを検索
        
        Args:
            value: 検索する値
        
        Returns:
            Optional[str]: ラベル（見つからない場合はNone）
        """
        # 主と副の両方のメタデータを検索
        for meta_key in ["main_mita_code_array[]", "sub_mita_code_array[]"]:
            if meta_key in self.metadata:
                for opt in self.metadata[meta_key].get("options", []):
                    if opt.get("value") == value or opt.get("label") == value:
                        return opt.get("label", "")
        return None
    
    def _on_retry(self):
        """やり直し"""
        self.candidates = {}
        self.candidate_text.clear()
        self.apply_btn.setEnabled(False)
        self.retry_btn.setEnabled(False)
        logger.debug("候補をクリア、やり直し")
    
    def _on_apply(self):
        """適用"""
        if not self.candidates:
            QMessageBox.warning(self, "警告", "候補が取得されていません")
            return
        
        # 確認ダイアログ（装置・プロセスリスト or 主・副形式）
        if "equipment" in self.candidates:
            # 装置・プロセス形式
            equipment_list = self.candidates.get("equipment", [])
            count = len(equipment_list)
            preview = "\n".join(equipment_list[:5])  # 最初の5件をプレビュー
            if count > 5:
                preview += f"\n... 他 {count - 5}件"
            
            reply = QMessageBox.question(
                self,
                "適用確認",
                f"以下の候補を適用しますか?\n\n装置・プロセス: {count}件\n\n{preview}",
                QMessageBox.Yes | QMessageBox.No
            )
        else:
            # 主・副形式
            reply = QMessageBox.question(
                self,
                "適用確認",
                f"以下の候補を適用しますか?\n\n主: {self.candidates.get('main', '(なし)')}\n副: {self.candidates.get('sub', '(なし)')}",
                QMessageBox.Yes | QMessageBox.No
            )
        
        if reply == QMessageBox.Yes:
            self.applied_result = self.candidates
            logger.info(f"候補適用: {self.applied_result}")
            self.accept()
    
    def get_result(self) -> Optional[Dict[str, str]]:
        """
        適用された結果を取得
        
        Returns:
            Optional[Dict[str, str]]: {"main": "value", "sub": "value"} または None
        """
        return self.applied_result
