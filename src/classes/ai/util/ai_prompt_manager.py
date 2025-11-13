"""
AI プロンプト管理クラス
AIControllerの分析プロンプト機能を分離して管理
"""

import datetime
import json
import os
from config.common import get_dynamic_file_path

import logging

# ロガー設定
logger = logging.getLogger(__name__)


class AIPromptManager:
    """AI分析プロンプトの構築と管理を担当"""
    
    def __init__(self, logger=None):
        """
        AIPromptManagerを初期化
        
        Args:
            logger: ログ出力用のロガー（オプション）
        """
        self.logger = logger
        
    def _log(self, message, category="INFO"):
        """ログ出力（ロガーがある場合はロガー、なければprint）"""
        if self.logger:
            self.logger.info(f"[{category}] {message}")
        else:
            logger.debug("[%s] %s", category, message)
    
    def _debug_log_and_print(self, message, log_file=None, category="DEBUG"):
        """
        統一ログ出力関数（重複log_and_print関数の代替）
        """
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] [{category}] {message}"
        
        # コンソール出力
        print(formatted_message)
        
        # ファイル出力（指定された場合）
        if log_file:
            try:
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(formatted_message + '\n')
            except Exception as e:
                logger.error("ログファイル書き込みエラー: %s", e)
        
        # ロガー出力（設定されている場合）
        if self.logger:
            self.logger.info(f"[{category}] {message}")
    
    def build_analysis_prompt(self, template, experiment_data, material_index, prepared_data=None):
        """
        分析用プロンプトを構築（prepared_data統合対応）
        
        Args:
            template: プロンプトテンプレート文字列
            experiment_data: 実験データ（辞書形式）
            material_index: 材料インデックス文字列
            prepared_data: 事前準備済みデータ（オプション）
            
        Returns:
            str: 構築されたプロンプト文字列
        """
        # 強制ログ - プロンプト構築開始
        self._log("プロンプト構築開始", "PROMPT_BUILD")
        self._log(f"template有無: {template is not None}", "PROMPT_BUILD")
        self._log(f"experiment_data有無: {experiment_data is not None}", "PROMPT_BUILD")
        self._log(f"material_index有無: {material_index is not None}", "PROMPT_BUILD")
        self._log(f"prepared_data有無: {prepared_data is not None}", "PROMPT_BUILD")
        
        # ログファイル準備
        log_dir = get_dynamic_file_path("output/log")
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = os.path.join(log_dir, f"ai_prompt_debug_{timestamp}.log")
        
        self._debug_log_and_print("=== プロンプト構築デバッグ開始 ===", log_file, "PROMPT_DEBUG")
        
        try:
            # テンプレートの検証
            if not template:
                self._debug_log_and_print("ERROR: テンプレートが空です", log_file, "ERROR")
                return ""
            
            self._debug_log_and_print(f"テンプレート長: {len(template)}", log_file, "PROMPT_DEBUG")
            
            # 実験データの検証と整形
            experiment_section = ""
            if experiment_data:
                self._debug_log_and_print(f"実験データ項目数: {len(experiment_data)}", log_file, "PROMPT_DEBUG")
                
                # 実験データを文字列形式に変換
                formatted_exp_data = []
                for key, value in experiment_data.items():
                    if value is not None and str(value).strip():
                        formatted_exp_data.append(f"{key}: {value}")
                
                experiment_section = "\n".join(formatted_exp_data)
                self._debug_log_and_print(f"フォーマット後実験データ行数: {len(formatted_exp_data)}", log_file, "PROMPT_DEBUG")
            else:
                self._debug_log_and_print("実験データが提供されていません", log_file, "PROMPT_DEBUG")
            
            # 材料インデックスの検証
            material_section = ""
            if material_index:
                material_section = str(material_index)
                self._debug_log_and_print(f"材料インデックス長: {len(material_section)}", log_file, "PROMPT_DEBUG")
            else:
                self._debug_log_and_print("材料インデックスが提供されていません", log_file, "PROMPT_DEBUG")
            
            # prepared_dataの処理
            prepared_section = ""
            if prepared_data:
                self._debug_log_and_print(f"prepared_data項目数: {len(prepared_data)}", log_file, "PROMPT_DEBUG")
                
                # prepared_dataを文字列形式に変換
                try:
                    prepared_section = json.dumps(prepared_data, ensure_ascii=False, indent=2)
                    self._debug_log_and_print(f"prepared_data JSON変換成功: {len(prepared_section)}文字", log_file, "PROMPT_DEBUG")
                except Exception as e:
                    self._debug_log_and_print(f"prepared_data JSON変換失敗: {e}", log_file, "ERROR")
                    prepared_section = str(prepared_data)
            else:
                self._debug_log_and_print("prepared_dataは提供されていません", log_file, "PROMPT_DEBUG")
            
            # プロンプトのプレースホルダー置換
            result_prompt = template
            
            # まず基本的なプレースホルダーの置換を実行
            basic_replacements = {
                "{experiment_data}": experiment_section,
                "{material_index}": material_section,
                "{prepared_data}": prepared_section,
                "{{experiment_data}}": experiment_section,
                "{{material_index}}": material_section,
                "{{prepared_data}}": prepared_section,
            }
            
            for placeholder, replacement in basic_replacements.items():
                if placeholder in result_prompt:
                    result_prompt = result_prompt.replace(placeholder, replacement)
                    self._debug_log_and_print(f"プレースホルダー置換: {placeholder} -> {len(replacement)}文字", log_file, "PROMPT_DEBUG")
            
            # prepared_dataに複雑な構造化データがある場合、セクション構造を構築
            if prepared_data and isinstance(prepared_data, dict):
                # 元のui_controller_ai.pyと同じセクション構造を再現
                has_structured_sections = any(key in prepared_data for key in ['prepare_exp_info', 'prepare_exp_info_ext'])
                
                if has_structured_sections:
                    self._debug_log_and_print("構造化セクション検出 - 複雑なプロンプト構築を実行", log_file, "PROMPT_DEBUG")
                    result_prompt = self._build_structured_prompt(template, experiment_data, material_index, prepared_data)
            
            self._debug_log_and_print(f"最終プロンプト長: {len(result_prompt)}", log_file, "PROMPT_DEBUG")
            self._debug_log_and_print("=== プロンプト構築デバッグ完了 ===", log_file, "PROMPT_DEBUG")
            
            return result_prompt
            
        except Exception as e:
            self._debug_log_and_print(f"プロンプト構築エラー: {e}", log_file, "ERROR")
            import traceback
            self._debug_log_and_print(f"エラー詳細: {traceback.format_exc()}", None, "ERROR")
            return ""

    def _build_structured_prompt(self, template, experiment_data, material_index, prepared_data):
        """
        構造化プロンプト構築（元のui_controller_ai.pyの複雑なセクション構造を再現）
        
        【重要】ARIM拡張情報の統合
        このメソッドは元のui_controller_ai.pyから移行された複雑なプロンプト構築ロジックを
        再現します。特にARIM拡張データが含まれる【拡張実験情報（ARIM拡張含む）】セクション
        構造を維持することが重要です。
        
        【コメント追加理由】
        - 過去にARIM拡張情報がプロンプトから欠落する問題が発生
        - このメソッドはARIM拡張データを適切に統合する責任を持つ
        - 構造化プロンプトの複雑性により、変更時は注意深い検証が必要
        - prepared_dataにはprepare_exp_info_extで準備されたARIM拡張情報が含まれる
        
        Args:
            template: プロンプトテンプレート
            experiment_data: 実験データ
            material_index: 材料インデックス
            prepared_data: 準備済みデータ（構造化情報含む、ARIM拡張データを含む）
            
        Returns:
            str: 構造化されたプロンプト
        """
        try:
            import json
            from datetime import datetime
            
            
            self._debug_log_and_print("構造化プロンプト構築開始", None, "STRUCTURED_PROMPT")
            
            # プロンプトを構築（基本構造）
            full_prompt_parts = [template]
            self._debug_log_and_print(f"1. テンプレート追加: 長さ {len(template)}", None, "STRUCTURED_PROMPT")
            
            # 課題情報セクション（prepare_exp_infoの結果を使用）
            if prepared_data and 'prepare_exp_info' in prepared_data:
                task_section = f"""
【課題・実験情報】
{prepared_data['prepare_exp_info']}"""
                full_prompt_parts.append(task_section)
                self._debug_log_and_print(f"2. 課題・実験情報セクション追加: 長さ {len(task_section)}", None, "STRUCTURED_PROMPT")
                self._debug_log_and_print(f"   内容プレビュー: {task_section[:200]}...", None, "STRUCTURED_PROMPT")
            else:
                self._debug_log_and_print("2. 課題・実験情報セクション: スキップ (prepare_exp_info無し)", None, "STRUCTURED_PROMPT")
            
            # 拡張実験情報セクション（prepare_exp_info_extの結果を使用）
            # 【重要】ARIM拡張データ統合ポイント
            # このセクションでARIM拡張データが正しく含まれることを確認
            # prepared_dataの'prepare_exp_info_ext'キーにARIM拡張情報が格納される
            if prepared_data and 'prepare_exp_info_ext' in prepared_data:
                ext_section = f"""
【拡張実験情報（ARIM拡張含む）】
{prepared_data['prepare_exp_info_ext']}"""
                full_prompt_parts.append(ext_section)
                self._debug_log_and_print(f"3. 拡張実験情報セクション追加: 長さ {len(ext_section)}", None, "STRUCTURED_PROMPT")
                self._debug_log_and_print(f"   内容プレビュー: {ext_section[:300]}...", None, "STRUCTURED_PROMPT")
            else:
                self._debug_log_and_print("3. 拡張実験情報セクション: スキップ (prepare_exp_info_ext無し)", None, "STRUCTURED_PROMPT")
            
            # 従来の実験データJSON（後方互換性のため維持）
            if experiment_data:
                experiment_json = json.dumps(experiment_data, ensure_ascii=False, indent=2)
                exp_section = f"""
【実験情報データ】
{experiment_json}"""
                full_prompt_parts.append(exp_section)
                self._debug_log_and_print(f"4. 実験情報データセクション追加: 長さ {len(exp_section)}", None, "STRUCTURED_PROMPT")
            
            # マテリアルインデックス
            if material_index:
                if isinstance(material_index, dict):
                    mi_json = json.dumps(material_index, ensure_ascii=False, indent=2)
                else:
                    mi_json = str(material_index)
                    
                mi_section = f"""
【マテリアルインデックス】
{mi_json}"""
                full_prompt_parts.append(mi_section)
                self._debug_log_and_print(f"5. マテリアルインデックスセクション追加: 長さ {len(mi_section)}", None, "STRUCTURED_PROMPT")
            
            # その他のprepared_dataがあれば追加
            other_section_count = 6
            if prepared_data:
                for key, value in prepared_data.items():
                    if key not in ['prepare_exp_info', 'prepare_exp_info_ext']:
                        other_section = f"""
【{key}】
{value}"""
                        full_prompt_parts.append(other_section)
                        self._debug_log_and_print(f"{other_section_count}. {key}セクション追加: 長さ {len(other_section)}", None, "STRUCTURED_PROMPT")
                        other_section_count += 1
            
            # 全セクションを結合
            full_prompt = "\n".join(full_prompt_parts)
            self._debug_log_and_print(f"=== 構造化プロンプト完了 ===", None, "STRUCTURED_PROMPT")
            self._debug_log_and_print(f"総セクション数: {len(full_prompt_parts)}", None, "STRUCTURED_PROMPT")
            self._debug_log_and_print(f"最終プロンプト長: {len(full_prompt)} 文字", None, "STRUCTURED_PROMPT")
            
            # セクション存在チェック
            has_exp_section = "【実験情報データ】" in full_prompt
            has_task_section = "【課題・実験情報】" in full_prompt
            has_ext_section = "【拡張実験情報（ARIM拡張含む）】" in full_prompt
            has_mi_section = "【マテリアルインデックス】" in full_prompt
            
            self._debug_log_and_print(f"セクション存在確認:", None, "STRUCTURED_PROMPT")
            self._debug_log_and_print(f"  実験情報セクション: {has_exp_section}", None, "STRUCTURED_PROMPT")
            self._debug_log_and_print(f"  課題・実験情報セクション: {has_task_section}", None, "STRUCTURED_PROMPT")
            self._debug_log_and_print(f"  拡張実験情報セクション: {has_ext_section}", None, "STRUCTURED_PROMPT")
            self._debug_log_and_print(f"  マテリアルインデックスセクション: {has_mi_section}", None, "STRUCTURED_PROMPT")
            
            return full_prompt
            
        except Exception as e:
            self._debug_log_and_print(f"構造化プロンプト構築エラー: {e}", None, "ERROR")
            import traceback
            self._debug_log_and_print(f"エラー詳細: {traceback.format_exc()}", None, "ERROR")
            # フォールバック: 基本プロンプト構築
            return template
