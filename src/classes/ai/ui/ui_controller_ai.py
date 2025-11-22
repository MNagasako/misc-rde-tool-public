"""
UIコントローラーAI機能クラス - ARIM RDE Tool v1.13.1
UIControllerのAI関連機能・レスポンス表示・AI設定・AI分析実行を担当
"""
import logging
import os
import json
import datetime

# ロガー設定
logger = logging.getLogger(__name__)

class UIControllerAI:
    """UIコントローラーのAI機能専門クラス"""
    
    def __init__(self, parent_controller):
        """
        UIControllerAIの初期化
        Args:
            parent_controller: 親のUIControllerインスタンス
        """
        self.parent = parent_controller
        self.parent_controller = parent_controller  # 別名での参照も追加
        self.logger = logging.getLogger("UIControllerAI")
        
        # 強制ログ機能を初期化
        self._setup_forced_logging()
        
        # AI関連の設定値
        self.ai_provider_combo = None
        self.ai_response_display = None
        self.ai_result_display = None
        self.ai_manager = None
        
        # AIデータマネージャーを初期化
        try:
            from classes.ai.core.ai_data_manager import AIDataManager
            self.ai_data_manager = AIDataManager(self.logger)
            self._force_log("AIDataManager初期化完了", "init")
        except Exception as e:
            import traceback
            self.logger.error(f"AIDataManager初期化失敗: {e}")
            traceback.print_exc()
            self.ai_data_manager = None
            self._force_log(f"AIDataManager初期化失敗: {e}", "init")
        
        # 初期化完了ログ
        self._force_log("UIControllerAI初期化完了", "init")
    
    def _setup_forced_logging(self):
        """強制ログ機能をセットアップ"""
        import datetime
        import os
        from config.common import get_dynamic_file_path
        
        self.forced_log_dir = get_dynamic_file_path("output/log")
        os.makedirs(self.forced_log_dir, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.forced_log_file = os.path.join(self.forced_log_dir, f"ai_forced_debug_{timestamp}.log")
        
        # 初期化ログ
        with open(self.forced_log_file, 'w', encoding='utf-8') as f:
            f.write(f"===== ARIM RDE Tool AI強制デバッグログ =====\n")
            f.write(f"初期化時刻: {datetime.datetime.now()}\n")
            f.write(f"ログファイル: {self.forced_log_file}\n")
            f.write(f"=========================================\n\n")
    
    def _get_safe_display(self, display_type):
        """安全に表示オブジェクトを取得（統一版）"""
        attr_name = f'ai_{display_type}_display'
        
        # 1. UIControllerAI自身の表示オブジェクトを優先
        if hasattr(self, attr_name):
            widget = getattr(self, attr_name)
            if widget:
                try:
                    # ウィジェットが有効かテスト
                    widget.isVisible()
                    return widget
                except RuntimeError:
                    logger.warning("%s (self) が削除されています", attr_name)
        
        # 2. 親の表示オブジェクトがあればそれを使用
        if hasattr(self.parent, attr_name):
            widget = getattr(self.parent, attr_name)
            if widget:
                try:
                    # ウィジェットが有効かテスト
                    widget.isVisible()
                    return widget
                except RuntimeError:
                    logger.warning("%s (parent) が削除されています", attr_name)
        
        # 3. フォールバック: ダミーオブジェクトを返す
        return self._get_dummy_display(display_type)
    
    def _get_safe_response_display(self):
        """安全にレスポンス表示オブジェクトを取得"""
        return self._get_safe_display('response')
    
    def _get_safe_result_display(self):
        """安全にAI結果表示オブジェクトを取得"""
        return self._get_safe_display('result')
    
    def _get_dummy_display(self, display_type='response'):
        """ダミーの表示オブジェクトを返す（統一版）"""
        class DummyDisplay:
            def __init__(self, type_name):
                self.type_name = type_name.upper()
                
            def append(self, text):
                logger.debug("[AI_%s] %s", self.type_name, text)
                
            def clear(self):
                logger.debug("[AI_%s] Cleared", self.type_name)
                
        return DummyDisplay(display_type)
    
    def _force_log(self, message, category="DEBUG"):
        """確実にファイルに残す強制ログ"""
        import datetime
        
        try:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{timestamp}] [{category}] {message}\n"
            
            # ファイルログ
            with open(self.forced_log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry)
            
            # コンソールログ
            logger.debug("[FORCE_LOG] %s", log_entry.strip())
            
            # UI表示ログ（利用可能な場合）
            if hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                self.parent.ai_response_display.append(f"[FORCE_LOG] {message}")
                
        except Exception as e:
            logger.error("[FORCE_LOG_ERROR] ログ書き込みエラー: %s", e)
    
    
    def execute_ai_analysis(self):
        """選択された分析方法に基づいてAI分析を実行"""
        try:
            # 強制ログ - AI分析開始
            self._force_log("AI分析実行開始", "ANALYSIS")
            
            # ai_response_displayの安全な取得
            response_display = self._get_safe_response_display()
            
            response_display.append("="*80)
            response_display.append("[DEBUG] AI分析実行開始 - 詳細ログモード")
            response_display.append("="*80)
            
            if not hasattr(self.parent, 'analysis_method_combo'):
                self._force_log("分析方法コンボボックスが見つからない", "ERROR")
                response_display.append("[ERROR] 分析方法が選択されていません")
                return
                
            method_name = self.parent.analysis_method_combo.currentText()
            method_data = self.parent.analysis_method_combo.itemData(self.parent.analysis_method_combo.currentIndex())
            
            self._force_log(f"選択された分析方法: {method_name}", "ANALYSIS")
            self._force_log(f"分析方法データ: {method_data}", "ANALYSIS")
            
            response_display.append(f"[DEBUG] 選択された分析方法: {method_name}")
            response_display.append(f"[DEBUG] 分析方法データ: {method_data}")
            
            if not method_data:
                self._force_log("無効な分析方法が選択された", "ERROR")
                response_display.append("[ERROR] 無効な分析方法が選択されています")
                return
            
            # 新しい設定構造から情報を取得
            exec_type = method_data.get("exec_type", "SINGLE")
            prompt_file = method_data.get("prompt_file", "")
            data_methods = method_data.get("data_methods", [])
            static_files = method_data.get("static_files", [])
            
            response_display.append(f"[DEBUG] 実行タイプ: {exec_type}")
            response_display.append(f"[DEBUG] プロンプトファイル: {prompt_file}")
            response_display.append(f"[DEBUG] データ取得メソッド: {data_methods}")
            response_display.append(f"[DEBUG] 静的ファイル: {static_files}")
            
            # 現在の選択状態をデバッグ出力
            self._debug_current_selections()
            
            # 課題番号と実験データの選択状態を検証
            validation_result = self._validate_task_and_experiment_selection(exec_type)
            if not validation_result["valid"]:
                response_display.append(f"[ERROR] {validation_result['message']}")
                return
            
            response_display.append(f"[INFO] {method_name} を開始...")
            response_display.append(f"[DEBUG] データ取得メソッド: {', '.join(data_methods)}")
            response_display.append(f"[DEBUG] 静的データファイル: {', '.join(static_files)}")
            
            # 実行タイプに応じて処理を分岐
            if exec_type == "MULTI":
                self._execute_analysis_batch(method_name, prompt_file, data_methods, static_files)
            elif exec_type == "SINGLE":
                self._execute_analysis_single(method_name, prompt_file, data_methods, static_files)
            else:
                response_display.append(f"[ERROR] 未対応の実行タイプ: {exec_type}")
                
        except Exception as e:
            response_display = self._get_safe_response_display()
            response_display.append(f"[ERROR] AI分析実行中にエラーが発生: {e}")
            import traceback
            response_display.append(f"[DEBUG] Traceback: {traceback.format_exc()}")

    def _debug_current_selections(self):
        """現在の選択状態を詳細デバッグ出力"""
        try:
            response_display = self._get_safe_response_display()
            response_display.append("[DEBUG] ===== 現在の選択状態 =====")
            
            # 課題番号の選択状態
            if hasattr(self.parent, 'task_id_combo') and self.parent.task_id_combo:
                current_task_index = self.parent.task_id_combo.currentIndex()
                if current_task_index >= 0:
                    task_text = self.parent.task_id_combo.currentText()
                    task_data = self.parent.task_id_combo.itemData(current_task_index)
                    response_display.append(f"[DEBUG] 選択課題番号: {task_text}")
                    response_display.append(f"[DEBUG] 課題データ: {task_data}")
                else:
                    response_display.append("[DEBUG] 課題番号: 未選択")
            else:
                response_display.append("[DEBUG] 課題番号コンボボックス: 未初期化")
            
            # 実験データの選択状態
            if hasattr(self.parent, 'experiment_combo') and self.parent.experiment_combo:
                current_exp_index = self.parent.experiment_combo.currentIndex()
                if current_exp_index >= 0:
                    exp_text = self.parent.experiment_combo.currentText()
                    exp_data = self.parent.experiment_combo.itemData(current_exp_index)
                    response_display.append(f"[DEBUG] 選択実験データ: {exp_text}")
                    if exp_data:
                        response_display.append(f"[DEBUG] 実験データキー数: {len(exp_data)}")
                        response_display.append(f"[DEBUG] 実験データキー: {list(exp_data.keys())[:10]}")
                        if "ARIM ID" in exp_data:
                            response_display.append(f"[DEBUG] ARIM ID: {exp_data['ARIM ID']}")
                        if "タイトル" in exp_data:
                            response_display.append(f"[DEBUG] タイトル: {exp_data['タイトル']}")
                    else:
                        response_display.append("[DEBUG] 実験データ: None")
                else:
                    response_display.append("[DEBUG] 実験データ: 未選択")
            else:
                response_display.append("[DEBUG] 実験データコンボボックス: 未初期化")
            
            # ARIM拡張情報の状態
            try:
                if (hasattr(self.parent, 'arim_extension_checkbox') and 
                    self.parent.arim_extension_checkbox and
                    hasattr(self.parent.arim_extension_checkbox, 'isChecked')):
                    
                    arim_checked = self.parent.arim_extension_checkbox.isChecked()
                    response_display.append(f"[DEBUG] ARIM拡張情報チェックボックス: {arim_checked}")
                    if arim_checked:
                        # ARIM拡張データの確認
                        try:
                            arim_data = self._load_arim_extension_data()
                            if arim_data:
                                response_display.append(f"[DEBUG] ARIM拡張データ件数: {len(arim_data)}")
                                if len(arim_data) > 0:
                                    sample_keys = list(arim_data[0].keys())[:10]
                                    response_display.append(f"[DEBUG] ARIM拡張データキー例: {sample_keys}")
                            else:
                                response_display.append("[DEBUG] ARIM拡張データ: 読み込み失敗")
                        except Exception as e:
                            response_display.append(f"[DEBUG] ARIM拡張データ確認エラー: {e}")
                else:
                    response_display.append("[DEBUG] ARIM拡張情報チェックボックス: 未初期化")
            except Exception as e:
                response_display.append(f"❌ エラーが発生しました: {e}")
                response_display.append("[DEBUG] ARIM拡張情報チェックボックス: アクセスエラー")
            
            # データソースの状態
            if hasattr(self.parent, 'arim_exp_radio') and self.parent.arim_exp_radio:
                arim_radio_checked = self.parent.arim_exp_radio.isChecked()
                arim_radio_enabled = self.parent.arim_exp_radio.isEnabled()
                response_display.append(f"[DEBUG] ARIMデータソースラジオ: checked={arim_radio_checked}, enabled={arim_radio_enabled}")
            else:
                response_display.append("[DEBUG] ARIMデータソースラジオ: 未初期化")
            
            response_display.append("[DEBUG] ===== 選択状態確認完了 =====")
            
        except Exception as e:
            response_display = self._get_safe_response_display()
            response_display.append(f"[ERROR] 選択状態確認中にエラー: {e}")

    def _validate_task_and_experiment_selection(self, exec_type="SINGLE"):
        """課題番号と実験データの選択状態を検証（実行タイプ対応）"""
        try:
            # 課題番号の選択状態確認
            if not hasattr(self.parent, 'task_id_combo') or not self.parent.task_id_combo:
                return {"valid": False, "message": "課題番号選択コンボボックスが見つかりません"}
            
            current_task_index = self.parent.task_id_combo.currentIndex()
            if current_task_index < 0:
                return {"valid": False, "message": "課題番号が選択されていません"}
            
            task_id = self.parent.task_id_combo.itemData(current_task_index)
            if not task_id:
                return {"valid": False, "message": "無効な課題番号が選択されています"}
            
            # 一括処理の場合は実験データ選択は必須ではない
            if exec_type == "MULTI":
                return {
                    "valid": True, 
                    "message": "一括処理用選択状態正常", 
                    "task_id": task_id, 
                    "experiment_data": None,
                    "is_no_data_case": False,
                    "exec_type": exec_type
                }
            
            # 単体処理の場合は実験データの選択状態確認
            if not hasattr(self.parent, 'experiment_combo') or not self.parent.experiment_combo:
                return {"valid": False, "message": "実験データ選択コンボボックスが見つかりません"}
            
            current_exp_index = self.parent.experiment_combo.currentIndex()
            if current_exp_index < 0:
                return {"valid": False, "message": "実験データが選択されていません"}
            
            experiment_data = self.parent.experiment_combo.itemData(current_exp_index)
            if not experiment_data:
                return {"valid": False, "message": "無効な実験データが選択されています"}
            
            # デフォルト状態の検出（課題番号選択待ち状態）
            current_exp_text = self.parent.experiment_combo.currentText()
            if "課題番号を選択してください" in current_exp_text:
                return {"valid": False, "message": "課題番号選択後の実験データ読み込みが必要です"}
            
            # 実験データなしの場合の追加検証
            is_no_data_case = experiment_data.get("実験データ種別") == "実験データなし"
            if is_no_data_case:
                # 実験データなしの場合、課題番号が正しく設定されているか確認
                if experiment_data.get("課題番号") != task_id:
                    return {"valid": False, "message": "実験データなしの場合の課題番号が一致しません"}
            else:
                # 実験データありの場合、必要なフィールドが存在するか確認
                if not experiment_data.get("ARIM ID") and not experiment_data.get("課題番号"):
                    return {"valid": False, "message": "実験データに必要な識別情報が不足しています"}
            
            return {
                "valid": True, 
                "message": "選択状態正常", 
                "task_id": task_id, 
                "experiment_data": experiment_data,
                "is_no_data_case": is_no_data_case,
                "exec_type": exec_type
            }
            
        except Exception as e:
            return {"valid": False, "message": f"選択状態検証中にエラー: {e}"}

    def _validate_for_dataset_explanation(self):
        """データセット説明専用の検証（実験データ必須）"""
        try:
            # 基本的な選択状態検証
            validation_result = self._validate_task_and_experiment_selection("SINGLE")
            if not validation_result["valid"]:
                return validation_result
            
            experiment_data = validation_result["experiment_data"]
            is_no_data_case = validation_result["is_no_data_case"]
            
            # データセット説明では実験データなしは許可しない
            if is_no_data_case:
                return {
                    "valid": False, 
                    "message": "データセット説明には実験データが必要です。実験データありの課題を選択してください。"
                }
            
            # 実験データが空またはNoneの場合
            if not experiment_data:
                return {
                    "valid": False, 
                    "message": "実験データが読み込まれていません。課題番号を選択し直してください。"
                }
            
            # 実験データの基本フィールドチェック
            required_fields = ["ARIM ID", "課題番号", "タイトル"]
            missing_fields = []
            for field in required_fields:
                if field not in experiment_data or not experiment_data.get(field):
                    missing_fields.append(field)
            
            if missing_fields:
                return {
                    "valid": False, 
                    "message": f"実験データに必要なフィールドが不足しています: {', '.join(missing_fields)}"
                }
            
            return {
                "valid": True,
                "message": "データセット説明用検証通過",
                "experiment_data": experiment_data,
                "is_no_data_case": False,
                "task_id": validation_result["task_id"]
            }
            
        except Exception as e:
            return {"valid": False, "message": f"データセット説明用検証中にエラー: {e}"}

    def _validate_experiment_data_content(self, experiment_data):
        """実験データの内容検証（強化版）"""
        try:
            response_display = self._get_safe_response_display()
            
            if not experiment_data:
                response_display.append("[DEBUG] 実験データがNullまたは空です")
                return False
            
            # 必須フィールドのチェック
            essential_fields = ["ARIM ID", "課題番号", "タイトル"]
            for field in essential_fields:
                value = experiment_data.get(field)
                if not value or str(value).strip() == "":
                    response_display.append(f"[DEBUG] 必須フィールド '{field}' が空です")
                    return False
            
            # 内部検証フラグをチェック（実験データリスト作成時に設定）
            if experiment_data.get("_has_valid_content") is False:
                response_display.append("[DEBUG] 実験データリスト作成時に内容不足と判定されました")
                return False
            
            # 内容フィールドのチェック（少なくとも1つは内容がある必要）
            content_fields = ["概要", "実験データ詳細", "利用装置", "装置仕様", "手法", "測定条件"]
            has_content = False
            content_summary = []
            for field in content_fields:
                value = experiment_data.get(field)
                if value and str(value).strip() != "" and str(value).strip().lower() != "nan":
                    has_content = True
                    content_length = len(str(value).strip())
                    content_summary.append(f"{field}({content_length}文字)")
            
            if not has_content:
                response_display.append("[DEBUG] 説明用の内容フィールドがすべて空です")
                return False
            
            response_display.append(f"[DEBUG] 実験データ内容検証通過 - 有効フィールド: {', '.join(content_summary)}")
            return True
            
        except Exception as e:
            try:
                response_display = self._get_safe_response_display()
                response_display.append(f"[DEBUG] 実験データ内容検証エラー: {e}")
            except:
                pass
            return False

    def _execute_analysis_single(self, method_name, prompt_file, data_methods, static_files):
        """単体分析の実行（プログレス表示付き）"""
        try:
            # 強制ログ - 分析実行開始
            self._force_log(f"単体分析実行開始: {method_name}", "SINGLE_ANALYSIS")
            self._force_log(f"プロンプトファイル: {prompt_file}", "SINGLE_ANALYSIS")
            self._force_log(f"データメソッド: {data_methods}", "SINGLE_ANALYSIS")
            self._force_log(f"静的ファイル: {static_files}", "SINGLE_ANALYSIS")
            
            # 安全なレスポンス表示オブジェクトを取得
            response_display = self._get_safe_response_display()
            
            # プログレス表示開始
            total_steps = len(data_methods) + len(static_files) + 3  # データ取得 + 静的ファイル + 検証・プロンプト・AI実行
            current_step = 0
            
            self.parent.show_progress(f"{method_name} 実行準備中...", current_step, total_steps)
            response_display.append(f"[INFO] 単体分析モードで実行: {method_name}")
            
            # 選択状態の検証結果を取得
            current_step += 1
            self.parent.update_progress(current_step, total_steps, "選択状態を検証中...")
            
            self._force_log("選択状態検証開始", "VALIDATION")
            
            # データセット説明の場合は特別な検証を実行
            if "データセット説明" in method_name:
                validation_result = self._validate_for_dataset_explanation()
                if not validation_result["valid"]:
                    response_display.append(f"[ERROR] {validation_result['message']}")
                    result_display = self._get_safe_result_display()
                    result_display.append(f"エラー: {validation_result['message']}")
                    self.parent.hide_progress()
                    return
            else:
                validation_result = self._validate_task_and_experiment_selection("SINGLE")
                if not validation_result["valid"]:
                    response_display.append(f"[ERROR] {validation_result['message']}")
                    self.parent.hide_progress()
                    return
            
            task_id = validation_result["task_id"]
            experiment_data = validation_result["experiment_data"]
            
            # 実験データの詳細ログを追加
            response_display.append(f"[DEBUG] 取得されたtask_id: {task_id}")
            response_display.append(f"[DEBUG] experiment_dataの型: {type(experiment_data)}")
            if experiment_data:
                response_display.append(f"[DEBUG] experiment_dataキー数: {len(experiment_data)}")
                response_display.append(f"[DEBUG] experiment_dataキー例: {list(experiment_data.keys())[:5]}")
                if "ARIM ID" in experiment_data:
                    response_display.append(f"[DEBUG] ARIM ID: {experiment_data['ARIM ID']}")
                if "タイトル" in experiment_data:
                    title = str(experiment_data.get("タイトル", ""))[:50]
                    response_display.append(f"[DEBUG] タイトル: {title}...")
            else:
                response_display.append(f"[DEBUG] ⚠️ experiment_dataがNullまたは空です")
            
            # データセット説明の場合は実験データの内容検証を追加実行
            if "データセット説明" in method_name:
                current_step += 1
                self.parent.update_progress(current_step, total_steps, "実験データ内容を検証中...")
                if not self._validate_experiment_data_content(experiment_data):
                    error_msg = "選択された実験データに必要な情報が不足しています。別の実験データを選択してください。"
                    response_display.append(f"[ERROR] {error_msg}")
                    result_display = self._get_safe_result_display()
                    result_display.append(f"エラー: {error_msg}")
                    self.parent.hide_progress()
                    return
                
                response_display.append(f"[INFO] 実験データ検証通過: {experiment_data.get('ARIM ID', '不明')} - {experiment_data.get('タイトル', '不明')}")
            
            # データ取得メソッドを実行してデータを準備
            response_display.append("[DEBUG] ===== データ取得メソッド実行開始 =====")
            
            # ファイルログ準備（データ取得用）
            import datetime
            import os
            from config.common import get_dynamic_file_path
            
            log_dir = get_dynamic_file_path("output/log")
            os.makedirs(log_dir, exist_ok=True)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            data_log_file = os.path.join(log_dir, f"ai_data_prepare_{timestamp}.log")
            
            def data_log_and_print(message):
                print(message)
                with open(data_log_file, 'a', encoding='utf-8') as f:
                    f.write(f"{message}\n")
            
            data_log_and_print(f"===== データ準備メソッド実行ログ =====")
            data_log_and_print(f"タイムスタンプ: {datetime.datetime.now()}")
            data_log_and_print(f"分析方法: {method_name}")
            data_log_and_print(f"データメソッド一覧: {data_methods}")
            data_log_and_print(f"課題ID: {task_id}")
            data_log_and_print(f"実験データ有無: {experiment_data is not None}")
            if experiment_data:
                data_log_and_print(f"実験データARIM ID: {experiment_data.get('ARIM ID', '不明')}")
                data_log_and_print(f"実験データタイトル: {experiment_data.get('タイトル', '不明')}")
            data_log_and_print("")
            
            prepared_data = {}
            for method in data_methods:
                current_step += 1
                self.parent.update_progress(current_step, total_steps, f"データ取得中: {method}")
                try:
                    data_log_and_print(f"=== {method} 実行開始 ===")
                    response_display.append(f"[DEBUG] データ取得メソッド実行: {method}")
                    response_display.append(f"[DEBUG] 引数 task_id: {task_id}")
                    response_display.append(f"[DEBUG] 引数 experiment_data有無: {experiment_data is not None}")
                    
                    if hasattr(self.parent, method):
                        method_func = getattr(self.parent, method)
                        data_log_and_print(f"メソッド {method} を実行中...")
                        response_display.append(f"[DEBUG] メソッド {method} を実行中...")
                        
                        # メソッド実行
                        result = method_func(task_id, experiment_data)
                        prepared_data[method] = result
                        
                        # 結果の詳細ログ
                        data_log_and_print(f"{method} 実行完了")
                        data_log_and_print(f"結果タイプ: {type(result)}")
                        if result:
                            result_str = str(result)
                            data_log_and_print(f"結果文字数: {len(result_str)}")
                            data_log_and_print(f"結果プレビュー: {result_str[:500]}...")
                            if len(result_str) > 1000:
                                data_log_and_print(f"結果末尾: ...{result_str[-500:]}")
                        else:
                            data_log_and_print(f"結果: None または空")
                        
                        # UI表示用の結果確認
                        if result:
                            result_preview = str(result)[:300] if len(str(result)) > 300 else str(result)
                            response_display.append(f"[DEBUG] {method} 結果プレビュー: {result_preview}...")
                            response_display.append(f"[DEBUG] {method} 結果文字数: {len(str(result))}")
                        else:
                            response_display.append(f"[DEBUG] {method} 結果: None または空")
                        
                        data_log_and_print(f"=== {method} 実行完了 ===")
                        response_display.append(f"[DEBUG] データ取得完了: {method}")
                        response_display.append(f"[DEBUG] データログファイル: {data_log_file}")
                    else:
                        data_log_and_print(f"[ERROR] メソッド {method} が見つかりません")
                        response_display.append(f"[WARNING] データ取得メソッドが見つかりません: {method}")
                        response_display.append(f"[DEBUG] 利用可能メソッド確認中...")
                        # 利用可能なメソッドをチェック
                        available_methods = [attr for attr in dir(self.parent) if not attr.startswith('_') and callable(getattr(self.parent, attr))]
                        matching_methods = [m for m in available_methods if method.lower() in m.lower()]
                        if matching_methods:
                            data_log_and_print(f"類似メソッド候補: {matching_methods[:5]}")
                            response_display.append(f"[DEBUG] 類似メソッド候補: {matching_methods[:5]}")
                except Exception as e:
                    data_log_and_print(f"[ERROR] {method} 実行エラー: {e}")
                    import traceback
                    data_log_and_print(f"スタックトレース:")
                    data_log_and_print(traceback.format_exc())
                    response_display.append(f"[ERROR] データ取得エラー ({method}): {e}")
            
            data_log_and_print(f"===== データ準備完了 =====")
            data_log_and_print(f"準備されたデータキー: {list(prepared_data.keys())}")
            for key, value in prepared_data.items():
                if value:
                    data_log_and_print(f"{key}: {len(str(value))} 文字")
                else:
                    data_log_and_print(f"{key}: None または空")
            data_log_and_print("")
            
            response_display.append(f"[DEBUG] データ準備完了: {list(prepared_data.keys())}")
            response_display.append(f"[DEBUG] prepared_data最終結果キー: {list(prepared_data.keys())}")
            response_display.append("[DEBUG] ===== データ取得メソッド実行完了 =====")
            
            # 静的ファイルを読み込み
            response_display.append("[DEBUG] ===== 静的ファイル読み込み開始 =====")
            static_data = {}
            for file_name in static_files:
                current_step += 1
                self.parent.update_progress(current_step, total_steps, f"静的ファイル読み込み中: {file_name}")
                try:
                    response_display.append(f"[DEBUG] 静的ファイル読み込み: {file_name}")
                    file_data = self._load_static_file(file_name)
                    static_data[file_name] = file_data
                    
                    if file_data:
                        if isinstance(file_data, dict):
                            response_display.append(f"[DEBUG] {file_name}: dict型、{len(file_data)}キー")
                            if len(file_data) > 0:
                                sample_keys = list(file_data.keys())[:5]
                                response_display.append(f"[DEBUG] {file_name} キー例: {sample_keys}")
                        else:
                            file_preview = str(file_data)[:200] if len(str(file_data)) > 200 else str(file_data)
                            response_display.append(f"[DEBUG] {file_name} 内容プレビュー: {file_preview}...")
                    else:
                        response_display.append(f"[DEBUG] {file_name}: 空またはNone")
                    
                    response_display.append(f"[DEBUG] 静的ファイル読み込み完了: {file_name}")
                except Exception as e:
                    response_display.append(f"[ERROR] 静的ファイル読み込みエラー ({file_name}): {e}")
            
            response_display.append(f"[DEBUG] static_data最終結果キー: {list(static_data.keys())}")
            response_display.append("[DEBUG] ===== 静的ファイル読み込み完了 =====")
            # プロンプトファイルを読み込み、データを挿入してAI分析実行
            current_step += 1
            self.parent.update_progress(current_step, total_steps, "AI分析実行中...")
            self._execute_ai_analysis_with_data(prompt_file, prepared_data, static_data, experiment_data, is_batch_mode=False)
            
            # 完了
            self.parent.update_progress(total_steps, total_steps, "分析完了")
            self.parent.hide_progress()
            
        except Exception as e:
            try:
                response_display = self._get_safe_response_display()
                response_display.append(f"[ERROR] 単体分析実行中にエラー: {e}")
            except:
                pass
            self.parent.hide_progress()

    def _execute_analysis_batch(self, method_name, prompt_file, data_methods, static_files):
        """一括分析の実行（プログレス表示付き）"""
        try:
            # 安全なレスポンス表示オブジェクトを取得
            response_display = self._get_safe_response_display()
            
            # プログレス表示開始（初期段階）
            self.parent.show_progress(f"{method_name} 一括実行準備中...", 0, 100)
            response_display.append(f"[INFO] 一括分析モードで実行: {method_name}")
            
            # 一括処理開始時に結果表示をクリア
            result_display = self._get_safe_result_display()
            result_display.clear()
            
            # 選択状態の検証結果を取得
            self.parent.update_progress(10, 100, "選択状態を検証中...")
            validation_result = self._validate_task_and_experiment_selection("MULTI")
            if not validation_result["valid"]:
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(f"[ERROR] {validation_result['message']}")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append(f"[ERROR] {validation_result['message']}")
                    else:
                        response_display.append(f"[ERROR] {validation_result['message']}")
                except:
                    pass
                self.parent.hide_progress()
                return
            
            task_id = validation_result["task_id"]
            
            # 課題に関連する全ての実験データを取得
            self.parent.update_progress(20, 100, "実験データ一覧を取得中...")
            all_experiments = self._get_all_experiments_for_task(task_id)
            
            # DataFrameが空かどうかを適切にチェック
            if all_experiments is None or (hasattr(all_experiments, 'empty') and all_experiments.empty) or len(all_experiments) == 0:
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(f"[WARNING] 課題 {task_id} に関連する実験データが見つかりません")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append(f"[WARNING] 課題 {task_id} に関連する実験データが見つかりません")
                    else:
                        response_display.append(f"[WARNING] 課題 {task_id} に関連する実験データが見つかりません")
                except:
                    pass
                self.parent.hide_progress()
                return
            
            # DataFrameを辞書のリストに変換
            if hasattr(all_experiments, 'to_dict'):
                # pandasのDataFrameの場合
                experiments_list = all_experiments.to_dict('records')
            else:
                # 既にリストの場合
                experiments_list = all_experiments
            
            try:
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append(f"[INFO] {len(experiments_list)} 件の実験データを一括処理します")
                elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                    self.parent.ai_response_display.append(f"[INFO] {len(experiments_list)} 件の実験データを一括処理します")
                else:
                    response_display.append(f"[INFO] {len(experiments_list)} 件の実験データを一括処理します")
            except:
                pass
            
            # 静的ファイルを一度だけ読み込み
            self.parent.update_progress(30, 100, "静的ファイル読み込み中...")
            static_data = {}
            for file_name in static_files:
                try:
                    file_data = self._load_static_file(file_name)
                    static_data[file_name] = file_data
                    try:
                        if hasattr(self, 'ai_response_display') and self.ai_response_display:
                            self.ai_response_display.append(f"[DEBUG] 静的ファイル読み込み完了: {file_name}")
                        elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                            self.parent.ai_response_display.append(f"[DEBUG] 静的ファイル読み込み完了: {file_name}")
                        else:
                            response_display.append(f"[DEBUG] 静的ファイル読み込み完了: {file_name}")
                    except:
                        pass
                except Exception as e:
                    try:
                        if hasattr(self, 'ai_response_display') and self.ai_response_display:
                            self.ai_response_display.append(f"[ERROR] 静的ファイル読み込みエラー ({file_name}): {e}")
                        elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                            self.parent.ai_response_display.append(f"[ERROR] 静的ファイル読み込みエラー ({file_name}): {e}")
                        else:
                            response_display.append(f"[ERROR] 静的ファイル読み込みエラー ({file_name}): {e}")
                    except:
                        pass
            
            # 各実験データに対して分析を実行
            for i, experiment_data in enumerate(experiments_list, 1):
                # プログレス計算（30%〜95%の範囲で実験処理）
                progress = 30 + int((i / len(experiments_list)) * 65)
                self.parent.update_progress(progress, 100, f"実験 {i}/{len(all_experiments)} を処理中...")
                
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(f"[INFO] 実験 {i}/{len(experiments_list)} を処理中...")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append(f"[INFO] 実験 {i}/{len(experiments_list)} を処理中...")
                    else:
                        response_display.append(f"[INFO] 実験 {i}/{len(experiments_list)} を処理中...")
                except:
                    pass
                
                # データ取得メソッドを実行してデータを準備
                prepared_data = {}
                for method in data_methods:
                    try:
                        if hasattr(self.parent, method):
                            method_func = getattr(self.parent, method)
                            result = method_func(task_id, experiment_data)
                            prepared_data[method] = result
                        else:
                            try:
                                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                                    self.ai_response_display.append(f"[WARNING] データ取得メソッドが見つかりません: {method}")
                                elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                                    self.parent.ai_response_display.append(f"[WARNING] データ取得メソッドが見つかりません: {method}")
                                else:
                                    response_display.append(f"[WARNING] データ取得メソッドが見つかりません: {method}")
                            except:
                                pass
                    except Exception as e:
                        try:
                            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                                self.ai_response_display.append(f"[ERROR] データ取得エラー ({method}): {e}")
                            elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                                self.parent.ai_response_display.append(f"[ERROR] データ取得エラー ({method}): {e}")
                            else:
                                response_display.append(f"[ERROR] データ取得エラー ({method}): {e}")
                        except:
                            pass
                
                # プロンプトファイルを読み込み、データを挿入してAI分析実行
                self._execute_ai_analysis_with_data(prompt_file, prepared_data, static_data, experiment_data, is_batch_mode=True)
            
            # 完了
            self.parent.update_progress(100, 100, "一括分析完了")
            try:
                self.parent.hide_progress()
            except RuntimeError as re:
                logger.warning("hide_progress failed (Widget deleted): %s", re)
                
        except Exception as e:
            try:
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append(f"[ERROR] 一括分析実行中にエラー: {e}")
                elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                    self.parent.ai_response_display.append(f"[ERROR] 一括分析実行中にエラー: {e}")
                else:
                    response_display = self._get_safe_response_display()
                    response_display.append(f"[ERROR] 一括分析実行中にエラー: {e}")
            except:
                pass
            try:
                self.parent.hide_progress()
            except RuntimeError as re:
                logger.warning("hide_progress failed (Widget deleted): %s", re)

    def _load_static_file(self, file_name):
        """静的ファイルを読み込み"""
        try:
            from config.common import INPUT_DIR
            
            # 設定ディレクトリから読み込み
            config_path = os.path.join(os.path.dirname(INPUT_DIR), "config", file_name)
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    if file_name.endswith('.json'):
                        return json.load(f)
                    else:
                        return f.read()
            
            # inputディレクトリから読み込み
            input_path = os.path.join(INPUT_DIR, file_name)
            if os.path.exists(input_path):
                with open(input_path, 'r', encoding='utf-8') as f:
                    if file_name.endswith('.json'):
                        return json.load(f)
                    else:
                        return f.read()
            
            # aiディレクトリから読み込み
            ai_path = os.path.join(INPUT_DIR, "ai", file_name)
            if os.path.exists(ai_path):
                with open(ai_path, 'r', encoding='utf-8') as f:
                    if file_name.endswith('.json'):
                        return json.load(f)
                    else:
                        return f.read()
            
            # ファイルが見つからない場合
            raise FileNotFoundError(f"静的ファイルが見つかりません: {file_name}")
            
        except Exception as e:
            self.logger.error(f"静的ファイル読み込みエラー: {e}")
            raise

    def _get_all_experiments_for_task(self, task_id):
        """課題IDに関連する全ての実験データを取得"""
        try:
            # AIテストウィジェットからデータソース選択状態を取得
            use_arim_data = False
            
            # current_ai_test_widgetを通じてデータソース状態を確認
            ai_test_widget = None
            if hasattr(self, 'current_ai_test_widget') and self.current_ai_test_widget:
                ai_test_widget = self.current_ai_test_widget
            elif (hasattr(self.parent_controller, 'ai_controller') and 
                  hasattr(self.parent_controller.ai_controller, 'current_ai_test_widget')):
                ai_test_widget = self.parent_controller.ai_controller.current_ai_test_widget
            elif hasattr(self.parent_controller, 'ai_test_widget'):
                ai_test_widget = self.parent_controller.ai_test_widget
            
            if (ai_test_widget and hasattr(ai_test_widget, 'arim_exp_radio') and 
                ai_test_widget.arim_exp_radio):
                use_arim_data = (ai_test_widget.arim_exp_radio.isChecked() and 
                               ai_test_widget.arim_exp_radio.isEnabled())
                logger.debug("AIテストウィジェットからデータソース状態取得: use_arim_data=%s", use_arim_data)
            else:
                logger.debug("AIテストウィジェット状態が取得できません、標準データを使用")
            
            # AIDataManagerを使用して実験データを取得
            if hasattr(self.parent_controller, 'ai_data_manager') and self.parent_controller.ai_data_manager:
                experiments = self.parent_controller.ai_data_manager.get_experiments_for_task(task_id, use_arim_data)
                if experiments is None:
                    self.logger.warning(f"課題{task_id}の実験データ取得に失敗")
                    return []
                return experiments
            
            # フォールバック: 親コントローラーのメソッドを利用
            if hasattr(self.parent, '_get_all_experiments_for_task'):
                return self.parent._get_all_experiments_for_task(task_id)
            else:
                self.logger.warning("_get_all_experiments_for_task メソッドが見つかりません")
                return []
        except Exception as e:
            self.logger.error(f"実験データ一覧取得エラー: {e}")
            return []

    def debug_excel_columns(self):
        """デバッグ用: Excelファイルの列構造確認"""
        if hasattr(self.parent, 'ai_data_manager'):
            self.parent.ai_data_manager.debug_column_structure(use_arim_data=False)
            self.parent.ai_data_manager.debug_column_structure(use_arim_data=True)
        else:
            self.logger.warning("ai_data_manager が見つかりません")

    
    def show_text_area_with_ai_response_info(self, text_widget, title):
        """
        AI関連のレスポンス情報を含むテキストエリア拡大表示
        Args:
            text_widget: 表示対象のテキストウィジェット
            title: ダイアログのタイトル
        """
        try:
            content = ""
            if hasattr(text_widget, 'toPlainText'):
                content = text_widget.toPlainText()
            elif hasattr(text_widget, 'text'):
                content = text_widget.text()
            else:
                content = str(text_widget)
            
            # AI関連の情報を追加表示
            info_text = ""
            
            # 問い合わせ結果の場合、レスポンス情報を追加
            if title == "問い合わせ結果" and hasattr(self.parent, 'last_response_info') and self.parent.last_response_info:
                response_info = self.parent.last_response_info
                
                info_text += "【レスポンス情報】\n"
                info_text += f"モデル: {response_info.get('model', '不明')}\n"
                info_text += f"応答時間: {response_info.get('response_time', 0):.2f}秒\n"
                
                # 使用量情報（あれば）
                usage = response_info.get('usage', {})
                if usage:
                    info_text += f"入力トークン: {usage.get('prompt_tokens', 0)}\n"
                    info_text += f"出力トークン: {usage.get('completion_tokens', 0)}\n"
                    info_text += f"総トークン: {usage.get('total_tokens', 0)}\n"
                
                info_text += f"分析種別: AI問い合わせ\n"
                info_text += f"タイムスタンプ: {response_info.get('timestamp', '不明')}\n"
                
                if not response_info.get('success', True):
                    error_msg = response_info.get('error', '不明なエラー')
                    info_text += f"エラー: {error_msg}\n"
                
                info_text += "\n" + "="*50 + "\n\n"
            
            # 最終的なコンテンツを組み立て
            full_content = info_text + content
            
            # ダイアログクラスのインポートと表示
            try:
                from classes.ui.dialogs.ui_dialogs import TextAreaExpandDialog
                dialog = TextAreaExpandDialog(
                    parent=self.parent.parent if hasattr(self.parent, 'parent') else None,
                    title=title,
                    content=full_content,
                    editable=False
                )
                dialog.show()
            except ImportError:
                # フォールバック: 元のダイアログを使用
                self._show_fallback_dialog(title, full_content)
                
        except Exception as e:
            self.logger.error(f"AI レスポンス情報表示エラー: {e}")
            # 基本的なテキスト表示にフォールバック
            if hasattr(self.parent, 'show_text_area_expanded'):
                self.parent.show_text_area_expanded(text_widget, title)
    
    def _show_fallback_dialog(self, title, content):
        """フォールバック用のダイアログ表示"""
        try:
            from qt_compat.widgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
            
            dialog = QDialog()
            dialog.setWindowTitle(title)
            dialog.setModal(True)
            dialog.resize(800, 600)
            
            layout = QVBoxLayout()
            
            text_edit = QTextEdit()
            text_edit.setPlainText(content)
            text_edit.setReadOnly(True)
            layout.addWidget(text_edit)
            
            close_btn = QPushButton("閉じる")
            close_btn.clicked.connect(dialog.close)
            layout.addWidget(close_btn)
            
            dialog.setLayout(layout)
            dialog.exec()
            
        except Exception as e:
            self.logger.error(f"フォールバックダイアログ表示エラー: {e}")
    
    def create_ai_test_widget(self):
        """
        AIテスト機能用のウィジェットを作成
        
        【重要】AIウィジェット初期化の修正
        このメソッドは Phase 2 Step 2.2 で発生した「AI provider combo not initialized」
        問題を修正するため、AITestWidgetで作成されたウィジェットをUIControllerAIに
        正しく転送するよう修正されました。
        
        【修正内容】
        - AITestWidgetで作成されたai_provider_combo等のウィジェットを取得
        - setup_ai_widgets()を呼び出してUIControllerAIに設定
        - ウィジェット初期化の確認とログ出力を追加
        
        【コメント追加理由】
        - 将来同様のウィジェット初期化問題を防ぐため
        - setup_ai_widgets呼び出しの重要性を明確化
        - AI接続テスト機能の正常動作を保証
        """
        try:
            from .ui_ai_test import AITestWidget
            ai_test_widget_instance = AITestWidget(self.parent)
            widget = ai_test_widget_instance.create_widget()
            # AIテストウィジェットインスタンスの参照を保存
            self.current_ai_test_widget = ai_test_widget_instance
            
            # AITestWidgetで作成されたウィジェットをAIControllerにも設定
            # parent（UIController）に設定されたウィジェットをAIControllerに転送
            if hasattr(self.parent, 'ai_provider_combo'):
                self.setup_ai_widgets(
                    ai_response_display=getattr(self.parent, 'ai_response_display', None),
                    ai_result_display=getattr(self.parent, 'ai_result_display', None),
                    ai_provider_combo=getattr(self.parent, 'ai_provider_combo', None)
                )
                self.logger.info("[DEBUG] AIウィジェットをUIControllerAIに設定完了")
            else:
                self.logger.warning("[DEBUG] ai_provider_comboが親コントローラーに設定されていません")
            
            return widget
        except ImportError as e:
            self.logger.error(f"AITestWidget インポート失敗: {e}")
            # フォールバック: 元の実装を維持
            self.current_ai_test_widget = None
            return self._create_ai_test_widget_fallback()
    
    def _create_ai_test_widget_fallback(self):
        """AIテストウィジェットのフォールバック実装"""
        try:
            from qt_compat.widgets import QWidget, QVBoxLayout, QLabel
            
            widget = QWidget()
            layout = QVBoxLayout()
            
            label = QLabel("AIテスト機能は現在利用できません")
            try:
                from classes.theme.theme_keys import ThemeKey as _ThemeKey
                from classes.theme.theme_manager import get_color as _get_color
                label.setStyleSheet(f"color: {_get_color(_ThemeKey.TEXT_MUTED)}; font-size: 14px; padding: 20px;")
            except Exception:
                label.setStyleSheet("font-size: 14px; padding: 20px;")
            layout.addWidget(label)
            
            widget.setLayout(layout)
            return widget
            
        except Exception as e:
            self.logger.error(f"AIテストウィジェットフォールバック作成エラー: {e}")
            return QWidget()  # 空のウィジェットを返す
    
    def test_ai_connection(self):
        """AI接続テスト"""
        try:
            if not self.ai_provider_combo:
                self.logger.warning("AI provider combo not initialized")
                if self.ai_response_display:
                    self.ai_response_display.append("[ERROR] AI provider combo not initialized")
                return
                
            provider_text = self.ai_provider_combo.currentText()
            provider_id = self.ai_provider_combo.currentData()  # 実際のプロバイダーIDを取得
            
            if provider_text == "設定なし" or not provider_id:
                if self.ai_response_display:
                    self.ai_response_display.append("[ERROR] AIプロバイダーが設定されていません")
                return
                
            if self.ai_response_display:
                self.ai_response_display.append(f"[INFO] {provider_text} との接続をテスト中...")
            
            if not self.ai_manager:
                self.logger.warning("AI manager not initialized")
                if self.ai_response_display:
                    self.ai_response_display.append("[ERROR] AI manager not initialized")
                return
                
            # プロバイダーIDを使用してテスト実行
            result = self.ai_manager.test_connection(provider_id)
            
            if result["success"]:
                if self.ai_response_display:
                    self.ai_response_display.append(f"[SUCCESS] {provider_text} との接続に成功しました")
                    
                    # モデル名と応答時間を表示
                    if "model" in result:
                        self.ai_response_display.append(f"使用モデル: {result['model']}")
                    if "response_time" in result:
                        self.ai_response_display.append(f"応答時間: {result['response_time']:.2f}秒")
                
                # 接続テスト情報を保存
                if hasattr(self.parent, 'last_response_info'):
                    self.parent.last_response_info = {
                        "model": result.get("model", "不明"),
                        "response_time": result.get("response_time", 0),
                        "usage": result.get("usage", {}),
                        "success": True,
                        "analysis_type": "接続テスト"
                    }
                
                # テスト応答は結果表示欄に表示
                if self.ai_result_display:
                    self.ai_result_display.clear()
                    self.ai_result_display.append(f"接続テスト成功: {result['response']}")
            else:
                if self.ai_response_display:
                    self.ai_response_display.append(f"[ERROR] {provider_text} との接続に失敗: {result['error']}")
                    
                    # エラー時でもモデル名と応答時間を表示（あれば）
                    if "model" in result:
                        self.ai_response_display.append(f"使用モデル: {result['model']}")
                    if "response_time" in result:
                        self.ai_response_display.append(f"応答時間: {result['response_time']:.2f}秒")
                
                # エラー時の情報を保存
                if hasattr(self.parent, 'last_response_info'):
                    self.parent.last_response_info = {
                        "model": result.get("model", "不明"),
                        "response_time": result.get("response_time", 0),
                        "usage": result.get("usage", {}),
                        "success": False,
                        "error": result.get("error", "不明なエラー"),
                        "analysis_type": "接続テスト"
                    }
                
                if self.ai_result_display:
                    self.ai_result_display.clear()
                    self.ai_result_display.append("接続テストに失敗しました。")
                    
        except Exception as e:
            error_msg = f"[ERROR] 接続テスト中にエラーが発生: {e}"
            self.logger.error(error_msg)
            if self.ai_response_display:
                self.ai_response_display.append(error_msg)
    
    def init_ai_settings(self):
        """AI設定の初期化（ユーザー選択を尊重）"""
        try:
            if not hasattr(self.parent, 'ai_manager'):
                self.logger.warning("Parent does not have ai_manager")
                return
                
            self.ai_manager = self.parent.ai_manager
            
            # プロバイダー設定の初期化
            if self.ai_provider_combo and self.ai_manager:
                try:
                    # 既に選択されているプロバイダーがあるかチェック
                    current_provider_id = None
                    current_index = self.ai_provider_combo.currentIndex()
                    if current_index >= 0:
                        current_provider_id = self.ai_provider_combo.itemData(current_index)
                        current_provider_text = self.ai_provider_combo.currentText()
                        
                        # 有効なプロバイダーが既に選択されている場合は変更しない
                        if current_provider_id and current_provider_id != "設定なし" and current_provider_text != "設定なし":
                            self.logger.info(f"[DEBUG] ユーザー選択を維持: プロバイダー={current_provider_text} (ID: {current_provider_id})")
                            
                            # モデル選択も維持するため、ここで初期化処理を終了
                            return
                    
                    # 有効な選択がない場合のみデフォルト値を設定
                    default_provider = self.ai_manager.get_default_provider()
                    self.logger.info(f"[DEBUG] デフォルトプロバイダーを設定: {default_provider}")
                    
                    if default_provider:
                        # コンボボックスでデフォルトプロバイダーをIDで検索
                        found_index = -1
                        for i in range(self.ai_provider_combo.count()):
                            item_data = self.ai_provider_combo.itemData(i)
                            self.logger.info(f"[DEBUG] コンボボックス項目 {i}: text='{self.ai_provider_combo.itemText(i)}', data='{item_data}'")
                            if item_data == default_provider:
                                found_index = i
                                break
                        
                        if found_index >= 0:
                            self.ai_provider_combo.setCurrentIndex(found_index)
                            self.logger.info(f"[DEBUG] デフォルトプロバイダー設定完了: インデックス {found_index}")
                        else:
                            self.logger.warning(f"[DEBUG] デフォルトプロバイダー '{default_provider}' がコンボボックスに見つかりません")
                        
                        # モデルコンボボックスがあれば更新
                        if hasattr(self.parent, 'ai_model_combo') and self.parent.ai_model_combo:
                            default_model = self.ai_manager.get_default_model(default_provider)
                            self.logger.info(f"[DEBUG] default_model={default_model}")
                            if default_model:
                                model_index = self.parent.ai_model_combo.findText(default_model)
                                if model_index >= 0:
                                    self.parent.ai_model_combo.setCurrentIndex(model_index)
                                    self.logger.info(f"[DEBUG] デフォルトモデル設定完了: {default_model}")
                    else:
                        self.logger.warning("[DEBUG] デフォルトプロバイダーが設定されていません")
                
                except Exception as e:
                    self.logger.warning(f"AI設定の初期化で警告: {e}")
                    
        except Exception as e:
            self.logger.error(f"AI設定初期化エラー: {e}")
    
    def setup_ai_widgets(self, ai_response_display=None, ai_result_display=None, ai_provider_combo=None):
        """AIウィジェットの設定"""
        self.logger.info(f"[DEBUG] setup_ai_widgets呼び出し: response_display={bool(ai_response_display)}, result_display={bool(ai_result_display)}, provider_combo={bool(ai_provider_combo)}")
        
        self.ai_response_display = ai_response_display
        self.ai_result_display = ai_result_display
        self.ai_provider_combo = ai_provider_combo
        
        self.logger.info(f"[DEBUG] AIウィジェット設定完了: ai_provider_combo={bool(self.ai_provider_combo)}")
        
        # AI設定の初期化を実行
        self.init_ai_settings()

    def send_ai_prompt(self):
        """AIにプロンプトを送信（プログレス表示付き）"""
        try:
            # 安全なレスポンス表示オブジェクトを取得
            response_display = self._get_safe_response_display()
            
            # プロバイダーとモデルを安全に取得（_get_ai_configメソッドを使用）
            provider, model = self._get_ai_config(response_display)
            
            # プロンプトを安全に取得
            prompt = ""
            if hasattr(self.parent, 'ai_prompt_input') and self.parent.ai_prompt_input:
                prompt = self.parent.ai_prompt_input.toPlainText().strip()
            
            if provider == "設定なし":
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append("[ERROR] AIプロバイダーが設定されていません")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append("[ERROR] AIプロバイダーが設定されていません")
                    else:
                        response_display.append("[ERROR] AIプロバイダーが設定されていません")
                except:
                    pass
                return
                
            if not prompt:
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append("[ERROR] プロンプトを入力してください")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append("[ERROR] プロンプトを入力してください")
                    else:
                        response_display.append("[ERROR] プロンプトを入力してください")
                except:
                    pass
                return
            
            # プログレス表示開始
            self.parent.show_progress("プロンプト送信準備中...", 0, 100)
            
            # リクエスト内容を保存（ポップアップ表示用）
            import datetime
            self.parent.last_request_content = prompt
            self.parent.last_request_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.debug("send_ai_prompt: リクエスト保存完了 - 長さ: %s 文字", len(prompt))
            
            # ログ表示（ログ・DEBUG・JSON用）
            try:
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append(f"[INFO] {provider} ({model}) にプロンプトを送信中...")
                    self.ai_response_display.append(f"プロンプト: {prompt}")
                    self.ai_response_display.append("---")
                elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                    self.parent.ai_response_display.append(f"[INFO] {provider} ({model}) にプロンプトを送信中...")
                    self.parent.ai_response_display.append(f"プロンプト: {prompt}")
                    self.parent.ai_response_display.append("---")
                else:
                    response_display.append(f"[INFO] {provider} ({model}) にプロンプトを送信中...")
                    response_display.append(f"プロンプト: {prompt}")
                    response_display.append("---")
            except:
                pass
            
            # プログレス更新
            self.parent.update_progress(20, 100, f"{provider} への接続中...")
            
            # API呼び出し
            self.parent.update_progress(40, 100, f"{model} での処理実行中...")
            
            # プロバイダー名を小文字に変換（AIManagerとの互換性のため）
            provider_normalized = provider.lower()
            
            result = self.parent.ai_manager.send_prompt(prompt, provider_normalized, model)
            
            # プログレス更新
            self.parent.update_progress(80, 100, "レスポンス処理中...")
            
            if result["success"]:
                # ログ情報のみをログ表示欄に表示
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(f"[SUCCESS] 応答を受信しました")
                        # モデル名と応答時間を表示
                        if "model" in result:
                            self.ai_response_display.append(f"使用モデル: {result['model']}")
                        if "response_time" in result:
                            self.ai_response_display.append(f"応答時間: {result['response_time']:.2f}秒")
                        if "usage" in result and result["usage"]:
                            self.ai_response_display.append(f"使用量: {result['usage']}")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append(f"[SUCCESS] 応答を受信しました")
                        # モデル名と応答時間を表示
                        if "model" in result:
                            self.parent.ai_response_display.append(f"使用モデル: {result['model']}")
                        if "response_time" in result:
                            self.parent.ai_response_display.append(f"応答時間: {result['response_time']:.2f}秒")
                        if "usage" in result and result["usage"]:
                            self.parent.ai_response_display.append(f"使用量: {result['usage']}")
                    else:
                        response_display.append(f"[SUCCESS] 応答を受信しました")
                        # モデル名と応答時間を表示
                        if "model" in result:
                            response_display.append(f"使用モデル: {result['model']}")
                        if "response_time" in result:
                            response_display.append(f"応答時間: {result['response_time']:.2f}秒")
                        if "usage" in result and result["usage"]:
                            response_display.append(f"使用量: {result['usage']}")
                except:
                    pass
                
                # 応答のみを結果表示欄に表示（HTMLエスケープなし）
                response_text = result["response"]
                result_display = self._get_safe_result_display()
                result_display.clear()
                if hasattr(result_display, 'setPlainText'):
                    result_display.setPlainText(response_text)
                else:
                    result_display.append(response_text)
                
                # 応答情報をポップアップ表示用に保存
                self.parent.last_response_info = {
                    "response": response_text,
                    "model": result.get("model", "Unknown"),
                    "response_time": result.get("response_time", 0),
                    "usage": result.get("usage", {}),
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "success": True
                }
                
                # メッセージも更新
                if hasattr(self.parent.parent, 'display_manager'):
                    self.parent.parent.display_manager.set_message(f"AIプロンプト送信完了: {provider}")
                
            else:
                error_msg = result.get("error", "不明なエラー")
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(f"[ERROR] {error_msg}")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append(f"[ERROR] {error_msg}")
                    else:
                        response_display.append(f"[ERROR] {error_msg}")
                except:
                    pass
                
                # エラー情報もポップアップ表示用に保存
                self.parent.last_response_info = {
                    "response": f"エラーが発生しました: {error_msg}",
                    "model": result.get("model", "Unknown"),
                    "response_time": result.get("response_time", 0),
                    "usage": {},
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "success": False,
                    "error": error_msg
                }
                
                if hasattr(self.parent.parent, 'display_manager'):
                    self.parent.parent.display_manager.set_message(f"AIプロンプト送信失敗: {error_msg}")
            
            # プログレス完了
            self.parent.update_progress(100, 100, "プロンプト送信完了")
            self.parent.hide_progress()
            
        except Exception as e:
            try:
                response_display = self._get_safe_response_display()
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append(f"[ERROR] プロンプト送信中にエラーが発生: {e}")
                elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                    self.parent.ai_response_display.append(f"[ERROR] プロンプト送信中にエラーが発生: {e}")
                else:
                    response_display.append(f"[ERROR] プロンプト送信中にエラーが発生: {e}")
            except:
                pass
            logger.debug("send_ai_prompt Exception: %s", e)
            import traceback
            traceback.print_exc()
            
            # エラー情報をポップアップ表示用に保存
            import datetime
            self.parent.last_response_info = {
                "response": f"システムエラーが発生しました: {e}",
                "model": "Unknown",
                "response_time": 0,
                "usage": {},
                "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "success": False,
                "error": str(e)
            }
            
            if hasattr(self.parent.parent, 'display_manager'):
                self.parent.parent.display_manager.set_message(f"プロンプト送信中にエラー: {e}")
            
            # プログレスを隠す
            self.parent.hide_progress()

    def _build_prompt_by_type(self, prompt_file, prompt_template, experiment_data, static_data, prepared_data, response_display):
        """
        Step 2.5.1.2: プロンプト構築層の分離
        プロンプトファイルの種類に応じて適切な構築方法を選択し、ARIMデータ統合を実行
        """
        try:
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(f"[DEBUG] プロンプト構築開始: {prompt_file}")
            elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                self.parent.ai_response_display.append(f"[DEBUG] プロンプト構築開始: {prompt_file}")
            else:
                response_display.append(f"[DEBUG] プロンプト構築開始: {prompt_file}")
        except:
            pass
        
        if prompt_file in ["prompt_data_summary_ja.txt", "prompt_data_summary_v2_ja.txt", "prompt_data_analysis_ja.txt", "prompt_data_analysis_v2_ja.txt"]:
            # データ要約・データ分析用プロンプトの場合、special_analysisを使用
            try:
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append(f"[DEBUG] データ要約・データ分析用プロンプト構築開始（prepared_data統合版）")
                elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                    self.parent.ai_response_display.append(f"[DEBUG] データ要約・データ分析用プロンプト構築開始（prepared_data統合版）")
                else:
                    response_display.append(f"[DEBUG] データ要約・データ分析用プロンプト構築開始（prepared_data統合版）")
            except:
                pass
                
            mi_data = static_data.get("MI.json", {})
            try:
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append(f"[DEBUG] MI.jsonデータ有無: {mi_data is not None}")
                    if mi_data:
                        self.ai_response_display.append(f"[DEBUG] MI.jsonキー数: {len(mi_data)}")
                elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                    self.parent.ai_response_display.append(f"[DEBUG] MI.jsonデータ有無: {mi_data is not None}")
                    if mi_data:
                        self.parent.ai_response_display.append(f"[DEBUG] MI.jsonキー数: {len(mi_data)}")
                else:
                    response_display.append(f"[DEBUG] MI.jsonデータ有無: {mi_data is not None}")
                    if mi_data:
                        response_display.append(f"[DEBUG] MI.jsonキー数: {len(mi_data)}")
            except:
                pass
                
            # ARIM拡張統合処理（実験データとprepared_dataを取得）
            experiment_data, arim_prepared_data = self._integrate_arim_extension(experiment_data, response_display)
            
            # prepared_dataにARIM拡張情報を統合
            if arim_prepared_data:
                if prepared_data is None:
                    prepared_data = {}
                prepared_data.update(arim_prepared_data)
            
            # プロンプトを構築（ARIM拡張データ結合後、prepared_data統合版）
            formatted_prompt = self._build_analysis_prompt(prompt_template, experiment_data, mi_data, prepared_data)
            try:
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append(f"[DEBUG] 構築完了 formatted_prompt長: {len(formatted_prompt) if formatted_prompt else 0}")
                elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                    self.parent.ai_response_display.append(f"[DEBUG] 構築完了 formatted_prompt長: {len(formatted_prompt) if formatted_prompt else 0}")
                else:
                    response_display.append(f"[DEBUG] 構築完了 formatted_prompt長: {len(formatted_prompt) if formatted_prompt else 0}")
            except:
                pass
        else:
            try:
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append(f"[DEBUG] その他分析({prompt_file})用プロンプト構築開始（JSON構造化形式に統一）")
                elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                    self.parent.ai_response_display.append(f"[DEBUG] その他分析({prompt_file})用プロンプト構築開始（JSON構造化形式に統一）")
                else:
                    response_display.append(f"[DEBUG] その他分析({prompt_file})用プロンプト構築開始（JSON構造化形式に統一）")
            except:
                pass
            
            # ARIM拡張統合処理（実験データとprepared_dataを取得）
            experiment_data, arim_prepared_data = self._integrate_arim_extension(experiment_data, response_display)
            
            # prepared_dataにARIM拡張情報を統合
            if arim_prepared_data:
                if prepared_data is None:
                    prepared_data = {}
                prepared_data.update(arim_prepared_data)
            
            # その他の分析もJSON構造化形式に統一（_build_analysis_prompt使用）
            mi_data = static_data.get("MI.json", {})
            formatted_prompt = self._build_analysis_prompt(prompt_template, experiment_data, mi_data, prepared_data)
        
        return formatted_prompt

    def _execute_ai_analysis(self, formatted_prompt, provider, model, experiment_data, is_batch_mode, response_display):
        """
        Step 2.5.1.4: AI実行・結果処理層の分離
        AI分析の実行と結果処理を統合
        """
        import datetime
        
        if provider == "設定なし":
            try:
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append("[ERROR] AIプロバイダーが設定されていません")
                elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                    self.parent.ai_response_display.append("[ERROR] AIプロバイダーが設定されていません")
                else:
                    response_display.append("[ERROR] AIプロバイダーが設定されていません")
            except:
                pass
            return
        
        # AIManagerを使用してプロンプトを送信
        try:
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append("[DEBUG] AIプロンプト送信開始...")
            elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                self.parent.ai_response_display.append("[DEBUG] AIプロンプト送信開始...")
            else:
                response_display.append("[DEBUG] AIプロンプト送信開始...")
        except:
            pass
        
        # プロバイダー名を小文字に変換（AIManagerとの互換性のため）
        provider_normalized = provider.lower()
        
        result = self.parent.ai_manager.send_prompt(formatted_prompt, provider_normalized, model)
        
        # リクエスト内容を保存（ポップアップ表示用）
        self.parent.last_request_content = formatted_prompt
        self.parent.last_request_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # リクエスト内容保存の詳細ログ
        try:
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(f"[DEBUG] リクエスト内容保存完了: 長さ={len(formatted_prompt)}")
                if "【実験情報データ】" in formatted_prompt:
                    self.ai_response_display.append("[DEBUG] リクエスト内容に実験情報セクション含有確認")
                else:
                    self.ai_response_display.append("[DEBUG] ⚠️ リクエスト内容に実験情報セクションなし")
                if "【マテリアルインデックス】" in formatted_prompt:
                    self.ai_response_display.append("[DEBUG] リクエスト内容にMIセクション含有確認")
                else:
                    self.ai_response_display.append("[DEBUG] ⚠️ リクエスト内容にMIセクションなし")
            elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                self.parent.ai_response_display.append(f"[DEBUG] リクエスト内容保存完了: 長さ={len(formatted_prompt)}")
                if "【実験情報データ】" in formatted_prompt:
                    self.parent.ai_response_display.append("[DEBUG] リクエスト内容に実験情報セクション含有確認")
                else:
                    self.parent.ai_response_display.append("[DEBUG] ⚠️ リクエスト内容に実験情報セクションなし")
                if "【マテリアルインデックス】" in formatted_prompt:
                    self.parent.ai_response_display.append("[DEBUG] リクエスト内容にMIセクション含有確認")
                else:
                    self.parent.ai_response_display.append("[DEBUG] ⚠️ リクエスト内容にMIセクションなし")
            else:
                response_display.append(f"[DEBUG] リクエスト内容保存完了: 長さ={len(formatted_prompt)}")
                if "【実験情報データ】" in formatted_prompt:
                    response_display.append("[DEBUG] リクエスト内容に実験情報セクション含有確認")
                else:
                    response_display.append("[DEBUG] ⚠️ リクエスト内容に実験情報セクションなし")
                if "【マテリアルインデックス】" in formatted_prompt:
                    response_display.append("[DEBUG] リクエスト内容にMIセクション含有確認")
                else:
                    response_display.append("[DEBUG] ⚠️ リクエスト内容にMIセクションなし")
        except:
            pass
        
        # 結果処理
        if result["success"]:
            response_content = result.get("response", "")
            response_display = self._get_safe_response_display()
            response_display.append(f"[SUCCESS] AI分析完了")
            
            # モデル名と応答時間を表示
            if "model" in result:
                response_display.append(f"使用モデル: {result['model']}")
            if "response_time" in result:
                response_display.append(f"応答時間: {result['response_time']:.2f}秒")
            
            if "usage" in result and result["usage"]:
                usage = result["usage"]
                response_display.append(f"使用量: {usage}")
            
            # レスポンス情報を保存（ポップアップ表示用）
            self.parent.last_response_info = {
                'model': result.get('model', '不明'),
                'response_time': result.get('response_time', 0),
                'usage': result.get('usage', {}),
                'success': True,
                'provider': provider,
                'analysis_type': 'AI問い合わせ'
            }
            
            # 結果を結果表示欄に表示（一括処理では追記、単体処理ではクリア）
            if response_content:
                result_display = self._get_safe_result_display()
                if not is_batch_mode:
                    result_display.clear()
                
                # 一括処理の場合は実験ごとの区切りを追加
                if is_batch_mode:
                    experiment_info = ""
                    if experiment_data:
                        experiment_name = experiment_data.get('タイトル', experiment_data.get('概要', '不明'))
                        arim_id = experiment_data.get('ARIM ID', experiment_data.get('ARIMID', '不明'))
                        experiment_info = f" - {experiment_name} (ID: {arim_id})"
                    
                    result_display = self._get_safe_result_display()
                    result_display.append(f"\n{'='*60}")
                    result_display.append(f"実験データ {experiment_info}")
                    result_display.append(f"{'='*60}")
                
                result_display = self._get_safe_result_display()
                result_display.append(response_content)
            else:
                result_display = self._get_safe_result_display()
                result_display.append("AIからの応答が空でした。")
        else:
            response_display = self._get_safe_response_display()
            response_display.append(f"[ERROR] AI分析に失敗: {result['error']}")
            # エラー時でもモデル名と応答時間を表示（あれば）
            if "model" in result:
                response_display.append(f"使用モデル: {result['model']}")
            if "response_time" in result:
                response_display.append(f"応答時間: {result['response_time']:.2f}秒")
            
            # エラー時のレスポンス情報を保存
            self.parent.last_response_info = {
                'model': result.get('model', '不明'),
                'response_time': result.get('response_time', 0),
                'usage': result.get('usage', {}),
                'success': False,
                'provider': provider,
                'analysis_type': 'AI問い合わせ',
                'error': result['error']
            }

    def _get_ai_config(self, response_display):
        """
        Step 2.5.1.3: AI設定管理層の分離
        AI プロバイダーとモデルの設定取得を統合
        """
        # プロバイダーとモデルを安全に取得
        provider = "未設定"
        model = "未設定"
        
        # AI設定コンポーネントの安全な取得
        ai_provider_combo = None
        ai_model_combo = None
        
        # UIController側のAI設定コンポーネントを取得
        if hasattr(self.parent, 'ai_provider_combo') and self.parent.ai_provider_combo:
            ai_provider_combo = self.parent.ai_provider_combo
            current_index = ai_provider_combo.currentIndex()
            if current_index >= 0:
                # データ（プロバイダーID）を優先し、なければテキストを使用
                provider_id = ai_provider_combo.itemData(current_index)
                if provider_id:
                    provider = provider_id
                else:
                    provider = ai_provider_combo.currentText()
            else:
                provider = ai_provider_combo.currentText()
        
        if hasattr(self.parent, 'ai_model_combo') and self.parent.ai_model_combo:
            ai_model_combo = self.parent.ai_model_combo
            model = ai_model_combo.currentText()
        
        try:
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(f"[DEBUG] AIプロバイダー: {provider}")
                self.ai_response_display.append(f"[DEBUG] AIモデル: {model}")
            elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                self.parent.ai_response_display.append(f"[DEBUG] AIプロバイダー: {provider}")
                self.parent.ai_response_display.append(f"[DEBUG] AIモデル: {model}")
            elif hasattr(self.parent, 'force_log'):
                self.parent.force_log(f"AIプロバイダー: {provider}, AIモデル: {model}", "DEBUG")
            else:
                logger.debug("AIプロバイダー: %s, AIモデル: %s", provider, model)
        except:
            pass
        
        return provider, model

    def _integrate_arim_extension(self, experiment_data, response_display):
        """
        ARIM拡張データの統合処理（プロンプト構築時の共通処理として分離）
        プロンプト用のprepared_dataも含めて返すように変更
        """
        # ARIM拡張情報のチェックボックス状態を確認
        use_arim_extension = False
        try:
            if (hasattr(self.parent, 'arim_extension_checkbox') and 
                self.parent.arim_extension_checkbox and
                hasattr(self.parent.arim_extension_checkbox, 'isChecked')):
                use_arim_extension = self.parent.arim_extension_checkbox.isChecked()
        except Exception as e:
            self._force_log(f"ARIM拡張情報チェックボックスアクセスエラー: {e}", "error")
            use_arim_extension = False
            
        try:
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(f"[DEBUG] ARIM拡張情報使用: {use_arim_extension}")
            elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                self.parent.ai_response_display.append(f"[DEBUG] ARIM拡張情報使用: {use_arim_extension}")
            else:
                response_display.append(f"[DEBUG] ARIM拡張情報使用: {use_arim_extension}")
        except:
            pass

        # prepared_dataを初期化
        prepared_data = {}
        
        # ARIM拡張情報を使用する場合、実験データにARIM拡張データを結合
        if use_arim_extension and experiment_data:
            try:
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append("[DEBUG] ARIM拡張データ結合処理開始...")
                elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                    self.parent.ai_response_display.append("[DEBUG] ARIM拡張データ結合処理開始...")
                else:
                    response_display.append("[DEBUG] ARIM拡張データ結合処理開始...")
            except:
                pass
            
            arim_extension_data = self._load_arim_extension_data()
            if arim_extension_data:
                original_keys = set(experiment_data.keys())
                experiment_data = self._merge_with_arim_data(experiment_data, arim_extension_data)
                new_keys = set(experiment_data.keys())
                added_keys = new_keys - original_keys
                
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(f"[DEBUG] ARIM拡張データ結合処理完了")
                        self.ai_response_display.append(f"[DEBUG] 追加されたキー: {list(added_keys)}")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append(f"[DEBUG] ARIM拡張データ結合処理完了")
                        self.parent.ai_response_display.append(f"[DEBUG] 追加されたキー: {list(added_keys)}")
                    else:
                        response_display.append(f"[DEBUG] ARIM拡張データ結合処理完了")
                        response_display.append(f"[DEBUG] 追加されたキー: {list(added_keys)}")
                except:
                    pass
                
                # ARIM拡張情報をprepared_dataに追加
                if added_keys:
                    arim_extension_info = []
                    for key in sorted(list(added_keys))[:20]:  # 最初の20項目まで
                        value = experiment_data.get(key)
                        if value is not None and str(value).strip() and str(value).strip().lower() not in ['nan', 'none', '']:
                            arim_extension_info.append(f"{key}: {value}")
                    
                    if arim_extension_info:
                        prepared_data['prepare_exp_info_ext'] = f"""=== ARIM拡張情報 ===
課題番号: {experiment_data.get('課題番号', 'N/A')}
ARIMNO: {experiment_data.get('ARIMNO', 'N/A')}

{chr(10).join(arim_extension_info)}
=== ARIM拡張情報終了 ==="""
                        
                        try:
                            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                                self.ai_response_display.append(f"[DEBUG] prepare_exp_info_extセクション作成: {len(prepared_data['prepare_exp_info_ext'])} 文字")
                            elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                                self.parent.ai_response_display.append(f"[DEBUG] prepare_exp_info_extセクション作成: {len(prepared_data['prepare_exp_info_ext'])} 文字")
                        except:
                            pass
            else:
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(f"[DEBUG] ARIM拡張データが読み込めませんでした")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append(f"[DEBUG] ARIM拡張データが読み込めませんでした")
                    else:
                        response_display.append(f"[DEBUG] ARIM拡張データが読み込めませんでした")
                except:
                    pass
        else:
            try:
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append(f"[DEBUG] ARIM拡張情報を使用しません")
                elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                    self.parent.ai_response_display.append(f"[DEBUG] ARIM拡張情報を使用しません")
                else:
                    response_display.append(f"[DEBUG] ARIM拡張情報を使用しません")
            except:
                pass
        
        # 実験データとprepared_dataの両方を返す
        return experiment_data, prepared_data

    def _validate_analysis_data(self, prompt_file, prepared_data, static_data, experiment_data):
        """
        AI分析データの検証とログ出力
        
        Args:
            prompt_file: プロンプトファイル名
            prepared_data: 準備されたデータ
            static_data: 静的データ
            experiment_data: 実験データ
            
        Returns:
            bool: 検証成功の場合True、失敗の場合False
        """
        import os
        from config.common import INPUT_DIR
        
        # 安全なレスポンス表示オブジェクトを取得
        response_display = self._get_safe_response_display()
        
        response_display.append("[DEBUG] ===== AI分析データ統合・プロンプト構築開始 =====")
        response_display.append(f"[DEBUG] prompt_file: {prompt_file}")
        response_display.append(f"[DEBUG] prepared_dataキー: {list(prepared_data.keys()) if prepared_data else 'None'}")
        response_display.append(f"[DEBUG] static_dataキー: {list(static_data.keys()) if static_data else 'None'}")
        response_display.append(f"[DEBUG] experiment_data有無: {experiment_data is not None}")
        if experiment_data:
            response_display.append(f"[DEBUG] experiment_dataキー数: {len(experiment_data)}")
            exp_keys_sample = list(experiment_data.keys())[:10]
            response_display.append(f"[DEBUG] experiment_dataキー例: {exp_keys_sample}")
        
        # prepared_dataの詳細確認
        if prepared_data:
            for key, value in prepared_data.items():
                value_preview = str(value)[:200] if value else "None"
                response_display.append(f"[DEBUG] prepared_data[{key}]: {value_preview}...")
        
        # static_dataの詳細確認
        if static_data:
            for key, value in static_data.items():
                if isinstance(value, dict):
                    response_display.append(f"[DEBUG] static_data[{key}]: dict with {len(value)} keys")
                else:
                    value_preview = str(value)[:200] if value else "None"
                    response_display.append(f"[DEBUG] static_data[{key}]: {value_preview}...")
        
        # プロンプトファイルの検証
        if not prompt_file:
            response_display.append("[ERROR] プロンプトファイルが指定されていません")
            return False
        
        prompt_path = os.path.join(INPUT_DIR, "ai", "prompts", prompt_file)
        if not os.path.exists(prompt_path):
            response_display.append(f"[ERROR] プロンプトファイルが見つかりません: {prompt_path}")
            return False
            
        return True
    
    def _execute_ai_analysis_with_data(self, prompt_file, prepared_data, static_data, experiment_data, is_batch_mode=False):
        """データを使用してAI分析を実行（元の実装を復元）"""
        try:
            import datetime
            from config.common import INPUT_DIR
            import os
            
            # TODO: 段階的分割 - データ検証を専用メソッドに委譲
            if not self._validate_analysis_data(prompt_file, prepared_data, static_data, experiment_data):
                return
            
            # 安全なレスポンス表示オブジェクトを取得
            response_display = self._get_safe_response_display()
            
            # TODO: Phase 2 Step 2.6.1 - プロンプト読み込み層を専用メソッドに委譲
            prompt_template = self._load_prompt_template(prompt_file, response_display)
            if prompt_template is None:
                return
            
            # プロンプトテンプレートにデータを挿入（元の実装通り）
            if prompt_file == "material_index.txt":
                # TODO: Phase 2 Step 2.6.2 - MI分析プロンプト構築を専用メソッドに委譲
                formatted_prompt = self._build_mi_analysis_prompt(prompt_template, experiment_data, static_data, prepared_data, response_display)
            elif prompt_file == "dataset_explanation.txt":
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append("[DEBUG] データセット説明用プロンプト構築開始（JSON構造化形式）")
                        self.ai_response_display.append(f"[DEBUG] 実験データ有無: {experiment_data is not None}")
                        if experiment_data:
                            self.ai_response_display.append(f"[DEBUG] 実験データキー数: {len(experiment_data)}")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append("[DEBUG] データセット説明用プロンプト構築開始（JSON構造化形式）")
                        self.parent.ai_response_display.append(f"[DEBUG] 実験データ有無: {experiment_data is not None}")
                        if experiment_data:
                            self.parent.ai_response_display.append(f"[DEBUG] 実験データキー数: {len(experiment_data)}")
                    else:
                        response_display.append("[DEBUG] データセット説明用プロンプト構築開始（JSON構造化形式）")
                        response_display.append(f"[DEBUG] 実験データ有無: {experiment_data is not None}")
                        if experiment_data:
                            response_display.append(f"[DEBUG] 実験データキー数: {len(experiment_data)}")
                except:
                    pass
                    
                mi_data = static_data.get("MI.json", {})
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(f"[DEBUG] MI.jsonデータ有無: {mi_data is not None}")
                        if mi_data:
                            self.ai_response_display.append(f"[DEBUG] MI.jsonキー数: {len(mi_data)}")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append(f"[DEBUG] MI.jsonデータ有無: {mi_data is not None}")
                        if mi_data:
                            self.parent.ai_response_display.append(f"[DEBUG] MI.jsonキー数: {len(mi_data)}")
                    else:
                        response_display.append(f"[DEBUG] MI.jsonデータ有無: {mi_data is not None}")
                        if mi_data:
                            response_display.append(f"[DEBUG] MI.jsonキー数: {len(mi_data)}")
                except:
                    pass
                
                # プロンプトを構築（ARIM拡張データ結合後、prepared_data統合版）
                formatted_prompt = self._build_dataset_explanation_prompt(prompt_template, experiment_data, mi_data, prepared_data, response_display)
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(f"[DEBUG] 構築完了 formatted_prompt長: {len(formatted_prompt) if formatted_prompt else 0}")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append(f"[DEBUG] 構築完了 formatted_prompt長: {len(formatted_prompt) if formatted_prompt else 0}")
                    else:
                        response_display.append(f"[DEBUG] 構築完了 formatted_prompt長: {len(formatted_prompt) if formatted_prompt else 0}")
                except:
                    pass
            else:
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(f"[DEBUG] その他分析({prompt_file})用プロンプト構築開始（JSON構造化形式に統一）")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append(f"[DEBUG] その他分析({prompt_file})用プロンプト構築開始（JSON構造化形式に統一）")
                    else:
                        response_display.append(f"[DEBUG] その他分析({prompt_file})用プロンプト構築開始（JSON構造化形式に統一）")
                except:
                    pass
                
                # その他の分析もJSON構造化形式に統一（_build_analysis_prompt使用）
                mi_data = static_data.get("MI.json", {})
                formatted_prompt = self._build_dataset_explanation_prompt(prompt_template, experiment_data, mi_data, prepared_data, response_display)
            
            # 作成されたプロンプトの詳細ログ
            try:
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append("[DEBUG] ===== 作成されたプロンプト詳細 =====")
                    self.ai_response_display.append(f"[DEBUG] 最終プロンプト長: {len(formatted_prompt) if formatted_prompt else 0} 文字")
                elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                    self.parent.ai_response_display.append("[DEBUG] ===== 作成されたプロンプト詳細 =====")
                    self.parent.ai_response_display.append(f"[DEBUG] 最終プロンプト長: {len(formatted_prompt) if formatted_prompt else 0} 文字")
                else:
                    response_display.append("[DEBUG] ===== 作成されたプロンプト詳細 =====")
                    response_display.append(f"[DEBUG] 最終プロンプト長: {len(formatted_prompt) if formatted_prompt else 0} 文字")
            except:
                pass
            
            if formatted_prompt:
                # プロンプトの構造確認
                sections_found = []
                if "【課題・実験情報】" in formatted_prompt:
                    sections_found.append("課題・実験情報")
                if "【拡張実験情報（ARIM拡張含む）】" in formatted_prompt:
                    sections_found.append("拡張実験情報（ARIM拡張含む）")
                if "【実験情報データ】" in formatted_prompt:
                    sections_found.append("実験情報データ")
                if "【マテリアルインデックス】" in formatted_prompt:
                    sections_found.append("マテリアルインデックス")
                
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append(f"[DEBUG] 検出されたセクション: {sections_found}")
                        self.ai_response_display.append(f"[DEBUG] プロンプト開始500文字: {formatted_prompt[:500]}...")
                        # ARIM拡張情報が含まれているかチェック
                        arim_mentions = formatted_prompt.upper().count("ARIM")
                        self.ai_response_display.append(f"[DEBUG] プロンプト内ARIM言及回数: {arim_mentions}")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append(f"[DEBUG] 検出されたセクション: {sections_found}")
                        self.parent.ai_response_display.append(f"[DEBUG] プロンプト開始500文字: {formatted_prompt[:500]}...")
                        # ARIM拡張情報が含まれているかチェック
                        arim_mentions = formatted_prompt.upper().count("ARIM")
                        self.parent.ai_response_display.append(f"[DEBUG] プロンプト内ARIM言及回数: {arim_mentions}")
                    else:
                        response_display.append(f"[DEBUG] 検出されたセクション: {sections_found}")
                        response_display.append(f"[DEBUG] プロンプト開始500文字: {formatted_prompt[:500]}...")
                        # ARIM拡張情報が含まれているかチェック
                        arim_mentions = formatted_prompt.upper().count("ARIM")
                        response_display.append(f"[DEBUG] プロンプト内ARIM言及回数: {arim_mentions}")
                except:
                    pass
            else:
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append("[ERROR] 作成されたプロンプトがNullです")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append("[ERROR] 作成されたプロンプトがNullです")
                    else:
                        response_display.append("[ERROR] 作成されたプロンプトがNullです")
                except:
                    pass
                return
            
            try:
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append("[DEBUG] ===== プロンプト詳細確認完了 =====")
                elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                    self.parent.ai_response_display.append("[DEBUG] ===== プロンプト詳細確認完了 =====")
                else:
                    response_display.append("[DEBUG] ===== プロンプト詳細確認完了 =====")
            except:
                pass
            
            # AI分析実行・レスポンス処理
            provider, model = self._get_ai_config(response_display)
            if provider == "設定なし":
                try:
                    if hasattr(self, 'ai_response_display') and self.ai_response_display:
                        self.ai_response_display.append("[ERROR] AIプロバイダーが設定されていません")
                    elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                        self.parent.ai_response_display.append("[ERROR] AIプロバイダーが設定されていません")
                    else:
                        response_display.append("[ERROR] AIプロバイダーが設定されていません")
                except:
                    pass
                return
            
            self._execute_ai_request_and_process_response(formatted_prompt, provider, model, is_batch_mode, response_display, experiment_data)
                
        except Exception as e:
            response_display = self._get_safe_response_display()
            response_display.append(f"[ERROR] AI分析実行エラー: {e}")
            import traceback
            traceback.print_exc()

    def _load_prompt_template(self, prompt_file, response_display):
        """
        Phase 2 Step 2.6.1: プロンプトファイル読み込み層の分離
        プロンプトファイルの存在確認・読み込み・デバッグ出力を担当
        """
        from config.common import INPUT_DIR
        import os
        
        # プロンプトファイルの読み込み
        prompt_path = os.path.join(INPUT_DIR, "ai", "prompts", prompt_file)
        if not os.path.exists(prompt_path):
            # フォールバック: aiディレクトリ直下も確認
            prompt_path = os.path.join(INPUT_DIR, "ai", prompt_file)
            if not os.path.exists(prompt_path):
                response_display.append(f"[ERROR] プロンプトファイルが見つかりません: {prompt_file}")
                return None
        
        response_display.append(f"[DEBUG] プロンプトファイルパス: {prompt_path}")
        
        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
                
            response_display.append(f"[DEBUG] プロンプトテンプレート長: {len(prompt_template)} 文字")
            response_display.append(f"[DEBUG] プロンプトテンプレート開始部分: {prompt_template[:300]}...")
            
            return prompt_template
        except Exception as e:
            response_display.append(f"[ERROR] プロンプトファイル読み込みエラー: {e}")
            return None

    def _build_mi_analysis_prompt(self, prompt_template, experiment_data, static_data, prepared_data, response_display):
        """
        Phase 2 Step 2.6.2: MI分析プロンプト構築層の分離
        Material Index分析用のプロンプト構築とARIM拡張統合処理
        """
        response_display.append("[DEBUG] MI分析用プロンプト構築開始（JSON構造化形式）")
        
        # ARIM拡張統合処理（実験データとprepared_dataを取得）
        experiment_data, arim_prepared_data = self._integrate_arim_extension(experiment_data, response_display)
        
        # prepared_dataにARIM拡張情報を統合
        if arim_prepared_data:
            if prepared_data is None:
                prepared_data = {}
            prepared_data.update(arim_prepared_data)
        
        # MI分析用は従来の形式を使用（prepared_data統合版）
        formatted_prompt = self._build_analysis_prompt(prompt_template, experiment_data, static_data.get("MI.json", {}), prepared_data)
        
        return formatted_prompt
    
    def _build_dataset_explanation_prompt(self, prompt_template, experiment_data, mi_data, prepared_data, response_display):
        """
        Phase 2 Step 2.6.3: データセット説明プロンプト構築層の分離
        データセット説明分析用のプロンプト構築とARIM拡張統合処理
        """
        response_display.append("[DEBUG] データセット説明用プロンプト構築開始（JSON構造化形式に統一）")
        
        # ARIM拡張統合処理（実験データとprepared_dataを取得）
        experiment_data, arim_prepared_data = self._integrate_arim_extension(experiment_data, response_display)
        
        # prepared_dataにARIM拡張情報を統合
        if arim_prepared_data:
            if prepared_data is None:
                prepared_data = {}
            prepared_data.update(arim_prepared_data)
        
        # データセット説明用分析もJSON構造化形式に統一（_build_analysis_prompt使用）
        formatted_prompt = self._build_analysis_prompt(prompt_template, experiment_data, mi_data, prepared_data)
        
        return formatted_prompt
    
    def _execute_ai_request_and_process_response(self, formatted_prompt, provider, model, is_batch_mode, response_display, experiment_data):
        """
        Phase 2 Step 2.6.4: AI実行・レスポンス処理層の分離
        AI分析の実行とレスポンスの処理・表示を担当
        """
        # TODO: Step 2.6.4 - AI実行・レスポンス処理実装
        if hasattr(self.parent, 'ai_manager') and self.parent.ai_manager:
            # AIManagerを使用してプロンプトを送信
            try:
                if hasattr(self, 'ai_response_display') and self.ai_response_display:
                    self.ai_response_display.append("[DEBUG] AIプロンプト送信開始...")
                elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                    self.parent.ai_response_display.append("[DEBUG] AIプロンプト送信開始...")
                else:
                    response_display.append("[DEBUG] AIプロンプト送信開始...")
            except:
                pass
            
            # プロバイダー名を小文字に変換（AIManagerとの互換性のため）
            provider_normalized = provider.lower()
            
            result = self.parent.ai_manager.send_prompt(formatted_prompt, provider_normalized, model)
            
            # リクエスト内容を保存（ポップアップ表示用）
            self.parent.last_request_content = formatted_prompt
            self.parent.last_request_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # リクエスト内容保存の詳細ログ
            self._log_request_details(formatted_prompt, response_display)
            
            return self._process_ai_response(result, provider, is_batch_mode, response_display, experiment_data)
        else:
            response_display.append("[ERROR] AI分析エンジンが初期化されていません")
            return False
    
    def _log_request_details(self, formatted_prompt, response_display):
        """リクエスト詳細ログ出力"""
        try:
            if hasattr(self, 'ai_response_display') and self.ai_response_display:
                self.ai_response_display.append(f"[DEBUG] リクエスト内容保存完了: 長さ={len(formatted_prompt)}")
                if "【実験情報データ】" in formatted_prompt:
                    self.ai_response_display.append("[DEBUG] リクエスト内容に実験情報セクション含有確認")
                else:
                    self.ai_response_display.append("[DEBUG] ⚠️ リクエスト内容に実験情報セクションなし")
                if "【マテリアルインデックス】" in formatted_prompt:
                    self.ai_response_display.append("[DEBUG] リクエスト内容にMIセクション含有確認")
                else:
                    self.ai_response_display.append("[DEBUG] ⚠️ リクエスト内容にMIセクションなし")
            elif hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                self.parent.ai_response_display.append(f"[DEBUG] リクエスト内容保存完了: 長さ={len(formatted_prompt)}")
                if "【実験情報データ】" in formatted_prompt:
                    self.parent.ai_response_display.append("[DEBUG] リクエスト内容に実験情報セクション含有確認")
                else:
                    self.parent.ai_response_display.append("[DEBUG] ⚠️ リクエスト内容に実験情報セクションなし")
                if "【マテリアルインデックス】" in formatted_prompt:
                    self.parent.ai_response_display.append("[DEBUG] リクエスト内容にMIセクション含有確認")
                else:
                    self.parent.ai_response_display.append("[DEBUG] ⚠️ リクエスト内容にMIセクションなし")
            else:
                response_display.append(f"[DEBUG] リクエスト内容保存完了: 長さ={len(formatted_prompt)}")
                if "【実験情報データ】" in formatted_prompt:
                    response_display.append("[DEBUG] リクエスト内容に実験情報セクション含有確認")
                else:
                    response_display.append("[DEBUG] ⚠️ リクエスト内容に実験情報セクションなし")
                if "【マテリアルインデックス】" in formatted_prompt:
                    response_display.append("[DEBUG] リクエスト内容にMIセクション含有確認")
                else:
                    response_display.append("[DEBUG] ⚠️ リクエスト内容にMIセクションなし")
        except:
            pass
    
    def _process_ai_response(self, result, provider, is_batch_mode, response_display, experiment_data):
        """AI分析結果の処理とUI更新"""
        if result.get('success', False):
            response_content = result.get("response", "")
            response_display = self._get_safe_response_display()
            response_display.append(f"[SUCCESS] AI分析完了")
            
            # モデル名と応答時間を表示
            if "model" in result:
                response_display.append(f"使用モデル: {result['model']}")
            if "response_time" in result:
                response_display.append(f"応答時間: {result['response_time']:.2f}秒")
            
            if "usage" in result and result["usage"]:
                usage = result["usage"]
                response_display.append(f"使用量: {usage}")
            
            # レスポンス情報を保存（ポップアップ表示用）
            self.parent.last_response_info = {
                'model': result.get('model', '不明'),
                'response_time': result.get('response_time', 0),
                'usage': result.get('usage', {}),
                'success': True,
                'provider': provider,
                'analysis_type': 'AI問い合わせ'
            }
            
            # 結果を結果表示欄に表示（一括処理では追記、単体処理ではクリア）
            if response_content:
                result_display = self._get_safe_result_display()
                if not is_batch_mode:
                    result_display.clear()
                
                # 一括処理の場合は実験ごとの区切りを追加
                if is_batch_mode:
                    experiment_info = ""
                    if experiment_data:
                        experiment_name = experiment_data.get('タイトル', experiment_data.get('概要', '不明'))
                        arim_id = experiment_data.get('ARIM ID', experiment_data.get('ARIMID', '不明'))
                        experiment_info = f" - {experiment_name} (ID: {arim_id})"
                    
                    result_display = self._get_safe_result_display()
                    result_display.append(f"\n{'='*60}")
                    result_display.append(f"実験データ {experiment_info}")
                    result_display.append(f"{'='*60}")
                
                result_display = self._get_safe_result_display()
                result_display.append(response_content)
            else:
                result_display = self._get_safe_result_display()
                result_display.append("AIからの応答が空でした。")
            return True
        else:
            response_display = self._get_safe_response_display()
            response_display.append(f"[ERROR] AI分析に失敗: {result['error']}")
            # エラー時でもモデル名と応答時間を表示（あれば）
            if "model" in result:
                response_display.append(f"使用モデル: {result['model']}")
            if "response_time" in result:
                response_display.append(f"応答時間: {result['response_time']:.2f}秒")
            
            # エラー時のレスポンス情報を保存
            self.parent.last_response_info = {
                'model': result.get('model', '不明'),
                'response_time': result.get('response_time', 0),
                'usage': result.get('usage', {}),
                'success': False,
                'error': result.get('error', '不明なエラー'),
                'provider': provider,
                'analysis_type': 'AI問い合わせ'
            }
            
            result_display = self._get_safe_result_display()
            if not is_batch_mode:
                result_display.clear()
            result_display.append("AI分析に失敗しました。")
            return False

    def _format_prompt_with_data(self, template, prepared_data, static_data, experiment_data):
        """プロンプトテンプレートにデータを挿入（元の実装を復元）"""
        try:
            formatted_prompt = template
            
            # 実験データ情報を挿入
            if experiment_data:
                for key, value in experiment_data.items():
                    placeholder = f"{{{key}}}"
                    if placeholder in formatted_prompt:
                        formatted_prompt = formatted_prompt.replace(placeholder, str(value))
            
            # 準備されたデータを挿入
            if prepared_data:
                for method, data in prepared_data.items():
                    placeholder = f"{{{method}}}"
                    if placeholder in formatted_prompt:
                        formatted_prompt = formatted_prompt.replace(placeholder, str(data))
            
            # 静的データを挿入
            if static_data:
                for file_name, data in static_data.items():
                    placeholder = f"{{{file_name}}}"
                    if placeholder in formatted_prompt:
                        formatted_prompt = formatted_prompt.replace(placeholder, str(data))
            
            return formatted_prompt
            
        except Exception as e:
            if hasattr(self.parent, 'ai_response_display') and self.parent.ai_response_display:
                self.parent.ai_response_display.append(f"[ERROR] プロンプトフォーマットエラー: {e}")
            return template

    def _build_analysis_prompt(self, template, experiment_data, material_index, prepared_data=None):
        """分析用プロンプトを構築（prepared_data統合対応）- AIPromptManagerに委譲"""
        if hasattr(self.parent_controller, 'ai_prompt_manager') and self.parent_controller.ai_prompt_manager:
            return self.parent_controller.ai_prompt_manager.build_analysis_prompt(
                template=template,
                experiment_data=experiment_data,
                material_index=material_index,
                prepared_data=prepared_data
            )
        return template or ""

    def _load_arim_extension_data(self):
        """ARIM拡張情報（converted.xlsx）を読み込む"""
        try:
            import pandas as pd
            from config.common import INPUT_DIR
            import os
            
            # ARIM拡張ファイルのパス
            arim_file_path = os.path.join(INPUT_DIR, 'ai', 'arim', 'converted.xlsx')
            
            if hasattr(self.parent, 'ai_response_display'):
                self.parent.ai_response_display.append(f"[DEBUG] ARIM拡張ファイルパス: {arim_file_path}")
            
            if not os.path.exists(arim_file_path):
                if hasattr(self.parent, 'ai_response_display'):
                    self.parent.ai_response_display.append(f"[DEBUG] ARIM拡張ファイルが見つかりません: {arim_file_path}")
                return None
            
            # Excelファイルを読み込み
            df = pd.read_excel(arim_file_path)
            
            if hasattr(self.parent, 'ai_response_display'):
                self.parent.ai_response_display.append(f"[DEBUG] ARIM拡張データ読み込み成功: {len(df)} 行, {len(df.columns)} 列")
                self.parent.ai_response_display.append(f"[DEBUG] ARIM拡張データ列名: {list(df.columns)}")
                
                # サンプルデータの表示
                if len(df) > 0:
                    sample_record = df.iloc[0].to_dict()
                    if '課題番号' in sample_record:
                        self.parent.ai_response_display.append(f"[DEBUG] サンプル課題番号: {repr(sample_record.get('課題番号'))}")
                    if 'ARIMNO' in sample_record:
                        self.parent.ai_response_display.append(f"[DEBUG] サンプルARIMNO: {repr(sample_record.get('ARIMNO'))}")
            
            # データフレームを辞書のリストに変換
            arim_data = df.to_dict('records')
            
            if hasattr(self.parent, 'ai_response_display'):
                self.parent.ai_response_display.append(f"[INFO] ARIM拡張情報を読み込みました: {len(arim_data)} 件")
            
            return arim_data
            
        except ImportError:
            if hasattr(self.parent, 'ai_response_display'):
                self.parent.ai_response_display.append("[WARNING] pandas がインストールされていません。ARIM拡張情報をスキップします")
            return None
        except Exception as e:
            if hasattr(self.parent, 'ai_response_display'):
                self.parent.ai_response_display.append(f"[WARNING] ARIM拡張情報の読み込みに失敗: {e}")
                import traceback
                self.parent.ai_response_display.append(f"[WARNING] ARIM拡張情報読み込みエラー詳細: {traceback.format_exc()}")
            return None

    def _merge_with_arim_data(self, experiment_data, arim_data):
        """
        実験データとARIM拡張データを結合（ARIM拡張情報ボタンと同じロジック）
        
        【重要】ARIM拡張情報の統合処理
        このメソッドは実験データにARIM拡張データを統合する中核的な処理を行います。
        プロンプト生成時にARIM拡張情報が正しく含まれるかはこの処理の成否にかかっています。
        
        【コメント追加理由】
        - 過去にARIM拡張情報がプロンプトから欠落する問題が発生
        - このメソッドでの統合処理失敗がプロンプト品質に直接影響
        - ARIMNO/課題番号による検索ロジックが複雑で変更時に注意が必要
        - デバッグ情報の出力により問題の早期発見が可能
        """
        try:
            if not arim_data or not experiment_data:
                if hasattr(self.parent, 'ai_response_display'):
                    self.parent.ai_response_display.append(f"[DEBUG] ARIM拡張データ結合: arim_data={bool(arim_data)}, experiment_data={bool(experiment_data)}")
                return experiment_data
            
            # 実験データから課題番号を取得
            task_id = experiment_data.get('課題番号', '').strip()
            arimno = experiment_data.get('ARIMNO', '').strip()  # 参考程度
            
            if hasattr(self.parent, 'ai_response_display'):
                self.parent.ai_response_display.append(f"[DEBUG] ARIM拡張データ結合開始: task_id='{task_id}', arimno='{arimno}'")
            
            # ポップアップ表示と同じ検索ロジックを使用
            matching_records = []
            
            # 1. ARIMNO列での完全一致検索（優先） - ポップアップと同じロジック
            if task_id:  # 課題番号をARIMNOとしても検索
                for record in arim_data:
                    record_arimno = record.get('ARIMNO', '')
                    if record_arimno and str(record_arimno) == str(task_id):
                        matching_records.append(record)
                        if hasattr(self.parent, 'ai_response_display'):
                            self.parent.ai_response_display.append(f"[DEBUG] ARIMNO完全一致: {record_arimno}")
                        break
            
            # 2. 課題番号列での完全一致検索 - シンプルに'課題番号'列のみチェック
            if not matching_records and task_id:
                for record in arim_data:
                    record_task = record.get('課題番号', '')
                    if record_task and str(record_task) == str(task_id):
                        matching_records.append(record)
                        if hasattr(self.parent, 'ai_response_display'):
                            self.parent.ai_response_display.append(f"[DEBUG] 課題番号完全一致: {record_task}")
                        break
            
            # 完全一致検索のみ - 末尾4桁検索は無効化
            if not matching_records and hasattr(self.parent, 'ai_response_display'):
                self.parent.ai_response_display.append(f"[DEBUG] 完全一致検索結果なし: {task_id}")
            
            # 結合処理
            if matching_records:
                # 最初のマッチした記録を使用
                matching_arim = matching_records[0]
                
                # 実験データのコピーを作成
                merged_data = experiment_data.copy()
                
                # ARIM拡張データの情報を追加
                added_count = 0
                for key, value in matching_arim.items():
                    if value is not None and str(value).strip() and str(value).strip().lower() not in ['nan', 'none', '']:
                        # 元のデータに存在しない、または空の場合のみ追加
                        if (key not in merged_data or 
                            str(merged_data.get(key, "")).strip() == "" or 
                            str(merged_data.get(key, "")).strip().lower() == "nan"):
                            merged_data[key] = value
                            added_count += 1
                
                if hasattr(self.parent, 'ai_response_display'):
                    self.parent.ai_response_display.append(f"[DEBUG] ARIM拡張データ結合成功: {added_count} 項目追加")
                    # 追加されたレコードの詳細
                    sample_arimno = matching_arim.get('ARIMNO', 'N/A')
                    sample_task = matching_arim.get('課題番号', matching_arim.get('課題番号（下4桁）', 'N/A'))
                    self.parent.ai_response_display.append(f"[DEBUG] 結合レコード詳細: ARIMNO={sample_arimno}, 課題番号={sample_task}")
                
                return merged_data
            else:
                if hasattr(self.parent, 'ai_response_display'):
                    self.parent.ai_response_display.append(f"[DEBUG] ARIM拡張データで一致する行が見つからず: task_id='{task_id}', arimno='{arimno}'")
                    self.parent.ai_response_display.append(f"[DEBUG] 総検索対象レコード数: {len(arim_data)}")
                return experiment_data
                
        except Exception as e:
            if hasattr(self.parent, 'ai_response_display'):
                self.parent.ai_response_display.append(f"[ERROR] ARIM拡張データ結合エラー: {e}")
                import traceback
                self.parent.ai_response_display.append(f"[ERROR] 結合エラー詳細: {traceback.format_exc()}")
            return experiment_data


