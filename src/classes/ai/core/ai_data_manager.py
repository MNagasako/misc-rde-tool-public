"""
AI機能用データ管理クラス - ARIM RDE Tool v1.13.2
UIControllerから分離したAI関連データ管理専用モジュール
"""
import os
import pandas as pd
from config.common import INPUT_DIR


class AIDataManager:
    """AI機能のデータ管理専用クラス"""
    
    def __init__(self, logger=None):
        """
        AIDataManagerの初期化
        Args:
            logger: ログ出力用のロガー（オプション）
        """
        self.logger = logger
        self.task_data = {}
        self.experiment_data = None
        self.request_history = []
        self.current_task_id = None
        
        # デバッグ用フラグ
        self.debug_enabled = True
        
    def _debug_log(self, message, prefix="[DATA_MGR]"):
        """デバッグログ出力"""
        if self.debug_enabled:
            #print(f"{prefix} {message}")
            pass
        if self.logger:
            #self.logger.debug(f"{prefix} {message}")
            pass
    
    def is_valid_data_value(self, value):
        """
        データ値が有効かどうかを判定
        Args:
            value: 判定対象の値
        Returns:
            bool: 有効な値の場合True
        """
        self._debug_log(f"_is_valid_data_value called with: {value} (type: {type(value)})")
        
        # None チェック
        if value is None:
            self._debug_log("Value is None, returning False")
            return False
        
        # pandas NaN チェック
        if pd.isna(value):
            self._debug_log("Value is pd.isna, returning False")
            return False
        
        # 文字列の場合の詳細チェック
        if isinstance(value, str):
            str_value = value.strip()
            self._debug_log(f"str_value: '{str_value}'")
            
            if str_value == "" or str_value.lower() == "nan":
                self._debug_log("Value is empty or 'nan', returning False")
                return False
            
            self._debug_log("Value is valid, returning True")
            return True
        
        # 数値の場合
        try:
            str_value = str(value).strip()
            self._debug_log(f"str_value: '{str_value}'")
            
            if str_value == "" or str_value.lower() == "nan":
                self._debug_log("Value is empty or 'nan', returning False")
                return False
            
            self._debug_log("Value is valid, returning True") 
            return True
        except:
            self._debug_log("Value conversion failed, returning False")
            return False

    def debug_column_structure(self, use_arim_data=True):
        """
        デバッグ用: Excelファイルの列構造を表示
        Args:
            use_arim_data: ARIMデータを使用するかどうか
        """
        df = self.load_experiment_data_file(use_arim_data)
        if df is None:
            self._debug_log("データフレームの読み込みに失敗")
            return
        
        data_type = "ARIMデータ" if use_arim_data else "通常データ"
        self._debug_log(f"=== {data_type} 列構造デバッグ ===")
        self._debug_log(f"データシェイプ: {df.shape}")
        self._debug_log(f"列数: {len(df.columns)}")
        
        for i, col in enumerate(df.columns, 1):
            sample_values = df[col].dropna().head(3).tolist()
            self._debug_log(f"{i:2d}. '{col}' - サンプル: {sample_values}")
        
        # 課題ID列の検出テスト
        detected_col = self._find_task_id_column(df, use_arim_data)
        if detected_col:
            unique_values = df[detected_col].dropna().unique()
            self._debug_log(f"検出された課題ID列: '{detected_col}' - ユニーク値数: {len(unique_values)}")
            self._debug_log(f"サンプル課題ID: {unique_values[:5].tolist()}")
        else:
            self._debug_log("課題ID列が検出されませんでした")
        
        self._debug_log(f"=== {data_type} 列構造デバッグ完了 ===")

    def load_experiment_data_file(self, use_arim_data=True):
        """
        実験データファイルを読み込み
        Args:
            use_arim_data: ARIMデータを使用するかどうか
        Returns:
            pandas.DataFrame: 読み込んだ実験データ
        """
        try:
            # ファイルパス決定
            if use_arim_data:
                exp_file_path = os.path.join(INPUT_DIR, "ai", "arim_exp.xlsx")
                data_type = "ARIM実験データ"
            else:
                exp_file_path = os.path.join(INPUT_DIR, "ai", "exp.xlsx")
                data_type = "通常実験データ"
            
            self._debug_log(f"課題リスト用{data_type}を読み込み中: {exp_file_path}")
            
            # 絶対パス変換
            abs_path = os.path.abspath(exp_file_path)
            self._debug_log(f"絶対パス: {abs_path}")
            
            # ファイル存在確認
            if not os.path.exists(abs_path):
                self._debug_log(f"ファイルが存在しません: {abs_path}")
                return None
            
            self._debug_log(f"ファイルが存在することを確認: {abs_path}")
            
            # ファイルサイズ確認
            file_size = os.path.getsize(abs_path)
            self._debug_log(f"ファイルサイズ: {file_size} bytes")
            
            # データ読み込み
            self._debug_log(f"pandas読み込み開始: {abs_path}")
            df = pd.read_excel(abs_path)
            self._debug_log(f"pandas読み込み成功: {df.shape}")
            
            # 課題番号列の自動マッピング（互換性のため）
            task_id_col = self._find_task_id_column(df, use_arim_data)
            if task_id_col and task_id_col != '課題番号':
                # 課題番号列として統一マッピング
                df['課題番号'] = df[task_id_col]
                self._debug_log(f"課題番号列をマッピング: {task_id_col} -> 課題番号")
            
            # データをインスタンス変数に保存
            self.experiment_data = df
            
            return df
            
        except Exception as e:
            self._debug_log(f"実験データ読み込みエラー: {e}")
            return None
    
    def _find_task_id_column(self, df, use_arim_data=True):
        """
        データフレームから課題ID列を自動検出
        Args:
            df: pandas DataFrame
            use_arim_data: ARIMデータを使用するかどうか
        Returns:
            str: 見つかった課題ID列名、見つからない場合はNone
        """
        # 課題ID列の候補（優先度順）
        if use_arim_data:
            # ARIMデータの場合の候補
            task_id_candidates = [
                'ARIM ID', 'task_id', 'Task_ID', 'taskid', 'TaskID',
                '課題番号', '課題ID', 'grant_number', 'Grant_Number',
                'project_id', 'Project_ID', 'id', 'ID'
            ]
        else:
            # 通常データの場合の候補（より広範囲）
            task_id_candidates = [
                '課題番号', 'task_id', 'Task_ID', 'taskid', 'TaskID',
                'ARIM ID', '課題ID', 'grant_number', 'Grant_Number',
                'project_id', 'Project_ID', 'id', 'ID', 'No', 'no'
            ]
        
        # 実際の列名をログ出力（デバッグ用）
        self._debug_log(f"実際のExcel列名: {list(df.columns)}")
        
        # 完全一致での検索
        for candidate in task_id_candidates:
            if candidate in df.columns:
                self._debug_log(f"課題ID列を検出: {candidate}")
                return candidate
        
        # 部分一致での検索（より柔軟な検索）
        for candidate in task_id_candidates:
            for col in df.columns:
                if candidate.lower() in col.lower() or col.lower() in candidate.lower():
                    self._debug_log(f"課題ID列を部分一致で検出: {col} (候補: {candidate})")
                    return col
        
        # 課題番号らしい列名のパターンマッチング
        import re
        task_patterns = [
            r'.*課題.*',
            r'.*task.*',
            r'.*id.*',
            r'.*番号.*',
            r'.*number.*',
            r'.*grant.*',
            r'.*project.*'
        ]
        
        for pattern in task_patterns:
            for col in df.columns:
                if re.match(pattern, col, re.IGNORECASE):
                    self._debug_log(f"課題ID列をパターンマッチで検出: {col} (パターン: {pattern})")
                    return col
        
        self._debug_log("課題ID列が見つかりませんでした")
        return None

    def get_task_list(self, use_arim_data=True):
        """
        課題IDリストを取得
        Args:
            use_arim_data: ARIMデータを使用するかどうか
        Returns:
            list: 課題IDのリスト
        """
        df = self.load_experiment_data_file(use_arim_data)
        if df is None:
            return []
        
        try:
            # 課題ID列を自動検出
            task_id_col = self._find_task_id_column(df, use_arim_data)
            
            if task_id_col is None:
                self._debug_log(f"課題ID列が見つかりません。利用可能カラム: {list(df.columns)}")
                return []
            
            # ユニークな課題IDを取得
            task_ids = df[task_id_col].dropna().unique().tolist()
            self._debug_log(f"課題ID数: {len(task_ids)} (from {task_id_col})")
            return sorted(task_ids)
            
        except Exception as e:
            self._debug_log(f"課題IDリスト取得エラー: {e}")
            return []
    
    def get_experiments_for_task(self, task_id, use_arim_data=True):
        """
        指定された課題IDの実験データを取得
        Args:
            task_id: 課題ID
            use_arim_data: ARIMデータを使用するかどうか
        Returns:
            pandas.DataFrame: 該当する実験データ
        """
        df = self.load_experiment_data_file(use_arim_data)
        if df is None:
            return pd.DataFrame()
        
        try:
            # 課題ID列を自動検出
            task_id_col = self._find_task_id_column(df, use_arim_data)
            
            if task_id_col is None:
                self._debug_log("課題ID列が見つかりません")
                return pd.DataFrame()
            
            # 課題IDで絞り込み
            task_experiments = df[df[task_id_col] == task_id]
            self._debug_log(f"課題 {task_id} の実験データ: {len(task_experiments)}件 (from {task_id_col})")
            
            # 結果をJSONライクな辞書のリストに変換
            if not task_experiments.empty:
                experiments_list = task_experiments.to_dict('records')
                
                # 課題番号列を統一（互換性のため）
                for exp in experiments_list:
                    if '課題番号' not in exp and task_id_col in exp:
                        exp['課題番号'] = exp[task_id_col]
                
                self._debug_log(f"変換後の実験データ: {len(experiments_list)}件")
                return experiments_list
            
            return []
            
        except Exception as e:
            self._debug_log(f"実験データ取得エラー: {e}")
            return []
    
    def get_task_info(self, task_id, use_arim_data=True):
        """
        課題の基本情報を取得
        Args:
            task_id: 課題ID
            use_arim_data: ARIMデータを使用するかどうか
        Returns:
            dict: 課題情報
        """
        experiments = self.get_experiments_for_task(task_id, use_arim_data)
        if experiments.empty:
            return {}
        
        try:
            # 最初の実験レコードから基本情報を取得
            first_exp = experiments.iloc[0]
            
            # カラム名の正規化（データソースに応じて）
            if use_arim_data:
                # ARIMデータの場合
                title_col = 'タイトル' if 'タイトル' in experiments.columns else 'title'
                summary_col = '概要' if '概要' in experiments.columns else 'summary'
                field_col = '分野' if '分野' in experiments.columns else 'field'
                keywords_col = 'キーワード' if 'キーワード' in experiments.columns else 'keywords'
                equipment_col = '実験装置' if '実験装置' in experiments.columns else 'equipment'
            else:
                # 通常データの場合
                title_col = 'title' if 'title' in experiments.columns else 'タイトル'
                summary_col = 'summary' if 'summary' in experiments.columns else '概要'
                field_col = 'field' if 'field' in experiments.columns else '分野'
                keywords_col = 'keywords' if 'keywords' in experiments.columns else 'キーワード'
                equipment_col = 'equipment' if 'equipment' in experiments.columns else '実験装置'
            
            task_info = {
                'task_id': task_id,
                'experiment_count': len(experiments),
                'title': first_exp.get(title_col, ''),
                'summary': first_exp.get(summary_col, ''),
                'field': first_exp.get(field_col, ''),
                'keywords': first_exp.get(keywords_col, ''),
                'equipment': first_exp.get(equipment_col, '')
            }
            
            self._debug_log(f"課題情報取得完了: {task_id}")
            return task_info
            
        except Exception as e:
            self._debug_log(f"課題情報取得エラー: {e}")
            return {}
