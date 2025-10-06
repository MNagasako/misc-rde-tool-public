"""
AI拡張機能基盤
他のAI拡張機能でも再利用できる共通基盤クラス・ユーティリティ
"""

import os
import json
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod


class AIPromptTemplate:
    """AIプロンプトテンプレート管理クラス"""
    
    def __init__(self, template_name: str, base_prompt: str, context_keys: List[str] = None):
        """
        Args:
            template_name: テンプレート名
            base_prompt: ベースプロンプト文字列（{key}形式のプレースホルダーを含む）
            context_keys: 必要なコンテキストキーのリスト
        """
        self.template_name = template_name
        self.base_prompt = base_prompt
        self.context_keys = context_keys or []
        
    def render(self, context_data: Dict[str, Any]) -> str:
        """
        コンテキストデータを使ってプロンプトをレンダリング
        
        Args:
            context_data: コンテキストデータ辞書
            
        Returns:
            レンダリングされたプロンプト文字列
        """
        try:
            # 空値の場合のフォールバック処理
            safe_context = {}
            for key in self.context_keys:
                value = context_data.get(key, '')
                safe_context[key] = value if value else f"[{key}未設定]"
            
            # 追加のコンテキストデータも含める
            for key, value in context_data.items():
                if key not in safe_context:
                    safe_context[key] = value if value else f"[{key}未設定]"
            
            return self.base_prompt.format(**safe_context)
            
        except KeyError as e:
            # 必要なキーが不足している場合
            missing_key = str(e).strip("'")
            raise ValueError(f"プロンプトテンプレートに必要なキー '{missing_key}' が不足しています")
        except Exception as e:
            raise ValueError(f"プロンプトレンダリングエラー: {str(e)}")


class AIExtensionBase(ABC):
    """AI拡張機能の基底クラス"""
    
    def __init__(self, extension_name: str):
        """
        Args:
            extension_name: 拡張機能名
        """
        self.extension_name = extension_name
        self.prompt_templates = {}
        
    def register_template(self, template: AIPromptTemplate):
        """プロンプトテンプレートを登録"""
        self.prompt_templates[template.template_name] = template
        
    def clear_templates(self):
        """登録されているテンプレートをすべてクリア"""
        self.prompt_templates.clear()
        
    def get_template(self, template_name: str) -> Optional[AIPromptTemplate]:
        """登録されたテンプレートを取得"""
        return self.prompt_templates.get(template_name)
        
    def reload_external_templates(self) -> bool:
        """
        外部テンプレートファイルを強制的に再読み込み
        
        Returns:
            読み込み成功時True
        """
        # 既存テンプレートをクリア
        self.clear_templates()
        
        # 外部テンプレートを再読み込み
        if hasattr(self, '_load_external_templates'):
            return self._load_external_templates()
        
        return False
        
    @abstractmethod
    def collect_context_data(self, **kwargs) -> Dict[str, Any]:
        """
        コンテキストデータを収集
        
        Returns:
            収集されたコンテキストデータ辞書
        """
        pass
        
    @abstractmethod
    def process_ai_response(self, response: str) -> List[Dict[str, str]]:
        """
        AI応答を処理して候補リストに変換
        
        Args:
            response: AI応答文字列
            
        Returns:
            候補辞書のリスト [{"title": "タイトル", "text": "内容"}, ...]
        """
        pass


class DatasetDescriptionExtension(AIExtensionBase):
    """データセット説明AI拡張機能"""
    
    def __init__(self):
        super().__init__("dataset_description")
        
        # プロンプトテンプレートを登録
        self._register_default_templates()
        
    def _register_default_templates(self):
        """デフォルトのプロンプトテンプレートを登録"""
        
        # 外部ファイルからテンプレートを読み込み
        if self._load_external_templates():
            print("[INFO] 外部テンプレートファイルからの読み込み成功")
            return
        
        # 保存されたテンプレートファイルを削除（新しいテンプレートを強制読み込み）
        try:
            from config.common import get_dynamic_file_path
            config_path = get_dynamic_file_path("input/prompt_templates.json")
            if os.path.exists(config_path):
                os.remove(config_path)
                print(f"[DEBUG] 古いテンプレートファイルを削除: {config_path}")
        except Exception as e:
            print(f"[WARNING] テンプレートファイル削除エラー: {e}")
        
        # 保存されたテンプレートを読み込み
        try:
            from config.common import get_dynamic_file_path
            config_path = get_dynamic_file_path("input/prompt_templates.json")
            
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    templates_config = json.load(f)
                    
                # dataset_description の設定があれば使用
                if "dataset_description" in templates_config:
                    for template_name, template_data in templates_config["dataset_description"].items():
                        template = AIPromptTemplate(
                            template_name,
                            template_data.get("prompt", ""),
                            ["name", "type", "grant_number", "existing_description", "dataset_existing_info", "arim_extension_data", "arim_experiment_data", "arim_detailed_experiment", "experiment_summary", "material_index_data", "equipment_data", "file_info", "metadata", "related_datasets"]
                        )
                        self.register_template(template)
                    return  # 保存されたテンプレートを使用
                    
        except Exception as e:
            print(f"[WARNING] 保存されたテンプレート読み込みエラー: {e}")
        
        # フォールバック: ハードコードされたデフォルトテンプレートを使用
        print("[WARNING] 外部テンプレートが利用できません。ハードコードされたテンプレートを使用します。")
        self._register_fallback_templates()

    def _load_external_templates(self) -> bool:
        """
        外部ファイルからテンプレートを読み込み
        
        Returns:
            読み込み成功時True
        """
        try:
            from config.common import get_dynamic_file_path
            
            # テンプレート設定ファイルを読み込み
            config_path = get_dynamic_file_path("input/ai/prompts/template_config.json")
            if not os.path.exists(config_path):
                print(f"[DEBUG] テンプレート設定ファイルが見つかりません: {config_path}")
                return False
            
            with open(config_path, 'r', encoding='utf-8') as f:
                template_config = json.load(f)
            
            # dataset_explanation の設定を読み込み
            dataset_config = template_config.get("dataset_explanation", {})
            if not dataset_config:
                print("[WARNING] dataset_explanation設定が見つかりません")
                return False
            
            # 各テンプレートファイルを読み込み
            for template_name, template_info in dataset_config.items():
                template_file = template_info.get("file", "")
                context_keys = template_info.get("context_keys", [])
                
                if not template_file:
                    print(f"[WARNING] テンプレート '{template_name}' のファイルパスが設定されていません")
                    continue
                
                # テンプレートファイルを読み込み
                template_path = get_dynamic_file_path(template_file)
                if not os.path.exists(template_path):
                    print(f"[WARNING] テンプレートファイルが見つかりません: {template_path}")
                    continue
                
                with open(template_path, 'r', encoding='utf-8') as f:
                    template_content = f.read()
                
                # テンプレートを登録
                template = AIPromptTemplate(template_name, template_content, context_keys)
                self.register_template(template)
                print(f"[INFO] 外部テンプレート読み込み成功: {template_name} ({len(template_content)}文字)")
            
            return True
            
        except Exception as e:
            print(f"[ERROR] 外部テンプレート読み込みエラー: {e}")
            return False
    
    def _register_fallback_templates(self):
        """フォールバック用のハードコードされたテンプレートを登録"""
        basic_template = AIPromptTemplate(
            "basic",
            """
データセットの説明文を3つの異なるスタイルで提案してください。

データセット情報:
- 名前: {name}
- タイプ: {type}
- 課題番号: {grant_number}
- 既存説明: {existing_description}

ARIM課題関連情報:
- 課題データ: {dataset_existing_info}
- 拡張情報: {arim_extension_data}
- 実験データ: {arim_experiment_data}

{arim_detailed_experiment}

実験データサマリー: {experiment_summary}

マテリアルインデックス(JSON): {material_index_data}

{equipment_data}

要求:
1. 学術的技術的で簡潔で分かりやすい説明文（日本語で200文字程度）
2. 学術的技術的で詳細な説明文（日本語で500文字程度）
3. 一般向けに親しみやすい説明文（日本語で200文字程度）

出力形式:
[簡潔版] ここに簡潔な説明
[学術版] ここに学術的な説明
[一般版] ここに一般向けの説明

注意: 各説明文は改行なしで1行で出力してください。
""",
            ["name", "type", "grant_number", "existing_description", "dataset_existing_info", "arim_extension_data", "arim_experiment_data", "arim_detailed_experiment", "experiment_summary", "material_index_data", "equipment_data"]
        )
        
        self.register_template(basic_template)
        
        # 詳細テンプレート（フォールバック用）
        detailed_template = AIPromptTemplate(
            "detailed",
            """
データセットの詳細説明文を生成してください。

基本情報:
- データセット名: {name}
- データセットタイプ: {type}
- 研究課題番号: {grant_number}
- 既存の説明: {existing_description}

ARIM課題データ:
- 課題データ: {dataset_existing_info}
- 拡張情報: {arim_extension_data}
- 実験データ: {arim_experiment_data}

{arim_detailed_experiment}

マテリアルインデックス(JSON): {material_index_data}

{equipment_data}

関連情報:
- ファイル情報: {file_info}
- メタデータ: {metadata}
- 関連データセット: {related_datasets}

要求:
専門的で包括的な説明文を作成してください。研究の背景、データの特徴、利用方法を含めてください。

出力: 詳細な説明文（500文字以内）
""",
            ["name", "type", "grant_number", "existing_description", "dataset_existing_info", "arim_extension_data", "arim_experiment_data", "arim_detailed_experiment", "material_index_data", "equipment_data", "file_info", "metadata", "related_datasets"]
        )
        
        self.register_template(detailed_template)
        
        # クイック版テンプレート（フォールバック用）
        quick_template = AIPromptTemplate(
            "quick",
            """
データセットの簡潔な説明文を1つ生成してください。

基本情報:
- データセット名: {name}
- データセットタイプ: {type}
- 研究課題番号: {grant_number}
- 既存の説明: {existing_description}

ARIM課題データ:
- 課題データ: {dataset_existing_info}
- 拡張情報: {arim_extension_data}
- 実験データ: {arim_experiment_data}

{experiment_summary}

マテリアルインデックス(JSON): {material_index_data}

{equipment_data}

要求:
- 学術的且つ技術的で簡潔な説明文を作成してください
- 150-250文字程度
- 箇条書きを避け、一続きの自然な文章とする
- 冗長な表現・重複は避ける

出力: 簡潔な説明文のみ（見出しや形式マーカーなし）
""",
            ["name", "type", "grant_number", "existing_description", "dataset_existing_info", "arim_extension_data", "arim_experiment_data", "experiment_summary", "material_index_data", "equipment_data"]
        )
        
        self.register_template(quick_template)
        print("[INFO] フォールバックテンプレート登録完了: basic, detailed, quick")
        
    def collect_context_data(self, **kwargs) -> Dict[str, Any]:
        """データセット関連のコンテキストデータを収集"""
        context = {}
        
        # 基本情報を取得
        context['name'] = kwargs.get('name', '')
        context['type'] = kwargs.get('type', '')
        context['grant_number'] = kwargs.get('grant_number', '')
        context['existing_description'] = kwargs.get('existing_description', '')
        
        # ARIM課題関連情報を取得
        context['dataset_existing_info'] = kwargs.get('dataset_existing_info', '')
        context['arim_extension_data'] = kwargs.get('arim_extension_data', '')
        context['arim_experiment_data'] = kwargs.get('arim_experiment_data', '')
        context['arim_detailed_experiment'] = kwargs.get('arim_detailed_experiment', '')
        context['experiment_summary'] = kwargs.get('experiment_summary', '')
        
        # MI情報を追加
        try:
            from .utils.data_loaders import MaterialIndexLoader
            context['material_index_data'] = MaterialIndexLoader.format_for_prompt()
        except Exception as e:
            print(f"[WARNING] MI情報取得エラー: {e}")
            context['material_index_data'] = '[MI情報取得エラー]'
        
        # 装置情報を追加（設備IDが指定されている場合）
        equipment_ids = kwargs.get('equipment_ids', [])
        if equipment_ids:
            try:
                from .utils.data_loaders import EquipmentLoader
                equipment_list = EquipmentLoader.find_equipment_by_ids(equipment_ids)
                context['equipment_data'] = EquipmentLoader.format_equipment_for_prompt(equipment_list)
            except Exception as e:
                print(f"[WARNING] 装置情報取得エラー: {e}")
                context['equipment_data'] = '[装置情報取得エラー]'
        else:
            context['equipment_data'] = '[設備ID未指定]'
        
        # 将来の拡張用フィールド
        context['file_info'] = kwargs.get('file_info', '')
        context['metadata'] = kwargs.get('metadata', '')
        context['related_datasets'] = kwargs.get('related_datasets', '')
        
        return context
        
    def process_ai_response(self, response: str) -> List[Dict[str, str]]:
        """AI応答を解析して候補リストに変換"""
        suggestions = []
        
        try:
            # より精密なパースロジック
            lines = response.split('\n')
            current_suggestion = None
            current_text = []
            
            for line in lines:
                line = line.strip()
                
                # [タイトル] 形式の検出
                if line.startswith('[') and ']' in line:
                    # 前の提案を保存
                    if current_suggestion and current_text:
                        text_content = ' '.join(current_text).strip()
                        if text_content:  # 空でない場合のみ保存
                            suggestions.append({
                                'title': current_suggestion,
                                'text': text_content
                            })
                    
                    # 新しい提案開始
                    bracket_end = line.find(']')
                    current_suggestion = line[1:bracket_end]  # [] を除去
                    
                    # ]の後に続くテキストも取得
                    remaining_text = line[bracket_end+1:].strip()
                    current_text = [remaining_text] if remaining_text else []
                    
                elif line and current_suggestion:
                    # 継続するテキスト
                    current_text.append(line)
                elif line and not current_suggestion:
                    # [タイトル]形式でない最初のテキスト
                    suggestions.append({
                        'title': f'提案{len(suggestions)+1}',
                        'text': line
                    })
            
            # 最後の提案を保存
            if current_suggestion and current_text:
                text_content = ' '.join(current_text).strip()
                if text_content:
                    suggestions.append({
                        'title': current_suggestion,
                        'text': text_content
                    })
            
            # フォールバック: パース失敗時または結果なしの場合
            if not suggestions:
                # 改行で分割して複数の提案として扱う
                lines = [line.strip() for line in response.split('\n') if line.strip()]
                if len(lines) > 1:
                    for i, line in enumerate(lines, 1):
                        if len(line) > 10:  # 意味のある長さのテキストのみ
                            suggestions.append({
                                'title': f'提案{i}',
                                'text': line
                            })
                else:
                    # 全体を1つの提案として扱う
                    suggestions.append({
                        'title': 'AI提案',
                        'text': response.strip()
                    })
                
        except Exception as e:
            print(f"[WARNING] AI応答解析エラー: {e}")
            # エラー時のフォールバック
            suggestions.append({
                'title': 'AI提案（解析エラー）',
                'text': response.strip()
            })
            
        return suggestions


class AIExtensionRegistry:
    """AI拡張機能レジストリ"""
    
    _registry = {}
    
    @classmethod
    def register(cls, extension: AIExtensionBase):
        """AI拡張機能を登録"""
        cls._registry[extension.extension_name] = extension
        
    @classmethod
    def get(cls, extension_name: str) -> Optional[AIExtensionBase]:
        """登録されたAI拡張機能を取得"""
        return cls._registry.get(extension_name)
        
    @classmethod
    def list_extensions(cls) -> List[str]:
        """登録されている拡張機能名のリストを取得"""
        return list(cls._registry.keys())


# デフォルト拡張機能を登録
AIExtensionRegistry.register(DatasetDescriptionExtension())