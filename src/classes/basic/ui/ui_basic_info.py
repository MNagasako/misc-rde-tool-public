"""
basic_info関連のUIロジック分離
"""
import logging
def _get_basic_info_parallel_workers(controller, default: int = 10) -> int:
    """基本情報タブの並列ダウンロード数（UI選択/設定値）を取得する。"""
    try:
        spin = getattr(controller, 'basic_parallel_download_spinbox', None)
        if spin is not None and hasattr(spin, 'value'):
            value = int(spin.value())
            if value < 1:
                return default
            return min(value, 50)
    except Exception:
        pass

    try:
        from classes.managers.app_config_manager import get_config_manager

        cfg = get_config_manager()
        value = int(cfg.get("basic_info.parallel_download_workers", default) or default)
        if value < 1:
            return default
        return min(value, 50)
    except Exception:
        return default

from qt_compat.core import QTimer, Qt
from qt_compat.widgets import QDialog, QProgressDialog, QMessageBox
import threading
from classes.utils.progress_worker import ProgressWorker, SimpleProgressWorker
from classes.theme import get_color, ThemeKey
from config.common import get_dynamic_file_path
from .basic_info_search_dialog import (
    BasicInfoSearchSelection,
    PATTERN_INSTITUTION,
    PATTERN_MANUAL,
    prompt_basic_info_search_options,
)

# ロガー設定
logger = logging.getLogger(__name__)


def _estimate_remaining_seconds(elapsed_seconds: float, current: int, total: int) -> float | None:
    """現在の進捗から残り秒(推定)を返す。推定不能な場合はNone。"""
    try:
        if elapsed_seconds <= 0:
            return None
        if current <= 0 or total <= 0:
            return None
        if current > total:
            return None
        rate = float(current) / float(elapsed_seconds)
        if rate <= 0:
            return None
        remaining = float(total - current) / rate
        if remaining < 0:
            return None
        return remaining
    except Exception:
        return None


def _format_hms(seconds: float) -> str:
    """秒数を h:mm:ss / m:ss 形式で返す。"""
    try:
        total = int(round(float(seconds)))
        if total < 0:
            total = 0
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
    except Exception:
        return ""


def _build_progress_label(*, message: str, current: int, total: int, elapsed_seconds: float) -> str:
    """プログレスダイアログ用のラベル文言を組み立てる。"""
    try:
        parts: list[str] = [str(message)]

        if total > 0:
            percent = min(max(int((int(current) * 100 + int(total) - 1) / int(total)), 0), 100)
            parts.append(f"進捗: {int(current)}/{int(total)} ({percent}%)")
        elif current > 0:
            parts.append(f"進捗: {int(current)}")

        elapsed_text = _format_hms(elapsed_seconds)
        if elapsed_text:
            parts.append(f"経過: {elapsed_text}")

        eta = _estimate_remaining_seconds(elapsed_seconds, int(current), int(total))
        if eta is not None:
            eta_text = _format_hms(eta)
            if eta_text:
                parts.append(f"残り(推定): {eta_text}")

        return "\n".join(parts)
    except Exception:
        return str(message)

def show_progress_dialog(parent, title, worker, show_completion_dialog=True):
    """プログレス表示付きで処理を実行する共通関数
    
    Args:
        parent: 親ウィジェット
        title: プログレスダイアログのタイトル
        worker: ProgressWorker or SimpleProgressWorker
        show_completion_dialog: 完了時にダイアログを表示するか（デフォルト: True）
    
    Returns:
        QProgressDialog: プログレスダイアログインスタンス
    """
    progress_dialog = QProgressDialog(parent)
    progress_dialog.setWindowTitle(title)
    progress_dialog.setLabelText("処理を開始しています...")
    progress_dialog.setRange(0, 100)
    progress_dialog.setValue(0)
    # QProgressDialog の autoClose/autoReset は 100% 到達時に勝手に閉じるため、
    # 長い処理や「丸めで一瞬100%」になるケースでチラつき/再表示の原因になり得る。
    try:
        progress_dialog.setAutoClose(False)
        progress_dialog.setAutoReset(False)
    except Exception:
        pass
    # 短時間処理で一瞬だけ表示されるのを避ける（必要ならQt側が自動で表示）
    progress_dialog.setMinimumDuration(700)
    progress_dialog.setWindowModality(Qt.WindowModal)
    progress_dialog.setCancelButtonText("キャンセル")
    
    import time
    _started = time.perf_counter()

    # 進捗イベントが来ない時間帯（長いHTTP待ち等）でも、経過時間表示だけは更新する。
    # ※進捗・ETAは最後に受け取った (current/total) を使って再計算する。
    _last_message: str = "処理を開始しています..."
    _last_current: int = 0
    _last_total: int = 100
    _last_progress_event: float = _started
    _in_busy_mode: bool = False
    _busy_after_seconds: float = 3.0

    # プログレス更新の接続
    def update_progress(value, message):
        # 旧インターフェイス: (percent, message)
        def set_progress():
            if progress_dialog:
                nonlocal _last_message, _last_current, _last_total, _last_progress_event, _in_busy_mode
                _last_message = str(message)
                _last_current = int(value)
                _last_total = 100
                _last_progress_event = time.perf_counter()

                if _in_busy_mode:
                    _in_busy_mode = False

                progress_dialog.setRange(0, 100)
                progress_dialog.setValue(int(value))
                elapsed = time.perf_counter() - _started
                progress_dialog.setLabelText(
                    _build_progress_label(
                        message=str(message),
                        current=int(value),
                        total=100,
                        elapsed_seconds=float(elapsed),
                    )
                )
        QTimer.singleShot(0, set_progress)

    def update_progress_detail(current, total, message):
        # 新インターフェイス: (current, total, message)
        def set_progress():
            if not progress_dialog:
                return

            nonlocal _last_message, _last_current, _last_total, _last_progress_event, _in_busy_mode
            _last_message = str(message)

            try:
                c = int(current)
            except Exception:
                c = 0
            try:
                t = int(total)
            except Exception:
                t = 0

            _last_current = c
            _last_total = t
            _last_progress_event = time.perf_counter()

            if _in_busy_mode:
                _in_busy_mode = False

            # totalが取れる場合は「件数ベース」でバーも動かす。
            # total=100 の場合は従来どおり percent として扱う（互換）。
            if t > 0 and not (t == 100 and c <= 100):
                progress_dialog.setRange(0, t)
                progress_dialog.setValue(min(max(c, 0), t))
            else:
                progress_dialog.setRange(0, 100)
                if t > 0:
                    percent = min(max(int((c * 100 + t - 1) / t), 0), 100)
                else:
                    percent = 0
                progress_dialog.setValue(percent)

            elapsed = time.perf_counter() - _started
            progress_dialog.setLabelText(
                _build_progress_label(
                    message=str(message),
                    current=c,
                    total=t,
                    elapsed_seconds=float(elapsed),
                )
            )

        QTimer.singleShot(0, set_progress)
    
    def _format_elapsed(seconds: float) -> str:
        try:
            total = int(round(seconds))
            h = total // 3600
            m = (total % 3600) // 60
            s = total % 60
            if h > 0:
                return f"{h}:{m:02d}:{s:02d}"
            return f"{m}:{s:02d}"
        except Exception:
            return ""

    # 完了時の処理
    # NOTE: completion_in_dialog=True の場合は、完了を同一ダイアログ内で表示して
    # 「閉じる」押下まで残す（別ダイアログを増やさない）。
    completion_in_dialog = False
    try:
        completion_in_dialog = bool(getattr(worker, "completion_in_dialog", False))
    except Exception:
        completion_in_dialog = False

    _state = {"done": False}

    def on_finished(success, message):
        def handle_finished():
            try:
                tick_timer = getattr(progress_dialog, "_elapsed_update_timer", None)
                if tick_timer is not None and hasattr(tick_timer, "stop"):
                    tick_timer.stop()
            except Exception:
                pass

            _state["done"] = True

            elapsed_text = _format_elapsed(time.perf_counter() - _started)
            if elapsed_text:
                message_with_time = f"{message}\n\n所要時間: {elapsed_text}"
            else:
                message_with_time = str(message)

            if completion_in_dialog:
                try:
                    progress_dialog.setRange(0, 100)
                    progress_dialog.setValue(100)
                except Exception:
                    pass
                try:
                    prefix = "✅ 完了" if success else "❌ エラー"
                    progress_dialog.setLabelText(f"{prefix}\n\n{message_with_time}")
                except Exception:
                    pass
                try:
                    progress_dialog.setCancelButtonText("閉じる")
                except Exception:
                    pass
                try:
                    progress_dialog.raise_()
                    progress_dialog.activateWindow()
                except Exception:
                    pass
                return

            if progress_dialog:
                progress_dialog.close()
            # show_completion_dialog=Falseの場合はダイアログを表示しない
            if show_completion_dialog:
                if success:
                    QMessageBox.information(parent, title, message_with_time)
                else:
                    QMessageBox.critical(parent, f"{title} - エラー", message_with_time)
        QTimer.singleShot(0, handle_finished)
    
    # キャンセル処理
    def on_cancel():
        # 完了後はキャンセルではなく「閉じる」として扱う
        if _state.get("done"):
            progress_dialog.close()
            return

        worker.cancel()
        try:
            tick_timer = getattr(progress_dialog, "_elapsed_update_timer", None)
            if tick_timer is not None and hasattr(tick_timer, "stop"):
                tick_timer.stop()
        except Exception:
            pass
        progress_dialog.close()

    # 進捗イベントが来ない間の「経過/残り(推定)」表示更新（UIスレッド）
    tick_timer = QTimer(progress_dialog)
    tick_timer.setInterval(250)

    def _tick_update_label():
        try:
            nonlocal _last_message, _last_current, _last_total, _last_progress_event, _in_busy_mode
            if not progress_dialog:
                return
            elapsed = time.perf_counter() - _started
            now = time.perf_counter()

            # 進捗イベントが一定時間来ない場合は“不定”バー（アニメーション）に切り替える。
            # 長いHTTP待ち/リトライでも「動いている」ことが視覚的に分かるようにする。
            if (not _in_busy_mode) and (now - _last_progress_event) >= _busy_after_seconds:
                try:
                    _in_busy_mode = True
                    progress_dialog.setRange(0, 0)
                except Exception:
                    _in_busy_mode = False

            message = str(_last_message)
            if _in_busy_mode and "待機中" not in message and "応答待ち" not in message:
                message = f"{message}\n(応答待ち...)"
            progress_dialog.setLabelText(
                _build_progress_label(
                    message=message,
                    current=int(_last_current),
                    total=int(_last_total),
                    elapsed_seconds=float(elapsed),
                )
            )
        except Exception:
            return

    tick_timer.timeout.connect(_tick_update_label)
    # 参照を保持してGCされないようにする
    progress_dialog._elapsed_update_timer = tick_timer  # type: ignore[attr-defined]
    tick_timer.start()
    
    # 新しい進捗(件数/ETA)が使える場合はそちらを優先
    if hasattr(worker, 'progress_detail'):
        try:
            worker.progress_detail.connect(update_progress_detail)
        except Exception:
            worker.progress.connect(update_progress)
    else:
        worker.progress.connect(update_progress)
    worker.finished.connect(on_finished)
    progress_dialog.canceled.connect(on_cancel)
    
    # ワーカーをスレッドで実行
    thread = threading.Thread(target=worker.run)
    thread.start()
    
    return progress_dialog

def fetch_basic_info(controller):
    """
    基本情報取得（全データセット）
    
    v2.0.1改善:
    - トークン検証の追加
    - エラーメッセージの明確化
    - 再ログイン促進機能の統合
    
    v2.1.16追加:
    - グループ選択ダイアログの統合
    """
    try:
        import json
        from pathlib import Path
        from ..core.basic_info_logic import fetch_basic_info_logic, show_fetch_confirmation_dialog
        from core.bearer_token_manager import BearerTokenManager
        from config.common import get_dynamic_file_path
        from .group_selection_dialog import show_group_selection_dialog
        
        # トークン取得（v2.0.1: BearerTokenManagerを使用）
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
        
        # トークンが取得できない場合は処理を中止
        if not bearer_token:
            logger.warning("基本情報取得処理: トークンが取得できませんでした")
            QMessageBox.warning(
                controller.parent,
                "認証エラー",
                "認証トークンが取得できません。\n"
                "ログインタブでRDEシステムにログインしてから再度実行してください。"
            )
            return
        
        webview = getattr(controller.parent, 'webview', controller.parent)
        
        # 確認ダイアログをメインスレッドで表示
        if not show_fetch_confirmation_dialog(controller.parent, onlySelf=False, searchWords=None, searchWordsList=None):
            logger.info("基本情報取得処理はユーザーによりキャンセルされました")
            return

        # 既存ファイルの有無を確認し、上書き可否をユーザーに確認
        target_files = [
            get_dynamic_file_path("output/rde/data/self.json"),
            get_dynamic_file_path("output/rde/data/group.json"),
            get_dynamic_file_path("output/rde/data/groupDetail.json"),
            get_dynamic_file_path("output/rde/data/subGroup.json"),
            get_dynamic_file_path("output/rde/data/organization.json"),
            get_dynamic_file_path("output/rde/data/instrumentType.json"),
            get_dynamic_file_path("output/rde/data/template.json"),
            get_dynamic_file_path("output/rde/data/instruments.json"),
            get_dynamic_file_path("output/rde/data/licenses.json"),
            get_dynamic_file_path("output/rde/data/dataset.json"),
        ]
        existing_files = [path for path in target_files if Path(path).exists()]
        force_download = False

        if existing_files:
            msg_box = QMessageBox(controller.parent)
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle("上書き取得の確認")
            msg_box.setText(
                "既存の基本情報JSONが見つかりました。\n"
                "再取得して上書き保存しますか？"
            )
            msg_box.setInformativeText(
                "• はい（上書き取得）: すべて再取得して最新データで上書き\n"
                "• いいえ（新規のみ取得）: 新規ファイルのみ取得します。\n"
                "  既存ファイルは内容が古くても更新されません。"
            )
            yes_btn = msg_box.addButton("はい（上書き取得）", QMessageBox.YesRole)
            no_btn = msg_box.addButton("いいえ（新規のみ取得）", QMessageBox.NoRole)
            msg_box.setDefaultButton(no_btn)
            msg_box.exec()
            force_download = msg_box.clickedButton() == yes_btn
        else:
            force_download = True  # 取得対象が存在しない場合は強制取得
        
        # === グループ選択ダイアログ（v2.1.16追加） ===
        selected_program_id = None
        group_json_path = get_dynamic_file_path("output/rde/data/group.json")
        
        if Path(group_json_path).exists():
            try:
                with open(group_json_path, "r", encoding="utf-8") as f:
                    group_data = json.load(f)
                
                # included配列からtype="group"を抽出
                groups = [item for item in group_data.get("included", []) 
                         if item.get("type") == "group"]
                
                if groups:
                    # 1件でも選択ダイアログを表示
                    selected_group = show_group_selection_dialog(groups, controller.parent)
                    if not selected_group:  # キャンセル時
                        logger.info("グループ選択がキャンセルされました")
                        return
                    selected_program_id = selected_group["id"]
                    logger.info(f"選択されたプログラム: {selected_group['name']}")
            except Exception as e:
                logger.warning(f"group.json の読み込みに失敗: {e}")
                # group.jsonが読めない場合はデフォルト値を使用（後続処理で設定）
        
        # プログレス表示付きワーカーを作成
        worker = ProgressWorker(
            task_func=fetch_basic_info_logic,
            task_kwargs={
                'bearer_token': bearer_token,
                'parent': controller.parent,
                'webview': webview,
                'onlySelf': False,
                'searchWords': None,
                'skip_confirmation': True,
                'force_download': force_download,
            },
            task_name="基本情報取得"
        )
        
        # プログレス表示
        show_progress_dialog(controller.parent, "基本情報取得", worker)
    except ImportError as e:
        logger.error(f"基本情報取得モジュールのインポートエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"基本情報取得機能の初期化に失敗しました: {e}")
    except Exception as e:
        logger.error(f"基本情報取得処理でエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"基本情報取得処理中にエラーが発生しました: {e}")

def fetch_basic_info_self(controller):
    """
    基本情報取得（検索条件付き）
    
    v2.0.1改善:
    - トークン検証の追加
    - エラーメッセージの明確化
    - 再ログイン促進機能の統合
    
    v2.1.16追加:
    - グループ選択ダイアログの統合
    """
    try:
        import json
        from pathlib import Path
        from ..core.basic_info_logic import fetch_basic_info_logic, show_fetch_confirmation_dialog
        from core.bearer_token_manager import BearerTokenManager
        from config.common import get_dynamic_file_path
        from .group_selection_dialog import show_group_selection_dialog
        
        # トークン取得（v2.0.1: BearerTokenManagerを使用）
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
        
        # トークンが取得できない場合は処理を中止
        if not bearer_token:
            logger.warning("基本情報取得処理（検索）: トークンが取得できませんでした")
            QMessageBox.warning(
                controller.parent,
                "認証エラー",
                "認証トークンが取得できません。\n"
                "ログインタブでRDEシステムにログインしてから再度実行してください。"
            )
            return
        
        webview = getattr(controller.parent, 'webview', controller.parent)
        previous_selection = getattr(controller, '_basic_info_search_state', None)
        if isinstance(previous_selection, BasicInfoSearchSelection):
            default_keyword = (previous_selection.manual_keyword or "").strip()
        else:
            default_keyword = ""
        if not isinstance(previous_selection, BasicInfoSearchSelection):
            previous_selection = None

        selection = prompt_basic_info_search_options(
            controller.parent,
            default_keyword=default_keyword,
            previous_state=previous_selection,
        )
        if not selection:
            logger.info("基本情報取得(検索)はユーザーによりキャンセルされました。(ダイアログ)")
            return

        controller._basic_info_search_state = selection
        searchWords = selection.manual_keyword or None
        searchWordsBatch = selection.keyword_batch or None
        keyword_preview = selection.display_keywords()

        # 検索条件の入力欄はダイアログ側に一本化したため、メイン画面の入力欄は更新しない

        # 確認ダイアログをメインスレッドで表示
        preview_list = keyword_preview if keyword_preview else None
        if not show_fetch_confirmation_dialog(
            controller.parent,
            onlySelf=True,
            searchWords=searchWords,
            searchWordsList=preview_list,
        ):
            logger.info("基本情報取得処理はユーザーによりキャンセルされました。")
            return

        # 既存ファイルの有無を確認し、上書き可否をユーザーに確認
        target_files = [
            get_dynamic_file_path("output/rde/data/self.json"),
            get_dynamic_file_path("output/rde/data/group.json"),
            get_dynamic_file_path("output/rde/data/groupDetail.json"),
            get_dynamic_file_path("output/rde/data/subGroup.json"),
            get_dynamic_file_path("output/rde/data/organization.json"),
            get_dynamic_file_path("output/rde/data/instrumentType.json"),
            get_dynamic_file_path("output/rde/data/template.json"),
            get_dynamic_file_path("output/rde/data/instruments.json"),
            get_dynamic_file_path("output/rde/data/licenses.json"),
            get_dynamic_file_path("output/rde/data/dataset.json"),
        ]
        existing_files = [path for path in target_files if Path(path).exists()]
        force_download = False

        if existing_files:
            msg_box = QMessageBox(controller.parent)
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle("上書き取得の確認")
            msg_box.setText(
                "既存の基本情報JSONが見つかりました。\n"
                "再取得して上書き保存しますか？"
            )
            msg_box.setInformativeText(
                "• はい（上書き取得）: すべて再取得して最新データで上書き\n"
                "• いいえ（新規のみ取得）: 新規ファイルのみ取得します。\n"
                "  既存ファイルは内容が古くても更新されません。"
            )
            yes_btn = msg_box.addButton("はい（上書き取得）", QMessageBox.YesRole)
            no_btn = msg_box.addButton("いいえ（新規のみ取得）", QMessageBox.NoRole)
            msg_box.setDefaultButton(no_btn)
            msg_box.exec()
            force_download = msg_box.clickedButton() == yes_btn
        else:
            force_download = True  # 取得対象が存在しない場合は強制取得
        
        # === グループ選択ダイアログ（v2.1.16追加） ===
        selected_program_id = None
        group_json_path = get_dynamic_file_path("output/rde/data/group.json")
        
        if Path(group_json_path).exists():
            try:
                with open(group_json_path, "r", encoding="utf-8") as f:
                    group_data = json.load(f)
                
                # included配列からtype="group"を抽出
                groups = [item for item in group_data.get("included", []) 
                         if item.get("type") == "group"]
                
                if groups:
                    # 1件でも選択ダイアログを表示
                    selected_group = show_group_selection_dialog(groups, controller.parent)
                    if not selected_group:  # キャンセル時
                        logger.info("グループ選択がキャンセルされました")
                        return
                    selected_program_id = selected_group["id"]
                    logger.info(f"選択されたプログラム: {selected_group['name']}")
            except Exception as e:
                logger.warning(f"group.json の読み込みに失敗: {e}")
        
        # プログレス表示付きワーカーを作成
        worker = ProgressWorker(
            task_func=fetch_basic_info_logic,
            task_kwargs={
                'bearer_token': bearer_token,
                'parent': controller.parent,
                'webview': webview,
                'onlySelf': True,
                'searchWords': searchWords,
                'searchWordsBatch': searchWordsBatch,
                'skip_confirmation': True,
                'program_id': selected_program_id,
                'force_download': force_download,
            },
            task_name="検索付き基本情報取得"
        )
        
        # プログレス表示
        show_progress_dialog(controller.parent, "自分の基本情報取得", worker)
    except ImportError as e:
        logger.error(f"基本情報取得モジュールのインポートエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"基本情報取得機能の初期化に失敗しました: {e}")
    except Exception as e:
        logger.error(f"基本情報取得処理でエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"基本情報取得処理中にエラーが発生しました: {e}")

def summary_basic_info_to_Xlsx(controller):
    """
    基本情報をXLSXにまとめる
    
    v2.0.4改善:
    - BearerTokenManager統一
    - トークン検証の追加
    """
    try:
        from ..util.xlsx_exporter import summary_basic_info_to_Xlsx_logic
        from core.bearer_token_manager import BearerTokenManager
        from .summary_xlsx_options_dialog import prompt_summary_export_options
        
        # トークン取得
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
        
        # トークンが取得できない場合は処理を中止
        if not bearer_token:
            logger.warning("XLSX出力処理: トークンが取得できませんでした")
            QMessageBox.warning(
                controller.parent,
                "認証エラー",
                "認証トークンが取得できません。\n"
                "ログインタブでRDEシステムにログインしてから再度実行してください。"
            )
            return
        
        webview = getattr(controller.parent, 'webview', controller.parent)

        export_options = prompt_summary_export_options(controller.parent)
        if export_options is None:
            logger.info("まとめXLSX作成: ユーザーが出力設定ダイアログをキャンセルしました")
            return
        
        # プログレス表示付きワーカーを作成（詳細プログレス対応）
        worker = ProgressWorker(
            task_func=summary_basic_info_to_Xlsx_logic,
            task_kwargs={
                'bearer_token': bearer_token,
                'parent': controller.parent,
                'webview': webview,
                'export_options': export_options.to_payload()
            },
            task_name="まとめXLSX作成"
        )
        
        # プログレス表示
        show_progress_dialog(controller.parent, "まとめXLSX作成", worker)
    except ImportError as e:
        logger.error(f"XLSX出力モジュールのインポートエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"XLSX出力機能の初期化に失敗しました: {e}")
    except Exception as e:
        logger.error(f"XLSX出力処理でエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"XLSX出力処理中にエラーが発生しました: {e}")

def apply_basic_info_to_Xlsx(controller):
    """
    基本情報をXLSXに反映
    
    v2.0.4改善:
    - BearerTokenManager統一
    - トークン検証の追加
    """
    try:
        from ..util.xlsx_exporter import apply_basic_info_to_Xlsx_logic
        from core.bearer_token_manager import BearerTokenManager
        
        # トークン取得
        bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
        
        # トークンが取得できない場合は処理を中止
        if not bearer_token:
            logger.warning("XLSX反映処理: トークンが取得できませんでした")
            QMessageBox.warning(
                controller.parent,
                "認証エラー",
                "認証トークンが取得できません。\n"
                "ログインタブでRDEシステムにログインしてから再度実行してください。"
            )
            return
        
        webview = getattr(controller.parent, 'webview', controller.parent)
        
        # プログレス表示付きワーカーを作成
        worker = SimpleProgressWorker(
            task_func=apply_basic_info_to_Xlsx_logic,
            task_kwargs={
                'bearer_token': bearer_token,
                'parent': controller.parent,
                'webview': webview
            },
            task_name="XLSX反映"
        )
        
        # プログレス表示
        show_progress_dialog(controller.parent, "XLSX反映", worker)
    except ImportError as e:
        logger.error(f"XLSX反映モジュールのインポートエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"XLSX反映機能の初期化に失敗しました: {e}")
    except Exception as e:
        logger.error(f"XLSX反映処理でエラー: {e}")
        QMessageBox.critical(controller.parent, "エラー", f"XLSX反映処理中にエラーが発生しました: {e}")

def fetch_invoice_schema(controller):
    """
    invoiceSchemasを取得する
    
    v2.0.4改善:
    - BearerTokenManager統一
    - トークン検証の追加
    """
    from ..core.basic_info_logic import fetch_invoice_schemas
    from core.bearer_token_manager import BearerTokenManager
    
    # トークン取得
    bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
    
    # トークンが取得できない場合は処理を中止
    if not bearer_token:
        logger.warning("invoiceSchemas取得処理: トークンが取得できませんでした")
        QMessageBox.warning(
            controller.parent,
            "認証エラー",
            "認証トークンが取得できません。\n"
            "ログインタブでRDEシステムにログインしてから再度実行してください。"
        )
        return
    
    output_dir = get_dynamic_file_path("output/rde/data")

    parallel_max_workers = _get_basic_info_parallel_workers(controller, default=10)

    # プログレス表示付きワーカーを作成
    worker = ProgressWorker(
        task_func=fetch_invoice_schemas,
        task_kwargs={
            'bearer_token': bearer_token,
            'output_dir': output_dir,
            'max_workers': parallel_max_workers,
        },
        task_name="invoiceSchemas取得"
    )
    
    # プログレス表示
    show_progress_dialog(controller.parent, "invoiceSchemas取得", worker)

def fetch_sample_info_only(controller):
    """
    サンプル情報のみを強制取得する
    
    v2.0.4改善:
    - BearerTokenManager統一
    - トークン検証の追加
    """
    from ..core.basic_info_logic import fetch_sample_info_only as fetch_sample_info_only_logic
    from core.bearer_token_manager import BearerTokenManager
    
    # トークン取得
    bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
    
    # トークンが取得できない場合は処理を中止
    if not bearer_token:
        logger.warning("サンプル情報取得処理: トークンが取得できませんでした")
        QMessageBox.warning(
            controller.parent,
            "認証エラー",
            "認証トークンが取得できません。\n"
            "ログインタブでRDEシステムにログインしてから再度実行してください。"
        )
        return
    
    # 確認ダイアログ
    reply = QMessageBox.question(
        controller.parent, 
        "サンプル情報強制取得の確認",
        "全サンプル情報を強制取得しますか？\n\n実行内容:\n• 既存ファイルを上書き更新\n• subGroup.jsonの全グループIDでサンプル情報を取得\n• 最新のサンプル情報に更新\n\n※事前にサブグループ情報が必要です",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
    )
    
    if reply != QMessageBox.Yes:
        logger.info("サンプル情報強制取得処理はユーザーによりキャンセルされました。")
        return
    
    # プログレス表示付きワーカーを作成
    parallel_max_workers = _get_basic_info_parallel_workers(controller, default=10)
    worker = ProgressWorker(
        task_func=fetch_sample_info_only_logic,
        task_kwargs={
            'bearer_token': bearer_token,
            'output_dir': get_dynamic_file_path("output/rde/data"),
            'max_workers': parallel_max_workers,
        },
        task_name="サンプル情報強制取得"
    )
    
    # プログレス表示
    show_progress_dialog(controller.parent, "サンプル情報強制取得", worker)

def fetch_common_info_only(controller):
    """
    9種類の共通情報JSONのみを取得する
    
    v2.0.1改善:
    - トークン検証の追加
    - エラーメッセージの明確化
    - 再ログイン促進機能の統合
    
    v2.1.16追加:
    - グループ選択ダイアログの統合
    """
    import json
    from pathlib import Path
    from ..core.basic_info_logic import fetch_common_info_only_logic
    from core.bearer_token_manager import BearerTokenManager
    from config.common import get_dynamic_file_path
    from .group_selection_dialog import show_group_selection_dialog
    
    # トークン取得（v2.0.1: BearerTokenManagerを使用）
    bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
    
    # トークンが取得できない場合は処理を中止
    if not bearer_token:
        logger.warning("共通情報取得処理: トークンが取得できませんでした")
        QMessageBox.warning(
            controller.parent,
            "認証エラー",
            "認証トークンが取得できません。\n"
            "ログインタブでRDEシステムにログインしてから再度実行してください。"
        )
        return
    
    webview = getattr(controller.parent, 'webview', controller.parent)
    
    # 確認ダイアログ
    reply = QMessageBox.question(
        controller.parent, 
        "共通情報取得の確認",
        "9種類の共通情報JSONを更新しますか？\n\n取得対象:\n• ユーザー情報\n• グループ情報\n• 組織情報\n• 装置情報\n• テンプレート情報\n• データセット一覧\n\n※個別データセットJSONは取得しません",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
    )
    
    if reply != QMessageBox.Yes:
        logger.info("共通情報取得処理はユーザーによりキャンセルされました。")
        return
    
    target_files = [
        get_dynamic_file_path("output/rde/data/self.json"),
        get_dynamic_file_path("output/rde/data/group.json"),
        get_dynamic_file_path("output/rde/data/groupDetail.json"),
        get_dynamic_file_path("output/rde/data/subGroup.json"),
        get_dynamic_file_path("output/rde/data/organization.json"),
        get_dynamic_file_path("output/rde/data/instrumentType.json"),
        get_dynamic_file_path("output/rde/data/template.json"),
        get_dynamic_file_path("output/rde/data/instruments.json"),
        get_dynamic_file_path("output/rde/data/licenses.json"),
        get_dynamic_file_path("output/rde/data/dataset.json"),
    ]
    existing_files = [path for path in target_files if Path(path).exists()]
    force_download = False

    if existing_files:
        msg_box = QMessageBox(controller.parent)
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setWindowTitle("上書き取得の確認")
        msg_box.setText(
            "既存の共通情報JSONが見つかりました。\n"
            "再取得して上書き保存しますか？"
        )
        msg_box.setInformativeText(
            "• はい（上書き取得）: すべて再取得して最新データで上書き\n"
            "• いいえ（新規のみ取得）: 新規ファイルのみ取得します。\n"
            "  既存ファイルは内容が古くても更新されません。"
        )
        yes_btn = msg_box.addButton("はい（上書き取得）", QMessageBox.YesRole)
        no_btn = msg_box.addButton("いいえ（新規のみ取得）", QMessageBox.NoRole)
        msg_box.setDefaultButton(no_btn)
        msg_box.exec()
        force_download = msg_box.clickedButton() == yes_btn

    # === グループ選択ダイアログ（v2.1.16追加） ===
    selected_program_id = None
    group_json_path = get_dynamic_file_path("output/rde/data/group.json")
    
    if Path(group_json_path).exists():
        try:
            with open(group_json_path, "r", encoding="utf-8") as f:
                group_data = json.load(f)
            
            # included配列からtype="group"を抽出
            groups = [item for item in group_data.get("included", []) 
                     if item.get("type") == "group"]
            
            if groups:
                # 1件でも選択ダイアログを表示
                selected_group = show_group_selection_dialog(groups, controller.parent)
                if not selected_group:  # キャンセル時
                    logger.info("グループ選択がキャンセルされました")
                    return
                selected_program_id = selected_group["id"]
                logger.info(f"選択されたプログラム: {selected_group['name']}")
        except Exception as e:
            logger.warning(f"group.json の読み込みに失敗: {e}")
    
    # プログレス表示付きワーカーを作成
    worker = ProgressWorker(
        task_func=fetch_common_info_only_logic,
        task_kwargs={
            'bearer_token': bearer_token,
            'parent': controller.parent,
            'webview': webview,
            'program_id': selected_program_id,
            'force_download': force_download,
        },
        task_name="共通情報取得"
    )
    
    # プログレス表示
    def on_finished_with_refresh(success, message):
        def handle_finished():
            if success:
                QMessageBox.information(controller.parent, "共通情報取得", message)
                # JSON状況表示を更新
                QTimer.singleShot(100, lambda: refresh_json_status_display(controller))
            else:
                QMessageBox.critical(controller.parent, "共通情報取得 - エラー", message)
        QTimer.singleShot(0, handle_finished)
    
    # 通常のプログレス表示
    progress_dialog = show_progress_dialog(controller.parent, "共通情報取得", worker)
    
    # 完了時処理を上書き
    worker.finished.disconnect()  # 既存の接続を削除
    worker.finished.connect(on_finished_with_refresh)


def fetch_common_info_only2(controller):
    """共通情報取得2: 取得対象/条件を事前選択して共通情報を取得する"""
    from core.bearer_token_manager import BearerTokenManager
    from .common_info_selection_dialog import (
        CommonInfoSelectionDialog,
        load_common_info2_selection_state,
        save_common_info2_selection_state,
    )
    from ..core.common_info_selection_logic import fetch_common_info_with_selection_logic

    bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
    if not bearer_token:
        logger.warning("共通情報取得2: トークンが取得できませんでした")
        QMessageBox.warning(
            controller.parent,
            "認証エラー",
            "認証トークンが取得できません。\n"
            "ログインタブでRDEシステムにログインしてから再度実行してください。",
        )
        return

    previous_state = load_common_info2_selection_state()
    dialog = CommonInfoSelectionDialog(parent=controller.parent, initial_state=previous_state)
    if dialog.exec() != QDialog.Accepted:
        logger.info("共通情報取得2はユーザーによりキャンセルされました（ダイアログ）")
        return

    selection_state = dialog.get_state()
    save_common_info2_selection_state(selection_state)

    webview = getattr(controller.parent, 'webview', controller.parent)

    worker = ProgressWorker(
        task_func=fetch_common_info_with_selection_logic,
        task_kwargs={
            'bearer_token': bearer_token,
            'parent': controller.parent,
            'webview': webview,
            'selection_state': selection_state,
        },
        task_name="共通情報取得2",
    )

    def on_finished_with_refresh(success, message):
        def handle_finished():
            if success:
                QMessageBox.information(controller.parent, "共通情報取得2", message)
                QTimer.singleShot(100, lambda: refresh_json_status_display(controller))
            else:
                QMessageBox.critical(controller.parent, "共通情報取得2 - エラー", message)
        QTimer.singleShot(0, handle_finished)

    progress_dialog = show_progress_dialog(controller.parent, "共通情報取得2", worker, show_completion_dialog=False)
    worker.finished.disconnect()
    worker.finished.connect(on_finished_with_refresh)

    return progress_dialog

def refresh_json_status_display(controller):
    """
    JSON取得状況表示を更新
    """
    if hasattr(controller, 'basic_unified_status_widget'):
        controller.basic_unified_status_widget.update_status()
    elif hasattr(controller, 'json_status_widget'):
        controller.json_status_widget.update_status()

def create_json_status_widget(parent=None):
    """
    JSON取得状況を表示するウィジェットを作成
    """
    from qt_compat.widgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, QPushButton
    from qt_compat.core import Qt
    
    class JsonStatusWidget(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.init_ui()
            # テーマ変更フック登録（メソッド定義後に接続されるよう遅延タイマー使用）
            from qt_compat.core import QTimer
            QTimer.singleShot(0, self._connect_theme_signal)
            
        def init_ui(self):
            layout = QVBoxLayout(self)
            
            # タイトル（必要ならここでラベル追加）
            
            # ボタンレイアウト（更新・デバッグ）
            btn_layout = QHBoxLayout()
            
            # 更新ボタン
            self.refresh_btn = QPushButton("状況更新")
            self.refresh_btn.setMaximumWidth(100)
            self.refresh_btn.clicked.connect(self.update_status)
            btn_layout.addWidget(self.refresh_btn)
            
            # API デバッグボタン
            self.debug_btn = QPushButton("🔍 API Debug")
            self.debug_btn.setMaximumWidth(120)
            self.debug_btn.clicked.connect(self.show_api_debug)
            btn_layout.addWidget(self.debug_btn)
            
            btn_layout.addStretch()
            layout.addLayout(btn_layout)
            
            # ステータス表示エリア
            self.status_text = QTextEdit()
            self.status_text.setReadOnly(True)
            self.status_text.setMaximumHeight(200)
            layout.addWidget(self.status_text)
            
            # 初期状態を表示
            self.update_status()

            # テーマ依存スタイル適用
            self.refresh_theme()
            
        def update_status(self):
            try:
                from ..core.basic_info_logic import get_json_status_info
                json_info = get_json_status_info()
                status_text = "【共通JSONファイル】\n"
                
                common_files = [
                    ("self.json", "ユーザー情報"),
                    ("group.json", "グループ情報"),
                    ("groupDetail.json", "グループ詳細"),
                    ("subGroup.json", "サブグループ"),
                    ("organization.json", "組織情報"),
                    ("instrumentType.json", "装置タイプ"),
                    ("template.json", "テンプレート"),
                    ("instruments.json", "設備情報"),
                    ("licenses.json", "利用ライセンス"),
                    ("info.json", "統合情報"),
                    ("dataset.json", "データセット一覧")
                ]
                
                for file_name, description in common_files:
                    info = json_info.get(file_name, {})
                    status = "✓" if info.get("exists") else "✗"
                    modified = info.get("modified", "未取得")
                    size = info.get("size_kb", 0)
                    status_text += f"{status} {description:12} | {modified} | {size:6.1f}KB\n"
                
                summary = json_info.get("summary", {})
                status_text += f"\n【個別JSONファイル】\n"
                status_text += f"個別データセット: {summary.get('individual_datasets', 0):4d} 件\n"
                status_text += f"データエントリ  : {summary.get('data_entries', 0):4d} 件\n"
                status_text += f"サンプル情報    : {summary.get('sample_files', 0):4d} 件\n"
                status_text += f"共通ファイル    : {summary.get('common_files_count', 0):4d}/11 件"
                
                self.status_text.setPlainText(status_text)
            except ImportError as e:
                self.status_text.setPlainText(f"モジュールインポートエラー: {e}")
            except Exception as e:
                self.status_text.setPlainText(f"状況取得エラー: {e}")
        def refresh_theme(self, *_args, **_kwargs):
            """テーマ変更時に必要なスタイルを再適用"""
            try:
                self.refresh_btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                        border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BORDER)};
                        border-radius: 4px;
                        padding: 5px;
                    }}
                    QPushButton:hover {{
                        background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
                    }}
                    QPushButton:pressed {{
                        background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_PRESSED)};
                    }}
                    """
                )

                self.debug_btn.setStyleSheet(
                    f"""
                    QPushButton {{
                        background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND)};
                        color: {get_color(ThemeKey.BUTTON_SECONDARY_TEXT)};
                        border: 1px solid {get_color(ThemeKey.BUTTON_SECONDARY_BORDER)};
                        border-radius: 4px;
                        padding: 5px;
                    }}
                    QPushButton:hover {{
                        background-color: {get_color(ThemeKey.BUTTON_SECONDARY_BACKGROUND_HOVER)};
                    }}
                    """
                )

                self.status_text.setStyleSheet(
                    f"""
                    font-family: 'Consolas';
                    font-size: 9pt;
                    background-color: {get_color(ThemeKey.INPUT_BACKGROUND)};
                    color: {get_color(ThemeKey.TEXT_PRIMARY)};
                    border: 1px solid {get_color(ThemeKey.PANEL_BORDER)};
                    border-radius: 4px;
                    """
                )
            except Exception as e:
                logger.debug("JsonStatusWidget refresh_theme failed: %s", e)

        def _connect_theme_signal(self):
            try:
                from classes.theme.theme_manager import ThemeManager
                ThemeManager.instance().theme_changed.connect(self.refresh_theme)
                self.refresh_theme()
            except Exception as e:
                logger.debug("JsonStatusWidget theme signal connect failed: %s", e)
        
        def show_api_debug(self):
            """APIアクセス履歴ダイアログを表示"""
            try:
                from .api_history_dialog import APIAccessHistoryDialog
                from net.api_call_recorder import get_global_recorder
                
                # グローバルレコーダーを取得
                recorder = get_global_recorder()
                
                # 記録がない場合は警告
                if not recorder.get_records():
                    QMessageBox.information(
                        self,
                        "APIアクセス履歴",
                        "まだAPIアクセス記録がありません。\n\n"
                        "基本情報取得などを実行すると、\n"
                        "APIアクセス履歴が記録されます。"
                    )
                    return
                
                # ダイアログを表示
                dialog = APIAccessHistoryDialog(recorder=recorder, parent=self)
                dialog.exec()
            except ImportError as e:
                logger.error(f"API Debug Dialog import error: {e}")
                QMessageBox.critical(
                    self,
                    "エラー",
                    f"APIデバッグ機能の読み込みに失敗しました:\n{e}"
                )
            except Exception as e:
                logger.error(f"show_api_debug error: {e}")
                QMessageBox.critical(
                    self,
                    "エラー",
                    f"APIデバッグ機能でエラーが発生しました:\n{e}"
                )
    
    return JsonStatusWidget(parent)

def execute_individual_stage_ui(controller, stage_name):
    """
    個別段階実行をUIから呼び出す
    """
    from ..core.basic_info_logic import execute_individual_stage, STAGE_FUNCTIONS
    
    if stage_name not in STAGE_FUNCTIONS:
        QMessageBox.warning(controller.parent, "エラー", f"不正な段階名です: {stage_name}")
        return
    
    # セパレータアイテムの場合は実行しない
    if STAGE_FUNCTIONS[stage_name] is None:
        QMessageBox.information(controller.parent, "情報", f"「{stage_name}」はセパレータです。実行できません。")
        return
    
    # トークン取得（v2.0.4）
    from core.bearer_token_manager import BearerTokenManager
    bearer_token = BearerTokenManager.get_token_with_relogin_prompt(controller.parent)
    
    # トークンが取得できない場合は処理を中止
    if not bearer_token:
        logger.warning(f"個別段階実行（{stage_name}）: トークンが取得できませんでした")
        QMessageBox.warning(
            controller.parent,
            "認証エラー",
            "認証トークンが取得できません。\n"
            "ログインタブでRDEシステムにログインしてから再度実行してください。"
        )
        return
    
    webview = getattr(controller.parent, 'webview', controller.parent)

    parallel_max_workers = _get_basic_info_parallel_workers(controller, default=10)
    
    # 確認ダイアログ
    reply = QMessageBox.question(
        controller.parent, 
        f"{stage_name}実行の確認",
        f"{stage_name}を個別実行しますか？\n\n実行対象: {stage_name}\n\n※前段階の情報が必要な場合があります",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
    )
    
    if reply != QMessageBox.Yes:
        logger.info(f"{stage_name}の個別実行はユーザーによりキャンセルされました")
        return
    
    # データセット情報の場合は検索条件を取得
    onlySelf = False
    searchWords = None
    searchWordsBatch = None
    if stage_name == "データセット情報":
        selection = getattr(controller, '_basic_info_search_state', None)
        if not isinstance(selection, BasicInfoSearchSelection):
            # メイン画面から入力欄を除去したため、必要ならここで検索条件ダイアログを表示
            selection = prompt_basic_info_search_options(
                controller.parent,
                default_keyword="",
                previous_state=None,
            )
            if not selection:
                logger.info("データセット情報(個別実行)はユーザーによりキャンセルされました。(検索ダイアログ)")
                return
            controller._basic_info_search_state = selection

        if isinstance(selection, BasicInfoSearchSelection):
            onlySelf = selection.mode in ("self", PATTERN_MANUAL, PATTERN_INSTITUTION)
            searchWords = selection.manual_keyword or None
            if selection.keyword_batch:
                searchWordsBatch = list(selection.keyword_batch)

    force_download = False
    if stage_name == "グループ関連情報":
        from pathlib import Path
        from config.common import get_dynamic_file_path

        target_files = [
            get_dynamic_file_path("output/rde/data/group.json"),
            get_dynamic_file_path("output/rde/data/groupDetail.json"),
            get_dynamic_file_path("output/rde/data/subGroup.json"),
        ]
        existing_files = [path for path in target_files if Path(path).exists()]

        if existing_files:
            overwrite_reply = QMessageBox.question(
                controller.parent,
                "上書き取得の確認",
                "既存のグループ関連JSONが見つかりました。\n"
                "再取得して上書き保存しますか？\n\n"
                "• はい: 再取得して上書き\n"
                "• いいえ: 既存ファイルを維持",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            force_download = overwrite_reply == QMessageBox.Yes

    
    # プログレス表示付きワーカーを作成
    worker = ProgressWorker(
        task_func=execute_individual_stage,
        task_kwargs={
            'stage_name': stage_name,
            'bearer_token': bearer_token,
            'webview': webview,
            'onlySelf': onlySelf,
            'searchWords': searchWords,
            'searchWordsBatch': searchWordsBatch,
            'parent_widget': controller.parent,
            'force_program_dialog': (stage_name == "グループ関連情報"),
            'force_download': force_download,
            'parallel_max_workers': parallel_max_workers,
        },
        task_name=f"{stage_name}実行"
    )
    
    # プログレス表示
    import time
    _started = time.perf_counter()

    def _format_elapsed(seconds: float) -> str:
        try:
            total = int(round(seconds))
            h = total // 3600
            m = (total % 3600) // 60
            s = total % 60
            if h > 0:
                return f"{h}:{m:02d}:{s:02d}"
            return f"{m}:{s:02d}"
        except Exception:
            return ""

    def on_finished_with_refresh(success, message):
        def handle_finished():
            elapsed = time.perf_counter() - _started
            elapsed_text = _format_elapsed(elapsed)
            if elapsed_text:
                message_with_time = f"{message}\n\n所要時間: {elapsed_text}"
            else:
                message_with_time = message
            if success:
                QMessageBox.information(controller.parent, f"{stage_name}実行", message_with_time)
                # JSON状況表示を更新
                if hasattr(controller, 'basic_unified_status_widget'):
                    QTimer.singleShot(100, lambda: controller.basic_unified_status_widget.update_status())
                elif hasattr(controller, 'json_status_widget'):
                    QTimer.singleShot(100, lambda: controller.json_status_widget.update_status())
            else:
                QMessageBox.critical(controller.parent, f"{stage_name}実行 - エラー", message_with_time)
        QTimer.singleShot(0, handle_finished)
    
    # 通常のプログレス表示
    progress_dialog = show_progress_dialog(controller.parent, f"{stage_name}実行", worker)
    
    # 完了時処理を上書き
    worker.finished.disconnect()  # 既存の接続を削除
    worker.finished.connect(on_finished_with_refresh)

def create_individual_execution_widget(parent=None):
    """
    個別実行用のドロップダウンとボタンを作成
    """
    from qt_compat.widgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                                QComboBox, QPushButton, QTextEdit)
    from qt_compat.core import QTimer
    from ..core.basic_info_logic import STAGE_FUNCTIONS
    
    class IndividualExecutionWidget(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.controller = None  # 後で設定される
            self.init_ui()
            # 自動更新は統合ステータス側で実施する
            
        def init_ui(self):
            layout = QVBoxLayout(self)
            
            # タイトル
            #title_label = QLabel("段階別個別実行")
            # title_label のスタイルはテーマ側で制御
            #layout.addWidget(title_label)
            
            # 実行コントロール行
            control_layout = QHBoxLayout()
            
            # ラベル
            label = QLabel("個別取得:")
            label.setMinimumWidth(70)
            control_layout.addWidget(label)
            
            # ドロップダウンリスト
            self.stage_combo = QComboBox()
            self.stage_combo.addItems(list(STAGE_FUNCTIONS.keys()))
            self.stage_combo.setMinimumWidth(200)
            self.stage_combo.currentTextChanged.connect(self.on_stage_selection_changed)
            control_layout.addWidget(self.stage_combo)
            
            # 実行ボタン
            self.execute_btn = QPushButton("実行")
            self.execute_btn.setMaximumWidth(80)
            self.execute_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_SUCCESS_TEXT)};
                    border: 1px solid {get_color(ThemeKey.BUTTON_SUCCESS_BORDER)};
                    border-radius: 4px;
                    padding: 5px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_HOVER)};
                }}
                QPushButton:pressed {{
                    background-color: {get_color(ThemeKey.BUTTON_SUCCESS_BACKGROUND_PRESSED)};
                }}
            """)
            self.execute_btn.clicked.connect(self.execute_stage)
            control_layout.addWidget(self.execute_btn)
            
            # 更新ボタン
            self.refresh_btn = QPushButton("状況更新")
            self.refresh_btn.setMaximumWidth(80)
            self.refresh_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND)};
                    color: {get_color(ThemeKey.BUTTON_PRIMARY_TEXT)};
                    border: 1px solid {get_color(ThemeKey.BUTTON_PRIMARY_BORDER)};
                    border-radius: 4px;
                    padding: 5px;
                }}
                QPushButton:hover {{
                    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_HOVER)};
                }}
                QPushButton:pressed {{
                    background-color: {get_color(ThemeKey.BUTTON_PRIMARY_BACKGROUND_PRESSED)};
                }}
            """)
            self.refresh_btn.clicked.connect(self.update_stage_status)
            control_layout.addWidget(self.refresh_btn)
            
            layout.addLayout(control_layout)
            # 段階別完了状況/取得状況は統合ステータス表示に一本化
            self.update_stage_status()
            
        def set_controller(self, controller):
            """コントローラーを設定"""
            self.controller = controller
            
        def execute_stage(self):
            """選択された段階を実行"""
            if not self.controller:
                QMessageBox.warning(self, "エラー", "コントローラーが設定されていません")
                return
                
            stage_name = self.stage_combo.currentText()
            execute_individual_stage_ui(self.controller, stage_name)
            
            # 実行後に状況を更新
            QTimer.singleShot(1000, self.update_stage_status)
            
        def on_stage_selection_changed(self):
            """段階選択が変更された時の処理"""
            self.update_stage_status()
            
        def update_stage_status(self):
            try:
                if self.controller is None:
                    return

                if hasattr(self.controller, 'basic_unified_status_widget'):
                    self.controller.basic_unified_status_widget.update_status()
                elif hasattr(self.controller, 'json_status_widget'):
                    # 統合ウィジェットがない場合のフォールバック
                    self.controller.json_status_widget.update_status()
            except Exception as e:
                import traceback
                logger.error(f"統合ステータス更新エラー: {e}")
                logger.error(traceback.format_exc())
    
    return IndividualExecutionWidget(parent)

