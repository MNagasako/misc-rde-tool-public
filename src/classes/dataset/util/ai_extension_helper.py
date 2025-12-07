"""
AI拡張設定管理モジュール
AI拡張機能のボタン設定とプロンプトファイルの管理を行う
"""

import os
import json
from config.common import get_dynamic_file_path

import logging

# ロガー設定
logger = logging.getLogger(__name__)

def load_ai_extension_config():
    """AI拡張設定ファイルを読み込む"""
    try:
        config_path = get_dynamic_file_path("input/ai/ai_ext_conf.json")
        
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info("AI拡張設定ファイルを読み込みました: %s", config_path)
                return config
        else:
            logger.info("AI拡張設定ファイルが見つかりません。デフォルト設定を使用します: %s", config_path)
            return get_default_ai_extension_config()
            
    except Exception as e:
        logger.error("AI拡張設定読み込みエラー: %s", e)
        logger.info("デフォルト設定を使用します")
        return get_default_ai_extension_config()

def get_default_ai_extension_config():
    """デフォルトのAI拡張設定を取得"""
    return {
        "version": "1.0.0",
        "description": "デフォルトAI拡張設定",
        "buttons": [
            {
                "id": "default_analysis",
                "label": "総合分析",
                "description": "データセットの総合的な分析を実行",
                "prompt_template": "以下のデータセットについて総合的な分析を行ってください。\n\nデータセット名: {name}\nタイプ: {type}\n課題番号: {grant_number}\n既存説明: {description}\n\n分析項目:\n1. 技術的特徴\n2. 学術的価値\n3. 応用可能性\n4. データ品質\n5. 改善提案\n\n各項目について詳しく分析し、200文字程度で要約してください。",
                "icon": "📊",
                "category": "総合"
            }
        ],
        "default_buttons": [],
        "ui_settings": {
            "buttons_per_row": 3,
            "button_height": 60,
            "button_width": 140,
            "response_area_height": 400,
            "enable_categories": True,
            "show_icons": True
        }
    }

def load_prompt_file(prompt_file_path):
    """プロンプトファイルを読み込む"""
    try:
        # 絶対パスかチェック
        if os.path.isabs(prompt_file_path):
            full_path = prompt_file_path
        else:
            # 相対パスは動的パスとして解決（バイナリ時はユーザーディレクトリを使用）
            full_path = get_dynamic_file_path(prompt_file_path)
        
        logger.debug("プロンプトファイル読み込み試行: %s", full_path)
        
        if os.path.exists(full_path):
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
                logger.info("プロンプトファイル読み込み成功: %s", full_path)
                return content
        else:
            logger.warning("プロンプトファイルが見つかりません: %s", full_path)
            return None
            
    except Exception as e:
        logger.error("プロンプトファイル読み込みエラー: %s", e)
        return None

def save_prompt_file(prompt_file_path, content):
    """プロンプトファイルを保存する"""
    try:
        full_path = get_dynamic_file_path(prompt_file_path)
        
        # ディレクトリが存在しない場合は作成
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
            
    except Exception as e:
        logger.error("プロンプトファイル保存エラー: %s", e)
        return False

def format_prompt_with_context(prompt_template, context_data):
    """プロンプトテンプレートをコンテキストデータで置換する（ARIM報告書対応・データポータルマスタ対応）"""
    try:
        # 基本的な置換処理
        formatted_prompt = prompt_template
        
        # ARIM報告書データを取得・統合
        enhanced_context = context_data.copy()
        # エイリアスと不足キーのフォールバックを事前適用
        try:
            if 'type' not in enhanced_context and 'dataset_type' in enhanced_context:
                enhanced_context['type'] = enhanced_context.get('dataset_type') or ''
            # description と existing_description の相互エイリアス
            if 'existing_description' not in enhanced_context and 'description' in enhanced_context:
                enhanced_context['existing_description'] = enhanced_context.get('description') or ''
            if 'description' not in enhanced_context and 'existing_description' in enhanced_context:
                enhanced_context['description'] = enhanced_context.get('existing_description') or ''
            if 'llm_model_name' not in enhanced_context:
                provider = enhanced_context.get('llm_provider') or ''
                model = enhanced_context.get('llm_model') or ''
                # provider/model が両方空の場合、AIManagerからデフォルト設定を取得
                if not provider and not model:
                    try:
                        from classes.ai.core.ai_manager import AIManager
                        ai_mgr = AIManager()
                        provider = ai_mgr.get_default_provider()
                        model = ai_mgr.get_default_model(provider)
                        logger.debug(f"llm_model_name未設定のため、AIManagerからデフォルト取得: {provider}:{model}")
                    except Exception as e:
                        logger.debug(f"AIManager設定取得失敗、デフォルト値を使用: {e}")
                        provider = 'gemini'
                        model = 'gemini-2.0-flash'
                enhanced_context['llm_model_name'] = f"{provider}:{model}".strip(':')
            # プレースホルダに空文字を入れて未置換を防ぐ
            for k in ['material_index_data', 'equipment_data', 'file_tree', 'text_from_structured_files']:
                if k not in enhanced_context:
                    enhanced_context[k] = ''
        except Exception as _alias_err:
            logger.debug("テンプレート置換のエイリアス適用で警告: %s", _alias_err)
        grant_number = context_data.get('grant_number')
        
        if grant_number and grant_number != "未設定":
            logger.debug("ARIM報告書データ取得開始: %s", grant_number)
            try:
                from classes.dataset.util.arim_report_fetcher import fetch_arim_report_data
                arim_data = fetch_arim_report_data(grant_number)
                
                if arim_data:
                    enhanced_context.update(arim_data)
                    logger.info("ARIM報告書データを統合: %s項目", len(arim_data))
                    
                    # デバッグ用：取得したキーを表示
                    for key in arim_data.keys():
                        logger.debug("ARIM データキー: %s", key)
                else:
                    logger.info("ARIM報告書が見つかりませんでした: %s", grant_number)
            except Exception as e:
                logger.warning("ARIM報告書取得でエラー: %s", e)
                # エラーがあってもベースのコンテキストで続行
        
        # データポータルマスタデータを取得・統合
        try:
            master_data = load_dataportal_master_data()
            if master_data:
                enhanced_context.update(master_data)
                logger.debug("データポータルマスタデータを統合: %s項目", len(master_data))
        except Exception as e:
            logger.warning("データポータルマスタデータ取得でエラー: %s", e)

        # 静的マテリアルインデックス（MI.json）を取得・統合
        try:
            static_mi = load_static_material_index()
            if static_mi:
                enhanced_context.update(static_mi)
                logger.debug("静的マテリアルインデックスを統合")
        except Exception as e:
            logger.warning("静的マテリアルインデックス取得でエラー: %s", e)
        
        # コンテキストデータのキーと値で置換
        for key, value in enhanced_context.items():
            placeholder = f"{{{key}}}"
            if placeholder in formatted_prompt:
                # 値がNoneまたは空の場合はデフォルト値を使用
                replacement_value = str(value) if value is not None else "未設定"
                formatted_prompt = formatted_prompt.replace(placeholder, replacement_value)
        
        return formatted_prompt
        
    except Exception as e:
        logger.error("プロンプト置換エラー: %s", e)
        return prompt_template


def load_dataportal_master_data():
    """データポータルマスタデータを読み込む
    
    Returns:
        dict: プレースホルダ用のマスタデータ辞書
            - dataportal_material_index: マテリアルインデックスマスタ（JSON文字列）
            - dataportal_tag: タグマスタ（JSON文字列）
            - dataportal_equipment: 装置分類マスタ（JSON文字列）
    """
    result = {}
    
    # マスタデータの定義（ファイル名パターン）
    master_types = [
        ('dataportal_material_index', 'material_index'),
        ('dataportal_tag', 'tag'),
        ('dataportal_equipment', 'equipment')
    ]
    
    for placeholder_key, file_prefix in master_types:
        try:
            # production優先、なければtestを使用
            production_path = get_dynamic_file_path(f'input/master_data/{file_prefix}_production.json')
            test_path = get_dynamic_file_path(f'input/master_data/{file_prefix}_test.json')
            
            target_path = None
            if os.path.exists(production_path):
                target_path = production_path
                logger.debug("マスタデータ読み込み（production）: %s", file_prefix)
            elif os.path.exists(test_path):
                target_path = test_path
                logger.debug("マスタデータ読み込み（test）: %s", file_prefix)
            else:
                logger.warning("マスタデータファイルが見つかりません: %s", file_prefix)
                result[placeholder_key] = "マスタデータなし"
                continue
            
            # JSONファイル読み込み
            with open(target_path, 'r', encoding='utf-8') as f:
                master_json = json.load(f)
            
            # JSON文字列として格納（整形して見やすく）
            result[placeholder_key] = json.dumps(master_json, ensure_ascii=False, indent=2)
            logger.info("マスタデータ読み込み成功: %s (件数: %s)", file_prefix, master_json.get('count', 'N/A'))
            
        except Exception as e:
            logger.error("マスタデータ読み込みエラー (%s): %s", file_prefix, e)
            result[placeholder_key] = f"マスタデータ読み込みエラー: {str(e)}"
    
    return result


def load_static_material_index():
    """静的マテリアルインデックス(MI.json)を読み込み、プレースホルダ提供

    Returns:
        dict: { 'static_material_index': '<JSON文字列>' }
    """
    try:
        mi_path = get_dynamic_file_path('input/ai/MI.json')
        if not os.path.exists(mi_path):
            logger.info("MI.jsonが見つかりません: %s", mi_path)
            # テストの安定性のため、空配列のJSONを返す
            return {'static_material_index': '[]'}

        with open(mi_path, 'r', encoding='utf-8') as f:
            mi_json = json.load(f)

        mi_str = json.dumps(mi_json, ensure_ascii=False, indent=2)
        logger.info("MI.json読み込み成功（カテゴリ数推定）")
        return {'static_material_index': mi_str}

    except Exception as e:
        logger.error("MI.json読み込みエラー: %s", e)
        # エラー時も空配列のJSONを返す
        return {'static_material_index': '[]'}