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
) -> str:
    """通常登録の進捗ダイアログ完了表示用テキストを生成する（純粋関数）。"""

    failed_files = failed_files or []
    upload_success_total = int(upload_success_data_files) + int(upload_success_attachments)
    status_line = "結果: 成功" if success else "結果: 失敗"
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

    try:
        progress.setValue(progress.maximum())
    except Exception:
        pass

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
        parent = progress.parent()
        if parent is not None and hasattr(parent, "frameGeometry"):
            pg = progress.frameGeometry()
            pg.moveCenter(parent.frameGeometry().center())
            progress.move(pg.topLeft())
    except Exception:
        pass
    try:
        progress.show()
        progress.raise_()
        progress.activateWindow()
    except Exception:
        pass

    QCoreApplication.processEvents()

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

def run_data_register_logic(parent=None, bearer_token=None, dataset_info=None, form_values=None, file_paths=None, attachment_paths=None):
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
        _continue_data_register_process(parent, bearer_token, dataset_info, form_values, temp_file_paths, temp_attachment_paths, dataFiles_preview, attachments_preview)
        
    except Exception as e:
        logger.error(f"データ登録処理中にエラーが発生: {e}")
        if parent:
            QMessageBox.critical(parent, "データ登録エラー", f"データ登録処理中にエラーが発生しました: {e}")

def _continue_data_register_process(parent, bearer_token, dataset_info, form_values, temp_file_paths, temp_attachment_paths, dataFiles_preview, attachments_preview):
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
        if parent is not None:
            # 親ウインドウの中央に重なるように配置
            pg = progress.frameGeometry()
            pg.moveCenter(parent.frameGeometry().center())
            progress.move(pg.topLeft())
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
    current_file_idx = 0
    # データファイルアップロード
    for path in temp_file_paths:
        filename = os.path.basename(path)
        current_file_idx += 1
        progress.setLabelText(f"アップロード中: {filename}\n({current_file_idx}/{total_files})")
        progress.setValue(current_file_idx - 1)
        QCoreApplication.processEvents()
        datasetId = None
        if dataset_info and isinstance(dataset_info, dict):
            datasetId = dataset_info.get('id')
        if not datasetId:
            datasetId = "a74b58c0-9907-40e7-a261-a75519730d82"  # fallback
        uploadId = upload_file(bearer_token, datasetId, path)
        if uploadId:
            dataFiles["data"].append({"type": "upload", "id": uploadId})
            succesedUploads.append(uploadId)
            numberUploaded += 1
        else:
            failedUploads.append(filename)
            flagUploadSuccess = False
        progress.setValue(current_file_idx)
        QCoreApplication.processEvents()
        if progress.wasCanceled():
            logger.info("アップロードがキャンセルされました。")
            return
    # 添付ファイルアップロード
    for path in temp_attachment_paths:
        filename = os.path.basename(path)
        current_file_idx += 1
        progress.setLabelText(f"添付アップロード中: {filename}\n({current_file_idx}/{total_files})")
        progress.setValue(current_file_idx - 1)
        QCoreApplication.processEvents()
        datasetId = None
        if dataset_info and isinstance(dataset_info, dict):
            datasetId = dataset_info.get('id')
        if not datasetId:
            datasetId = "a74b58c0-9907-40e7-a261-a75519730d82"  # fallback
        uploadId = upload_file(bearer_token, datasetId, path)
        if uploadId:
            attachments.append({"uploadId": uploadId, "description": filename})
        else:
            failedUploads.append(filename)
            flagUploadSuccess = False
        progress.setValue(current_file_idx)
        QCoreApplication.processEvents()
        if progress.wasCanceled():
            logger.info("アップロードがキャンセルされました。")
            return
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
        )
        _finalize_progress_dialog(progress, title=title, text=text, require_confirmation=require_confirmation)

    try:
        if progress:
            progress.setLabelText("エントリー登録バリデーション中...")
            QCoreApplication.processEvents()
        # bearer_token=Noneで自動選択を有効化
        resp_validation = api_request("POST", url_validation, bearer_token=None, headers=headers, json_data=payload, timeout=60)
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
        # bearer_token=Noneで自動選択を有効化
        resp = api_request("POST", url, bearer_token=None, headers=headers, json_data=payload, timeout=60)
        if resp is None:
            _finalize_with_summary(
                ok=False,
                title="データ登録失敗",
                detail=(
                    "通信エラー: サーバーとの通信に失敗しました。\n"
                    "ネットワーク接続とトークンの有効性を確認してください。"
                ),
            )
            return {"error": "post", "detail": "Request failed"}
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