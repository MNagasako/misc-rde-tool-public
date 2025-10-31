"""
AI拡張設定管理モジュール
AI拡張機能のボタン設定とプロンプトファイルの管理を行う
"""

import os
import json
from config.common import get_base_dir

def load_ai_extension_config():
    """AI拡張設定ファイルを読み込む"""
    try:
        config_path = os.path.join(get_base_dir(), "input", "ai", "ai_ext_conf.json")
        
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                print(f"[INFO] AI拡張設定ファイルを読み込みました: {config_path}")
                return config
        else:
            print(f"[INFO] AI拡張設定ファイルが見つかりません。デフォルト設定を使用します: {config_path}")
            return get_default_ai_extension_config()
            
    except Exception as e:
        print(f"[ERROR] AI拡張設定読み込みエラー: {e}")
        print("[INFO] デフォルト設定を使用します")
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
            # 相対パスの場合はベースディレクトリから構築
            full_path = os.path.join(get_base_dir(), prompt_file_path)
        
        print(f"[DEBUG] プロンプトファイル読み込み試行: {full_path}")
        
        if os.path.exists(full_path):
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
                print(f"[INFO] プロンプトファイル読み込み成功: {full_path}")
                return content
        else:
            print(f"[WARNING] プロンプトファイルが見つかりません: {full_path}")
            return None
            
    except Exception as e:
        print(f"[ERROR] プロンプトファイル読み込みエラー: {e}")
        return None

def save_prompt_file(prompt_file_path, content):
    """プロンプトファイルを保存する"""
    try:
        full_path = os.path.join(get_base_dir(), prompt_file_path)
        
        # ディレクトリが存在しない場合は作成
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
            
    except Exception as e:
        print(f"[ERROR] プロンプトファイル保存エラー: {e}")
        return False

def format_prompt_with_context(prompt_template, context_data):
    """プロンプトテンプレートをコンテキストデータで置換する（ARIM報告書対応）"""
    try:
        # 基本的な置換処理
        formatted_prompt = prompt_template
        
        # ARIM報告書データを取得・統合
        enhanced_context = context_data.copy()
        grant_number = context_data.get('grant_number')
        
        if grant_number and grant_number != "未設定":
            print(f"[DEBUG] ARIM報告書データ取得開始: {grant_number}")
            try:
                from classes.dataset.util.arim_report_fetcher import fetch_arim_report_data
                arim_data = fetch_arim_report_data(grant_number)
                
                if arim_data:
                    enhanced_context.update(arim_data)
                    print(f"[INFO] ARIM報告書データを統合: {len(arim_data)}項目")
                    
                    # デバッグ用：取得したキーを表示
                    for key in arim_data.keys():
                        print(f"[DEBUG] ARIM データキー: {key}")
                else:
                    print(f"[INFO] ARIM報告書が見つかりませんでした: {grant_number}")
            except Exception as e:
                print(f"[WARNING] ARIM報告書取得でエラー: {e}")
                # エラーがあってもベースのコンテキストで続行
        
        # コンテキストデータのキーと値で置換
        for key, value in enhanced_context.items():
            placeholder = f"{{{key}}}"
            if placeholder in formatted_prompt:
                # 値がNoneまたは空の場合はデフォルト値を使用
                replacement_value = str(value) if value is not None else "未設定"
                formatted_prompt = formatted_prompt.replace(placeholder, replacement_value)
        
        return formatted_prompt
        
    except Exception as e:
        print(f"[ERROR] プロンプト置換エラー: {e}")
        return prompt_template