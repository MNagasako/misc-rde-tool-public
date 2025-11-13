"""
AI Manager - ARIM RDE Tool v1.13.0 AI機能テスト（パス管理修正版）
各種AI API（OpenAI、Gemini、ローカルLLM）との連携機能
プロキシ対応: net.httpラッパーを使用してプロキシ設定を透過的に適用
"""
import os
import json
import time
# === セッション管理ベースのプロキシ対応 ===
from net.session_manager import get_proxy_session
import requests as _requests_types  # 型ヒント・例外処理用
import logging
from typing import Dict, List, Any
from config.common import get_dynamic_file_path

logger = logging.getLogger("RDE_AI")

class AIManager:
    """AI機能の統合管理クラス"""
    
    def __init__(self):
        self.config_path = get_dynamic_file_path("input/ai_config.json")
        self.config = self._load_config()
        # セッション管理ベースの初期化
        self.session = get_proxy_session()
        
    def _load_config(self) -> Dict[str, Any]:
        """AI設定ファイルを読み込み"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                logger.warning(f"AI設定ファイルが見つかりません: {self.config_path}")
                return self._get_default_config()
        except Exception as e:
            logger.error(f"AI設定ファイルの読み込みに失敗: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """デフォルト設定を返す"""
        return {
            "ai_providers": {
                "openai": {"enabled": False, "api_key": "", "models": ["gpt-5-mini"]},
                "gemini": {"enabled": False, "api_key": "", "models": ["gemini-1.5-flash"]},
                "local_llm": {"enabled": False, "base_url": "http://localhost:11434/v1", "models": ["llama3.2:3b"]}
            },
            "default_provider": "gemini",
            "timeout": 30,
            "max_tokens": 1000,
            "temperature": 0.7
        }
    
    def get_available_providers(self) -> List[str]:
        """利用可能なAIプロバイダーのリストを取得"""
        providers = []
        for provider, config in self.config["ai_providers"].items():
            if config.get("enabled", False):
                providers.append(provider)
        return providers
    
    def get_models_for_provider(self, provider: str) -> List[str]:
        """指定されたプロバイダーのモデル一覧を取得"""
        if provider in self.config["ai_providers"]:
            return self.config["ai_providers"][provider].get("models", [])
        return []
    
    def get_default_provider(self) -> str:
        """デフォルトプロバイダーを取得"""
        return self.config.get("default_provider", "openai")
    
    def get_default_model(self, provider: str) -> str:
        """指定されたプロバイダーのデフォルトモデルを取得"""
        if provider in self.config["ai_providers"]:
            provider_config = self.config["ai_providers"][provider]
            default_model = provider_config.get("default_model", "")
            
            # default_modelが設定されていない場合は最初のモデルを返す
            if not default_model:
                models = provider_config.get("models", [])
                if models:
                    return models[0]
            
            return default_model
        return ""
    
    def send_prompt(self, prompt: str, provider: str, model: str) -> Dict[str, Any]:
        """プロンプトをAIに送信して応答を取得"""
        try:
            # プロンプト長の制限チェック（文字数ベース）
            max_prompt_length = 50000  # 約12,500トークン相当（4文字=1トークン想定）
            if len(prompt) > max_prompt_length:
                # プロンプトを切り詰める
                truncated_prompt = prompt[:max_prompt_length]
                truncated_prompt += "\n\n[注意: プロンプトが長すぎるため切り詰められました]"
                logger.debug("プロンプトが長すぎます。元の長さ: %s, 切り詰め後: %s", len(prompt), len(truncated_prompt))
                prompt = truncated_prompt
            
            if provider == "openai":
                return self._send_openai_request(prompt, model)
            elif provider == "gemini":
                return self._send_gemini_request(prompt, model)
            elif provider == "local_llm":
                return self._send_local_llm_request(prompt, model)
            else:
                return {"success": False, "error": f"未対応のプロバイダー: {provider}"}
        except Exception as e:
            logger.error(f"AI API呼び出しエラー ({provider}): {e}")
            return {"success": False, "error": str(e)}
    
    def _send_openai_request(self, prompt: str, model: str) -> Dict[str, Any]:
        """OpenAI APIにリクエストを送信"""
        import time
        
        config = self.config["ai_providers"]["openai"]
        api_key = config.get("api_key", "")
        
        if not api_key:
            return {"success": False, "error": "OpenAI APIキーが設定されていません"}
        
        url = f"{config.get('base_url', 'https://api.openai.com/v1')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # モデル名によってパラメータを切り替え
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        if model.startswith("gpt-5") or model.startswith("gpt-4.1"):
            # GPT-5系およびGPT-4.1系では max_completion_tokens を使用
            # GPT-5系はパラメータなしでデフォルト動作を使用
            if model.startswith("gpt-5"):
                pass  # パラメータを指定しない
            elif "nano" in model.lower():
                data["max_completion_tokens"] = 50
            else:
                data["max_completion_tokens"] = max(1000, self.config.get("max_tokens", 1000))
        else:
            # GPT-4以前では従来のパラメータを使用
            data["max_tokens"] = self.config.get("max_tokens", 1000)
            data["temperature"] = self.config.get("temperature", 0.7)
        
        start_time = time.time()
        response = self.session.post(
            url,
            headers=headers,
            json=data,
            timeout=self.config.get("timeout", 120)
        )
        response_time = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            logger.debug("OpenAI API レスポンス構造: %s", list(result.keys()))
            if "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]
                logger.debug("OpenAI API choice構造: %s", list(choice.keys()))
                
                message = choice.get("message", {})
                logger.debug("OpenAI API message構造: %s", list(message.keys()))
                
                content = message.get("content")
                
                # GPT-5系では、finish_reasonを確認
                finish_reason = choice.get("finish_reason")
                logger.debug("OpenAI API finish_reason: %s", finish_reason)
                
                if content is None or content == "":
                    # contentが空の場合の詳細ログ
                    logger.debug("OpenAI API content is None/empty")
                    logger.debug("OpenAI API full choice: %s", choice)
                    
                    # finish_reasonがlengthの場合、トークン制限に達している
                    if finish_reason == "length":
                        error_msg = f"応答がトークン制限により切り詰められました。プロンプトが長すぎるか、max_completion_tokensが小さすぎます。現在の設定: {data.get('max_completion_tokens', data.get('max_tokens', 'unknown'))}"
                        return {"success": False, "error": error_msg}
                    
                    # GPT-5系でcontentが空の場合、他の場所にデータがある可能性
                    if "delta" in choice:
                        logger.debug("OpenAI API delta found: %s", choice['delta'])
                        content = choice["delta"].get("content", "")
                    
                    if not content:
                        return {"success": False, "error": f"OpenAI APIから空の応答を受信しました。finish_reason: {finish_reason}"}
                
                logger.debug("OpenAI API 応答内容長: %s", len(content) if content else 0)
                logger.debug("OpenAI API 応答内容（最初の100文字）: %s", content[:100] if content else 'None')
                
                return {
                    "success": True, 
                    "response": content,
                    "content": content,  # 互換性のため追加
                    "usage": result.get("usage", {}),
                    "tokens_used": result.get("usage", {}).get("total_tokens", 0),  # 互換性のため追加
                    "model": model,
                    "response_time": response_time
                }
            else:
                logger.debug("OpenAI API choices が空またはなし: %s", result)
                return {
                    "success": False, 
                    "error": "OpenAI APIからの応答が空です",
                    "model": model,
                    "response_time": response_time
                }
        else:
            return {
                "success": False, 
                "error": f"API エラー: {response.status_code} - {response.text}",
                "model": model,
                "response_time": response_time
            }
    
    def _send_gemini_request(self, prompt: str, model: str) -> Dict[str, Any]:
        """Gemini APIにリクエストを送信"""        
        config = self.config["ai_providers"]["gemini"]
        api_key = config.get("api_key", "")
        
        if not api_key:
            return {"success": False, "error": "Gemini APIキーが設定されていません"}
        
        url = f"{config.get('base_url', 'https://generativelanguage.googleapis.com/v1beta')}/models/{model}:generateContent"
        headers = {
            "Content-Type": "application/json"
        }
        
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": self.config.get("max_tokens", 1000),
                "temperature": self.config.get("temperature", 0.7)
            }
        }
        
        start_time = time.time()
        response = self.session.post(
            f"{url}?key={api_key}",
            headers=headers,
            json=data,
            timeout=self.config.get("timeout", 120)
        )
        response_time = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            if "candidates" in result and len(result["candidates"]) > 0:
                content = result["candidates"][0]["content"]["parts"][0]["text"]
                usage_metadata = result.get("usageMetadata", {})
                
                return {
                    "success": True, 
                    "response": content,
                    "content": content,  # 互換性のため追加
                    "usage": usage_metadata,
                    "tokens_used": usage_metadata.get("totalTokenCount", 0),  # 互換性のため追加
                    "model": model,
                    "response_time": response_time
                }
            else:
                return {
                    "success": False, 
                    "error": "Geminiからの応答が空です",
                    "model": model,
                    "response_time": response_time
                }
        else:
            return {
                "success": False, 
                "error": f"API エラー: {response.status_code} - {response.text}",
                "model": model,
                "response_time": response_time
            }
    
    def _send_local_llm_request(self, prompt: str, model: str) -> Dict[str, Any]:
        """ローカルLLM（Ollama等）にリクエストを送信"""        
        config = self.config["ai_providers"]["local_llm"]
        base_url = config.get("base_url", "http://localhost:11434/api/generate")
        
        # Ollama独自APIの場合は /api/generate エンドポイントを直接使用
        if "/api/generate" in base_url:
            url = base_url
        else:
            # OpenAI互換APIの場合
            url = f"{base_url}/chat/completions"
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # Ollama独自API形式のリクエスト
        if "/api/generate" in base_url:
            data = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }
        else:
            # OpenAI互換API形式のリクエスト
            data = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": self.config.get("max_tokens", 1000),
                "temperature": self.config.get("temperature", 0.7),
                "stream": False
            }
        
        start_time = time.time()
        try:
            # ローカルLLMの場合はタイムアウトを5分（300秒）に設定
            local_timeout = 300 if "/api/generate" in base_url else self.config.get("timeout", 120)
            
            response = self.session.post(
                url,
                headers=headers,
                json=data,
                timeout=local_timeout
            )
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                
                # Ollama独自API形式のレスポンス処理
                if "/api/generate" in base_url:
                    content = result.get("response", "")
                    usage_info = {
                        "prompt_eval_count": result.get("prompt_eval_count", 0),
                        "eval_count": result.get("eval_count", 0),
                        "total_duration": result.get("total_duration", 0)
                    }
                    tokens_used = usage_info.get("prompt_eval_count", 0) + usage_info.get("eval_count", 0)
                else:
                    # OpenAI互換API形式のレスポンス処理
                    content = result["choices"][0]["message"]["content"]
                    usage_info = result.get("usage", {})
                    tokens_used = usage_info.get("total_tokens", 0)
                
                return {
                    "success": True, 
                    "response": content,
                    "content": content,  # 互換性のため追加
                    "usage": usage_info,
                    "tokens_used": tokens_used,  # 互換性のため追加
                    "model": model,
                    "response_time": response_time
                }
            else:
                return {
                    "success": False, 
                    "error": f"ローカルLLM エラー: {response.status_code} - {response.text}",
                    "model": model,
                    "response_time": response_time
                }
        except _requests_types.exceptions.ConnectionError:
            response_time = time.time() - start_time
            return {
                "success": False, 
                "error": "ローカルLLMサーバーに接続できません。Ollama等が起動しているか確認してください。",
                "model": model,
                "response_time": response_time
            }
    
    def test_connection(self, provider: str) -> Dict[str, Any]:
        """指定されたプロバイダーとの接続をテスト"""
        test_prompt = "Hello, this is a connection test."
        models = self.get_models_for_provider(provider)
        
        if not models:
            return {"success": False, "error": f"{provider} のモデルが設定されていません"}
        
        default_model = self.get_default_model(provider) or models[0]
        return self.send_prompt(test_prompt, provider, default_model)
