"""
データセット編集専用ウィジェット
"""
import os
import json
import datetime
import webbrowser
import shutil
import codecs
from qt_compat.widgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QGridLayout, 
    QPushButton, QMessageBox, QScrollArea, QCheckBox, QRadioButton, 
    QButtonGroup, QDialog, QTextEdit, QComboBox, QCompleter, QDateEdit,
    QListWidget, QListWidgetItem, QProgressDialog, QApplication
)
from qt_compat.core import Qt, QDate, QTimer
from config.common import get_dynamic_file_path
from classes.dataset.util.dataset_refresh_notifier import get_dataset_refresh_notifier
from classes.dataset.ui.taxonomy_builder_dialog import TaxonomyBuilderDialog
from classes.dataset.ui.ai_suggestion_dialog import AISuggestionDialog


def repair_json_file(file_path):
    """破損したJSONファイルの修復を試行"""
    try:
        import codecs
        import re
        
        print("[INFO] JSONファイル修復を開始")
        print(f"[DEBUG] 対象ファイル: {file_path}")
        
        # 複数のエンコーディングでの読み込みを試行
        encodings = ['utf-8', 'utf-8-sig', 'cp1252', 'latin1', 'shift_jis']
        
        for encoding in encodings:
            try:
                print(f"[DEBUG] エンコーディング '{encoding}' で読み込み試行")
                with codecs.open(file_path, 'r', encoding=encoding, errors='replace') as f:
                    content = f.read()
                
                print(f"[DEBUG] 読み込み完了。文字数: {len(content)}")
                
                # より包括的なクリーンアップ
                # 1. すべての制御文字を除去（\t, \n, \r, スペースは保持）
                print("[DEBUG] 制御文字クリーンアップを実行")
                original_len = len(content)
                # \x00-\x1F の制御文字のうち、\t(\x09), \n(\x0A), \r(\x0D), space(\x20)以外を除去
                content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', content)
                
                # 2. Unicode置換文字(\uFFFD)を除去
                content = content.replace('\uFFFD', '')
                
                # 3. その他の問題のある文字を除去
                # NULL文字やその他の問題を引き起こす可能性のある文字
                content = content.replace('\x00', '')
                
                print(f"[DEBUG] クリーンアップ後の文字数: {len(content)} (削減: {original_len - len(content)}文字)")
                
                # JSONとしてパース可能かテスト
                try:
                    data = json.loads(content)
                    print(f"[INFO] エンコーディング '{encoding}' で読み込み成功")
                    
                    # 修復したファイルをUTF-8で保存
                    backup_path = file_path + '.corrupted_backup'
                    shutil.copy2(file_path, backup_path)
                    print(f"[INFO] 破損ファイルをバックアップ: {backup_path}")
                    
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    print(f"[INFO] ファイルをUTF-8で再保存しました")
                    
                    return data
                    
                except json.JSONDecodeError as json_err:
                    # JSONパースエラーの詳細を表示
                    print(f"[DEBUG] JSONパースエラー詳細: {json_err}")
                    print(f"[DEBUG] エラー位置: 行{getattr(json_err, 'lineno', '不明')} 列{getattr(json_err, 'colno', '不明')}")
                    
                    # エラー位置周辺のテキストを表示
                    if hasattr(json_err, 'pos') and json_err.pos:
                        start_pos = max(0, json_err.pos - 50)
                        end_pos = min(len(content), json_err.pos + 50)
                        context = content[start_pos:end_pos]
                        print(f"[DEBUG] エラー位置周辺のテキスト: {context!r}")
                    
                    continue
                
            except (UnicodeError, Exception) as e:
                print(f"[DEBUG] エンコーディング '{encoding}' 失敗: {e}")
                continue
        
        print("[ERROR] すべてのエンコーディング試行が失敗しました")
        
        # 最後の手段として、ファイルの修復を試みる
        print("[INFO] 最後の手段として、部分的な修復を試行")
        try:
            return attempt_partial_recovery(file_path)
        except Exception as recovery_err:
            print(f"[ERROR] 部分回復も失敗: {recovery_err}")
        
        return None
        
    except Exception as e:
        print(f"[ERROR] ファイル修復中の予期しないエラー: {e}")
        import traceback
        traceback.print_exc()
        return None


def attempt_partial_recovery(file_path):
    """部分的な修復を試行"""
    import re
    
    print("[DEBUG] 部分的修復を開始")
    
    # バイナリモードで読み込み、有効なJSON部分を抽出を試みる
    with open(file_path, 'rb') as f:
        raw_data = f.read()
    
    # UTF-8で読み込み、エラー文字を置換
    content = raw_data.decode('utf-8', errors='replace')
    
    # JSON構造の開始と終了を見つける
    json_start = content.find('{"data"')
    if json_start == -1:
        json_start = content.find('{"')
    
    if json_start == -1:
        print("[ERROR] JSON構造の開始が見つかりません")
        return None
    
    print(f"[DEBUG] JSON開始位置: {json_start}")
    
    # 後方から有効な終了位置を見つける
    json_end = content.rfind('}')
    if json_end == -1:
        print("[ERROR] JSON構造の終了が見つかりません")
        return None
    
    print(f"[DEBUG] JSON終了位置: {json_end}")
    
    # 部分的なJSONを抽出
    partial_json = content[json_start:json_end + 1]
    
    # 基本的なクリーンアップ
    partial_json = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', partial_json)
    partial_json = partial_json.replace('\uFFFD', '')
    
    try:
        data = json.loads(partial_json)
        print("[INFO] 部分的修復に成功")
        return data
    except json.JSONDecodeError as e:
        print(f"[ERROR] 部分的修復も失敗: {e}")
        return None


def get_grant_numbers_from_dataset(dataset_data):
    """
    データセットから対応するサブグループの課題番号リストを取得
    
    Args:
        dataset_data (dict): データセット情報
        
    Returns:
        set: 課題番号のセット
    """
    if not dataset_data:
        return set()
    
    grant_numbers = set()
    try:
        # データセットのgrantNumberを取得
        dataset_grant_number = dataset_data.get("attributes", {}).get("grantNumber", "")
        if dataset_grant_number:
            grant_numbers.add(dataset_grant_number)
            print(f"[DEBUG] データセットの課題番号: {dataset_grant_number}")
            
            # このgrantNumberを持つサブグループを探し、そのサブグループの全課題番号を取得
            sub_group_path = get_dynamic_file_path('output/rde/data/subGroup.json')
            if os.path.exists(sub_group_path):
                with open(sub_group_path, encoding="utf-8") as f:
                    sub_group_data = json.load(f)
                
                # このgrantNumberを含むサブグループを検索
                for item in sub_group_data.get("included", []):
                    if item.get("type") == "group" and item.get("attributes", {}).get("groupType") == "TEAM":
                        subjects = item.get("attributes", {}).get("subjects", [])
                        # このグループにデータセットのgrantNumberが含まれているかチェック
                        group_grant_numbers = set()
                        dataset_grant_found = False
                        
                        for subject in subjects:
                            subject_grant_number = subject.get("grantNumber", "")
                            if subject_grant_number:
                                group_grant_numbers.add(subject_grant_number)
                                if subject_grant_number == dataset_grant_number:
                                    dataset_grant_found = True
                        
                        # このサブグループがデータセットの課題番号を含む場合、このグループの全課題番号を返す
                        if dataset_grant_found:
                            grant_numbers = group_grant_numbers
                            group_name = item.get("attributes", {}).get("name", "不明")
                            print(f"[DEBUG] データセットのサブグループ '{group_name}' の全課題番号: {sorted(grant_numbers)}")
                            break
    
    except Exception as e:
        print(f"[ERROR] データセットから課題番号取得に失敗: {e}")
    
    return grant_numbers


def get_user_grant_numbers():
    """
    ログインユーザーが属するサブグループのgrantNumberリストを取得
    dataset_open_logic.pyと同様の処理
    """
    sub_group_path = get_dynamic_file_path('output/rde/data/subGroup.json')
    self_path = get_dynamic_file_path('output/rde/data/self.json')
    user_grant_numbers = set()
    
    print(f"[DEBUG] サブグループファイルパス: {sub_group_path}")
    print(f"[DEBUG] セルフファイルパス: {self_path}")
    print(f"[DEBUG] サブグループファイル存在: {os.path.exists(sub_group_path)}")
    print(f"[DEBUG] セルフファイル存在: {os.path.exists(self_path)}")
    
    try:
        # ログインユーザーID取得
        with open(self_path, encoding="utf-8") as f:
            self_data = json.load(f)
        user_id = self_data.get("data", {}).get("id", None)
        print(f"[DEBUG] ユーザーID: {user_id}")
        
        if not user_id:
            print("[ERROR] self.jsonからユーザーIDが取得できませんでした。")
            return user_grant_numbers
        
        # ユーザーが属するサブグループを抽出
        with open(sub_group_path, encoding="utf-8") as f:
            sub_group_data = json.load(f)
        
        groups_count = 0
        for item in sub_group_data.get("included", []):
            if item.get("type") == "group" and item.get("attributes", {}).get("groupType") == "TEAM":
                groups_count += 1
                roles = item.get("attributes", {}).get("roles", [])
                # ユーザーがこのグループのメンバーかチェック
                user_in_group = False
                for r in roles:
                    if r.get("userId") == user_id:
                        if r.get("role") in ["OWNER", "ASSISTANT"]:
                            user_in_group = True
                            break
                
                if user_in_group:
                    # このグループのgrantNumbersを取得
                    subjects = item.get("attributes", {}).get("subjects", [])
                    group_name = item.get("attributes", {}).get("name", "不明")
                    print(f"[DEBUG] ユーザーが所属するグループ: '{group_name}' (課題数: {len(subjects)})")
                    
                    for subject in subjects:
                        grant_number = subject.get("grantNumber", "")
                        if grant_number:
                            user_grant_numbers.add(grant_number)
                            print(f"[DEBUG]   課題番号追加: {grant_number}")
        
        print(f"[DEBUG] 検査したTEAMグループ数: {groups_count}")
        print(f"[DEBUG] 最終的なユーザー課題番号: {sorted(user_grant_numbers)}")
    
    except Exception as e:
        print(f"[ERROR] ユーザーgrantNumber取得に失敗: {e}")
        import traceback
        traceback.print_exc()
    
    return user_grant_numbers


def create_dataset_edit_widget(parent, title, color, create_auto_resize_button):
    """データセット編集専用ウィジェット"""
    widget = QWidget()
    layout = QVBoxLayout()
    
    # タイトル
    title_label = QLabel(f"{title}機能")
    title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #1976d2; padding: 10px;")
    #layout.addWidget(title_label)
    
    # フィルタ設定エリア
    filter_widget = QWidget()
    filter_layout = QVBoxLayout()
    filter_layout.setContentsMargins(0, 0, 0, 0)
    
    # フィルタタイプ選択（ラジオボタン）
    filter_type_widget = QWidget()
    filter_type_layout = QHBoxLayout()
    filter_type_layout.setContentsMargins(0, 0, 0, 0)
    
    filter_type_label = QLabel("表示データセット:")
    filter_type_label.setMinimumWidth(120)
    filter_type_label.setStyleSheet("font-weight: bold;")
    
    filter_user_only_radio = QRadioButton("ユーザー所属のみ")
    filter_others_only_radio = QRadioButton("その他のみ")
    filter_all_radio = QRadioButton("すべて")
    filter_user_only_radio.setChecked(True)  # デフォルトは「ユーザー所属のみ」
    
    filter_type_layout.addWidget(filter_type_label)
    filter_type_layout.addWidget(filter_user_only_radio)
    filter_type_layout.addWidget(filter_others_only_radio)
    filter_type_layout.addWidget(filter_all_radio)
    filter_type_layout.addStretch()  # 右側にスペースを追加
    
    filter_type_widget.setLayout(filter_type_layout)
    filter_layout.addWidget(filter_type_widget)
    
    # 課題番号部分一致検索
    grant_number_filter_widget = QWidget()
    grant_number_filter_layout = QHBoxLayout()
    grant_number_filter_layout.setContentsMargins(0, 0, 0, 0)
    
    grant_number_filter_label = QLabel("課題番号絞り込み:")
    grant_number_filter_label.setMinimumWidth(120)
    grant_number_filter_label.setStyleSheet("font-weight: bold;")
    
    grant_number_filter_edit = QLineEdit()
    grant_number_filter_edit.setPlaceholderText("課題番号の一部を入力（部分一致検索・リアルタイム絞り込み）")
    grant_number_filter_edit.setMinimumWidth(400)
    
    # キャッシュ更新ボタンを追加
    cache_refresh_button = QPushButton("キャッシュ更新")
    cache_refresh_button.setMaximumWidth(100)
    cache_refresh_button.setStyleSheet("background-color: #FF5722; color: white; font-weight: bold; border-radius: 4px; padding: 5px;")
    cache_refresh_button.setToolTip("データセット一覧を強制的に再読み込みしてキャッシュを更新します\n大量データの場合はプログレス表示されます")
    
    grant_number_filter_layout.addWidget(grant_number_filter_label)
    grant_number_filter_layout.addWidget(grant_number_filter_edit)
    grant_number_filter_layout.addWidget(cache_refresh_button)
    grant_number_filter_layout.addStretch()
    
    grant_number_filter_widget.setLayout(grant_number_filter_layout)
    filter_layout.addWidget(grant_number_filter_widget)
    
    filter_widget.setLayout(filter_layout)
    layout.addWidget(filter_widget)
    
    # 既存データセットドロップダウン（ラベルとコンボボックスを一行で表示）
    dataset_selection_widget = QWidget()
    dataset_selection_layout = QHBoxLayout()
    dataset_selection_layout.setContentsMargins(0, 0, 0, 0)
    
    existing_dataset_label = QLabel("表示するデータセット:")
    existing_dataset_label.setMinimumWidth(150)
    existing_dataset_combo = QComboBox()
    existing_dataset_combo.setMinimumWidth(650)  # 幅を広げてID表示対応
    existing_dataset_combo.setEditable(True)  # 検索補完のために編集可能にする
    existing_dataset_combo.setInsertPolicy(QComboBox.NoInsert)  # 新しいアイテムの挿入を禁止
    existing_dataset_combo.setMaxVisibleItems(12)  # ドロップダウンの表示行数を12行に
    existing_dataset_combo.view().setMinimumHeight(240)  # 12行分程度（1行約20px想定）
    
    # パフォーマンス最適化設定
    existing_dataset_combo.view().setUniformItemSizes(True)  # アイテムサイズを統一（高速化）
    existing_dataset_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)  # サイズ調整ポリシー
    existing_dataset_combo.setToolTip("クリックでデータセット一覧を展開します\n大量データの場合はプログレス表示されます")
    
    dataset_selection_layout.addWidget(existing_dataset_label)
    dataset_selection_layout.addWidget(existing_dataset_combo)
    dataset_selection_widget.setLayout(dataset_selection_layout)
    layout.addWidget(dataset_selection_widget)
    
    # データセットキャッシュシステム
    dataset_cache = {
        "raw_data": None,  # 元のJSONデータ
        "last_modified": None,  # ファイルの最終更新時刻
        "user_grant_numbers": None,  # ユーザーのgrantNumber一覧
        "filtered_datasets": {},  # フィルタごとのキャッシュ: {(filter_type, grant_filter): datasets}
        "display_data": {}  # 表示用データのキャッシュ: {(filter_type, grant_filter): display_names}
    }
    
    def get_cache_key(filter_type, grant_number_filter):
        """キャッシュキーを生成"""
        return (filter_type, grant_number_filter.lower().strip())
    
    def is_cache_valid():
        """キャッシュが有効かどうかを判定"""
        dataset_path = get_dynamic_file_path("output/rde/data/dataset.json")
        if not os.path.exists(dataset_path):
            return False
        
        current_modified = os.path.getmtime(dataset_path)
        return (dataset_cache["last_modified"] is not None and 
                dataset_cache["last_modified"] == current_modified and
                dataset_cache["raw_data"] is not None)
    
    def clear_cache():
        """キャッシュをクリア"""
        dataset_cache["raw_data"] = None
        dataset_cache["last_modified"] = None
        dataset_cache["user_grant_numbers"] = None
        dataset_cache["filtered_datasets"].clear()
        dataset_cache["display_data"].clear()
        print("[INFO] データセットキャッシュをクリアしました")
    
    def create_progress_dialog(title, text, maximum=0):
        """プログレスダイアログを作成"""
        progress = QProgressDialog(text, "キャンセル", 0, maximum, widget)
        progress.setWindowTitle(title)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(500)  # 500ms後に表示
        progress.setCancelButton(None)  # キャンセルボタンを無効化
        progress.setAutoClose(True)
        progress.setAutoReset(True)
        return progress
    
    def process_datasets_with_progress(datasets, user_grant_numbers, filter_type, grant_number_filter):
        """プログレス表示付きでデータセットを処理"""
        total_datasets = len(datasets)
        if total_datasets == 0:
            return [], []
        
        # プログレスダイアログを作成
        progress = create_progress_dialog(
            "データ処理中", 
            f"データセットを処理しています... (0/{total_datasets})",
            total_datasets
        )
        
        filtered_datasets = []
        other_datasets = []
        user_datasets = []
        grant_number_matches = {}
        
        try:
            for i, dataset in enumerate(datasets):
                # プログレス更新
                if i % 50 == 0 or i == total_datasets - 1:  # 50件ごと、または最後の処理時に更新
                    progress.setValue(i)
                    progress.setLabelText(f"データセットを処理しています... ({i+1}/{total_datasets})")
                    QApplication.processEvents()  # UIの更新を強制
                
                dataset_grant_number = dataset.get("attributes", {}).get("grantNumber", "")
                dataset_name = dataset.get("attributes", {}).get("name", "名前なし")
                
                # デバッグ用：最初の10件のデータセットの課題番号を表示
                if i < 10:
                    print(f"[DEBUG] データセット{i+1}: '{dataset_name}' (課題番号: '{dataset_grant_number}')")
                
                # 課題番号部分一致フィルタを適用
                if grant_number_filter and grant_number_filter.lower() not in dataset_grant_number.lower():
                    continue
                
                # ユーザー所属かどうかで分類
                if dataset_grant_number in user_grant_numbers:
                    user_datasets.append(dataset)
                    if dataset_grant_number not in grant_number_matches:
                        grant_number_matches[dataset_grant_number] = 0
                    grant_number_matches[dataset_grant_number] += 1
                else:
                    other_datasets.append(dataset)
            
            # 最終プログレス更新
            progress.setValue(total_datasets)
            progress.setLabelText("処理完了")
            QApplication.processEvents()
            
        finally:
            progress.close()
        
        # フィルタタイプに基づいて表示対象を決定
        if filter_type == "user_only":
            filtered_datasets = user_datasets
            print(f"[DEBUG] フィルタ適用: ユーザー所属のみ ({len(filtered_datasets)}件)")
        elif filter_type == "others_only":
            filtered_datasets = other_datasets
            print(f"[DEBUG] フィルタ適用: その他のみ ({len(filtered_datasets)}件)")
        elif filter_type == "all":
            filtered_datasets = user_datasets + other_datasets
            print(f"[DEBUG] フィルタ適用: すべて (ユーザー所属: {len(user_datasets)}件, その他: {len(other_datasets)}件, 合計: {len(filtered_datasets)}件)")
        
        return filtered_datasets, grant_number_matches
    
    def create_display_names_with_progress(datasets, user_grant_numbers):
        """プログレス表示付きで表示名リストを作成"""
        total_datasets = len(datasets)
        if total_datasets == 0:
            return []
        
        # 表示名作成のプログレスダイアログ
        progress = create_progress_dialog(
            "表示データ作成中",
            f"表示用データを作成しています... (0/{total_datasets})",
            total_datasets
        )
        
        display_names = []
        
        try:
            for i, dataset in enumerate(datasets):
                # プログレス更新（表示名作成は高速なので100件ごと）
                if i % 100 == 0 or i == total_datasets - 1:
                    progress.setValue(i)
                    progress.setLabelText(f"表示用データを作成しています... ({i+1}/{total_datasets})")
                    QApplication.processEvents()
                
                attrs = dataset.get("attributes", {})
                dataset_id = dataset.get("id", "")
                name = attrs.get("name", "名前なし")
                grant_number = attrs.get("grantNumber", "")
                dataset_type = attrs.get("datasetType", "")
                
                # ユーザー所属かどうかで表示を区別
                if grant_number in user_grant_numbers:
                    display_text = f"★ {grant_number} - {name} (ID: {dataset_id})"
                else:
                    display_text = f"{grant_number} - {name} (ID: {dataset_id})"
                
                if dataset_type:
                    display_text += f" [{dataset_type}]"
                display_names.append(display_text)
            
            # 最終プログレス更新
            progress.setValue(total_datasets)
            progress.setLabelText("表示データ作成完了")
            QApplication.processEvents()
            
        finally:
            progress.close()
        
        return display_names

    def populate_combo_box_with_progress(combo_box, datasets, display_names):
        """プログレス表示付きでコンボボックスにアイテムを追加"""
        total_items = len(datasets)
        if total_items == 0:
            return
        
        # アイテム数が多い場合のみプログレス表示
        if total_items > 100:
            progress = create_progress_dialog(
                "リスト展開中",
                f"データセット一覧を展開しています... (0/{total_items})",
                total_items
            )
            progress.show()
            QApplication.processEvents()
        else:
            progress = None
        
        try:
            # 効率化のため、blockSignalsを使用してシグナルを一時的に無効化
            combo_box.blockSignals(True)
            
            # 最初にヘッダーアイテムを追加
            combo_box.addItem("-- データセットを選択してください --", None)
            
            # バッチでアイテムを追加（応答性を保つため）
            batch_size = 50  # 50件ずつ処理
            for i in range(0, total_items, batch_size):
                batch_end = min(i + batch_size, total_items)
                
                # バッチ処理
                for j in range(i, batch_end):
                    display_text = display_names[j] if j < len(display_names) else f"データセット{j+1}"
                    dataset = datasets[j]
                    combo_box.addItem(display_text, dataset)
                
                # プログレス更新（大量データの場合のみ）
                if progress:
                    progress.setValue(batch_end)
                    progress.setLabelText(f"データセット一覧を展開しています... ({batch_end}/{total_items})")
                    QApplication.processEvents()
                
                # 応答性を保つため、バッチごとに少し待機
                if total_items > 500:  # 500件以上の場合のみ
                    QTimer.singleShot(1, lambda: None)  # 1msの非ブロッキング待機
                    QApplication.processEvents()
            
        finally:
            combo_box.blockSignals(False)
            if progress:
                progress.close()

    def update_combo_box_ui(datasets, display_names, filter_type, grant_number_filter, dataset_count):
        """コンボボックスのUIを更新する"""
        # 更新ボタンの有効/無効を制御
        is_default_filter = (filter_type == "user_only" and not grant_number_filter)
        update_button.setEnabled(is_default_filter)
        if not is_default_filter:
            update_button.setToolTip("デフォルト設定（ユーザー所属のみ、課題番号フィルタなし）でのみ更新可能です")
            update_button.setStyleSheet("background-color: #CCCCCC; color: #666666; font-weight: bold; border-radius: 6px;")
        else:
            update_button.setToolTip("")
            update_button.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold; border-radius: 6px;")
        
        # コンボボックスを完全にクリア（キャッシュも含む）
        existing_dataset_combo.clear()
        if hasattr(existing_dataset_combo, '_datasets_cache'):
            delattr(existing_dataset_combo, '_datasets_cache')
        if hasattr(existing_dataset_combo, '_display_names_cache'):
            delattr(existing_dataset_combo, '_display_names_cache')
        
        # 既存のCompleterがあればクリア
        if existing_dataset_combo.completer():
            existing_dataset_combo.completer().deleteLater()
        
        # QCompleterを設定
        completer = QCompleter(display_names, existing_dataset_combo)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        # 検索時の補完リスト（popup）の高さを12行分に制限
        popup_view = completer.popup()
        popup_view.setMinimumHeight(240)
        popup_view.setMaximumHeight(240)
        existing_dataset_combo.setCompleter(completer)
        
        # プレースホルダーテキストを設定
        if existing_dataset_combo.lineEdit():
            filter_desc = f"フィルタ: {filter_type}"
            if grant_number_filter:
                filter_desc += f", 課題番号: '{grant_number_filter}'"
            existing_dataset_combo.lineEdit().setPlaceholderText(f"データセット ({dataset_count}件) から検索... [{filter_desc}]")
        
        # データセット一覧をComboBoxに保存（mousePressEvent用）
        existing_dataset_combo._datasets_cache = datasets
        existing_dataset_combo._display_names_cache = display_names

    # データセット情報を読み込んでドロップダウンに追加
    def load_existing_datasets(filter_type="user_only", grant_number_filter="", force_reload=False):
        """
        データセット一覧を読み込み、フィルタ条件に基づいて表示
        
        Args:
            filter_type: "user_only", "others_only", "all"
            grant_number_filter: 課題番号の部分一致検索文字列
            force_reload: キャッシュを無視して強制再読み込み
        """
        dataset_path = get_dynamic_file_path("output/rde/data/dataset.json")
        print(f"[DEBUG] データセットファイルパス: {dataset_path}")
        print(f"[DEBUG] ファイル存在確認: {os.path.exists(dataset_path)}")
        print(f"[DEBUG] フィルタタイプ: {filter_type}, 課題番号フィルタ: '{grant_number_filter}'")
        print(f"[DEBUG] 強制再読み込み: {force_reload}")
        
        # キャッシュキーを生成
        cache_key = get_cache_key(filter_type, grant_number_filter)
        
        # キャッシュが有効で、強制再読み込みでない場合はキャッシュを使用
        if not force_reload and is_cache_valid() and cache_key in dataset_cache["filtered_datasets"]:
            print(f"[INFO] キャッシュからデータセット一覧を読み込み: {cache_key}")
            datasets = dataset_cache["filtered_datasets"][cache_key]
            display_names = dataset_cache["display_data"][cache_key]
            user_grant_numbers = dataset_cache["user_grant_numbers"]
            
            # UIを更新
            update_combo_box_ui(datasets, display_names, filter_type, grant_number_filter, len(datasets))
            print(f"[INFO] キャッシュからの読み込み完了: {len(datasets)}件")
            return
        
        try:
            print("[INFO] データセット一覧の再読み込みを開始")
            
            if not os.path.exists(dataset_path):
                print(f"[ERROR] データセットファイルが見つかりません: {dataset_path}")
                return
            
            # ファイルの最終更新時刻を取得
            current_modified = os.path.getmtime(dataset_path)
            
                # 基本データの読み込み（キャッシュまたは新規読み込み）
            if not is_cache_valid() or force_reload:
                print("[INFO] 基本データを新規読み込み")
                
                # ファイル読み込みのプログレス表示
                file_progress = create_progress_dialog("ファイル読み込み中", "dataset.jsonを読み込んでいます...", 0)
                file_progress.show()
                QApplication.processEvents()
                
                try:
                    with open(dataset_path, encoding="utf-8", errors='replace') as f:
                        data = json.load(f)
                        
                    file_progress.setLabelText("JSONデータを解析中...")
                    QApplication.processEvents()
                    
                except (json.JSONDecodeError, UnicodeDecodeError) as json_error:
                    file_progress.close()
                    print(f"[ERROR] データセット読み込みエラー: {json_error}")
                    print(f"[ERROR] ファイルパス: {dataset_path}")
                    
                    # UTF-8デコードエラーの場合は修復を試行
                    if isinstance(json_error, UnicodeDecodeError):
                        print("[INFO] UTF-8デコードエラーを検出、ファイル修復を試行します")
                        try:
                            repaired_data = repair_json_file(dataset_path)
                            if repaired_data:
                                data = repaired_data
                                print("[INFO] ファイル修復に成功しました")
                            else:
                                print("[ERROR] ファイル修復に失敗しました")
                                return
                        except Exception as repair_error:
                            print(f"[ERROR] ファイル修復中にエラー: {repair_error}")
                            return
                    else:
                        # ファイルサイズ確認
                        file_size = os.path.getsize(dataset_path)
                        print(f"[ERROR] ファイルサイズ: {file_size} bytes")
                    
                    # バックアップファイルの確認と復旧試行
                    backup_file = dataset_path + ".backup"
                    if os.path.exists(backup_file):
                        print(f"[INFO] バックアップファイルから復旧を試行: {backup_file}")
                        try:
                            # バックアップファイルも修復機能を使用
                            backup_data = repair_json_file(backup_file)
                            if backup_data:
                                data = backup_data
                                print(f"[INFO] バックアップファイルから正常に読み込み、元ファイルを置き換えました")
                                # 修復したバックアップで元ファイルを置き換え
                                shutil.copy2(backup_file, dataset_path)
                            else:
                                print(f"[ERROR] バックアップファイルも破損しています")
                                return
                            
                        except Exception as backup_error:
                            print(f"[ERROR] バックアップファイルからの復旧も失敗: {backup_error}")
                            return
                    else:
                        print(f"[ERROR] バックアップファイルが見つかりません: {backup_file}")
                        print("[INFO] 最初から読み込みなおしを試行します...")
                        
                        # 最後の手段として、元ファイルを修復機能で直接修復
                        try:
                            repaired_original = repair_json_file(dataset_path)
                            if repaired_original:
                                data = repaired_original
                                print("[INFO] 元ファイルの直接修復が成功しました")
                            else:
                                print("[ERROR] 元ファイルの修復も失敗しました")
                                QMessageBox.critical(widget, "エラー", 
                                                   "データセットファイルが破損しており、修復できませんでした。\n"
                                                   "新しいファイルが作成されます。")
                                data = {"data": [], "links": {}, "meta": {}}
                        except Exception as final_error:
                            print(f"[ERROR] 最終修復試行も失敗: {final_error}")
                            QMessageBox.critical(widget, "エラー", 
                                               "データセットファイルの読み込みに完全に失敗しました。\n"
                                               "空のデータセットリストから開始します。")
                            data = {"data": [], "links": {}, "meta": {}}
                finally:
                    file_progress.close()
                
                # ユーザーのgrantNumber取得のプログレス表示
                user_progress = create_progress_dialog("ユーザー情報取得中", "ユーザーの権限情報を取得しています...", 0)
                user_progress.show()
                QApplication.processEvents()
                
                try:
                    # データをキャッシュに保存
                    dataset_cache["raw_data"] = data.get("data", [])
                    dataset_cache["last_modified"] = current_modified
                    dataset_cache["user_grant_numbers"] = get_user_grant_numbers()
                    print(f"[INFO] 基本データキャッシュ更新: データセット数={len(dataset_cache['raw_data'])}")
                finally:
                    user_progress.close()
            else:
                print("[INFO] キャッシュから基本データを使用")
            
            # キャッシュからデータを取得
            all_datasets = dataset_cache["raw_data"]
            user_grant_numbers = dataset_cache["user_grant_numbers"]
            print(f"[DEBUG] データセット数: {len(all_datasets)}")
            print(f"[DEBUG] ユーザーのgrantNumber一覧: {sorted(user_grant_numbers)}")
            
            # フィルタリング処理（プログレス表示付き）
            datasets, grant_number_matches = process_datasets_with_progress(
                all_datasets, user_grant_numbers, filter_type, grant_number_filter
            )
            
            # 課題番号ごとのマッチ結果を表示（ユーザー所属のみ）
            if grant_number_matches:
                print(f"[DEBUG] 課題番号別マッチ結果（ユーザー所属）:")
                for grant_number, count in grant_number_matches.items():
                    print(f"[DEBUG]   {grant_number}: {count}件")
            
            # セキュリティ情報をログ出力
            print(f"[INFO] データセット編集: 全データセット数={len(all_datasets)}, 表示データセット数={len(datasets)}")
            print(f"[INFO] ユーザーが属するgrantNumber: {sorted(user_grant_numbers)}")
            print(f"[INFO] フィルタ設定: タイプ={filter_type}, 課題番号='{grant_number_filter}'")
            
            # 表示名リストを作成（プログレス表示付き）
            display_names = create_display_names_with_progress(datasets, user_grant_numbers)
            
            # キャッシュに保存
            dataset_cache["filtered_datasets"][cache_key] = datasets
            dataset_cache["display_data"][cache_key] = display_names
            print(f"[INFO] フィルタ結果をキャッシュに保存: {cache_key} -> {len(datasets)}件")
            
            # UIを更新
            update_combo_box_ui(datasets, display_names, filter_type, grant_number_filter, len(datasets))
            
            print(f"[INFO] データセット一覧の再読み込み完了: {len(datasets)}件")
            
            # QComboBox自体のmousePressEventをラップして全リスト表示＋popup（初回のみ設定）
            if not hasattr(existing_dataset_combo, '_mouse_press_event_set'):
                orig_mouse_press = existing_dataset_combo.mousePressEvent
                def combo_mouse_press_event(event):
                    if not existing_dataset_combo.lineEdit().text():
                        # コンボボックスをクリア
                        existing_dataset_combo.clear()
                        
                        # キャッシュされたデータセット一覧と表示名を使用
                        cached_datasets = getattr(existing_dataset_combo, '_datasets_cache', [])
                        cached_display_names = getattr(existing_dataset_combo, '_display_names_cache', [])
                        
                        print(f"[DEBUG] コンボボックス展開: {len(cached_datasets)}件のデータセット")
                        
                        # 高速化されたアイテム追加処理
                        if cached_datasets:
                            populate_combo_box_with_progress(existing_dataset_combo, cached_datasets, cached_display_names)
                        else:
                            # フォールバック：キャッシュがない場合は従来の方法
                            existing_dataset_combo.addItem("-- データセットを選択してください --", None)
                    
                    existing_dataset_combo.showPopup()
                    orig_mouse_press(event)
                
                existing_dataset_combo.mousePressEvent = combo_mouse_press_event
                existing_dataset_combo._mouse_press_event_set = True
            
        except Exception as e:
            QMessageBox.warning(widget, "エラー", f"データセット情報の読み込みに失敗しました: {e}")
            print(f"[ERROR] データセット読み込みエラー: {e}")
            import traceback
            traceback.print_exc()
    
    # 関連データセット選択機能
    def setup_related_datasets(related_dataset_combo, exclude_dataset_id=None):
        """関連データセット選択機能のセットアップ
        
        Args:
            related_dataset_combo: 関連データセット選択用のコンボボックス
            exclude_dataset_id: 除外するデータセットID（現在編集中のデータセット）
        """
        try:
            datasets_file = get_dynamic_file_path("output/rde/data/dataset.json")
            print(f"[DEBUG] 関連データセット用全データセット読み込み開始: {datasets_file}")
            
            if not os.path.exists(datasets_file):
                print(f"[ERROR] データセットファイルが見つかりません: {datasets_file}")
                return
            
            try:
                with open(datasets_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except json.JSONDecodeError as json_error:
                print(f"[ERROR] JSONパースエラー: {json_error}")
                print(f"[ERROR] ファイルパス: {datasets_file}")
                
                # ファイルサイズ確認
                file_size = os.path.getsize(datasets_file)
                print(f"[ERROR] ファイルサイズ: {file_size} bytes")
                
                # バックアップファイルの確認と復旧試行
                backup_file = datasets_file + ".backup"
                if os.path.exists(backup_file):
                    print(f"[INFO] バックアップファイルから復旧を試行: {backup_file}")
                    try:
                        with open(backup_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        print(f"[INFO] バックアップファイルから正常に読み込みました")
                        
                        # 破損したファイルを置き換え
                        import shutil
                        shutil.copy2(backup_file, datasets_file)
                        print(f"[INFO] バックアップファイルで破損ファイルを置き換えました")
                        
                    except Exception as backup_error:
                        print(f"[ERROR] バックアップファイルからの復旧も失敗: {backup_error}")
                        return
                else:
                    print(f"[ERROR] バックアップファイルが見つかりません: {backup_file}")
                    return
            
            all_datasets = data.get("data", [])
            
            # 除外するデータセットIDがある場合はフィルタリング
            if exclude_dataset_id:
                all_datasets = [dataset for dataset in all_datasets if dataset.get("id") != exclude_dataset_id]
                print(f"[DEBUG] データセットID '{exclude_dataset_id}' を除外")
            
            print(f"[INFO] 全データセット読み込み完了: {len(all_datasets)}件")
            
            # ユーザーのgrantNumberを取得
            user_grant_numbers = get_user_grant_numbers()
            
            # ユーザーのデータセットとその他のデータセットに分離
            user_datasets = []
            other_datasets = []
            
            for dataset in all_datasets:
                attrs = dataset.get("attributes", {})
                grant_number = attrs.get("grantNumber", "")
                
                if grant_number in user_grant_numbers:
                    user_datasets.append(dataset)
                else:
                    other_datasets.append(dataset)
            
            # ユーザーのデータセットを先頭に配置
            sorted_datasets = user_datasets + other_datasets
            
            # 表示名リストを作成
            display_names = []
            for i, dataset in enumerate(sorted_datasets):
                attrs = dataset.get("attributes", {})
                name = attrs.get("name", "名前なし")
                grant_number = attrs.get("grantNumber", "")
                dataset_type = attrs.get("datasetType", "")
                
                # ユーザー所属かどうかで表示を区別
                if i < len(user_datasets):
                    display_text = f"★ {grant_number} - {name}"  # ユーザー所属
                else:
                    display_text = f"{grant_number} - {name}"  # その他
                    
                if dataset_type:
                    display_text += f" ({dataset_type})"
                display_names.append(display_text)
            
            # コンボボックスのクリアとCompleter設定
            related_dataset_combo.clear()
            if hasattr(related_dataset_combo, '_all_datasets_cache'):
                delattr(related_dataset_combo, '_all_datasets_cache')
            
            # コンボボックスにアイテムを追加
            for i, dataset in enumerate(sorted_datasets):
                attrs = dataset.get("attributes", {})
                name = attrs.get("name", "名前なし")
                grant_number = attrs.get("grantNumber", "")
                dataset_type = attrs.get("datasetType", "")
                
                # ユーザー所属かどうかで表示を区別
                if i < len(user_datasets):
                    display_text = f"★ {grant_number} - {name}"  # ユーザー所属
                else:
                    display_text = f"{grant_number} - {name}"  # その他
                    
                if dataset_type:
                    display_text += f" ({dataset_type})"
                
                # コンボボックスにアイテムを追加（データセット情報も保存）
                related_dataset_combo.addItem(display_text, dataset)
            
            # QCompleterを設定
            completer = QCompleter(display_names, related_dataset_combo)
            completer.setCaseSensitivity(Qt.CaseInsensitive)
            completer.setFilterMode(Qt.MatchContains)
            popup_view = completer.popup()
            popup_view.setMinimumHeight(240)
            popup_view.setMaximumHeight(240)
            related_dataset_combo.setCompleter(completer)
            
            # プレースホルダーテキストを設定
            if related_dataset_combo.lineEdit():
                related_dataset_combo.lineEdit().setPlaceholderText(f"関連データセット ({len(sorted_datasets)}件) から検索...")
            
            # データセット一覧をComboBoxに保存
            related_dataset_combo._all_datasets_cache = sorted_datasets
            
            print(f"[INFO] 関連データセット選択機能セットアップ完了: ユーザー所属={len(user_datasets)}件, その他={len(other_datasets)}件")
            
        except Exception as e:
            print(f"[ERROR] 関連データセット読み込み中にエラー: {e}")
    
    # 関連データセット選択イベント処理
    def on_related_dataset_selected(related_dataset_combo, selected_datasets_list):
        """関連データセットが選択された時の処理"""
        current_text = related_dataset_combo.lineEdit().text().strip()
        if not current_text:
            return
        
        # キャッシュからデータセットを検索
        cached_datasets = getattr(related_dataset_combo, '_all_datasets_cache', [])
        selected_dataset = None
        
        for dataset in cached_datasets:
            attrs = dataset.get("attributes", {})
            name = attrs.get("name", "名前なし")
            grant_number = attrs.get("grantNumber", "")
            dataset_type = attrs.get("datasetType", "")
            display_text = f"{grant_number} - {name}"
            if dataset_type:
                display_text += f" ({dataset_type})"
            
            # ★マークありでもなしでも一致検索
            if current_text.replace("★ ", "") == display_text:
                selected_dataset = dataset
                break
        
        if selected_dataset:
            dataset_id = selected_dataset.get("id", "")
            dataset_name = selected_dataset.get("attributes", {}).get("name", "名前なし")
            
            # 既に選択済みかチェック
            for i in range(selected_datasets_list.count()):
                item = selected_datasets_list.item(i)
                if item.data(Qt.UserRole) == dataset_id:
                    print(f"[INFO] データセット '{dataset_name}' は既に選択済みです")
                    related_dataset_combo.lineEdit().clear()
                    return
            
            # リストに追加
            list_item = QListWidgetItem(f"{dataset_name} (ID: {dataset_id})")
            list_item.setData(Qt.UserRole, dataset_id)
            selected_datasets_list.addItem(list_item)
            
            # コンボボックスをクリア
            related_dataset_combo.lineEdit().clear()
            print(f"[INFO] 関連データセットを追加: {dataset_name} (ID: {dataset_id})")
    
    # 関連データセット削除処理
    def on_remove_dataset(selected_datasets_list):
        """選択されたデータセットを削除"""
        current_item = selected_datasets_list.currentItem()
        if current_item:
            dataset_id = current_item.data(Qt.UserRole)
            dataset_text = current_item.text()
            selected_datasets_list.takeItem(selected_datasets_list.row(current_item))
            print(f"[INFO] 関連データセットを削除: {dataset_text}")
    
    # 編集フォーム作成
    def create_edit_form():
        """編集フォームを作成"""
        form_widget = QWidget()
        form_layout = QGridLayout()
        
        # データセット名
        form_layout.addWidget(QLabel("データセット名:"), 0, 0)
        edit_dataset_name_edit = QLineEdit()
        edit_dataset_name_edit.setPlaceholderText("データセット名を入力")
        form_layout.addWidget(edit_dataset_name_edit, 0, 1)
        
        # 課題番号（コンボボックスに変更）
        form_layout.addWidget(QLabel("課題番号:"), 1, 0)
        edit_grant_number_combo = QComboBox()
        edit_grant_number_combo.setEditable(True)
        edit_grant_number_combo.setInsertPolicy(QComboBox.NoInsert)
        edit_grant_number_combo.lineEdit().setPlaceholderText("課題番号を選択または入力")
        
        # 初期状態でユーザーの課題番号を設定
        def update_grant_number_combo_local(grant_numbers):
            """課題番号コンボボックスを更新する"""
            # 既存のアイテムをクリア
            edit_grant_number_combo.clear()
            
            # 既存のCompleterがあればクリア
            if edit_grant_number_combo.completer():
                edit_grant_number_combo.completer().deleteLater()
            
            if grant_numbers:
                sorted_grant_numbers = sorted(grant_numbers)
                for grant_number in sorted_grant_numbers:
                    edit_grant_number_combo.addItem(grant_number, grant_number)
                edit_grant_number_combo.setCurrentIndex(-1)  # 初期選択なし
                
                # 自動補完機能を追加
                grant_completer = QCompleter(sorted_grant_numbers, edit_grant_number_combo)
                grant_completer.setCaseSensitivity(Qt.CaseInsensitive)
                grant_completer.setFilterMode(Qt.MatchContains)
                edit_grant_number_combo.setCompleter(grant_completer)
                
                print(f"[DEBUG] 課題番号コンボボックスを更新: {sorted_grant_numbers}")
            else:
                print("[DEBUG] 課題番号が空のため、コンボボックスは空のまま")
        
        # この関数をedit_grant_number_comboのプロパティとして保存
        edit_grant_number_combo.update_grant_numbers = update_grant_number_combo_local
        
        try:
            user_grant_numbers = get_user_grant_numbers()
            update_grant_number_combo_local(user_grant_numbers)
        except Exception as e:
            print(f"[DEBUG] 初期課題番号リスト取得エラー: {e}")
        
        form_layout.addWidget(edit_grant_number_combo, 1, 1)
        
        # 説明
        form_layout.addWidget(QLabel("説明:"), 2, 0)
        
        # 説明フィールド用の水平レイアウト
        description_layout = QHBoxLayout()
        edit_description_edit = QTextEdit()
        edit_description_edit.setPlaceholderText("データセットの説明を入力")
        edit_description_edit.setMaximumHeight(80)  # 4行程度
        description_layout.addWidget(edit_description_edit)
        
        # AIサジェストボタン用の縦並びレイアウト
        ai_buttons_layout = QVBoxLayout()
        ai_buttons_layout.setContentsMargins(0, 0, 0, 0)
        ai_buttons_layout.setSpacing(4)  # ボタン間の間隔
        
        # SpinnerButtonをインポート
        from classes.dataset.ui.spinner_button import SpinnerButton
        
        # AIボタン（通常版・ダイアログ表示）
        ai_suggest_button = SpinnerButton("🤖 AI提案")
        ai_suggest_button.setMinimumWidth(80)  # サイズを拡大
        ai_suggest_button.setMaximumWidth(100)
        ai_suggest_button.setMinimumHeight(45)  # 高さを拡大
        ai_suggest_button.setMaximumHeight(50)
        ai_suggest_button.setToolTip("AIによる説明文の提案（ダイアログ表示）\n複数の候補から選択できます")
        ai_suggest_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 11px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #81C784;
                color: #E8F5E9;
            }
        """)
        
        # クイックAIボタン（即座反映版）
        quick_ai_button = SpinnerButton("⚡ Quick AI")
        quick_ai_button.setMinimumWidth(80)  # サイズを拡大
        quick_ai_button.setMaximumWidth(100)
        quick_ai_button.setMinimumHeight(45)  # 高さを拡大
        quick_ai_button.setMaximumHeight(50)
        quick_ai_button.setToolTip("AIによる説明文の即座生成（直接反映）\nワンクリックで自動入力されます")
        quick_ai_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-size: 11px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 8px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:disabled {
                background-color: #64B5F6;
                color: #E3F2FD;
            }
        """)
        
        ai_buttons_layout.addWidget(ai_suggest_button)
        ai_buttons_layout.addWidget(quick_ai_button)
        
        # AI提案ダイアログ表示のコールバック関数（既存）
        def show_ai_suggestion():
            try:
                # スピナー開始
                ai_suggest_button.start_loading("AI生成中")
                QApplication.processEvents()  # UI更新
                
                # 現在のフォームデータを収集してコンテキストとして使用
                context_data = {}
                
                # 【重要】現在選択されているデータセットIDを取得
                current_index = existing_dataset_combo.currentIndex()
                if current_index > 0:  # 0は"選択してください"項目
                    selected_dataset = existing_dataset_combo.itemData(current_index)
                    if selected_dataset:
                        dataset_id = selected_dataset.get("id")
                        if dataset_id:
                            context_data['dataset_id'] = dataset_id
                            print(f"[DEBUG] データセットID設定: {dataset_id}")
                
                # データセット名
                if hasattr(edit_dataset_name_edit, 'text'):
                    context_data['name'] = edit_dataset_name_edit.text().strip()
                
                # データセットタイプ（デフォルトまたは推定）
                context_data['type'] = 'mixed'  # デフォルト
                
                # 課題番号
                if hasattr(edit_grant_number_combo, 'currentText'):
                    grant_text = edit_grant_number_combo.currentText().strip()
                    if grant_text and grant_text != "課題番号を選択してください":
                        context_data['grant_number'] = grant_text
                    else:
                        context_data['grant_number'] = ''
                
                # 既存の説明文
                if hasattr(edit_description_edit, 'toPlainText'):
                    existing_desc = edit_description_edit.toPlainText().strip()
                    context_data['description'] = existing_desc if existing_desc else ''
                
                # アクセスポリシー（必要に応じて）
                context_data['access_policy'] = 'restricted'  # デフォルト
                
                # その他のフォーム情報
                if hasattr(edit_contact_edit, 'text'):
                    context_data['contact'] = edit_contact_edit.text().strip()
                
                print(f"[DEBUG] AI提案に渡すコンテキストデータ: {context_data}")
                
                # AI提案ダイアログを表示（自動生成有効）
                dialog = AISuggestionDialog(parent=widget, context_data=context_data, auto_generate=True)
                
                # スピナー停止
                ai_suggest_button.stop_loading()
                
                if dialog.exec() == QDialog.Accepted:
                    suggestion = dialog.get_selected_suggestion()
                    if suggestion:
                        # QTextEditの場合はsetPlainTextを使用して改行を保持
                        if hasattr(edit_description_edit, 'setPlainText'):
                            edit_description_edit.setPlainText(suggestion)
                        else:
                            edit_description_edit.setText(suggestion)
                        
            except Exception as e:
                # エラー時もスピナーを停止
                ai_suggest_button.stop_loading()
                QMessageBox.critical(widget, "エラー", f"AI提案機能でエラーが発生しました: {str(e)}")
        
        # クイックAI生成のコールバック関数（新規）
        def show_quick_ai_suggestion():
            try:
                # スピナー開始
                quick_ai_button.start_loading("生成中")
                QApplication.processEvents()  # UI更新
                
                # 現在のフォームデータを収集してコンテキストとして使用
                context_data = {}
                
                # 【重要】現在選択されているデータセットIDを取得
                current_index = existing_dataset_combo.currentIndex()
                if current_index > 0:  # 0は"選択してください"項目
                    selected_dataset = existing_dataset_combo.itemData(current_index)
                    if selected_dataset:
                        dataset_id = selected_dataset.get("id")
                        if dataset_id:
                            context_data['dataset_id'] = dataset_id
                            print(f"[DEBUG] データセットID設定（クイック版）: {dataset_id}")
                
                # データセット名
                if hasattr(edit_dataset_name_edit, 'text'):
                    context_data['name'] = edit_dataset_name_edit.text().strip()
                
                # データセットタイプ（デフォルトまたは推定）
                context_data['type'] = 'mixed'  # デフォルト
                
                # 課題番号
                if hasattr(edit_grant_number_combo, 'currentText'):
                    grant_text = edit_grant_number_combo.currentText().strip()
                    if grant_text and grant_text != "課題番号を選択してください":
                        context_data['grant_number'] = grant_text
                    else:
                        context_data['grant_number'] = ''
                
                # 既存の説明文
                if hasattr(edit_description_edit, 'toPlainText'):
                    existing_desc = edit_description_edit.toPlainText().strip()
                    context_data['description'] = existing_desc if existing_desc else ''
                
                # アクセスポリシー（必要に応じて）
                context_data['access_policy'] = 'restricted'  # デフォルト
                
                # その他のフォーム情報
                if hasattr(edit_contact_edit, 'text'):
                    context_data['contact'] = edit_contact_edit.text().strip()
                
                print(f"[DEBUG] クイックAI提案に渡すコンテキストデータ: {context_data}")
                
                # クイック版AI機能を実行（ダイアログなし）
                from classes.dataset.core.quick_ai_suggestion import generate_quick_suggestion
                suggestion = generate_quick_suggestion(context_data)
                
                if suggestion:
                    # 既存の説明文を置き換え（QTextEditの場合はsetPlainTextを使用して改行を保持）
                    if hasattr(edit_description_edit, 'setPlainText'):
                        edit_description_edit.setPlainText(suggestion)
                    else:
                        edit_description_edit.setText(suggestion)
                    print(f"[INFO] クイックAI提案を適用: {len(suggestion)}文字")
                else:
                    QMessageBox.warning(widget, "警告", "クイックAI提案の生成に失敗しました")
                    
            except Exception as e:
                QMessageBox.critical(widget, "エラー", f"クイックAI提案機能でエラーが発生しました: {str(e)}")
            finally:
                # 必ずスピナーを停止
                quick_ai_button.stop_loading()
        
        ai_suggest_button.clicked.connect(show_ai_suggestion)
        quick_ai_button.clicked.connect(show_quick_ai_suggestion)
        
        # ボタンレイアウトをウィジェット化
        ai_buttons_widget = QWidget()
        ai_buttons_widget.setLayout(ai_buttons_layout)
        description_layout.addWidget(ai_buttons_widget)
        
        # 水平レイアウトを含むウィジェットを作成
        description_widget = QWidget()
        description_widget.setLayout(description_layout)
        form_layout.addWidget(description_widget, 2, 1)
        
        # エンバーゴ期間終了日
        form_layout.addWidget(QLabel("エンバーゴ期間終了日:"), 3, 0)
        edit_embargo_edit = QDateEdit()
        edit_embargo_edit.setDisplayFormat("yyyy-MM-dd")
        edit_embargo_edit.setCalendarPopup(True)
        edit_embargo_edit.setMinimumWidth(120)
        # デフォルトを翌年度末日に設定
        today = datetime.date.today()
        next_year = today.year + 1
        embargo_date = QDate(next_year, 3, 31)
        edit_embargo_edit.setDate(embargo_date)
        form_layout.addWidget(edit_embargo_edit, 3, 1)
        
        # データセットテンプレート（表示のみ）
        form_layout.addWidget(QLabel("データセットテンプレート:"), 4, 0)
        edit_template_display = QLineEdit()
        edit_template_display.setPlaceholderText("データセットテンプレート名（表示のみ）")
        edit_template_display.setReadOnly(True)
        edit_template_display.setStyleSheet("background-color: #f0f0f0;")  # 読み取り専用の視覚的表示
        form_layout.addWidget(edit_template_display, 4, 1)
        
        # 問い合わせ先
        form_layout.addWidget(QLabel("問い合わせ先:"), 5, 0)
        edit_contact_edit = QLineEdit()
        edit_contact_edit.setPlaceholderText("問い合わせ先を入力")
        form_layout.addWidget(edit_contact_edit, 5, 1)
        
        # タクソノミーキー（ビルダーダイアログ使用）
        form_layout.addWidget(QLabel("タクソノミーキー:"), 6, 0)
        taxonomy_layout = QHBoxLayout()
        edit_taxonomy_edit = QLineEdit()
        edit_taxonomy_edit.setPlaceholderText("タクソノミーキー（設定ボタンで編集）")
        edit_taxonomy_edit.setReadOnly(True)  # 読み取り専用
        
        taxonomy_builder_button = QPushButton("設定...")
        taxonomy_builder_button.setMaximumWidth(80)
        
        taxonomy_layout.addWidget(edit_taxonomy_edit)
        taxonomy_layout.addWidget(taxonomy_builder_button)
        
        # レイアウトをWidgetでラップしてGridLayoutに追加
        taxonomy_widget = QWidget()
        taxonomy_widget.setLayout(taxonomy_layout)
        form_layout.addWidget(taxonomy_widget, 6, 1)
        
        # タクソノミービルダーボタンのイベントハンドラー
        def open_taxonomy_builder():
            """タクソノミービルダーダイアログを開く"""
            try:
                # 現在選択されているデータセットからテンプレートIDを取得
                template_id = getattr(widget, 'current_template_id', '')
                
                current_taxonomy = edit_taxonomy_edit.text().strip()
                
                dialog = TaxonomyBuilderDialog(
                    parent=widget,
                    current_taxonomy=current_taxonomy,
                    dataset_template_id=template_id
                )
                
                # タクソノミー変更シグナルに接続
                dialog.taxonomy_changed.connect(
                    lambda taxonomy: edit_taxonomy_edit.setText(taxonomy)
                )
                
                dialog.exec()
                
            except Exception as e:
                QMessageBox.warning(widget, "エラー", f"タクソノミービルダーの起動に失敗しました:\n{e}")
        
        taxonomy_builder_button.clicked.connect(open_taxonomy_builder)
        
        # 関連情報（旧：関連リンク）
        form_layout.addWidget(QLabel("関連情報:"), 7, 0)
        edit_related_links_edit = QTextEdit()
        edit_related_links_edit.setPlaceholderText("関連情報を入力（タイトル1:URL1,タイトル2:URL2 の形式）")
        edit_related_links_edit.setMaximumHeight(80)  # 4行程度
        form_layout.addWidget(edit_related_links_edit, 7, 1)
        
        # TAGフィールド（ビルダーダイアログ使用）
        form_layout.addWidget(QLabel("TAG:"), 8, 0)
        tag_layout = QHBoxLayout()
        edit_tags_edit = QLineEdit()
        edit_tags_edit.setPlaceholderText("TAGを入力（カンマ区切り、設定ボタンでも編集可能）")
        
        tag_builder_button = QPushButton("設定...")
        tag_builder_button.setMaximumWidth(80)
        
        tag_layout.addWidget(edit_tags_edit)
        tag_layout.addWidget(tag_builder_button)
        
        # レイアウトをWidgetでラップしてGridLayoutに追加
        tag_widget = QWidget()
        tag_widget.setLayout(tag_layout)
        form_layout.addWidget(tag_widget, 8, 1)
        
        # TAGビルダーボタンのイベントハンドラー
        def open_tag_builder():
            """TAGビルダーダイアログを開く"""
            try:
                from classes.dataset.ui.tag_builder_dialog import TagBuilderDialog
                
                current_tags = edit_tags_edit.text().strip()
                
                dialog = TagBuilderDialog(
                    parent=widget,
                    current_tags=current_tags
                )
                
                # TAG変更シグナルに接続
                dialog.tags_changed.connect(
                    lambda tags: edit_tags_edit.setText(tags)
                )
                
                dialog.exec()
                
            except Exception as e:
                QMessageBox.warning(widget, "エラー", f"TAGビルダーの起動に失敗しました:\n{e}")
        
        tag_builder_button.clicked.connect(open_tag_builder)
        
        # データセット引用の書式（高さを3行程度に調整）
        form_layout.addWidget(QLabel("データセット引用の書式:"), 9, 0)
        edit_citation_format_edit = QTextEdit()
        edit_citation_format_edit.setPlaceholderText("データセット引用の書式を入力")
        edit_citation_format_edit.setMaximumHeight(60)  # 80 → 60に変更（約3行）
        form_layout.addWidget(edit_citation_format_edit, 9, 1)
        
        # 利用ライセンス選択
        form_layout.addWidget(QLabel("利用ライセンス:"), 10, 0)
        edit_license_combo = QComboBox()
        edit_license_combo.setEditable(True)
        edit_license_combo.setInsertPolicy(QComboBox.NoInsert)
        edit_license_combo.lineEdit().setPlaceholderText("ライセンスを選択または検索")
        
        # ライセンスデータをlicenses.jsonから読み込み
        license_data = []
        try:
            from config.common import LICENSES_JSON_PATH
            if os.path.exists(LICENSES_JSON_PATH):
                with open(LICENSES_JSON_PATH, 'r', encoding='utf-8') as f:
                    licenses_json = json.load(f)
                    license_data = licenses_json.get("data", [])
                print(f"[INFO] licenses.jsonから{len(license_data)}件のライセンス情報を読み込みました")
            else:
                print(f"[WARNING] licenses.jsonが見つかりません: {LICENSES_JSON_PATH}")
        except Exception as e:
            print(f"[ERROR] licenses.json読み込みエラー: {e}")
        
        # フォールバック用のデフォルトライセンスリスト
        if not license_data:
            print("[INFO] デフォルトライセンスリストを使用します")
            license_data = [
                {"id": "CC0-1.0", "fullName": "Creative Commons Zero v1.0 Universal"},
                {"id": "CC-BY-4.0", "fullName": "Creative Commons Attribution 4.0 International"},
                {"id": "CC-BY-SA-4.0", "fullName": "Creative Commons Attribution Share Alike 4.0 International"},
                {"id": "CC-BY-NC-4.0", "fullName": "Creative Commons Attribution Non Commercial 4.0 International"},
                {"id": "CC-BY-NC-SA-4.0", "fullName": "Creative Commons Attribution Non Commercial Share Alike 4.0 International"},
                {"id": "CC-BY-ND-4.0", "fullName": "Creative Commons Attribution No Derivatives 4.0 International"},
                {"id": "CC-BY-NC-ND-4.0", "fullName": "Creative Commons Attribution Non Commercial No Derivatives 4.0 International"},
                {"id": "MIT", "fullName": "MIT License"},
                {"id": "Apache-2.0", "fullName": "Apache License 2.0"},
                {"id": "GPL-3.0-only", "fullName": "GNU General Public License v3.0 only"},
                {"id": "BSD-3-Clause", "fullName": "BSD 3-Clause \"New\" or \"Revised\" License"},
                {"id": "MPL-2.0", "fullName": "Mozilla Public License 2.0"},
                {"id": "Unlicense", "fullName": "The Unlicense"},
                {"id": "ISC", "fullName": "ISC License"},
                {"id": "LGPL-3.0-only", "fullName": "GNU Lesser General Public License v3.0 only"},
            ]
        
        # ライセンス選択肢を追加
        for license_item in license_data:
            license_id = license_item.get("id", "")
            attributes = license_item.get("attributes", {})
            # fullNameまたはnameフィールドを使用
            license_name = attributes.get("fullName") or attributes.get("name", "")
            if license_id and license_name:
                display_text = f"{license_id} - {license_name}"
                edit_license_combo.addItem(display_text, license_id)
        
        edit_license_combo.setCurrentIndex(-1)  # 初期選択なし
        
        # 自動補完機能を追加
        license_display_texts = []
        for item in license_data:
            license_id = item.get("id", "")
            attributes = item.get("attributes", {})
            license_name = attributes.get("fullName") or attributes.get("name", "")
            if license_id and license_name:
                license_display_texts.append(f"{license_id} - {license_name}")
        
        license_completer = QCompleter(license_display_texts, edit_license_combo)
        license_completer.setCaseSensitivity(Qt.CaseInsensitive)
        license_completer.setFilterMode(Qt.MatchContains)
        edit_license_combo.setCompleter(license_completer)
        
        form_layout.addWidget(edit_license_combo, 10, 1)
        
        # 関連データセット選択
        form_layout.addWidget(QLabel("関連データセット:"), 11, 0)
        related_datasets_widget = QWidget()
        related_datasets_layout = QVBoxLayout()
        
        # 関連データセット選択コンボボックス
        related_dataset_combo = QComboBox()
        related_dataset_combo.setEditable(True)
        related_dataset_combo.setInsertPolicy(QComboBox.NoInsert)
        related_dataset_combo.lineEdit().setPlaceholderText("関連データセットを検索・選択...")
        related_datasets_layout.addWidget(related_dataset_combo)
        
        # 選択されたデータセット一覧（4行程度）
        selected_datasets_list = QListWidget()
        selected_datasets_list.setMaximumHeight(80)  # 4行程度
        selected_datasets_list.setAlternatingRowColors(True)
        related_datasets_layout.addWidget(selected_datasets_list)
        
        # 削除ボタン
        remove_dataset_btn = QPushButton("選択解除")
        remove_dataset_btn.setMaximumWidth(100)
        related_datasets_layout.addWidget(remove_dataset_btn)
        
        related_datasets_widget.setLayout(related_datasets_layout)
        form_layout.addWidget(related_datasets_widget, 11, 1)
        
        # データ一覧表示タイプ選択（ラジオボタン）- 関連データセットの下に移動
        form_layout.addWidget(QLabel("データ一覧表示タイプ:"), 12, 0)
        data_listing_type_widget = QWidget()
        data_listing_type_layout = QHBoxLayout()
        data_listing_type_layout.setContentsMargins(0, 0, 0, 0)
        
        edit_data_listing_gallery_radio = QRadioButton("ギャラリー表示")
        edit_data_listing_tree_radio = QRadioButton("ツリー表示")
        edit_data_listing_gallery_radio.setChecked(True)  # デフォルトはギャラリー表示
        
        data_listing_type_layout.addWidget(edit_data_listing_gallery_radio)
        data_listing_type_layout.addWidget(edit_data_listing_tree_radio)
        data_listing_type_layout.addStretch()  # 右側にスペースを追加
        
        data_listing_type_widget.setLayout(data_listing_type_layout)
        form_layout.addWidget(data_listing_type_widget, 12, 1)
        
        # チェックボックス（2列表示）
        checkbox_widget = QWidget()
        checkbox_layout = QGridLayout()
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        
        edit_anonymize_checkbox = QCheckBox("データセットを匿名にする")
        checkbox_layout.addWidget(edit_anonymize_checkbox, 0, 0)
        
        edit_data_entry_prohibited_checkbox = QCheckBox("データ登録を禁止する")
        # checkbox_layout.addWidget(edit_data_entry_prohibited_checkbox, 0, 1)
        
        # データ登録及び削除を禁止するチェックボックスを追加
        edit_data_entry_delete_prohibited_checkbox = QCheckBox("データの登録及び削除を禁止する")
        checkbox_layout.addWidget(edit_data_entry_delete_prohibited_checkbox, 1, 0)
        
        # データ中核拠点広域シェア
        edit_share_core_scope_checkbox = QCheckBox("データ中核拠点広域シェア（RDE全体での共有）を有効にする")
        checkbox_layout.addWidget(edit_share_core_scope_checkbox, 1, 1)
        
        checkbox_widget.setLayout(checkbox_layout)
        
        form_layout.addWidget(QLabel("共有範囲/利用制限:"), 14, 0)
        form_layout.addWidget(checkbox_widget, 14, 1)
        
        form_widget.setLayout(form_layout)
        
        # フォーム内のウィジェットを返す
        return (form_widget, edit_dataset_name_edit, edit_grant_number_combo, 
                edit_description_edit, edit_embargo_edit, edit_contact_edit,
                edit_taxonomy_edit, edit_related_links_edit, edit_tags_edit,
                edit_citation_format_edit, edit_license_combo, edit_data_listing_gallery_radio, edit_data_listing_tree_radio, 
                related_dataset_combo, selected_datasets_list,
                remove_dataset_btn, edit_anonymize_checkbox,
                edit_data_entry_prohibited_checkbox, edit_data_entry_delete_prohibited_checkbox, edit_share_core_scope_checkbox,
                edit_template_display)
    
    # 編集フォームを作成
    (edit_form_widget, edit_dataset_name_edit, edit_grant_number_combo, 
     edit_description_edit, edit_embargo_edit, edit_contact_edit,
     edit_taxonomy_edit, edit_related_links_edit, edit_tags_edit,
     edit_citation_format_edit, edit_license_combo, edit_data_listing_gallery_radio, edit_data_listing_tree_radio, 
     related_dataset_combo, selected_datasets_list,
     remove_dataset_btn, edit_anonymize_checkbox,
     edit_data_entry_prohibited_checkbox, edit_data_entry_delete_prohibited_checkbox, edit_share_core_scope_checkbox,
     edit_template_display) = create_edit_form()
    
    layout.addWidget(edit_form_widget)
    
    # 関連データセット機能のセットアップとイベント接続
    setup_related_datasets(related_dataset_combo)
    
    # ラムダ関数を使用してイベント接続（引数を渡すため）
    related_dataset_combo.lineEdit().returnPressed.connect(
        lambda: on_related_dataset_selected(related_dataset_combo, selected_datasets_list)
    )
    
    # コンボボックスのアイテム選択時のイベント処理
    def on_related_combo_activated(index):
        """コンボボックスでアイテムが選択された時の処理"""
        if index >= 0:
            dataset = related_dataset_combo.itemData(index)
            if dataset:
                dataset_id = dataset.get("id", "")
                dataset_title = dataset.get("attributes", {}).get("name", "名前なし")
                
                # 自己参照チェック - 現在編集中のデータセットと同じIDかどうか
                current_dataset_index = existing_dataset_combo.currentIndex()
                if current_dataset_index > 0:  # 有効なデータセットが選択されている場合
                    current_dataset = existing_dataset_combo.itemData(current_dataset_index)
                    if current_dataset:
                        current_dataset_id = current_dataset.get("id", "")
                        if dataset_id == current_dataset_id:
                            print(f"[INFO] 自分自身を関連データセットに指定することはできません: {dataset_title}")
                            related_dataset_combo.setCurrentIndex(-1)  # 選択をクリア
                            return
                
                # 重複チェック
                for row in range(selected_datasets_list.count()):
                    existing_item = selected_datasets_list.item(row)
                    if existing_item.data(Qt.UserRole) == dataset_id:
                        print(f"[INFO] データセットは既に選択されています: {dataset_title}")
                        related_dataset_combo.setCurrentIndex(-1)  # 選択をクリア
                        return
                
                # リストに追加
                item = QListWidgetItem(f"{dataset_title} (ID: {dataset_id})")
                item.setData(Qt.UserRole, dataset_id)
                selected_datasets_list.addItem(item)
                
                print(f"[INFO] 関連データセットを追加: {dataset_title}")
                related_dataset_combo.setCurrentIndex(-1)  # 選択をクリア
    
    related_dataset_combo.activated.connect(on_related_combo_activated)
    
    remove_dataset_btn.clicked.connect(
        lambda: on_remove_dataset(selected_datasets_list)
    )
    
    # フォームクリア処理
    def clear_edit_form():
        """編集フォームをクリア"""
        edit_dataset_name_edit.clear()
        edit_grant_number_combo.setCurrentIndex(-1)
        edit_description_edit.clear()
        edit_contact_edit.clear()
        edit_taxonomy_edit.clear()
        edit_related_links_edit.clear()  # 関連情報もクリア
        edit_tags_edit.clear()  # TAGフィールドをクリア
        edit_citation_format_edit.clear()  # 引用書式フィールドをクリア
        edit_license_combo.setCurrentIndex(-1)  # ライセンス選択をクリア
        edit_template_display.clear()  # テンプレート表示をクリア
        selected_datasets_list.clear()  # 関連データセット一覧をクリア
        edit_anonymize_checkbox.setChecked(False)
        edit_data_entry_prohibited_checkbox.setChecked(False)
        edit_data_entry_delete_prohibited_checkbox.setChecked(False)  # 新しいチェックボックス
        edit_share_core_scope_checkbox.setChecked(False)
        
        # データ一覧表示タイプをデフォルト（ギャラリー）に設定
        edit_data_listing_gallery_radio.setChecked(True)
        edit_data_listing_tree_radio.setChecked(False)
        
        # エンバーゴ期間終了日をデフォルト値に戻す
        today = datetime.date.today()
        next_year = today.year + 1
        embargo_date = QDate(next_year, 3, 31)
        edit_embargo_edit.setDate(embargo_date)
    
    # 関連情報バリデーション機能
    def validate_related_links(text):
        """関連情報の書式をバリデーション"""
        if not text.strip():
            return True, "関連情報が空です"
        
        errors = []
        valid_links = []
        
        # コンマ区切りで分割
        items = text.split(',')
        for i, item in enumerate(items, 1):
            item = item.strip()
            if not item:
                continue
                
            # TITLE:URL の形式をチェック
            if ':' not in item:
                errors.append(f"項目{i}: ':' が見つかりません")
                continue
                
            # タイトルとURLを分離
            try:
                title, url = item.split(':', 1)
                title = title.strip()
                url = url.strip()
                
                if not title:
                    errors.append(f"項目{i}: タイトルが空です")
                    continue
                    
                if not url:
                    errors.append(f"項目{i}: URLが空です")
                    continue
                    
                valid_links.append({"title": title, "url": url})
                
            except Exception as e:
                errors.append(f"項目{i}: 解析エラー - {e}")
        
        if errors:
            return False, "\\n".join(errors)
        else:
            return True, f"{len(valid_links)}件の関連情報が有効です"
    
    # 関連情報のリアルタイムバリデーション
    def on_related_links_changed():
        text = edit_related_links_edit.toPlainText()
        is_valid, message = validate_related_links(text)
        
        if is_valid:
            edit_related_links_edit.setStyleSheet("border: 1px solid green;")
        else:
            edit_related_links_edit.setStyleSheet("border: 2px solid red;")
        
        # ツールチップでメッセージを表示
        edit_related_links_edit.setToolTip(message)
    
    edit_related_links_edit.textChanged.connect(on_related_links_changed)
    
    # 選択されたデータセットの情報をフォームに反映
    def populate_edit_form_local(selected_dataset):
        """選択されたデータセットの情報をフォームに反映"""
        if not selected_dataset:
            clear_edit_form()  # データセットが選択されていない場合はフォームをクリア
            return
        
        # テンプレートIDを保存（タクソノミービルダーで使用）
        current_template_id = ""
        relationships = selected_dataset.get("relationships", {})
        template_data = relationships.get("template", {}).get("data", {})
        if template_data:
            current_template_id = template_data.get("id", "")
        
        # テンプレートIDをウィジェットに保存し、表示フィールドにも設定
        widget.current_template_id = current_template_id
        edit_template_display.setText(current_template_id)
        print(f"[DEBUG] テンプレートID保存・表示: {current_template_id}")
        
        attrs = selected_dataset.get("attributes", {})
        
        # 基本情報
        edit_dataset_name_edit.setText(attrs.get("name", ""))
        
        # 課題番号の設定 - 選択されたデータセットに対応するサブグループの課題番号を取得
        dataset_grant_numbers = get_grant_numbers_from_dataset(selected_dataset)
        if hasattr(edit_grant_number_combo, 'update_grant_numbers'):
            edit_grant_number_combo.update_grant_numbers(dataset_grant_numbers)
        
        # 現在のデータセットの課題番号を選択状態にする
        current_grant_number = attrs.get("grantNumber", "")
        if current_grant_number and dataset_grant_numbers:
            # コンボボックスに該当アイテムがあるかチェック
            found_index = -1
            for i in range(edit_grant_number_combo.count()):
                if edit_grant_number_combo.itemData(i) == current_grant_number:
                    found_index = i
                    break
            
            if found_index >= 0:
                edit_grant_number_combo.setCurrentIndex(found_index)
                print(f"[DEBUG] 課題番号 '{current_grant_number}' を選択状態に設定")
            else:
                # 見つからない場合はテキストとして設定
                edit_grant_number_combo.lineEdit().setText(current_grant_number)
                print(f"[DEBUG] 課題番号 '{current_grant_number}' をテキストとして設定")
        else:
            print(f"[DEBUG] 課題番号設定スキップ: current='{current_grant_number}', available={len(dataset_grant_numbers) if dataset_grant_numbers else 0}")
        edit_description_edit.setText(attrs.get("description", ""))
        edit_contact_edit.setText(attrs.get("contact", ""))
        
        # エンバーゴ期間終了日
        embargo_date_str = attrs.get("embargoDate", "")
        if embargo_date_str:
            try:
                # ISO形式の日付をパース（簡易版）
                # "2026-03-31T03:00:00.000Z" のような形式を想定
                if "T" in embargo_date_str:
                    date_part = embargo_date_str.split("T")[0]
                else:
                    date_part = embargo_date_str.split()[0] if " " in embargo_date_str else embargo_date_str
                
                year, month, day = map(int, date_part.split("-"))
                qdate = QDate(year, month, day)
                edit_embargo_edit.setDate(qdate)
            except Exception as e:
                print(f"[WARNING] エンバーゴ日付のパースに失敗: {e}")
                # デフォルト値のまま
        
        # タクソノミーキー（スペース区切りで表示）
        taxonomy_keys = attrs.get("taxonomyKeys", [])
        if taxonomy_keys:
            edit_taxonomy_edit.setText(" ".join(taxonomy_keys))
        else:
            edit_taxonomy_edit.clear()  # 空の場合は明示的にクリア
        
        # 関連情報（新しい書式で表示）
        related_links = attrs.get("relatedLinks", [])
        print(f"[DEBUG] データセットの関連リンク: {related_links}")
        
        if related_links:
            links_text = []
            for link in related_links:
                title = link.get("title", "")
                url = link.get("url", "")
                if title and url:
                    # 新しい書式: タイトル:URL
                    link_line = f"{title}:{url}"
                    links_text.append(link_line)
                    print(f"[DEBUG] 関連情報行追加: '{link_line}'")
            
            final_text = ",".join(links_text)  # カンマ区切りに変更
            print(f"[DEBUG] テキストエリアに設定する関連情報: '{final_text}'")
            edit_related_links_edit.setText(final_text)
        else:
            print("[DEBUG] 関連情報が空 - テキストエリアをクリアします")
            edit_related_links_edit.clear()  # 関連情報が空の場合は明示的にクリア
        
        # TAGフィールド
        tags = attrs.get("tags", [])
        if tags:
            tags_text = ", ".join(tags)
            edit_tags_edit.setText(tags_text)
            print(f"[DEBUG] TAGを設定: '{tags_text}'")
        else:
            edit_tags_edit.clear()
            print("[DEBUG] TAGが空 - テキストエリアをクリアします")
        
        # データセット引用の書式
        citation_format = attrs.get("citationFormat", "")
        if citation_format:
            edit_citation_format_edit.setText(citation_format)
            print(f"[DEBUG] 引用書式を設定: '{citation_format}'")
        else:
            edit_citation_format_edit.clear()
            print("[DEBUG] 引用書式が空 - テキストエリアをクリアします")
        
        # 利用ライセンスの設定（relationshipsから取得）
        license_value = ""
        relationships = selected_dataset.get("relationships", {})
        if "license" in relationships:
            license_data = relationships["license"].get("data")
            if license_data is not None:
                license_value = license_data.get("id", "")
            # license_data が None の場合は license_value は空文字のまま
            
        if license_value:
            # コンボボックスに該当アイテムがあるかチェック
            found_index = -1
            for i in range(edit_license_combo.count()):
                if edit_license_combo.itemData(i) == license_value:
                    found_index = i
                    break
            
            if found_index >= 0:
                edit_license_combo.setCurrentIndex(found_index)
                print(f"[DEBUG] ライセンス設定 (コンボボックス): '{license_value}'")
            else:
                # 見つからない場合はテキストとして設定
                edit_license_combo.lineEdit().setText(license_value)
                print(f"[DEBUG] ライセンス設定 (テキスト): '{license_value}'")
        else:
            edit_license_combo.setCurrentIndex(-1)
            print("[DEBUG] ライセンスが空 - 選択をクリア")
        
        # 関連データセット表示
        relationships = selected_dataset.get("relationships", {})
        related_datasets_data = relationships.get("relatedDatasets", {}).get("data", [])
        
        # 関連データセット一覧をクリア
        selected_datasets_list.clear()
        
        if related_datasets_data:
            print(f"[DEBUG] 関連データセット: {len(related_datasets_data)}件")
            for related_dataset in related_datasets_data:
                dataset_id = related_dataset.get("id", "")
                if dataset_id:
                    # 全データセットキャッシュから詳細情報を取得
                    cached_datasets = getattr(related_dataset_combo, '_all_datasets_cache', [])
                    dataset_name = "名前取得中..."
                    for cached_dataset in cached_datasets:
                        if cached_dataset.get("id") == dataset_id:
                            dataset_name = cached_dataset.get("attributes", {}).get("name", "名前なし")
                            break
                    
                    # リストに追加
                    list_item = QListWidgetItem(f"{dataset_name} (ID: {dataset_id})")
                    list_item.setData(Qt.UserRole, dataset_id)
                    selected_datasets_list.addItem(list_item)
                    print(f"[DEBUG] 関連データセット追加: {dataset_name} (ID: {dataset_id})")
        else:
            print("[DEBUG] 関連データセットが空")
        
        # チェックボックス
        edit_anonymize_checkbox.setChecked(attrs.get("isAnonymized", False))
        edit_data_entry_prohibited_checkbox.setChecked(attrs.get("isDataEntryProhibited", False))
        
        # 新しいチェックボックス: データ登録及び削除を禁止する
        # isDataEntryProhibitedがTrueの場合にこちらもチェック（仮の実装）
        edit_data_entry_delete_prohibited_checkbox.setChecked(attrs.get("isDataEntryProhibited", False))
        
        # データ一覧表示タイプの設定
        data_listing_type = attrs.get("dataListingType", "GALLERY")
        if data_listing_type == "TREE":
            edit_data_listing_tree_radio.setChecked(True)
            edit_data_listing_gallery_radio.setChecked(False)
        else:
            edit_data_listing_gallery_radio.setChecked(True)
            edit_data_listing_tree_radio.setChecked(False)
        
        # 共有ポリシーから広域シェア設定を取得
        sharing_policies = attrs.get("sharingPolicies", [])
        core_scope_enabled = False
        for policy in sharing_policies:
            # RDE全体共有のscope ID（データセット開設機能と同じID）
            if policy.get("scopeId") == "22aec474-bbf2-4826-bf63-60c82d75df41":
                core_scope_enabled = policy.get("permissionToView", False)
                break
        edit_share_core_scope_checkbox.setChecked(core_scope_enabled)
    
    # ドロップダウン選択時の処理
    def on_dataset_selection_changed():
        current_index = existing_dataset_combo.currentIndex()
        print(f"[DEBUG] データセット選択変更: インデックス={current_index}")
        
        if current_index <= 0:  # 最初のアイテム（"-- データセットを選択してください --"）または無効な選択
            print("[DEBUG] データセット未選択状態 - フォームをクリアします")
            clear_edit_form()
            # 関連データセットリストを再セットアップ（除外なし）
            setup_related_datasets(related_dataset_combo)
        else:
            selected_dataset = existing_dataset_combo.itemData(current_index)
            if selected_dataset:
                dataset_name = selected_dataset.get("attributes", {}).get("name", "不明")
                dataset_id = selected_dataset.get("id", "")
                print(f"[DEBUG] データセット '{dataset_name}' を選択 - フォームに反映します")
                
                # 関連データセットリストを再セットアップ（現在のデータセットを除外）
                setup_related_datasets(related_dataset_combo, exclude_dataset_id=dataset_id)
                
                populate_edit_form_local(selected_dataset)
            else:
                print("[DEBUG] データセットデータが取得できません - フォームをクリアします")
                clear_edit_form()
                # 関連データセットリストを再セットアップ（除外なし）
                setup_related_datasets(related_dataset_combo)
    
    existing_dataset_combo.currentIndexChanged.connect(on_dataset_selection_changed)
    
    # フィルタ機能のイベントハンドラー
    def apply_filter(force_reload=False):
        """フィルタを適用してデータセット一覧を更新"""
        # 現在のフィルタ設定を取得
        if filter_user_only_radio.isChecked():
            filter_type = "user_only"
        elif filter_others_only_radio.isChecked():
            filter_type = "others_only"
        elif filter_all_radio.isChecked():
            filter_type = "all"
        else:
            filter_type = "user_only"  # デフォルト
        
        grant_number_filter = grant_number_filter_edit.text().strip()
        
        if force_reload:
            print(f"[INFO] キャッシュ更新: タイプ={filter_type}, 課題番号='{grant_number_filter}'")
        else:
            print(f"[INFO] フィルタ適用: タイプ={filter_type}, 課題番号='{grant_number_filter}'")
        
        # データセット一覧を再読み込み
        load_existing_datasets(filter_type, grant_number_filter, force_reload)
        
        # 選択をクリア
        existing_dataset_combo.setCurrentIndex(-1)
        clear_edit_form()
    
    def refresh_cache():
        """キャッシュを強制更新"""
        clear_cache()
        apply_filter(force_reload=True)
    
    # 動的フィルタリング用のタイマー
    filter_timer = QTimer()
    filter_timer.setSingleShot(True)
    filter_timer.timeout.connect(apply_filter)
    
    def on_filter_text_changed():
        """フィルタテキスト変更時の処理（遅延実行）"""
        filter_timer.stop()  # 既存のタイマーを停止
        filter_timer.start(500)  # 500ms後にフィルタを実行
    
    # フィルタイベントを接続
    cache_refresh_button.clicked.connect(refresh_cache)
    filter_user_only_radio.toggled.connect(lambda: apply_filter() if filter_user_only_radio.isChecked() else None)
    filter_others_only_radio.toggled.connect(lambda: apply_filter() if filter_others_only_radio.isChecked() else None)
    filter_all_radio.toggled.connect(lambda: apply_filter() if filter_all_radio.isChecked() else None)
    grant_number_filter_edit.textChanged.connect(on_filter_text_changed)  # リアルタイム絞り込み
    
    # ボタンエリア
    button_layout = QHBoxLayout()
    
    # データセットページ表示ボタン
    open_dataset_page_button = create_auto_resize_button(
        "RDEデータセットページを開く", 200, 40, "background-color: #2196F3; color: white; font-weight: bold; border-radius: 6px;"
    )
    button_layout.addWidget(open_dataset_page_button)
    
    # 更新ボタン
    update_button = create_auto_resize_button(
        "データセット更新", 200, 40, "background-color: #FF9800; color: white; font-weight: bold; border-radius: 6px;"
    )
    button_layout.addWidget(update_button)
    
    layout.addLayout(button_layout)
    
    def on_open_dataset_page():
        """データセットページをブラウザで開く"""
        current_index = existing_dataset_combo.currentIndex()
        if current_index <= 0:
            QMessageBox.warning(widget, "データセット未選択", "開くデータセットを選択してください。")
            return
        
        selected_dataset = existing_dataset_combo.itemData(current_index)
        if not selected_dataset:
            QMessageBox.warning(widget, "データセットエラー", "選択されたデータセットの情報が取得できません。")
            return
        
        dataset_id = selected_dataset.get("id")
        if not dataset_id:
            QMessageBox.warning(widget, "データエラー", "選択されたデータセットのIDが取得できません。")
            return
        
        # データセットページのURLを生成してブラウザで開く
        url = f"https://rde.nims.go.jp/rde/datasets/{dataset_id}"
        try:
            webbrowser.open(url)
            print(f"[INFO] データセットページをブラウザで開きました: {url}")
        except Exception as e:
            QMessageBox.warning(widget, "エラー", f"ブラウザでページを開けませんでした: {str(e)}")
    
    def on_update_dataset():
        """データセット更新処理"""
        current_index = existing_dataset_combo.currentIndex()
        if current_index <= 0:
            QMessageBox.warning(widget, "データセット未選択", "修正するデータセットを選択してください。")
            return
        
        selected_dataset = existing_dataset_combo.itemData(current_index)
        if not selected_dataset:
            QMessageBox.warning(widget, "データセットエラー", "選択されたデータセットの情報が取得できません。")
            return
        
        # 現在選択されているデータセットIDを保存（更新後の再選択用）
        current_dataset_id = selected_dataset.get("id")
        
        def refresh_ui_after_update():
            """データセット更新後のUI再読み込み"""
            try:
                print("[INFO] データセット更新後のUI再読み込みを開始")
                # 現在のフィルタ設定でデータセットリストを再読み込み（強制再読み込み）
                if filter_user_only_radio.isChecked():
                    filter_type = "user_only"
                elif filter_others_only_radio.isChecked():
                    filter_type = "others_only"
                elif filter_all_radio.isChecked():
                    filter_type = "all"
                else:
                    filter_type = "user_only"
                
                grant_number_filter = grant_number_filter_edit.text().strip()
                # キャッシュをクリアして強制再読み込み
                clear_cache()
                load_existing_datasets(filter_type, grant_number_filter, force_reload=True)
                
                # 更新したデータセットを再選択
                if current_dataset_id:
                    # キャッシュされたデータセットから検索
                    cached_datasets = getattr(existing_dataset_combo, '_datasets_cache', [])
                    updated_dataset = None
                    for dataset in cached_datasets:
                        if dataset.get("id") == current_dataset_id:
                            updated_dataset = dataset
                            break
                    
                    if updated_dataset:
                        # キャッシュされた表示名も取得
                        cached_display_names = getattr(existing_dataset_combo, '_display_names_cache', [])
                        
                        # 高速化されたアイテム追加処理を使用
                        existing_dataset_combo.clear()
                        if cached_datasets and cached_display_names:
                            print(f"[INFO] 高速再選択処理: {len(cached_datasets)}件のデータセット")
                            populate_combo_box_with_progress(existing_dataset_combo, cached_datasets, cached_display_names)
                        else:
                            # フォールバック処理
                            existing_dataset_combo.addItem("-- データセットを選択してください --", None)
                            for ds in cached_datasets:
                                attrs = ds.get("attributes", {})
                                dataset_id = ds.get("id", "")
                                name = attrs.get("name", "名前なし")
                                grant_number = attrs.get("grantNumber", "")
                                dataset_type = attrs.get("datasetType", "")
                                
                                # ユーザー所属かどうかで表示を区別
                                user_grant_numbers = get_user_grant_numbers()
                                if grant_number in user_grant_numbers:
                                    display_text = f"★ {grant_number} - {name} (ID: {dataset_id})"
                                else:
                                    display_text = f"{grant_number} - {name} (ID: {dataset_id})"
                                    
                                if dataset_type:
                                    display_text += f" [{dataset_type}]"
                                existing_dataset_combo.addItem(display_text, ds)
                        
                        # 更新したデータセットを検索して選択
                        selected_index = 0
                        for i in range(existing_dataset_combo.count()):
                            item_data = existing_dataset_combo.itemData(i)
                            if item_data and item_data.get("id") == current_dataset_id:
                                selected_index = i
                                break
                        
                        # 更新したデータセットを選択
                        existing_dataset_combo.setCurrentIndex(selected_index)
                        print(f"[INFO] データセット '{current_dataset_id}' を再選択しました (インデックス: {selected_index})")
                        
                        # 選択されたデータセットの情報をフォームに再表示
                        if selected_index > 0:
                            selected_dataset_new = existing_dataset_combo.itemData(selected_index)
                            if selected_dataset_new:
                                populate_edit_form_local(selected_dataset_new)
                    else:
                        print(f"[WARNING] 更新後のデータセット '{current_dataset_id}' がキャッシュに見つかりません")
                        # コンボボックスをクリア状態に戻す
                        existing_dataset_combo.clear()
                else:
                    # コンボボックスをクリア状態に戻す
                    existing_dataset_combo.clear()
                    
            except Exception as e:
                print(f"[ERROR] UI再読み込み中にエラー: {e}")
        
        # 編集機能を実装（後で追加）
        from classes.dataset.core.dataset_edit_functions import send_dataset_update_request
        send_dataset_update_request(
            widget, parent, selected_dataset,
            edit_dataset_name_edit, edit_grant_number_combo, edit_description_edit,
            edit_embargo_edit, edit_contact_edit, edit_taxonomy_edit,
            edit_related_links_edit, edit_tags_edit, edit_citation_format_edit, edit_license_combo,
            edit_data_listing_gallery_radio, edit_data_listing_tree_radio, selected_datasets_list, edit_anonymize_checkbox, 
            edit_data_entry_prohibited_checkbox, edit_data_entry_delete_prohibited_checkbox,
            edit_share_core_scope_checkbox, ui_refresh_callback=refresh_ui_after_update
        )
    
    # イベント接続
    open_dataset_page_button.clicked.connect(on_open_dataset_page)
    update_button.clicked.connect(on_update_dataset)
    
    # データ読み込み実行（デフォルトフィルタで）
    load_existing_datasets("user_only", "")
    
    # 初期状態でフォームをクリア
    clear_edit_form()
    print("[INFO] データセット編集ウィジェット初期化完了 - フォームをクリアしました")
    
    # 外部からリフレッシュできるように関数を属性として追加
    def refresh_with_current_filter(force_reload=False):
        """現在のフィルタ設定でリフレッシュ"""
        if filter_user_only_radio.isChecked():
            filter_type = "user_only"
        elif filter_others_only_radio.isChecked():
            filter_type = "others_only"
        elif filter_all_radio.isChecked():
            filter_type = "all"
        else:
            filter_type = "user_only"
        
        grant_number_filter = grant_number_filter_edit.text().strip()
        
        if force_reload:
            print("[INFO] 外部からキャッシュクリア付きリフレッシュ")
            clear_cache()
        
        load_existing_datasets(filter_type, grant_number_filter, force_reload)
    
    def refresh_cache_from_external():
        """外部からキャッシュを強制更新"""
        refresh_with_current_filter(force_reload=True)
    
    widget._refresh_dataset_list = refresh_with_current_filter
    widget._refresh_cache = refresh_cache_from_external
    
    # グローバル通知システムに登録
    notifier = get_dataset_refresh_notifier()
    notifier.register_callback(refresh_with_current_filter)
    
    # ウィジェットが削除されるときに通知システムから登録解除
    def cleanup():
        try:
            notifier.unregister_callback(refresh_with_current_filter)
        except:
            pass
    widget.destroyed.connect(cleanup)
    
    layout.addStretch()
    widget.setLayout(layout)
    return widget
