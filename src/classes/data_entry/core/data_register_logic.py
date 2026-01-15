import os
import json
import logging
import tempfile
import urllib.parse
import re


def _build_data_register_completion_text(
    *,
    success: bool,
    upload_total: int,
    upload_success_data_files: int,
    upload_success_attachments: int,
    failed_files: list[str] | None = None,
    detail: str | None = None,
    result_text: str | None = None,
) -> str:
    """通常登録の進捗ダイアログ完了表示用テキストを生成する（純粋関数）。"""

    failed_files = failed_files or []
    upload_success_total = int(upload_success_data_files) + int(upload_success_attachments)
    status_line = f"結果: {result_text}" if result_text else ("結果: 成功" if success else "結果: 失敗")
    lines: list[str] = [
        status_line,
        f"アップロード: {upload_success_total}件 / {upload_total}件 (データ: {upload_success_data_files}件, 添付: {upload_success_attachments}件)",
    ]
    if failed_files:
        # 長すぎると見落としやすいので、ここでは列挙のみ（UIは手動コピー可能）
        lines.append("失敗ファイル:\n- " + "\n- ".join(failed_files))
    if detail:
        lines.append(detail)
    return "\n".join(lines)


def _center_on_screen(widget) -> None:
    """ウィジェットを画面中央へ移動する（可能な場合）。"""

    try:
        from qt_compat.widgets import QApplication

        screen = None
        try:
            screen = widget.screen()
        except Exception:
            screen = None
        if screen is None:
            try:
                screen = QApplication.primaryScreen()
            except Exception:
                screen = None
        if screen is None:
            return

        geo = screen.availableGeometry()
        fg = widget.frameGeometry()
        fg.moveCenter(geo.center())
        widget.move(fg.topLeft())
    except Exception:
        return


def _center_on_parent(widget, parent) -> None:
    """ウィジェットを親ウィンドウの中央へ移動する（可能な場合）。

    QMessageBox/QDialog は環境により親中央に出ないことがあるため、明示的に寄せる。
    """

    try:
        if widget is None or parent is None:
            return
        try:
            parent_geo = parent.frameGeometry()
        except Exception:
            parent_geo = None
        if parent_geo is None:
            return
        try:
            fg = widget.frameGeometry()
            fg.moveCenter(parent_geo.center())
            widget.move(fg.topLeft())
        except Exception:
            return
    except Exception:
        return


def _finalize_progress_dialog(progress, *, title: str, text: str, require_confirmation: bool = True) -> None:
    """進捗ダイアログを完了状態として整形する。

    Args:
        progress: QProgressDialog
        title: ウィンドウタイトル
        text: 完了文言
        require_confirmation: True=通常登録（確認押下まで閉じない） / False=一括登録等（自動クローズ寄り）
    """

    from qt_compat.core import Qt, QCoreApplication, QTimer
    from qt_compat.widgets import QPushButton

    if require_confirmation:
        try:
            progress.setAutoClose(False)
            progress.setAutoReset(False)
            progress.setMinimumDuration(0)
        except Exception:
            pass

        # 完了時はアプリ全体をブロック（他機能を操作させない）
        try:
            progress.setWindowModality(Qt.ApplicationModal)
        except Exception:
            pass
        try:
            progress.setModal(True)
        except Exception:
            pass
    else:
        # 一括登録など: 確認回数を減らすため、自動クローズ寄りにする
        try:
            progress.setAutoClose(True)
            progress.setAutoReset(True)
            progress.setMinimumDuration(0)
        except Exception:
            pass

    try:
        progress.setWindowTitle(title)
    except Exception:
        pass

    try:
        existing = progress.labelText() or ""
    except Exception:
        existing = ""
    if existing:
        progress.setLabelText(existing + "\n\n" + text)
    else:
        progress.setLabelText(text)

    if require_confirmation:
        # run_data_register_logic 側で仕込んだ隠しボタンがあれば再利用し、確実に表示する
        confirm_btn = None
        try:
            existing_btn = getattr(progress, "_hidden_cancel_button", None)
            if isinstance(existing_btn, QPushButton):
                confirm_btn = existing_btn
        except Exception:
            confirm_btn = None

        if confirm_btn is not None:
            # 既にセット済みのボタンを再セットすると Qt 側で警告 & 無視されることがあるため、
            # setCancelButton() は呼ばずに表示・接続だけ行う。
            try:
                confirm_btn.setText("確認")
                confirm_btn.setVisible(True)
                confirm_btn.setEnabled(True)
            except Exception:
                pass
            try:
                confirm_btn.clicked.connect(progress.close)
            except Exception:
                pass
            try:
                setattr(progress, "_confirm_button", confirm_btn)
            except Exception:
                pass
            try:
                progress.setCancelButtonText("確認")
            except Exception:
                pass
        else:
            # hiddenボタンが無い場合のみ新規でボタンを差し込み
            confirm_btn = QPushButton("確認")
            try:
                progress.setCancelButton(confirm_btn)
                confirm_btn.clicked.connect(progress.close)
                setattr(progress, "_confirm_button", confirm_btn)
                progress.setCancelButtonText("確認")
            except Exception:
                # フォールバック: 標準キャンセルボタンのテキストだけ差し替える
                try:
                    progress.setCancelButtonText("確認")
                    progress.canceled.connect(progress.close)
                except Exception:
                    pass

    try:
        flags = progress.windowFlags() | Qt.WindowStaysOnTopHint
        if require_confirmation:
            # 「確認」ボタンでのみ閉じる運用にしたいので、ウィンドウの×を無効化する
            try:
                flags = flags & ~Qt.WindowCloseButtonHint
            except Exception:
                pass
        progress.setWindowFlags(flags)
    except Exception:
        pass
    try:
        progress.show()
        progress.raise_()
        progress.activateWindow()
    except Exception:
        pass

    # autoClose は「表示された後に最大値に到達」したタイミングで閉じる挙動のため、
    # show() の後に value を最大へ遷移させる。
    try:
        max_value = progress.maximum()
    except Exception:
        max_value = None

    def _set_value_and_maybe_close() -> None:
        try:
            if max_value is not None:
                progress.setValue(max_value)
        except Exception:
            pass
        if not require_confirmation:
            # バインディング差・環境差で autoClose が効かないケースの保険。
            try:
                QTimer.singleShot(50, progress.close)
            except Exception:
                pass

    try:
        QTimer.singleShot(0, _set_value_and_maybe_close)
    except Exception:
        _set_value_and_maybe_close()

    # プログレスダイアログは「親ウィンドウ中央」を優先して表示する。
    # （親が取れない/親の geometry が取れない場合のみ画面中央へフォールバック）
    try:
        parent_widget = None
        try:
            parent_widget = progress.parentWidget()
        except Exception:
            parent_widget = None
        if parent_widget is None:
            try:
                parent_widget = progress.parent()
            except Exception:
                parent_widget = None

        if parent_widget is not None:
            _center_on_parent(progress, parent_widget)
        else:
            _center_on_screen(progress)
    except Exception:
        try:
            _center_on_screen(progress)
        except Exception:
            pass

    # リンクが含まれる場合はクリック可能にする（QProgressDialog内部のQLabelを調整）
    try:
        if "<a href=" in (progress.labelText() or ""):
            from qt_compat.widgets import QLabel

            lbl = progress.findChild(QLabel)
            if lbl is not None:
                lbl.setTextFormat(Qt.RichText)
                lbl.setTextInteractionFlags(Qt.TextBrowserInteraction)
                lbl.setOpenExternalLinks(True)
    except Exception:
        pass

    # 横幅が伸びすぎないよう、画面の短辺を最大幅として制限（ユーザー操作で可変）
    try:
        from qt_compat.widgets import QApplication

        screen = None
        try:
            screen = progress.screen()
        except Exception:
            screen = None
        if screen is None:
            try:
                screen = QApplication.primaryScreen()
            except Exception:
                screen = None
        if screen is not None:
            geo = screen.availableGeometry()
            max_w = int(min(geo.width(), geo.height()))
            if max_w > 0:
                try:
                    progress.setSizeGripEnabled(True)
                except Exception:
                    pass
                try:
                    progress.setMaximumWidth(max_w)
                except Exception:
                    pass
                try:
                    if int(progress.width()) > max_w:
                        progress.resize(max_w, progress.height())
                except Exception:
                    pass
    except Exception:
        pass

    # POST/validation のレスポンス表示ボタン（成功/失敗/タイムアウトいずれでも確認できる）
    try:
        responses = getattr(progress, "_last_http_responses", None)
        if isinstance(responses, dict) and responses:
            existing_btn = getattr(progress, "_response_view_button", None)
            if not isinstance(existing_btn, QPushButton):
                btn = QPushButton("レスポンス表示")
                setattr(progress, "_response_view_button", btn)

                def _build_response_text() -> str:
                    parts: list[str] = []
                    for key in ("validation", "entries_post"):
                        info = responses.get(key)
                        if not isinstance(info, dict):
                            continue
                        parts.append(f"[{key}]")
                        method = info.get("method")
                        url = info.get("url")
                        if method or url:
                            parts.append(f"request: {method or ''} {url or ''}".strip())
                        status = info.get("status")
                        reason = info.get("reason")
                        if status is not None:
                            parts.append(f"status: {status} {reason or ''}".strip())
                        err = info.get("error")
                        if err:
                            parts.append(f"error: {err}")
                        note = info.get("note")
                        if note:
                            parts.append(f"note: {note}")
                        body = info.get("body")
                        if body:
                            parts.append("body:")
                            parts.append(str(body))
                        parts.append("")
                    return "\n".join(parts).rstrip()

                def _show_response_dialog():
                    from qt_compat.widgets import QDialog, QVBoxLayout, QTextEdit, QDialogButtonBox

                    dlg = QDialog(progress)
                    dlg.setWindowTitle("HTTPレスポンス")
                    try:
                        dlg.setSizeGripEnabled(True)
                    except Exception:
                        pass
                    layout = QVBoxLayout(dlg)
                    edit = QTextEdit(dlg)
                    edit.setReadOnly(True)
                    edit.setPlainText(_build_response_text())
                    layout.addWidget(edit)
                    buttons = QDialogButtonBox(QDialogButtonBox.Close, parent=dlg)
                    buttons.rejected.connect(dlg.reject)
                    buttons.accepted.connect(dlg.accept)
                    layout.addWidget(buttons)
                    dlg.resize(900, 600)
                    dlg.exec()

                try:
                    btn.clicked.connect(_show_response_dialog)
                except Exception:
                    pass
                try:
                    lay = progress.layout()
                    if lay is not None:
                        lay.addWidget(btn)
                except Exception:
                    pass
    except Exception:
        pass

    QCoreApplication.processEvents()


def _add_action_button_to_progress(progress, button) -> bool:
    """QProgressDialog にボタンを安全に埋め込む。

    QProgressDialog の layout が取れない環境があるため、
    layout -> QDialogButtonBox の順で追加を試みる。
    追加に失敗した場合は False を返す（単独ウィンドウ化の回避目的）。
    """

    try:
        from qt_compat.core import QObject, QEvent, Qt, QTimer
        from qt_compat.widgets import QGridLayout, QSizePolicy, QWidget
    except Exception:
        return False

    if progress is None or button is None:
        return False

    # どのパスでも単独ウィンドウ化しないよう、まず親を progress にする
    try:
        button.setParent(progress)
    except Exception:
        pass
    try:
        button.setWindowFlags(Qt.Widget)
    except Exception:
        pass

    def _ensure_panel() -> tuple[QWidget | None, QGridLayout | None]:
        try:
            panel = getattr(progress, "_action_button_panel", None)
            grid = getattr(progress, "_action_button_panel_grid", None)
        except Exception:
            panel, grid = None, None

        if panel is None or grid is None:
            try:
                panel = QWidget(progress)
                panel.setObjectName("action_button_panel")
                grid = QGridLayout(panel)
                grid.setContentsMargins(0, 0, 0, 0)
                grid.setHorizontalSpacing(6)
                grid.setVerticalSpacing(6)
                panel.setLayout(grid)
                setattr(progress, "_action_button_panel", panel)
                setattr(progress, "_action_button_panel_grid", grid)
            except Exception:
                return None, None

        # パネルの再配置（標準ボタンと重ならないように）
        def _reposition_panel() -> None:
            try:
                if panel is None:
                    return
                margin = 10
                width = max(0, int(progress.width()) - margin * 2)
                if width <= 0:
                    return

                # 標準キャンセル/確認ボタン（progress直下）を探し、その上にパネルを置く
                bottom_limit = int(progress.height()) - margin
                try:
                    from qt_compat.widgets import QPushButton

                    for b in progress.findChildren(QPushButton):
                        try:
                            if b is None or b is button:
                                continue
                            if b.parent() is not progress:
                                continue
                            if not b.isVisible():
                                continue
                            if bool(b.property("_is_action_button")):
                                continue
                            g = b.geometry()
                            if g.isValid() and g.height() > 0:
                                bottom_limit = min(bottom_limit, int(g.top()) - 6)
                        except Exception:
                            continue
                except Exception:
                    pass

                try:
                    panel.adjustSize()
                    panel_h = int(panel.sizeHint().height())
                except Exception:
                    panel_h = 0
                panel_h = max(panel_h, 0)
                y = max(margin, int(bottom_limit) - panel_h)
                panel.setGeometry(margin, y, width, panel_h)
                panel.raise_()
            except Exception:
                return

        try:
            mgr = getattr(progress, "_action_button_panel_manager", None)
        except Exception:
            mgr = None

        if mgr is None:
            class _PanelManager(QObject):
                def eventFilter(self, watched, event):
                    try:
                        et = event.type()
                        if et in (QEvent.Show, QEvent.Resize, QEvent.LayoutRequest):
                            QTimer.singleShot(0, _reposition_panel)
                    except Exception:
                        pass
                    return False

            try:
                mgr = _PanelManager(progress)
                progress.installEventFilter(mgr)
                setattr(progress, "_action_button_panel_manager", mgr)
            except Exception:
                mgr = None

        try:
            QTimer.singleShot(0, _reposition_panel)
        except Exception:
            _reposition_panel()

        return panel, grid

    panel, grid = _ensure_panel()
    if panel is None or grid is None:
        try:
            button.setVisible(False)
        except Exception:
            pass
        return True

    # アクションボタンであることを識別し、標準ボタン判定から除外
    try:
        button.setProperty("_is_action_button", True)
    except Exception:
        pass

    try:
        button.setParent(panel)
    except Exception:
        pass
    try:
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    except Exception:
        pass

    try:
        count = int(grid.count())
        max_cols = 2
        row = count // max_cols
        col = count % max_cols
        grid.addWidget(button, row, col)
        grid.activate()
    except Exception:
        return False

    try:
        panel.show()
        panel.raise_()
    except Exception:
        pass

    try:
        progress.adjustSize()
        progress.updateGeometry()
    except Exception:
        pass

    return True

    if not require_confirmation:
        # 一括登録側は「確認」を出さず、短時間で閉じる（呼び出し元でcloseする場合もある）
        try:
            QTimer.singleShot(800, progress.close)
        except Exception:
            pass


def _resolve_parent_widget(parent):
    """通常登録のダイアログ親ウィンドウを解決する。

    呼び出し元が parent=None の場合、参照切れでダイアログが勝手に閉じることがあるため、
    可能ならアクティブウィンドウを親として採用する。
    """

    if parent is not None:
        return parent
    try:
        from qt_compat.widgets import QApplication

        app = QApplication.instance()
        if app is not None:
            active = app.activeWindow()
            if active is not None:
                return active
    except Exception:
        pass
    return None
from copy import deepcopy
from qt_compat.widgets import QMessageBox, QFileDialog
from qt_compat.core import QCoreApplication
from config.common import OUTPUT_RDE_DIR, INPUT_DIR
from classes.utils.api_request_helper import api_request, post_form, post_binary  # refactored to use api_request_helper
from core.bearer_token_manager import BearerTokenManager
from config.common import get_dynamic_file_path
# ロガー設定
logger = logging.getLogger(__name__)


def select_and_save_files_to_temp(parent=None) -> list[str]:
    """ファイル選択ダイアログで選択したファイルを一時フォルダへコピーして返す。"""

    import shutil

    files, _ = QFileDialog.getOpenFileNames(parent, "登録するファイルを選択", "", "すべてのファイル (*)")
    if not files:
        return []

    temp_dir = tempfile.mkdtemp(prefix="rde_upload_")
    temp_file_paths: list[str] = []
    for src_path in files:
        filename = os.path.basename(src_path)
        dst_path = os.path.join(temp_dir, filename)
        shutil.copy2(src_path, dst_path)
        temp_file_paths.append(dst_path)
    return temp_file_paths

def run_data_register_logic(
    parent=None,
    bearer_token=None,
    dataset_info=None,
    form_values=None,
    file_paths=None,
    attachment_paths=None,
    *,
    parallel_upload_workers: int = 5,
):
    """データ登録ボタン押下時のロジック（ファイル選択・一時保存付き）"""
    try:
        parent = _resolve_parent_widget(parent)
        # Bearer Token統一管理システムで取得
        if not bearer_token:
            bearer_token = BearerTokenManager.get_token_with_relogin_prompt(parent)
            if not bearer_token:
                logger.error("Bearer Tokenが取得できません。ログインを確認してください")
                QMessageBox.warning(parent, "認証エラー", "Bearer Tokenが取得できません。ログインを確認してください。")
                return
        
        # file_pathsが指定されていればそれを使う。なければ従来通りファイル選択ダイアログを出す
        if file_paths is not None:
            temp_file_paths = file_paths
        else:
            temp_file_paths = select_and_save_files_to_temp(parent)
            if not temp_file_paths:
                logger.info("ファイルが選択されませんでした")
                return
        logger.info(f"一時フォルダに保存: {temp_file_paths}")

        # 添付ファイルパス
        temp_attachment_paths = attachment_paths if attachment_paths else []

        # dataset_infoの検証
        logger.debug(f"dataset_info検証: type={type(dataset_info)}, value={dataset_info}")
        if dataset_info is None:
            logger.error("dataset_infoがNoneです。データセット選択が正しく動作していません")
            QMessageBox.critical(parent, "データセット未選択", "データセット情報がUIから渡されていません。\nドロップダウンの生成・選択処理・itemDataの設定を確認してください。")
            return
        if not isinstance(dataset_info, dict):
            logger.error(f"dataset_infoの型がdictではありません: {type(dataset_info)}")
            QMessageBox.critical(parent, "データセット情報エラー", f"データセット情報の型が不正です: {type(dataset_info)}\n値: {dataset_info}")
            return

        # payloadプレビュー用の仮データFilesを作成
        dataFiles_preview = {"data": [{"type": "upload", "id": os.path.basename(p)} for p in temp_file_paths]}
        # attachments_previewはアップロードIDが確定するまで空でOK（プレビュー時はファイル名のみ）
        attachments_preview = [{"uploadId": None, "description": os.path.basename(p)} for p in temp_attachment_paths]
        
        # データ登録処理の続行
        _continue_data_register_process(
            parent,
            bearer_token,
            dataset_info,
            form_values,
            temp_file_paths,
            temp_attachment_paths,
            dataFiles_preview,
            attachments_preview,
            parallel_upload_workers=parallel_upload_workers,
        )
        
    except Exception as e:
        logger.error(f"データ登録処理中にエラーが発生: {e}")
        if parent:
            QMessageBox.critical(parent, "データ登録エラー", f"データ登録処理中にエラーが発生しました: {e}")

def _continue_data_register_process(
    parent,
    bearer_token,
    dataset_info,
    form_values,
    temp_file_paths,
    temp_attachment_paths,
    dataFiles_preview,
    attachments_preview,
    *,
    parallel_upload_workers: int = 5,
):
    """データ登録処理の継続部分"""
    try:
        # dataset_infoから必要な値を抽出。初期値を必ず宣言
        datasetId = "a74b58c0-9907-40e7-a261-a75519730d82"
        dataOwnerId = "03b8fc123d0a67ba407dd2f06fe49768d9cbddca6438366632366466"
        instrumentId = "db16a466-1245-46f8-947a-4884633471a1"
        ownerId = dataOwnerId
        
        if dataset_info and isinstance(dataset_info, dict):
            datasetId = dataset_info.get('id', datasetId)
            relationships = dataset_info.get('relationships', {})
            attr = dataset_info.get('attributes', {})
            ownerId_candidate = None
            manager = relationships.get('manager', {}).get('data', {})
            if isinstance(manager, dict) and manager.get('id'):
                ownerId_candidate = manager.get('id')
            if not ownerId_candidate:
                applicant = relationships.get('applicant', {}).get('data', {})
                if isinstance(applicant, dict) and applicant.get('id'):
                    ownerId_candidate = applicant.get('id')
            if not ownerId_candidate:
                data_owners = relationships.get('dataOwners', {}).get('data', [])
                if isinstance(data_owners, list) and len(data_owners) > 0 and isinstance(data_owners[0], dict):
                    ownerId_candidate = data_owners[0].get('id')
            if not ownerId_candidate:
                ownerId_candidate = attr.get('ownerId') or attr.get('userId')
            if ownerId_candidate:
                dataOwnerId = ownerId_candidate
                ownerId = ownerId_candidate
            instrumentId_candidate = None
            instruments = relationships.get('instruments', {}).get('data', [])
            if isinstance(instruments, list) and len(instruments) > 0 and isinstance(instruments[0], dict):
                instrumentId_candidate = instruments[0].get('id')
            if instrumentId_candidate:
                instrumentId = instrumentId_candidate
        dataName = form_values.get('dataName') if form_values else None
        basicDescription = form_values.get('basicDescription') if form_values else None
        experimentId = form_values.get('experimentId') if form_values else None
        sampleDescription = form_values.get('sampleDescription') if form_values else None
        sampleComposition = form_values.get('sampleComposition') if form_values else None
        sampleReferenceUrl = form_values.get('sampleReferenceUrl') if form_values else None
        sampleTags = form_values.get('sampleTags') if form_values else None
        sampleNames = form_values.get('sampleNames') if form_values else ["試料名(ローカルID)"]
        relatedSamples = form_values.get('relatedSamples') if form_values else []
        hideOwner = form_values.get('hideOwner') if form_values else None
        ownerId_from_form = form_values.get('ownerId') if form_values else None
        if ownerId_from_form:
            ownerId = ownerId_from_form
        
        if isinstance(sampleTags, list):
            tags_list = sampleTags
        elif isinstance(sampleTags, str):
            tags_list = [t.strip() for t in sampleTags.split(',')] if sampleTags else None
        else:
            tags_list = None

        if isinstance(sampleNames, list):
            names_list = sampleNames
        elif isinstance(sampleNames, str):
            names_list = [n.strip() for n in sampleNames.split(',')] if sampleNames else ["試料名(ローカルID)"]
        else:
            names_list = ["試料名(ローカルID)"]
        # カスタム欄（スキーマフォーム）の値をpayloadに反映
        custom_values = form_values.get('custom') if form_values and 'custom' in form_values else {}
        
        # custom_valuesが空の辞書の場合、null値を含むフィールドがあるか確認
        if not custom_values:
            # form_valuesからcustom_valuesキーを直接取得してみる
            custom_values = form_values.get('custom_values', {}) if form_values else {}
            logger.debug("プレビュー - customが空のためcustom_valuesを取得: %s", custom_values)
        preview_payload = {
            "data": {
                "type": "entry",
                "attributes": {
                    "invoice": {
                        "datasetId": datasetId,
                        "basic": {
                            "dataOwnerId": dataOwnerId,
                            "dataName": dataName or "データ名",
                            "instrumentId": instrumentId,
                            "description": basicDescription or "説明",
                            "experimentId": experimentId or "basic/experimentId"
                        },
                        "custom": custom_values,
                        "sample": {
                            "description": sampleDescription or "試料の説明",
                            "composition": sampleComposition or "化学式・組成式・分子式",
                            "referenceUrl": sampleReferenceUrl or "",
                            "hideOwner": hideOwner,
                            "names": names_list,
                            "relatedSamples": relatedSamples,
                            "tags": tags_list,
                            "generalAttributes": None,
                            "specificAttributes": None,
                            "ownerId": ownerId
                        }
                    }
                },
                "relationships": {
                    "dataFiles": dataFiles_preview
                }
            },
            "meta": {
                "attachments": attachments_preview
            }
        }
    except Exception as e:
        preview_payload = {"error": str(e)}

    # ファイル数・合計サイズ
    file_count = len(temp_file_paths)
    file_total_size = sum(os.path.getsize(p) for p in temp_file_paths)
    file_total_size_mb = file_total_size / (1024*1024)
    attachment_count = len(temp_attachment_paths)
    attachment_total_size = sum(os.path.getsize(p) for p in temp_attachment_paths) if temp_attachment_paths else 0
    attachment_total_size_mb = attachment_total_size / (1024*1024) if temp_attachment_paths else 0

    # 確認ウインドウ
    from qt_compat.widgets import QMessageBox, QPushButton, QDialog, QVBoxLayout, QTextEdit
    msg_box = QMessageBox(parent)
    msg_box.setWindowTitle("データ登録内容の確認")
    msg_box.setIcon(QMessageBox.Question)
    msg_box.setText(f"本当にデータ登録を実行しますか？\n\nファイル数: {file_count}\n合計サイズ: {file_total_size_mb:.2f} MB\n添付ファイル数: {attachment_count}\n添付合計サイズ: {attachment_total_size_mb:.2f} MB\n\nこの操作はRDEに新規エントリーを作成します。")
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
        text_edit.setPlainText(json.dumps(preview_payload, ensure_ascii=False, indent=2))
        text_edit.setMinimumSize(600, 400)
        layout.addWidget(text_edit)
        dlg.setLayout(layout)
        dlg.exec()
    detail_btn.clicked.connect(show_detail)

    reply = msg_box.exec()
    if msg_box.clickedButton() != yes_btn:
        logger.info("データ登録処理はユーザーによりキャンセルされました。")
        return

    # --- ここからアップロード処理（プログレスバー付き） ---
    from qt_compat.widgets import QProgressDialog
    from qt_compat.core import Qt, QCoreApplication
    import time
    from net.http_helpers import parallel_upload

    total_files = len(temp_file_paths) + len(temp_attachment_paths)
    dataFiles = {"data": []}
    attachments = []
    flagUploadSuccess = True
    numberUploaded = 0
    succesedUploads = []
    failedUploads = []
    progress = QProgressDialog("ファイルアップロード中...", "キャンセル", 0, total_files, parent)
    progress.setWindowTitle("アップロード進捗")
    progress.setWindowModality(Qt.WindowModal)
    progress.setAutoClose(False)
    progress.setAutoReset(False)
    progress.setMinimumDuration(0)
    progress.setValue(0)
    # 完了時に「確認」ボタンとして確実に表示するため、cancelボタン自体は保持しつつ非表示にする
    try:
        from qt_compat.widgets import QPushButton

        hidden_btn = QPushButton("")
        hidden_btn.setVisible(False)
        progress.setCancelButton(hidden_btn)
        setattr(progress, "_hidden_cancel_button", hidden_btn)
    except Exception:
        try:
            progress.setCancelButtonText("")
        except Exception:
            pass
    try:
        progress.setWindowFlags(progress.windowFlags() | Qt.WindowStaysOnTopHint)
    except Exception:
        pass
    progress.show()
    try:
        _center_on_screen(progress)
    except Exception:
        pass
    try:
        progress.raise_()
        progress.activateWindow()
    except Exception:
        pass
    try:
        if parent is not None:
            setattr(parent, "_data_register_progress_dialog", progress)
    except Exception:
        pass
    QCoreApplication.processEvents()
    # datasetId を確定
    datasetId = None
    if dataset_info and isinstance(dataset_info, dict):
        datasetId = dataset_info.get('id')
    if not datasetId:
        datasetId = "a74b58c0-9907-40e7-a261-a75519730d82"  # fallback

    try:
        max_workers = max(1, int(parallel_upload_workers))
    except Exception:
        max_workers = 5

    def upload_worker(idx: int, path: str) -> dict:
        filename = os.path.basename(path)
        uploadId = upload_file(bearer_token, datasetId, path)
        if uploadId:
            return {"status": "success", "idx": idx, "path": path, "filename": filename, "uploadId": uploadId}
        return {"status": "failed", "idx": idx, "path": path, "filename": filename, "error": "uploadId が取得できませんでした"}

    def _make_progress_callback(start_offset: int, group_total: int):
        def _cb(current: int, total: int, message: str) -> bool:
            if group_total <= 0:
                return True
            try:
                done_in_group = int((current / 100) * group_total)
                progress.setValue(min(total_files, start_offset + done_in_group))
                progress.setLabelText(f"{message}\n({min(total_files, start_offset + done_in_group)}/{total_files})")
                QCoreApplication.processEvents()
            except Exception:
                pass
            return not progress.wasCanceled()

        return _cb

    # データファイル（並列）
    data_tasks = [(idx, path) for idx, path in enumerate(temp_file_paths)]
    if data_tasks:
        progress.setLabelText("並列アップロード準備中... (データファイル)")
        QCoreApplication.processEvents()
        data_result = parallel_upload(
            data_tasks,
            upload_worker,
            max_workers=max_workers,
            progress_callback=_make_progress_callback(start_offset=0, group_total=len(data_tasks)),
            threshold=2,
            collect_results=True,
        )
        if data_result.get("cancelled"):
            logger.info("アップロードがキャンセルされました。")
            return

        data_items = [r.get("result") for r in data_result.get("results", []) if isinstance(r, dict)]
        data_items = [d for d in data_items if isinstance(d, dict)]
        for item in sorted(data_items, key=lambda d: d.get("idx", 0)):
            if item.get("status") == "success":
                uploadId = item.get("uploadId")
                if uploadId:
                    dataFiles["data"].append({"type": "upload", "id": uploadId})
                    succesedUploads.append(uploadId)
                    numberUploaded += 1
            else:
                failedUploads.append(item.get("filename") or os.path.basename(item.get("path") or ""))
                flagUploadSuccess = False

    # 添付ファイル（並列）
    attach_tasks = [(idx, path) for idx, path in enumerate(temp_attachment_paths)]
    if attach_tasks:
        progress.setLabelText("並列アップロード準備中... (添付ファイル)")
        QCoreApplication.processEvents()
        attach_result = parallel_upload(
            attach_tasks,
            upload_worker,
            max_workers=max_workers,
            progress_callback=_make_progress_callback(start_offset=len(data_tasks), group_total=len(attach_tasks)),
            threshold=2,
            collect_results=True,
        )
        if attach_result.get("cancelled"):
            logger.info("アップロードがキャンセルされました。")
            return

        attach_items = [r.get("result") for r in attach_result.get("results", []) if isinstance(r, dict)]
        attach_items = [d for d in attach_items if isinstance(d, dict)]
        for item in sorted(attach_items, key=lambda d: d.get("idx", 0)):
            if item.get("status") == "success":
                uploadId = item.get("uploadId")
                filename = item.get("filename")
                if uploadId and filename:
                    attachments.append({"uploadId": uploadId, "description": filename})
            else:
                failedUploads.append(item.get("filename") or os.path.basename(item.get("path") or ""))
                flagUploadSuccess = False

    progress.setValue(total_files)
    progress.setValue(total_files)
    progress.setLabelText("アップロード完了")
    QCoreApplication.processEvents()
    logger.info("アップロード完了: %s", dataFiles)
    if numberUploaded == 0 and not attachments:
        logger.error("アップロードされたファイルがありません。")
        return
    if not flagUploadSuccess:
        logger.error("アップロードに失敗したファイルがあります。")
        logger.debug("失敗したファイル: %s", failedUploads)
        logger.debug("エントリー作成を中止します。")
        if progress:
            text = _build_data_register_completion_text(
                success=False,
                upload_total=total_files,
                upload_success_data_files=numberUploaded,
                upload_success_attachments=len(attachments),
                failed_files=failedUploads,
                detail="アップロードに失敗したため、登録を中止しました。",
            )
            _finalize_progress_dialog(progress, title="アップロード失敗", text=text)
        return
    
    # アップロード後もプログレスバーを維持し、エントリー本体POSTまで進捗表示
    progress.setLabelText("エントリー登録バリデーション中...")
    QCoreApplication.processEvents()
    if progress:
        try:
            setattr(
                progress,
                "_upload_summary",
                {
                    "upload_total": total_files,
                    "upload_success_data_files": numberUploaded,
                    "upload_success_attachments": len(attachments),
                    "failed_files": list(failedUploads),
                },
            )
        except Exception:
            pass

    entry_result = entry_data(
        bearer_token, dataFiles, attachements=attachments, dataset_info=dataset_info, form_values=form_values, progress=progress
    )
    
    # エントリー登録結果の処理
    if entry_result.get("success"):
        logger.info("データ登録が正常に完了しました")
        # 成功メッセージは entry_data 関数内で進捗ダイアログへ表示済み
    else:
        error_type = entry_result.get("error", "unknown")
        error_detail = entry_result.get("detail", "詳細不明")
        logger.error(f"データ登録に失敗: {error_type} - {error_detail}")
        # エラーメッセージは entry_data 関数内で進捗ダイアログへ表示済み
    # progress.close() は entry_data 内でのみ呼ぶ


import re
def entry_data(
    bearer_token,
    dataFiles,
    attachements=[],
    dataset_info=None,
    form_values=None,
    progress=None,
    require_confirmation: bool = True,
):
    """
    エントリー作成
    """
    output_dir=get_dynamic_file_path('output/rde/data')
    # 注意: Bearer Tokenは不要（API呼び出し時に自動選択される）
    # 古いチェックを削除: if not bearer_token: return
    
    url = "https://rde-entry-api-arim.nims.go.jp/entries"
    url_validation="https://rde-entry-api-arim.nims.go.jp/entries?validationOnly=true"
    # attachementsはrun_data_register_logicから渡されたアップロード結果のみを使う
    # dataset_infoから必要な値を抽出。初期値を必ず宣言
    datasetId = "a74b58c0-9907-40e7-a261-a75519730d82"
    dataOwnerId = "03b8fc123d0a67ba407dd2f06fe49768d9cbddca6438366632366466"
    instrumentId = "db16a466-1245-46f8-947a-4884633471a1"
    ownerId = dataOwnerId
    if dataset_info and isinstance(dataset_info, dict):
        datasetId = dataset_info.get('id', datasetId)
        # dataOwnerId: manager, applicant, dataOwners, ownerId, userIdの順で取得
        relationships = dataset_info.get('relationships', {})
        attr = dataset_info.get('attributes', {})
        ownerId_candidate = None
        manager = relationships.get('manager', {}).get('data', {})
        if isinstance(manager, dict) and manager.get('id'):
            ownerId_candidate = manager.get('id')
        if not ownerId_candidate:
            applicant = relationships.get('applicant', {}).get('data', {})
            if isinstance(applicant, dict) and applicant.get('id'):
                ownerId_candidate = applicant.get('id')
        if not ownerId_candidate:
            data_owners = relationships.get('dataOwners', {}).get('data', [])
            if isinstance(data_owners, list) and len(data_owners) > 0 and isinstance(data_owners[0], dict):
                ownerId_candidate = data_owners[0].get('id')
        if not ownerId_candidate:
            ownerId_candidate = attr.get('ownerId') or attr.get('userId')
        if ownerId_candidate:
            dataOwnerId = ownerId_candidate
            ownerId = ownerId_candidate
        # instrumentId: relationships.instruments.data[0].id
        instrumentId_candidate = None
        instruments = relationships.get('instruments', {}).get('data', [])
        if isinstance(instruments, list) and len(instruments) > 0 and isinstance(instruments[0], dict):
            instrumentId_candidate = instruments[0].get('id')
        if instrumentId_candidate:
            instrumentId = instrumentId_candidate

    # --- フォーム値反映 ---
    dataName = form_values.get('dataName') if form_values else None
    basicDescription = form_values.get('basicDescription') if form_values else None
    experimentId = form_values.get('experimentId') if form_values else None
    sampleDescription = form_values.get('sampleDescription') if form_values else None
    sampleComposition = form_values.get('sampleComposition') if form_values else None
    sampleReferenceUrl = form_values.get('sampleReferenceUrl') if form_values else None
    sampleTags = form_values.get('sampleTags') if form_values else None
    sampleNames = form_values.get('sampleNames') if form_values else None
    relatedSamples = form_values.get('relatedSamples') if form_values else []
    hideOwner = form_values.get('hideOwner') if form_values else None
    ownerId_from_form = form_values.get('ownerId') if form_values else None
    if ownerId_from_form:
        ownerId = ownerId_from_form
    
    # データ所有者（所属）の反映
    dataOwnerId_from_form = form_values.get('dataOwnerId') if form_values else None
    if dataOwnerId_from_form:
        dataOwnerId = dataOwnerId_from_form

    sample_id = form_values.get('sampleId') if form_values else None
    logger.info(f"DEBUG: sample_id from form_values = {sample_id}")  # デバッグログ追加

    # experimentIdバリデーション（半角英数記号のみ）
    if experimentId and not re.fullmatch(r'[\w\-\.\/:;#@\[\]\(\)\{\}\!\$%&\*\+=\?\^\|~<>,]*', experimentId):
        print("[ERROR] experimentIdは半角英数記号のみです。: ", experimentId)
        QMessageBox.warning(None, "入力エラー", "experimentIdは半角英数記号のみで入力してください。")
        return

    # tags, namesはカンマ区切りでリスト化
    if isinstance(sampleTags, list):
        tags_list = sampleTags
    elif isinstance(sampleTags, str):
        tags_list = [t.strip() for t in sampleTags.split(',')] if sampleTags else None
    else:
        tags_list = None

    if isinstance(sampleNames, list):
        names_list = sampleNames
    elif isinstance(sampleNames, str):
        names_list = [n.strip() for n in sampleNames.split(',')] if sampleNames else []
    else:
        names_list = []

    # カスタム欄（スキーマフォーム）の値をpayloadに反映
    custom_values = form_values.get('custom') if form_values and 'custom' in form_values else {}
    
    # custom_valuesが空の辞書の場合、null値を含むフィールドがあるか確認
    if not custom_values:
        # form_valuesからcustom_valuesキーを直接取得してみる
        custom_values = form_values.get('custom_values', {}) if form_values else {}
        logger.debug("正式登録 - customが空のためcustom_valuesを取得: %s", custom_values)

    if not sample_id:
        payload_detail_sample = {
                            "description": sampleDescription or "",
                            "composition": sampleComposition or "",
                            "referenceUrl": sampleReferenceUrl or "",
                            "hideOwner": hideOwner,
                            "names": names_list,
                            "relatedSamples": relatedSamples,
                            "tags": tags_list,
                            "generalAttributes": None,
                            "specificAttributes": None,
                            "ownerId": ownerId
                        }
    else:
        payload_detail_sample = {"sampleId": sample_id}

    payload = {
        "data": {
            "type": "entry",
            "attributes": {
                "invoice": {
                    "datasetId": datasetId,
                    "basic": {
                        "dataOwnerId": dataOwnerId,
                        "dataName": dataName or "データ名",
                        "instrumentId": instrumentId,
                        "description": basicDescription or "説明",
                        "experimentId": experimentId or "basic/experimentId"
                    },
                    "custom": custom_values,
                    "sample": payload_detail_sample
                }
            },
            "relationships": {
                "dataFiles": dataFiles
            }
        },
        "meta": {
            "attachments": attachements
        }
    }
    # Authorizationヘッダーは削除（api_request内で自動選択）
    headers = {
        "Accept": "application/vnd.api+json",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Content-Type": "application/vnd.api+json",
        "Host": "rde-entry-api-arim.nims.go.jp",
        "Origin": "https://rde-entry-arim.nims.go.jp",
        "Referer": "https://rde-entry-arim.nims.go.jp/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

    print (f"headers: {headers}")
    print (f"payload: {payload}")
    from qt_compat.core import QCoreApplication

    def _store_http_response(*, key: str, method: str, url: str, resp: object | None, error: str | None = None, note: str | None = None) -> None:
        if not progress:
            return
        try:
            store = getattr(progress, "_last_http_responses", None)
            if not isinstance(store, dict):
                store = {}
                setattr(progress, "_last_http_responses", store)
        except Exception:
            return

        info: dict[str, object] = {"method": method, "url": url}
        if error:
            info["error"] = str(error)
        if note:
            info["note"] = str(note)
        if resp is None:
            store[key] = info
            return
        try:
            status_code = getattr(resp, "status_code", None)
            reason = getattr(resp, "reason", None)
            if status_code is not None:
                info["status"] = int(status_code)
            if reason is not None:
                info["reason"] = str(reason)
        except Exception:
            pass
        try:
            text = getattr(resp, "text", None)
            if isinstance(text, str) and text:
                if len(text) > 20000:
                    info["body"] = text[:20000] + "\n... (truncated)"
                else:
                    info["body"] = text
        except Exception:
            pass
        store[key] = info

    def _format_elapsed(seconds: float) -> str:
        try:
            s = max(0, int(seconds))
        except Exception:
            s = 0
        h = s // 3600
        m = (s % 3600) // 60
        sec = s % 60
        if h > 0:
            return f"{h:02d}:{m:02d}:{sec:02d}"
        return f"{m:02d}:{sec:02d}"

    def _run_post_entries_with_spinner(*, timeout_sec: int) -> tuple[object | None, str | None, dict | None]:
        """POST /entries をUIを止めずに実行し、応答待ち中はスピナー+経過時間を表示する。

        Returns:
            (resp, error_text, forced_result)
        """

        if not progress:
            # progressが無い場合は同期実行（従来通り）
            try:
                r = api_request("POST", url, bearer_token=None, headers=headers, json_data=payload, timeout=timeout_sec)
                return r, None, None
            except Exception as exc:
                return None, str(exc), None

        from qt_compat.core import QThread, QTimer, QEventLoop
        import time

        # 既存の進捗レンジを退避（完了時に戻す）
        try:
            prev_min = int(progress.minimum())
            prev_max = int(progress.maximum())
        except Exception:
            prev_min, prev_max = 0, 0

        started_at = time.monotonic()
        base_msg = "エントリー登録中…（サーバー応答待ち）"
        hint_msg = "10秒以上応答がない場合は「応答待ちを停止」で登録状況を確認できます。"

        # スピナー表示（無限進捗）
        try:
            progress.setRange(0, 0)
        except Exception:
            pass

        label_mode = {"mode": "spinner"}  # spinner / checking / choice

        def _update_label():
            try:
                if label_mode.get("mode") != "spinner":
                    return
            except Exception:
                pass
            elapsed = _format_elapsed(time.monotonic() - started_at)
            try:
                show_hint = (time.monotonic() - started_at) >= 10
            except Exception:
                show_hint = False
            try:
                if show_hint:
                    progress.setLabelText(f"{base_msg}\n{hint_msg}\n経過: {elapsed}")
                else:
                    progress.setLabelText(f"{base_msg}\n経過: {elapsed}")
            except Exception:
                pass

        _update_label()
        QCoreApplication.processEvents()

        timer = QTimer(progress)
        timer.setInterval(250)
        timer.timeout.connect(_update_label)
        timer.start()

        forced_result: dict | None = None

        status_thread = None

        # 「強制完了/待機継続/ブラウザで開く」ボタン（必要時のみ表示）
        force_finish_btn = None
        continue_wait_btn = None
        open_entry_btn = None
        status_info = {"entry": None, "link_url": None, "status": None, "state": None}

        # 10秒経過で「応答待ちを停止」ボタンを表示
        stop_btn = None
        stop_btn_added = False
        try:
            from qt_compat.widgets import QPushButton
            from classes.utils.button_styles import get_button_style

            stop_btn = QPushButton("応答待ちを停止", progress)
            stop_btn.setVisible(False)
            try:
                stop_btn.setStyleSheet(get_button_style('warning'))
            except Exception:
                pass
            stop_btn_added = _add_action_button_to_progress(progress, stop_btn)
        except Exception:
            stop_btn = None

        def _set_stop_button_label_for_mode() -> None:
            if stop_btn is None:
                return
            try:
                mode = label_mode.get("mode")
            except Exception:
                mode = None
            try:
                # 4ボタン表示（choice）時は「応答待ちを停止」が紛らわしいため、
                # スピナー表示へ戻す動作に合わせて文言を切り替える。
                if mode == "choice":
                    stop_btn.setText("応答待ちを続ける")
                else:
                    stop_btn.setText("応答待ちを停止")
                stop_btn.adjustSize()
            except Exception:
                return

        def _show_stop_button():
            if stop_btn is None:
                return
            try:
                stop_btn.setVisible(True)
                stop_btn.setEnabled(True)
                try:
                    progress.adjustSize()
                    progress.updateGeometry()
                except Exception:
                    pass
            except Exception:
                pass

        try:
            QTimer.singleShot(10_000, _show_stop_button)
        except Exception:
            pass

        class _ApiThread(QThread):
            def __init__(self):
                super().__init__()
                self.resp = None
                self.err = None

            def run(self):
                try:
                    self.resp = api_request(
                        "POST",
                        url,
                        bearer_token=None,
                        headers=headers,
                        json_data=payload,
                        timeout=timeout_sec,
                    )
                except Exception as exc:
                    self.err = str(exc)

        th = _ApiThread()
        loop = QEventLoop()
        th.finished.connect(loop.quit)
        th.start()

        def _hide_action_buttons() -> None:
            for btn in (force_finish_btn, continue_wait_btn, open_entry_btn):
                try:
                    if btn is not None:
                        btn.setVisible(False)
                except Exception:
                    pass
            _set_stop_button_label_for_mode()

        def _show_action_buttons() -> None:
            for btn in (force_finish_btn, continue_wait_btn, open_entry_btn):
                try:
                    if btn is not None:
                        btn.setVisible(True)
                        btn.setEnabled(True)
                except Exception:
                    pass
            _set_stop_button_label_for_mode()
            try:
                progress.adjustSize()
                progress.updateGeometry()
            except Exception:
                pass

        def _ensure_action_buttons() -> None:
            nonlocal force_finish_btn, continue_wait_btn, open_entry_btn
            if progress is None:
                return
            if force_finish_btn is not None and continue_wait_btn is not None and open_entry_btn is not None:
                return
            try:
                from qt_compat.widgets import QPushButton
                from classes.utils.button_styles import get_button_style

                if open_entry_btn is None:
                    open_entry_btn = QPushButton("該当エントリをブラウザで開く", progress)
                    try:
                        open_entry_btn.setStyleSheet(get_button_style('primary'))
                    except Exception:
                        pass
                    open_entry_btn.setVisible(False)
                    if not _add_action_button_to_progress(progress, open_entry_btn):
                        open_entry_btn = None

                if force_finish_btn is None:
                    force_finish_btn = QPushButton("強制完了して閉じる", progress)
                    try:
                        force_finish_btn.setStyleSheet(get_button_style('danger'))
                    except Exception:
                        pass
                    force_finish_btn.setVisible(False)
                    if not _add_action_button_to_progress(progress, force_finish_btn):
                        force_finish_btn = None

                if continue_wait_btn is None:
                    continue_wait_btn = QPushButton("タイムアウトまで待つ", progress)
                    try:
                        continue_wait_btn.setStyleSheet(get_button_style('secondary'))
                    except Exception:
                        pass
                    continue_wait_btn.setVisible(False)
                    if not _add_action_button_to_progress(progress, continue_wait_btn):
                        continue_wait_btn = None
            except Exception:
                return

        def _try_force_finish_by_status_check():
            nonlocal forced_result
            if progress is None:
                return

            # スピナーの自動更新が status 表示を上書きしてしまうため、ここからは停止
            try:
                label_mode["mode"] = "checking"
            except Exception:
                pass
            try:
                if timer is not None:
                    timer.stop()
            except Exception:
                pass

            _ensure_action_buttons()
            _hide_action_buttons()

            try:
                progress.setLabelText(
                    "登録状況を確認中…\n"
                    "サーバー側で処理が継続している可能性があります。"
                )
                QCoreApplication.processEvents()
            except Exception:
                pass

            nonlocal status_thread
            try:
                if status_thread is not None:
                    try:
                        setattr(status_thread, "_cancelled", True)
                    except Exception:
                        pass
            except Exception:
                pass

            class _StatusThread(QThread):
                def __init__(self):
                    super().__init__()
                    self.match_obj = None
                    self.err = None
                    self.attempts = 0
                    self._cancelled = False

                def run(self):
                    import time as _time
                    try:
                        from classes.data_entry.core import registration_status_service as regsvc
                        from classes.data_entry.core.registration_status_matcher import find_registration_status_match

                        max_attempts = 5
                        for i in range(max_attempts):
                            if getattr(self, "_cancelled", False):
                                return
                            self.attempts = i + 1
                            latest = regsvc.fetch_latest(limit=100, use_cache=False)
                            match_obj = find_registration_status_match(
                                latest,
                                data_name=str(target_data_name or '').strip(),
                                dataset_name=(str(target_dataset_name).strip() if target_dataset_name else None),
                                near_time_utc=post_started_at_utc,
                            )
                            if getattr(match_obj, "entry", None):
                                self.match_obj = match_obj
                                return
                            _time.sleep(2.0)
                    except Exception as exc:
                        self.err = str(exc)

            status_thread = _StatusThread()

            def _on_status_finished():
                try:
                    if getattr(status_thread, "_cancelled", False):
                        return
                except Exception:
                    pass

                try:
                    err = getattr(status_thread, "err", None)
                    match_obj = getattr(status_thread, "match_obj", None)
                    attempts = int(getattr(status_thread, "attempts", 0) or 0)
                except Exception:
                    err, match_obj, attempts = None, None, 0

                if err:
                    try:
                        progress.setLabelText(
                            f"{base_msg}\n"
                            "登録状況の自動照会に失敗しました。\n"
                            "このまま応答待ちを継続します。\n\n"
                            f"詳細: {err}\n"
                            f"経過: {_format_elapsed(time.monotonic() - started_at)}"
                        )
                        QCoreApplication.processEvents()
                    except Exception:
                        pass
                    try:
                        label_mode["mode"] = "spinner"
                        timer.start()
                    except Exception:
                        pass
                    return

                match_entry = getattr(match_obj, "entry", None) if match_obj is not None else None
                if not match_entry:
                    try:
                        progress.setLabelText(
                            f"{base_msg}\n"
                            "登録状況(最新100件)に該当するエントリが見つかりませんでした。\n"
                            "反映遅延の可能性があるため、このまま応答待ちを継続します。\n"
                            f"（再試行: {attempts}/5）\n"
                            f"{hint_msg}\n"
                            f"経過: {_format_elapsed(time.monotonic() - started_at)}"
                        )
                        QCoreApplication.processEvents()
                    except Exception:
                        pass
                    try:
                        label_mode["mode"] = "spinner"
                        timer.start()
                    except Exception:
                        pass
                    return

                entry_id = (match_entry or {}).get('id')
                link_url = (
                    f"https://rde-entry-arim.nims.go.jp/data-entry/datasets/entries/{entry_id}" if entry_id else None
                )
                status = str((match_entry or {}).get('status') or '').strip().lower()
                try:
                    status_info.update({"entry": match_entry, "link_url": link_url, "status": status, "state": getattr(match_obj, "state", None)})
                except Exception:
                    pass

                status_line = f"status: {status or '(不明)'}"
                if status == 'failed' or getattr(match_obj, "state", None) == 'failed':
                    head = "登録は失敗している可能性があります。"
                else:
                    head = "登録は完了している/進行中である可能性があります。"

                try:
                    label_mode["mode"] = "choice"
                except Exception:
                    pass

                _set_stop_button_label_for_mode()

                try:
                    progress.setLabelText(
                        f"{base_msg}\n"
                        "登録状況(最新100件)で、今回の登録に該当しそうなエントリが見つかりました。\n"
                        f"entryId: {entry_id}\n"
                        f"{status_line}\n"
                        f"{head}\n\n"
                        "このまま待機を継続するか、応答待ちを中断して強制完了するかを選択してください。"
                    )
                except Exception:
                    pass

                _show_action_buttons()

            try:
                status_thread.finished.connect(_on_status_finished)
            except Exception:
                pass
            try:
                status_thread.start()
            except Exception:
                _on_status_finished()

        # ダイアログ内ボタンの配線（作成されている場合のみ）
        _ensure_action_buttons()

        def _return_to_waiting() -> None:
            """choice/checking 表示からスピナー（応答待ち）へ戻す。"""
            nonlocal status_thread
            try:
                if status_thread is not None:
                    setattr(status_thread, "_cancelled", True)
            except Exception:
                pass

            _hide_action_buttons()

            try:
                label_mode["mode"] = "spinner"
                if timer is not None and not timer.isActive():
                    timer.start()
            except Exception:
                pass

            _set_stop_button_label_for_mode()
            _update_label()
            QCoreApplication.processEvents()

        if stop_btn is not None:
            def _on_stop_btn_clicked() -> None:
                try:
                    mode = label_mode.get("mode")
                except Exception:
                    mode = None

                # 4ボタン状態（choice）では「応答待ちを続ける」= スピナーへ戻す
                if mode == "choice":
                    _return_to_waiting()
                    return

                # 通常状態（spinner）では従来通り「応答待ちを停止」= 登録状況確認へ
                if mode == "spinner":
                    _try_force_finish_by_status_check()
                    return

                # checking 等は無視
                return

            try:
                stop_btn.clicked.connect(_on_stop_btn_clicked)
            except Exception:
                pass
        if open_entry_btn is not None:
            def _open_entry_in_browser() -> None:
                try:
                    url_str = status_info.get("link_url")
                    if not url_str:
                        return
                    from qt_compat.core import QUrl
                    from qt_compat.gui import QDesktopServices

                    QDesktopServices.openUrl(QUrl(str(url_str)))
                except Exception:
                    return

            try:
                open_entry_btn.clicked.connect(_open_entry_in_browser)
            except Exception:
                pass

        if continue_wait_btn is not None:
            try:
                continue_wait_btn.clicked.connect(_return_to_waiting)
            except Exception:
                pass

        if force_finish_btn is not None:
            def _force_finish() -> None:
                nonlocal forced_result
                if not status_info.get("entry"):
                    return
                forced_result = {
                    "state": status_info.get("state"),
                    "entry": status_info.get("entry"),
                    "link_url": status_info.get("link_url"),
                }
                loop.quit()

            try:
                force_finish_btn.clicked.connect(_force_finish)
            except Exception:
                pass

        # UIを動かしながら待機
        loop.exec()

        try:
            timer.stop()
            timer.deleteLater()
        except Exception:
            pass

        try:
            if status_thread is not None:
                try:
                    setattr(status_thread, "_cancelled", True)
                except Exception:
                    pass
        except Exception:
            pass

        try:
            if stop_btn is not None:
                stop_btn.setEnabled(False)
                stop_btn.deleteLater()
        except Exception:
            pass

        try:
            for btn in (force_finish_btn, continue_wait_btn, open_entry_btn):
                if btn is not None:
                    btn.setEnabled(False)
                    btn.deleteLater()
        except Exception:
            pass

        # 進捗レンジを戻す（以後は完了表示に使う）
        try:
            progress.setRange(prev_min, prev_max)
        except Exception:
            pass

        QCoreApplication.processEvents()
        return th.resp, th.err, forced_result
    def _get_upload_summary_from_progress() -> dict:
        if not progress:
            return {}
        try:
            summary = getattr(progress, "_upload_summary", None)
            if isinstance(summary, dict):
                return summary
        except Exception:
            pass
        return {}

    def _finalize_with_summary(
        *,
        ok: bool,
        title: str,
        detail: str | None = None,
        failed_files: list[str] | None = None,
        result_text: str | None = None,
        link_url: str | None = None,
    ) -> None:
        if not progress:
            return
        summary = _get_upload_summary_from_progress()
        upload_total = int(summary.get("upload_total") or 0)
        upload_success_data_files = int(summary.get("upload_success_data_files") or 0)
        upload_success_attachments = int(summary.get("upload_success_attachments") or 0)
        merged_failed_files: list[str] = []
        try:
            merged_failed_files.extend(list(summary.get("failed_files") or []))
        except Exception:
            pass
        if failed_files:
            merged_failed_files.extend(list(failed_files))
        text = _build_data_register_completion_text(
            success=ok,
            upload_total=upload_total,
            upload_success_data_files=upload_success_data_files,
            upload_success_attachments=upload_success_attachments,
            failed_files=merged_failed_files,
            detail=detail,
            result_text=result_text,
        )
        if link_url:
            import html as _html

            safe_url = _html.escape(str(link_url), quote=True)
            safe_text = _html.escape(text)
            rich = (
                f'<div style="white-space: pre-wrap;">{safe_text}</div>'
                f'<br><a href="{safe_url}">登録状況エントリをRDEサイトで開く</a><br>'
                f'<span>{safe_url}</span>'
            )
            _finalize_progress_dialog(progress, title=title, text=rich, require_confirmation=require_confirmation)
        else:
            _finalize_progress_dialog(progress, title=title, text=text, require_confirmation=require_confirmation)

    def _extract_dataset_name_for_status_match() -> str:
        try:
            if isinstance(dataset_info, dict):
                # 一括登録: dataset_info['name'] を保持しているケースがある
                name = str(dataset_info.get('name') or '').strip()
                if name:
                    return name
                attr = dataset_info.get('attributes') or {}
                if isinstance(attr, dict):
                    name = str(attr.get('name') or '').strip()
                    if name:
                        return name
        except Exception:
            pass
        return ""

    def _build_timeout_detail(*, data_name: str, dataset_name: str, match: dict | None) -> str:
        pretty_dataset = dataset_name or "(不明)"
        lines: list[str] = [
            "RDEサーバー側でタイムアウトしました（構造化サーバー処理待ち）。",
            "このタイムアウトは『登録失敗』を意味しないことが多く、処理が継続している可能性があります。",
            "",
            "照合条件:",
            f"- データ名: {data_name}",
            f"- データセット名: {pretty_dataset}",
            "- 開始時刻: 直近（登録状況のstartTimeと近いもの）",
            "",
            "登録状況(最新100件)での照会結果:",
        ]
        if match:
            lines.append(f"- entryId: {match.get('id')}")
            lines.append(f"- status: {match.get('status')}")
            lines.append(f"- startTime: {match.get('startTime')}")
            lines.append(f"- dataName: {match.get('dataName')}")
            lines.append(f"- datasetName: {match.get('datasetName')}")
            status = str(match.get('status') or '').strip().lower()
            if status and status != 'failed':
                lines.append("")
                lines.append("判定: statusがFAILEDではないため、登録は成功している可能性が高いです。")
            elif status == 'failed':
                lines.append("")
                lines.append("判定: statusがFAILEDのため、登録は失敗しています。")
        else:
            lines.append("判定: 一致する最近の登録が見つかりませんでした（反映遅延の可能性があります）。")
        lines.append("")
        lines.append("確認方法: データ登録/タイルの『登録状況』タブで『最新100件を取得』を押して確認できます。")
        return "\n".join(lines)

    try:
        if progress:
            progress.setLabelText("エントリー登録バリデーション中...")
            QCoreApplication.processEvents()
        # bearer_token=Noneで自動選択を有効化
        resp_validation = api_request("POST", url_validation, bearer_token=None, headers=headers, json_data=payload, timeout=60)
        _store_http_response(key="validation", method="POST", url=url_validation, resp=resp_validation)
        if resp_validation is None:
            _finalize_with_summary(
                ok=False,
                title="データ登録失敗",
                detail=(
                    "バリデーション通信エラー: サーバーとの通信に失敗しました。\n"
                    "ネットワーク接続とトークンの有効性を確認してください。"
                ),
            )
            return {"error": "validation", "detail": "Request failed"}
        if progress:
            progress.setLabelText(f"バリデーション応答: {resp_validation.status_code} {resp_validation.reason}")
            QCoreApplication.processEvents()
        logger.debug("response validation:   %s %s %s", resp_validation.status_code, resp_validation.reason, resp_validation.text)
        if resp_validation.status_code not in [200, 201, 202]:
            logger.error("バリデーションエラー: %s", resp_validation.text)
            _finalize_with_summary(
                ok=False,
                title="データ登録失敗",
                detail=f"バリデーションエラー: データの検証に失敗しました。\n\n{resp_validation.text}",
            )
            return {"error": "validation", "detail": resp_validation.text}
        if progress:
            progress.setLabelText("エントリー本体POST中...")
            QCoreApplication.processEvents()

        # タイムアウト時の照合用（entries の startTime と近い時刻でマッチングする）
        from datetime import datetime, timezone

        post_started_at_utc = datetime.now(timezone.utc)
        target_dataset_name = _extract_dataset_name_for_status_match()
        target_data_name = str(dataName or '').strip()

        # bearer_token=Noneで自動選択を有効化（応答待ちはスピナー+経過時間で可視化）
        resp, post_exc, forced = _run_post_entries_with_spinner(timeout_sec=60)
        if post_exc:
            logger.warning("entries POSTスレッドで例外: %s", post_exc)
        _store_http_response(
            key="entries_post",
            method="POST",
            url=url,
            resp=resp,
            error=post_exc,
            note=None if resp is not None else "No response (timeout or network error)",
        )

        if forced is not None:
            # 10秒経過後の「応答待ちを停止」から、登録状況で確認して強制完了した
            try:
                if progress:
                    progress.close()
            except Exception:
                pass
            return {
                "error": "timeout",
                "detail": "response wait stopped by user",
                "forced": True,
                "registration_status": forced.get("entry"),
                "link_url": forced.get("link_url"),
            }
        if resp is None:
            # タイムアウト(60秒)の可能性が高いので、登録状況で進行中か判定して表示する
            try:
                from classes.data_entry.core import registration_status_service as regsvc
                from classes.data_entry.core.registration_status_matcher import find_registration_status_match

                latest = regsvc.fetch_latest(limit=100, use_cache=False)
                match_obj = find_registration_status_match(
                    latest,
                    data_name=target_data_name,
                    dataset_name=target_dataset_name or None,
                    near_time_utc=post_started_at_utc,
                )
                match_entry = match_obj.entry
                link_url = None
                try:
                    entry_id = (match_entry or {}).get('id')
                    if entry_id:
                        link_url = f"https://rde-entry-arim.nims.go.jp/data-entry/datasets/entries/{entry_id}"
                except Exception:
                    link_url = None
                if match_obj.state == 'failed':
                    _finalize_with_summary(
                        ok=False,
                        title="データ登録失敗",
                        detail=_build_timeout_detail(
                            data_name=target_data_name,
                            dataset_name=target_dataset_name,
                            match=match_entry,
                        ),
                        result_text="タイムアウト（登録失敗の可能性あり）",
                        link_url=link_url,
                    )
                else:
                    _finalize_with_summary(
                        ok=False,
                        title="データ登録: タイムアウト",
                        detail=_build_timeout_detail(
                            data_name=target_data_name,
                            dataset_name=target_dataset_name,
                            match=match_entry,
                        ),
                        result_text="タイムアウト（処理継続の可能性）",
                        link_url=link_url,
                    )
                return {
                    "error": "timeout",
                    "detail": "entries post timeout",
                    "registration_status": match_entry,
                    "link_url": link_url,
                }
            except Exception as exc:
                _finalize_with_summary(
                    ok=False,
                    title="データ登録: タイムアウト",
                    detail=(
                        "エントリー登録(POST /entries)後の応答がタイムアウトしました。\n"
                        "処理が継続している可能性があります。\n\n"
                        f"登録状況の自動照会で例外が発生しました: {exc}\n"
                        "データ登録/タイルの『登録状況』タブで『最新100件を取得』を押して確認してください。"
                    ),
                    result_text="タイムアウト（処理継続の可能性）",
                )
                return {"error": "timeout", "detail": "entries post timeout (status check failed)", "exception": str(exc)}

        # RDE側が構造化サーバー待ちでタイムアウトした場合、504等で返ることがある
        try:
            resp_text_lower = (resp.text or '').lower()
        except Exception:
            resp_text_lower = ''
        if getattr(resp, 'status_code', None) in (502, 503, 504) or ('timeout' in resp_text_lower and int(getattr(resp, 'status_code', 0) or 0) >= 500):
            try:
                from classes.data_entry.core import registration_status_service as regsvc
                from classes.data_entry.core.registration_status_matcher import find_registration_status_match

                latest = regsvc.fetch_latest(limit=100, use_cache=False)
                match_obj = find_registration_status_match(
                    latest,
                    data_name=target_data_name,
                    dataset_name=target_dataset_name or None,
                    near_time_utc=post_started_at_utc,
                )
                match_entry = match_obj.entry
                link_url = None
                try:
                    entry_id = (match_entry or {}).get('id')
                    if entry_id:
                        link_url = f"https://rde-entry-arim.nims.go.jp/data-entry/datasets/entries/{entry_id}"
                except Exception:
                    link_url = None
                if match_obj.state == 'failed':
                    _finalize_with_summary(
                        ok=False,
                        title="データ登録失敗",
                        detail=_build_timeout_detail(
                            data_name=target_data_name,
                            dataset_name=target_dataset_name,
                            match=match_entry,
                        ),
                        result_text="タイムアウト（登録失敗の可能性あり）",
                        link_url=link_url,
                    )
                else:
                    _finalize_with_summary(
                        ok=False,
                        title="データ登録: タイムアウト",
                        detail=_build_timeout_detail(
                            data_name=target_data_name,
                            dataset_name=target_dataset_name,
                            match=match_entry,
                        ),
                        result_text="タイムアウト（処理継続の可能性）",
                        link_url=link_url,
                    )
                return {
                    "error": "timeout",
                    "detail": f"entries post timeout-like response: {getattr(resp, 'status_code', None)}",
                    "registration_status": match_entry,
                    "link_url": link_url,
                }
            except Exception as exc:
                _finalize_with_summary(
                    ok=False,
                    title="データ登録: タイムアウト",
                    detail=(
                        "エントリー登録(POST /entries)がタイムアウト相当の応答でした。\n"
                        "処理が継続している可能性があります。\n\n"
                        f"登録状況の自動照会で例外が発生しました: {exc}\n"
                        "データ登録/タイルの『登録状況』タブで『最新100件を取得』を押して確認してください。"
                    ),
                    result_text="タイムアウト（処理継続の可能性）",
                )
                return {"error": "timeout", "detail": "entries post timeout-like response (status check failed)", "exception": str(exc)}

        if progress:
            progress.setLabelText(f"POST応答: {resp.status_code} {resp.reason}")
            QCoreApplication.processEvents()
        resp.raise_for_status()
        data = resp.json()
        os.makedirs(output_dir, exist_ok=True)
        with open(os.path.join(output_dir, "create_entry.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.debug("response:   %s %s", resp.status_code, resp.reason)
        logger.info("(create_entry.json)の取得・保存に成功しました。")
        
        # データ登録成功時にサンプル情報を自動取得
        try:
            logger.info("データ登録成功。サンプル情報を自動取得中...")
            from classes.basic.core.basic_info_logic import fetch_sample_info_for_dataset_only
            # bearer_token=Noneで自動選択（Material API用トークンが自動的に選ばれる）
            sample_result = fetch_sample_info_for_dataset_only(None, datasetId)
            if isinstance(sample_result, str) and "エラー" not in sample_result and "失敗" not in sample_result:
                logger.info("サンプル情報の自動取得完了: %s", sample_result)
            else:
                logger.warning("サンプル情報の自動取得に問題: %s", sample_result)
        except Exception as e:
            logger.warning("サンプル情報の自動取得に失敗: %s", e)
        
        if progress:
            _finalize_with_summary(
                ok=True,
                title="データ登録完了",
                detail="登録が完了しました。内容を確認したら「確認」を押して閉じてください。",
            )
        
        return {"success": True, "response": data}
    except Exception as e:
        logger.error("(create_entry.json)の取得・保存に失敗しました: %s", e)
        if progress:
            _finalize_with_summary(
                ok=False,
                title="データ登録失敗",
                detail=f"例外が発生しました: {e}",
            )
        else:
            try:
                QMessageBox.critical(None, "登録失敗", f"例外が発生しました: {e}")
            except Exception:
                pass
        return {"error": "exception", "detail": str(e)}

def upload_file(bearer_token, datasetId="a74b58c0-9907-40e7-a261-a75519730d82", file_path=None):
    """ファイルアップロード（net.http_helpers経由 / リトライ付き）
    502/503/504 などのサーバ・ゲートウェイ系エラーは指数バックオフ再試行 (最大3回)
    戻り値: uploadId もしくは None
    """
    from net.http_helpers import proxy_post
    if not bearer_token:
        logger.error("Bearerトークン未取得のためアップロード不可。ログイン状態を確認してください。")
        return None
    output_dir = get_dynamic_file_path('output/rde/data')
    if not file_path:
        file_path = os.path.join(INPUT_DIR, "file", "test.dm4")  # フォールバックテストファイル
    url = f"https://rde-entry-api-arim.nims.go.jp/uploads?datasetId={datasetId}"
    try:
        filename = os.path.basename(file_path)
        with open(file_path, 'rb') as f:
            binary_data = f.read()
        size_bytes = len(binary_data)
        encoded_filename = urllib.parse.quote(filename)
        base_headers = {
            "Accept": "application/json",
            "X-File-Name": encoded_filename,
            "Content-Type": "application/octet-stream",
            "User-Agent": "PythonUploader/1.0",
        }
        max_attempts = 3
        backoff = 1.5
        for attempt in range(1, max_attempts + 1):
            logger.info(f"[UPLOAD] 開始 attempt={attempt}/{max_attempts} file={filename} size={size_bytes}B datasetId={datasetId}")
            try:
                resp = proxy_post(url, data=binary_data, headers=base_headers, timeout=90)
                status = resp.status_code
                if status >= 500:
                    logger.warning(f"[UPLOAD] サーバエラー status={status} attempt={attempt} body_length={len(resp.text)}")
                    if attempt < max_attempts:
                        import time as _t
                        sleep_sec = backoff ** attempt
                        logger.info(f"[UPLOAD] リトライ待機 {sleep_sec:.1f}s")
                        _t.sleep(sleep_sec)
                        continue
                resp.raise_for_status()
                data = resp.json()
                os.makedirs(output_dir, exist_ok=True)
                with open(os.path.join(output_dir, "upload_file.json"), "w", encoding="utf-8") as outf:
                    json.dump(data, outf, ensure_ascii=False, indent=2)
                upload_id = data.get("uploadId")
                logger.info(f"[UPLOAD] 成功 uploadId={upload_id} status={status} attempts={attempt}")
                return upload_id
            except Exception as ue:
                if 'resp' in locals() and resp is not None:
                    status = getattr(resp, 'status_code', 'N/A')
                    text_preview = resp.text[:300] if hasattr(resp, 'text') else ''
                    logger.error(f"[UPLOAD] 失敗 attempt={attempt} status={status} error={ue} resp_preview={text_preview}")
                else:
                    logger.error(f"[UPLOAD] 失敗 attempt={attempt} error={ue}")
                if attempt < max_attempts:
                    import time as _t
                    sleep_sec = backoff ** attempt
                    logger.info(f"[UPLOAD] リトライ待機 {sleep_sec:.1f}s (exception)")
                    _t.sleep(sleep_sec)
                    continue
                return None
    except Exception as e:
        logger.error(f"[UPLOAD] 致命的エラー file={file_path} error={e}")
        return None
    return None