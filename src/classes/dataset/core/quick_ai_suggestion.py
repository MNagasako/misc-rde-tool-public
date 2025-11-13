"""
クイック版AI提案機能
ダイアログを表示せずに直接説明文を生成・返すモジュール
"""

import json
from typing import Dict, Any, Optional
from classes.ai.core.ai_manager import AIManager
from classes.ai.extensions import AIExtensionRegistry, DatasetDescriptionExtension
from classes.dataset.util.dataset_context_collector import get_dataset_context_collector

import logging

# ロガー設定
logger = logging.getLogger(__name__)


def generate_quick_suggestion(context_data: Dict[str, Any]) -> Optional[str]:
    """
    クイック版AI提案生成
    
    Args:
        context_data: コンテキストデータ辞書
        
    Returns:
        生成された説明文（失敗時はNone）
    """
    try:
        logger.debug("クイックAI提案生成開始 - 入力コンテキスト: %s", context_data)
        
        # AI設定を取得してプロバイダー・モデル情報を追加
        from classes.config.ui.ai_settings_widget import get_ai_config
        ai_config = get_ai_config()
        provider = ai_config.get('default_provider', 'gemini') if ai_config else 'gemini'
        model = ai_config.get('providers', {}).get(provider, {}).get('default_model', 'gemini-2.0-flash') if ai_config else 'gemini-2.0-flash'
        
        logger.debug("使用予定AI: provider=%s, model=%s", provider, model)
        
        # データセットコンテキストコレクターを使用して完全なコンテキストを収集
        context_collector = get_dataset_context_collector()
        
        # データセットIDを取得（context_dataから）
        dataset_id = context_data.get('dataset_id')
        logger.debug("データセットID: %s", dataset_id)
        
        # context_dataからdataset_idを一時的に除外してから渡す
        context_data_without_id = {k: v for k, v in context_data.items() if k != 'dataset_id'}
        
        # collect_full_contextにdataset_idを明示的に渡す
        full_context = context_collector.collect_full_context(
            dataset_id=dataset_id,
            **context_data_without_id
        )
        
        logger.debug("コンテキストコレクター処理後: %s", list(full_context.keys()))
        
        # AI拡張機能を取得・初期化
        ai_extension = AIExtensionRegistry.get("dataset_description")
        if not ai_extension:
            ai_extension = DatasetDescriptionExtension()
        
        # AI拡張機能からコンテキストデータを収集（既に統合されたfull_contextを使用）
        context = ai_extension.collect_context_data(**full_context)
        
        logger.debug("AI拡張機能処理後: %s", list(context.keys()))
        
        # プロバイダーとモデル情報をコンテキストに追加
        context['llm_provider'] = provider
        context['llm_model'] = model
        context['llm_model_name'] = f"{provider}:{model}"  # プロンプトテンプレート用
        
        # 外部テンプレートファイルを最新の状態で読み込み
        logger.debug("外部テンプレートファイルを再読み込み中...")
        reload_success = ai_extension.reload_external_templates()
        if reload_success:
            logger.debug("外部テンプレート再読み込み成功")
        else:
            logger.warning("外部テンプレート再読み込み失敗、既存テンプレートを使用")
        
        # クイック版テンプレートを取得
        template = ai_extension.get_template("quick")
        if not template:
            logger.warning("クイック版テンプレートが取得できませんでした、基本テンプレートにフォールバック")
            template = ai_extension.get_template("basic")
            
        if not template:
            logger.error("利用可能なテンプレートがありません")
            return None
        
        # プロンプトをレンダリング（contextを使用）
        prompt = template.render(context)
        
        logger.debug("生成されたプロンプト長: %s 文字", len(prompt))
        logger.debug("ARIM関連情報含有: %s", 'ARIM課題関連情報' in prompt)
        
        # AIリクエストを実行
        ai_manager = AIManager()
        
        logger.info("AIリクエスト開始（クイック版）")
        result = ai_manager.send_prompt(prompt, provider, model)
        
        if result.get('success', False):
            response_text = result.get('response') or result.get('content', '')
            logger.info("AIリクエスト成功: %s文字の応答", len(response_text))
            
            # クイック版は1つの説明文のみを期待
            # 不要な形式マーカーを削除してクリーンアップ
            cleaned_response = _clean_quick_response(response_text)
            
            return cleaned_response
        else:
            error_msg = result.get('error', '不明なエラー')
            logger.error("AIリクエスト失敗: %s", error_msg)
            return None
            
    except Exception as e:
        logger.error("クイック版AI提案生成エラー: %s", e)
        import traceback
        traceback.print_exc()
        return None


def _clean_quick_response(response_text: str) -> str:
    """
    クイック版のAI応答をクリーンアップ
    
    Args:
        response_text: AIからの生応答
        
    Returns:
        クリーンアップされた説明文
    """
    if not response_text:
        return ""
    
    # 改行を削除
    cleaned = response_text.strip()
    
    # 不要な形式マーカーを削除（[簡潔版]、[学術版]など）
    lines = cleaned.split('\n')
    
    # 最初の有効な行を取得（形式マーカーでない行）
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 形式マーカーのパターンをチェック
        if line.startswith('[') and ']' in line:
            # [簡潔版] のような形式マーカーの場合は、その後の内容を取得
            marker_end = line.find(']')
            if marker_end != -1 and marker_end < len(line) - 1:
                content = line[marker_end + 1:].strip()
                if content:
                    return content
            continue
        
        # 通常の文章の場合はそのまま返す
        return line
    
    # フォールバック: 全文を返す
    return cleaned


def test_quick_suggestion():
    """クイック版AI提案機能のテスト"""
    test_context = {
        'name': 'テストデータセット',
        'type': 'mixed',
        'grant_number': 'JPMXP1234TEST01',
        'description': '',
        'contact': 'test@example.com'
    }
    
    logger.debug("クイック版AI提案機能テスト開始")
    result = generate_quick_suggestion(test_context)
    
    if result:
        logger.debug("成功: %s文字の説明文を生成", len(result))
        logger.debug("生成内容: %s", result)
    else:
        logger.debug("失敗: 説明文を生成できませんでした")


if __name__ == "__main__":
    test_quick_suggestion()