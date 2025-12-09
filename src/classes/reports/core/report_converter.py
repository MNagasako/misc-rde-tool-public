"""
報告書データ変換モジュール

ARIM-extracted2フォーマットから標準フォーマットへのExcel変換を実施。
カラムマッピング、設備列の変換、チャンク処理、レジューム対応を含む。
"""

import ast
import json
import os
import re
from typing import Optional, Dict, Any, List, Callable

import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class ConversionResult:
    """変換結果"""
    success: bool
    output_path: Optional[str] = None
    row_count: int = 0
    error: Optional[str] = None


class ReportConverter:
    """報告書データ変換クラス
    
    ARIM-extracted2フォーマットのExcelファイルを標準フォーマットに変換。
    """
    
    # カラムマッピング定義
    COLUMN_MAPPING = {
        'ARIM-extracted2 Columns': [
            'ARIMNO', 'コード', '年度', '機関コード', '課題番号（下4桁）', 
            '機関外・機関内の利用', '利用形態（主）', '利用形態（副）', 
            '利用課題名', '利用者名', '所属名', 
            '横断技術領域（主）', '横断技術領域（副）', 
            '重要技術領域（主）', '重要技術領域（副）', 
            '利用した主な設備1', '利用した主な設備2', '利用した主な設備3', 
            '利用した主な設備4', '利用した主な設備5', 
            'キーワード【横断技術領域】（主）', 'キーワード【横断技術領域】（副）', 
            'キーワード【重要技術領域】（主）', 'キーワード【重要技術領域】（副）', 
            'キーワード【自由記述】', '概要（目的・実施内容）', '実験', '結果と考察'
        ],
        'Output Columns': [
            '課題番号 / Project Issue Number', 'code', 'np.nan', 'np.nan', 'np.nan',
            '機関外・機関内の利用 / External or Internal Use', 
            '利用形態・主', '利用形態・副', 
            '利用課題名 / Title', 
            '利用者名（課題申請者）/ User Name (Project Applicant)', 
            '所属名 / Affiliation', 
            '横断技術領域・主', '横断技術領域・副', 
            '重要技術領域・主', '重要技術領域・副', 
            'np.nan', 'np.nan', 'np.nan', 'np.nan', 'np.nan', 
            'np.nan', 'np.nan', 'np.nan', 'np.nan', 
            'キーワード / Keywords', 
            '概要（目的・用途・実施内容）/ Abstract (Aim, Use Applications and Contents)', 
            '実験 / Experimental', 
            '結果と考察 / Results and Discussion', 
            '利用した実施機関 / Support Institute', 
            '共同利用者氏名 / Names of Collaborators in Other Institutes Than Hub and Spoke Institutes', 
            'ARIM実施機関支援担当者 / Names of Collaborators in The Hub and Spoke Institutes', 
            '利用した主な設備 / Equipment Used in This Project', 
            'その他・特記事項（参考文献・謝辞等） / Remarks(References and Acknowledgements)', 
            '論文・プロシーディング（DOIのあるもの） / DOI (Publication and Proceedings)', 
            '口頭発表、ポスター発表および、その他の論文 / Oral Presentations etc.', 
            '特許出願件数', '特許登録件数', 'key'
        ]
    }
    
    # ARIM-extracted2カラム名
    ARIM_COLUMNS = [
        'ARIMNO', 'コード', '年度', '機関コード', '課題番号（下4桁）', 
        '機関外・機関内の利用', '利用形態（主）', '利用形態（副）', 
        '利用課題名', '利用者名', '所属名', 
        '横断技術領域（主）', '横断技術領域（副）', 
        '重要技術領域（主）', '重要技術領域（副）', 
        '利用した主な設備1', '利用した主な設備2', '利用した主な設備3', 
        '利用した主な設備4', '利用した主な設備5', 
        'キーワード【横断技術領域】（主）', 'キーワード【横断技術領域】（副）', 
        'キーワード【重要技術領域】（主）', 'キーワード【重要技術領域】（副）', 
        'キーワード【自由記述】', '概要（目的・実施内容）', '実験', '結果と考察'
    ]
    
    # 分割処理が必要なカラム(日本語/英語)
    COLUMNS_TO_SPLIT = [
        '機関外・機関内の利用', '利用形態（主）', '利用形態（副）', 
        '横断技術領域（主）', '横断技術領域（副）', 
        '重要技術領域（主）', '重要技術領域（副）'
    ]
    
    # ダッシュ変換が必要なカラム
    COLUMNS_TO_DASH_CONVERT = [
        '利用形態（主）', '利用形態（副）', 
        '横断技術領域（主）', '横断技術領域（副）', 
        '重要技術領域（主）', '重要技術領域（副）'
    ]
    
    CHUNK_SIZE = 100  # 100件ごとに保存
    EQUIPMENT_COLUMN_NAME = '利用した主な設備 / Equipment Used in This Project'
    
    def __init__(self, progress_callback: Optional[Callable[[str], None]] = None):
        """
        Args:
            progress_callback: プログレスコールバック関数
        """
        self.progress_callback = progress_callback
    
    def _log(self, message: str):
        """ログ出力"""
        if self.progress_callback:
            self.progress_callback(message)
    
    @staticmethod
    def safely_evaluate_literal(literal_str: Any) -> List:
        """文字列をPythonリテラル(リスト)として安全に評価
        
        Args:
            literal_str: 評価する文字列
            
        Returns:
            評価結果のリスト（失敗時は空リスト）
        """
        if not isinstance(literal_str, str):
            return []

        candidate = literal_str.strip()
        if not candidate:
            return []

        try:
            return ast.literal_eval(candidate)
        except (ValueError, SyntaxError):
            # フォールバック: カンマまたは改行で区切られた文字列をリスト化
            if "," in candidate or "\n" in candidate:
                parts = [part.strip() for part in re.split(r"[,\n]", candidate)]
                return [part for part in parts if part]
            return [candidate]
    
    def _transform_chunk(self, chunk_df: pd.DataFrame) -> pd.DataFrame:
        """データチャンクの変換処理
        
        Args:
            chunk_df: 変換対象のDataFrame
            
        Returns:
            変換後のDataFrame
        """
        chunk_transformed = pd.DataFrame(columns=self.ARIM_COLUMNS)
        
        # カラムマッピングに基づいて変換
        for arim_col, output_col in zip(
            self.COLUMN_MAPPING['ARIM-extracted2 Columns'], 
            self.COLUMN_MAPPING['Output Columns']
        ):
            if output_col != 'np.nan':
                if arim_col in self.COLUMNS_TO_SPLIT:
                    # 日本語/英語の分割（日本語部分のみ取得）
                    chunk_transformed[arim_col] = chunk_df[output_col].apply(
                        lambda x: x.split('/')[0].strip() if isinstance(x, str) else x
                    )
                else:
                    chunk_transformed[arim_col] = chunk_df[output_col]
                
                # ダッシュ変換
                if arim_col in self.COLUMNS_TO_DASH_CONVERT:
                    chunk_transformed[arim_col] = chunk_transformed[arim_col].apply(
                        lambda x: '----' if x == '-' else x
                    )
            else:
                # 設備列の処理
                if '利用した主な設備' in arim_col:
                    equipment_num = int(arim_col[-1])
                    chunk_transformed[arim_col] = chunk_df[self.EQUIPMENT_COLUMN_NAME].apply(
                        lambda x: x[equipment_num - 1] if isinstance(x, list) and len(x) >= equipment_num else None
                    )
        
        # ARIMNO変換
        chunk_transformed['ARIMNO'] = 'JPMXP12' + chunk_transformed['ARIMNO'].astype(str)
        
        # 年度、機関コード、課題番号の抽出
        chunk_transformed['年度'] = '20' + chunk_transformed['ARIMNO'].str[7:9]
        chunk_transformed['機関コード'] = chunk_transformed['ARIMNO'].str[9:11]
        chunk_transformed['課題番号（下4桁）'] = chunk_transformed['ARIMNO'].str[-4:].astype(int)
        
        # key列を追加（Output Columnsの最後の列から）
        chunk_transformed['key'] = chunk_df[self.COLUMN_MAPPING['Output Columns'][-1]]
        
        return chunk_transformed
    
    def convert_report_data(
        self, 
        input_path: str, 
        output_path: str,
        resume: bool = True
    ) -> ConversionResult:
        """報告書データの変換
        
        Args:
            input_path: 入力Excelファイルパス
            output_path: 出力Excelファイルパス
            resume: レジューム機能を有効化（デフォルト: True）
            
        Returns:
            ConversionResult
        """
        try:
            # 入力ファイル存在確認
            if not os.path.exists(input_path):
                return ConversionResult(
                    success=False,
                    error=f"入力ファイルが見つかりません: {input_path}"
                )
            
            self._log(f"入力ファイル読み込み: {input_path}")
            
            # データ読み込み（engine明示指定）
            output_df = pd.read_excel(input_path, engine='openpyxl')
            
            # 設備列の変換（文字列→リスト）
            output_df[self.EQUIPMENT_COLUMN_NAME] = output_df[self.EQUIPMENT_COLUMN_NAME].apply(
                lambda x: self.safely_evaluate_literal(x) if isinstance(x, str) else []
            )
            
            # 進捗管理用ファイル
            output_dir = os.path.dirname(output_path)
            progress_file = os.path.join(output_dir, 'convert_progress.json')
            tmp_output_file = output_path + '.tmp.xlsx'
            
            # レジューム対応
            start_idx = 0
            if resume and os.path.exists(progress_file):
                with open(progress_file, 'r', encoding='utf-8') as f:
                    progress = json.load(f)
                    start_idx = progress.get('last_index', 0)
                self._log(f"レジューム: {start_idx}行目から再開")
            
            # チャンク処理
            num_rows = len(output_df)
            self._log(f"変換開始: {num_rows}行 ({start_idx}行目から)")
            
            for chunk_start in range(start_idx, num_rows, self.CHUNK_SIZE):
                chunk_end = min(chunk_start + self.CHUNK_SIZE, num_rows)
                chunk_df = output_df.iloc[chunk_start:chunk_end]
                
                # チャンク変換
                chunk_transformed = self._transform_chunk(chunk_df)
                
                # 保存
                if chunk_start == 0:
                    chunk_transformed.to_excel(tmp_output_file, index=False)
                else:
                    with pd.ExcelWriter(
                        tmp_output_file, 
                        mode='a', 
                        if_sheet_exists='overlay', 
                        engine='openpyxl'
                    ) as writer:
                        chunk_transformed.to_excel(
                            writer, 
                            index=False, 
                            header=False, 
                            startrow=chunk_start
                        )
                
                # 進捗保存
                with open(progress_file, 'w', encoding='utf-8') as f:
                    json.dump({'last_index': chunk_end}, f)
                
                progress_pct = (chunk_end / num_rows) * 100
                self._log(f"変換中: {chunk_end}/{num_rows}行 ({progress_pct:.1f}%)")
            
            # 完了時にリネーム&進捗ファイル削除
            os.replace(tmp_output_file, output_path)
            if os.path.exists(progress_file):
                os.remove(progress_file)
            
            self._log(f"変換完了: {output_path}")
            
            return ConversionResult(
                success=True,
                output_path=output_path,
                row_count=num_rows
            )
            
        except Exception as e:
            return ConversionResult(
                success=False,
                error=f"変換エラー: {str(e)}"
            )
