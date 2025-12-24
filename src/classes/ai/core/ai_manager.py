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
import copy
from config.common import get_dynamic_file_path

from classes.ai.util.generation_params import (
    build_gemini_generate_content_body,
    build_openai_chat_completions_payload,
    normalize_ai_config_inplace,
    selected_generation_params,
)

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
                    config = json.load(f)
                    return normalize_ai_config_inplace(config)
            else:
                logger.warning(f"AI設定ファイルが見つかりません: {self.config_path}")
                return self._get_default_config()
        except Exception as e:
            logger.error(f"AI設定ファイルの読み込みに失敗: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """デフォルト設定を返す"""
        config = {
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
        return normalize_ai_config_inplace(config)
    
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
                result = self._send_openai_request(prompt, model)
            elif provider == "gemini":
                result = self._send_gemini_request(prompt, model)
            elif provider == "local_llm":
                result = self._send_local_llm_request(prompt, model)
            else:
                result = {"success": False, "error": f"未対応のプロバイダー: {provider}"}

            # 呼び出し側で参照できるように provider/model を常に付与
            if isinstance(result, dict):
                result.setdefault("provider", provider)
                result.setdefault("model", model)

                req_params = result.get("request_params")
                if isinstance(req_params, dict):
                    req_params.setdefault("provider", provider)
                    req_params.setdefault("model", model)

                resp_params = result.get("response_params")
                if isinstance(resp_params, dict):
                    resp_params.setdefault("provider", provider)
                    resp_params.setdefault("model", model)

            return result
        except Exception as e:
            logger.error(f"AI API呼び出しエラー ({provider}): {e}")
            return {"success": False, "error": str(e), "provider": provider, "model": model}
    
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
        
        data = build_openai_chat_completions_payload(prompt=prompt, model=model, config=self.config)

        # 表示/デバッグ用: 本文（messages）以外のリクエストパラメータ
        request_params: Dict[str, Any] = {k: v for k, v in data.items() if k != "messages"}
        request_params["messages_count"] = len(data.get("messages", []) or [])

        # 互換性維持: GPT-4.1-nano は明示的に小さい上限が安全（未指定時のみ）
        if model.startswith("gpt-4.1") and "nano" in model.lower() and "max_completion_tokens" not in data:
            data["max_completion_tokens"] = 50
        
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
                    "response_time": response_time,
                    "request_params": request_params,
                    "response_params": {
                        "status_code": response.status_code,
                        "finish_reason": finish_reason,
                        "usage": result.get("usage", {}),
                        "response_time": response_time,
                        "model": model,
                    },
                }
            else:
                logger.debug("OpenAI API choices が空またはなし: %s", result)
                return {
                    "success": False, 
                    "error": "OpenAI APIからの応答が空です",
                    "model": model,
                    "response_time": response_time,
                    "request_params": request_params,
                    "response_params": {
                        "status_code": response.status_code,
                        "usage": result.get("usage", {}),
                        "response_time": response_time,
                        "model": model,
                    },
                }
        else:
            return {
                "success": False, 
                "error": f"API エラー: {response.status_code} - {response.text}",
                "model": model,
                "response_time": response_time,
                "request_params": request_params,
                "response_params": {
                    "status_code": response.status_code,
                    "response_time": response_time,
                    "model": model,
                },
            }
    
    def _send_gemini_request(self, prompt: str, model: str, retry_count: int = 0) -> Dict[str, Any]:
        """Gemini APIにリクエストを送信（リトライ対応）
        
        Args:
            prompt: 送信するプロンプト
            model: 使用するモデル名
            retry_count: 現在のリトライ回数（内部使用）
        
        Returns:
            APIレスポンスの辞書
        """        
        config = self.config["ai_providers"]["gemini"]
        api_key = config.get("api_key", "")
        max_retries = 2  # 最大リトライ回数
        
        if not api_key:
            return {"success": False, "error": "Gemini APIキーが設定されていません"}
        
        url = f"{config.get('base_url', 'https://generativelanguage.googleapis.com/v1beta')}/models/{model}:generateContent"
        headers = {
            "Content-Type": "application/json"
        }

        def _bump_max_output_tokens(body: Dict[str, Any]) -> Dict[str, Any]:
            bumped = copy.deepcopy(body)
            gen_cfg = bumped.setdefault("generationConfig", {})
            current = gen_cfg.get("maxOutputTokens")
            try:
                current_int = int(current)
            except Exception:
                current_int = 0

            # Geminiで MAX_TOKENS なのに parts が空の場合、出力上限が小さすぎる可能性があるため
            # 最低値を確保しつつ増量して再試行する（安全側の上限も設ける）
            min_tokens = 256
            cap_tokens = 8192

            if current_int <= 0:
                new_value = min_tokens
            else:
                new_value = max(min_tokens, current_int + 64, current_int * 2)
                new_value = min(new_value, cap_tokens)

            gen_cfg["maxOutputTokens"] = new_value
            return bumped

        # 初期ボディ
        data = build_gemini_generate_content_body(prompt=prompt, model=model, config=self.config, drop_experimental=False)
        dropped_experimental = False
        adjustments: List[Dict[str, Any]] = []

        last_response_time = 0.0
        last_status_code = 0
        last_result: Dict[str, Any] = {}
        last_request_params: Dict[str, Any] = {}

        # retry_count は「追加試行回数」を返すため、成功時は attempt_index をセットする
        for attempt_index in range(max_retries + 1):
            # 表示/デバッグ用: 本文（contents）以外のリクエストパラメータ
            request_params = {k: v for k, v in data.items() if k != "contents"}
            request_params["contents_count"] = len(data.get("contents", []) or [])
            if adjustments:
                request_params["auto_adjustments"] = adjustments

            last_request_params = request_params

            start_time = time.time()
            response = self.session.post(
                f"{url}?key={api_key}",
                headers=headers,
                json=data,
                timeout=self.config.get("timeout", 120)
            )
            last_response_time = time.time() - start_time
            last_status_code = response.status_code

            # Gemini: 一部パラメータ（penalty系など）が未対応の場合があるため、400時はexperimentalを落として1回だけ再試行
            if response.status_code == 400 and not dropped_experimental:
                try:
                    gen_cfg = data.get("generationConfig") or {}
                    has_experimental = any(k in gen_cfg for k in ("presencePenalty", "frequencyPenalty"))
                except Exception:
                    has_experimental = False

                if has_experimental:
                    data = build_gemini_generate_content_body(
                        prompt=prompt,
                        model=model,
                        config=self.config,
                        drop_experimental=True,
                    )
                    dropped_experimental = True
                    adjustments.append({"kind": "drop_experimental_generation_config", "keys": ["presencePenalty", "frequencyPenalty"]})
                    # 同じ attempt_index 内で即再試行（これ自体はカウントしない）
                    retry_resp = self.session.post(
                        f"{url}?key={api_key}",
                        headers=headers,
                        json=data,
                        timeout=self.config.get("timeout", 120)
                    )
                    response = retry_resp
                    last_status_code = response.status_code
                    # response_time は最後に計測したものを維持（ここでは厳密さより可観測性を優先）

            if response.status_code != 200:
                return {
                    "success": False,
                    "error": f"API エラー: {response.status_code} - {response.text}",
                    "model": model,
                    "response_time": last_response_time,
                    "request_params": last_request_params,
                    "response_params": {
                        "status_code": response.status_code,
                        "response_time": last_response_time,
                        "model": model,
                        "retry_count": attempt_index,
                    },
                }

            try:
                result = response.json()
            except Exception as e:
                return {
                    "success": False,
                    "error": f"GeminiレスポンスJSONの解析に失敗しました: {type(e).__name__}",
                    "model": model,
                    "response_time": last_response_time,
                    "request_params": last_request_params,
                    "response_params": {
                        "status_code": response.status_code,
                        "response_time": last_response_time,
                        "model": model,
                        "retry_count": attempt_index,
                    },
                }

            last_result = result

            candidates = result.get("candidates") or []
            if not candidates:
                return {
                    "success": False,
                    "error": "Geminiからの応答が空です",
                    "model": model,
                    "response_time": last_response_time,
                    "request_params": last_request_params,
                    "response_params": {
                        "status_code": response.status_code,
                        "response_time": last_response_time,
                        "model": model,
                        "retry_count": attempt_index,
                        "model_version": result.get("modelVersion"),
                        "response_id": result.get("responseId"),
                    },
                }

            candidate = candidates[0] or {}
            finish_reason = candidate.get("finishReason")
            content_obj = candidate.get("content") or {}
            parts = content_obj.get("parts") or []

            usage_metadata = result.get("usageMetadata", {})

            if not parts:
                logger.warning(
                    f"Gemini API レスポンスにpartsが存在しません (試行 {attempt_index + 1}/{max_retries + 1}): {result}"
                )

                # MAX_TOKENS で parts が空の場合、maxOutputTokens を増量して再試行
                if finish_reason == "MAX_TOKENS" and attempt_index < max_retries:
                    before = ((data.get("generationConfig") or {}).get("maxOutputTokens"))
                    data = _bump_max_output_tokens(data)
                    after = ((data.get("generationConfig") or {}).get("maxOutputTokens"))
                    adjustments.append({"kind": "bump_maxOutputTokens", "before": before, "after": after})
                    logger.info(
                        f"Gemini MAX_TOKENS + parts無しのため maxOutputTokens を増量してリトライします (before={before}, after={after})"
                    )
                    time.sleep(1)
                    continue

                # 従来通り、リトライ回数に余裕があればそのままリトライ
                if attempt_index < max_retries:
                    logger.info(f"Gemini APIリクエストをリトライします (試行 {attempt_index + 2}/{max_retries + 1})")
                    time.sleep(1)
                    continue

                logger.error(f"Gemini API リトライ回数上限に達しました。最終レスポンス: {result}")
                return {
                    "success": False,
                    "error": f"Geminiからの応答にpartsが存在しません（{max_retries + 1}回試行後も失敗）",
                    "model": model,
                    "response_time": last_response_time,
                    "raw_response": result,
                    "request_params": last_request_params,
                    "response_params": {
                        "status_code": response.status_code,
                        "usage": usage_metadata,
                        "response_time": last_response_time,
                        "model": model,
                        "retry_count": attempt_index,
                        "finish_reason": finish_reason,
                        "model_version": result.get("modelVersion"),
                        "response_id": result.get("responseId"),
                        "auto_adjustments": adjustments,
                    },
                }

            # parts があるケース
            try:
                texts = [p.get("text", "") for p in parts if isinstance(p, dict)]
            except Exception:
                texts = []

            content = "".join(texts)

            # partsがあっても本文が空の場合がある（特に MAX_TOKENS で出力枠が不足するケース）
            if not (content or "").strip():
                logger.warning(
                    f"Gemini API レスポンスの本文が空です (finishReason={finish_reason}, 試行 {attempt_index + 1}/{max_retries + 1}): {result}"
                )

                if finish_reason == "MAX_TOKENS" and attempt_index < max_retries:
                    before = ((data.get("generationConfig") or {}).get("maxOutputTokens"))
                    data = _bump_max_output_tokens(data)
                    after = ((data.get("generationConfig") or {}).get("maxOutputTokens"))
                    adjustments.append({"kind": "bump_maxOutputTokens", "before": before, "after": after})
                    logger.info(
                        f"Gemini MAX_TOKENS + 本文空のため maxOutputTokens を増量してリトライします (before={before}, after={after})"
                    )
                    time.sleep(1)
                    continue

                # MAX_TOKENS 以外で本文が空の場合は、後方互換性のため「空文字で成功」扱いにする。
                # （呼び出し側が本文の有無を判定できるよう response_params に warning を付与）
                return {
                    "success": True,
                    "response": "",
                    "content": "",  # 互換性のため追加
                    "usage": usage_metadata,
                    "tokens_used": usage_metadata.get("totalTokenCount", 0),
                    "model": model,
                    "response_time": last_response_time,
                    "retry_count": attempt_index,
                    "request_params": last_request_params,
                    "response_params": {
                        "status_code": response.status_code,
                        "usage": usage_metadata,
                        "response_time": last_response_time,
                        "model": model,
                        "retry_count": attempt_index,
                        "finish_reason": finish_reason,
                        "model_version": result.get("modelVersion"),
                        "response_id": result.get("responseId"),
                        "auto_adjustments": adjustments,
                        "warning": "empty_content",
                    },
                }
            if attempt_index > 0:
                logger.info(f"Gemini APIリクエストが {attempt_index + 1}回目の試行で成功しました")

            return {
                "success": True,
                "response": content,
                "content": content,  # 互換性のため追加
                "usage": usage_metadata,
                "tokens_used": usage_metadata.get("totalTokenCount", 0),  # 互換性のため追加
                "model": model,
                "response_time": last_response_time,
                "retry_count": attempt_index,
                "request_params": last_request_params,
                "response_params": {
                    "status_code": response.status_code,
                    "usage": usage_metadata,
                    "response_time": last_response_time,
                    "model": model,
                    "retry_count": attempt_index,
                    "finish_reason": finish_reason,
                    "model_version": result.get("modelVersion"),
                    "response_id": result.get("responseId"),
                    "auto_adjustments": adjustments,
                },
            }

        # 通常ここには到達しないが、念のため
        return {
            "success": False,
            "error": f"Geminiリクエストが失敗しました（{max_retries + 1}回試行）",
            "model": model,
            "response_time": last_response_time,
            "raw_response": last_result,
            "request_params": last_request_params,
            "response_params": {
                "status_code": last_status_code,
                "response_time": last_response_time,
                "model": model,
                "retry_count": max_retries,
            },
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

            # 生成パラメータ（カスタム使用のみ）をOllama optionsへ反映
            selected = selected_generation_params(self.config)
            options: Dict[str, Any] = {}
            if 'temperature' in selected:
                options['temperature'] = selected['temperature']
            if 'top_p' in selected:
                options['top_p'] = selected['top_p']
            if 'top_k' in selected:
                options['top_k'] = selected['top_k']
            if 'max_output_tokens' in selected:
                # Ollama: num_predict が生成トークン上限に相当
                options['num_predict'] = selected['max_output_tokens']
            if 'stop_sequences' in selected:
                options['stop'] = selected['stop_sequences']

            if options:
                data['options'] = options
        else:
            # OpenAI互換API形式のリクエスト
            data = build_openai_chat_completions_payload(prompt=prompt, model=model, config=self.config)
            data["stream"] = False

        # 表示/デバッグ用: 本文以外のリクエストパラメータ
        if "/api/generate" in base_url:
            request_params: Dict[str, Any] = {k: v for k, v in data.items() if k != "prompt"}
        else:
            request_params = {k: v for k, v in data.items() if k != "messages"}
            request_params["messages_count"] = len(data.get("messages", []) or [])
        
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
                
                try:
                    # Ollama独自API形式のレスポンス処理
                    if "/api/generate" in base_url:
                        content = result.get("response", "")
                        if not content:
                            logger.warning(f"Local LLM APIから空の応答を受信: {result}")
                            return {
                                "success": False, 
                                "error": "Local LLM APIから空の応答を受信しました",
                                "raw_response": result,
                                "model": model,
                                "response_time": response_time
                            }
                        
                        usage_info = {
                            "prompt_eval_count": result.get("prompt_eval_count", 0),
                            "eval_count": result.get("eval_count", 0),
                            "total_duration": result.get("total_duration", 0)
                        }
                        tokens_used = usage_info.get("prompt_eval_count", 0) + usage_info.get("eval_count", 0)
                    else:
                        # OpenAI互換API形式のレスポンス処理（安全なアクセス）
                        choices = result.get("choices", [])
                        if not choices:
                            logger.error(f"Local LLM APIレスポンスにchoicesが存在しません: {result}")
                            return {
                                "success": False,
                                "error": "Local LLM APIレスポンスにchoicesが存在しません",
                                "raw_response": result,
                                "model": model,
                                "response_time": response_time
                            }
                        
                        message = choices[0].get("message", {})
                        content = message.get("content", "")
                        if not content:
                            logger.warning(f"Local LLM APIから空のcontentを受信: {result}")
                            return {
                                "success": False,
                                "error": "Local LLM APIから空のcontentを受信しました",
                                "raw_response": result,
                                "model": model,
                                "response_time": response_time
                            }
                        
                        usage_info = result.get("usage", {})
                        tokens_used = usage_info.get("total_tokens", 0)
                    
                    return {
                        "success": True, 
                        "response": content,
                        "content": content,  # 互換性のため追加
                        "usage": usage_info,
                        "tokens_used": tokens_used,  # 互換性のため追加
                        "model": model,
                        "response_time": response_time,
                        "request_params": request_params,
                        "response_params": {
                            "status_code": response.status_code,
                            "usage": usage_info,
                            "tokens_used": tokens_used,
                            "response_time": response_time,
                            "model": model,
                        },
                    }
                except (KeyError, IndexError, TypeError) as e:
                    logger.error(f"Local LLM API レスポンス解析エラー: {e}")
                    logger.error(f"レスポンス全体: {result}")
                    return {
                        "success": False, 
                        "error": f"Local LLM API レスポンス解析エラー: {str(e)}",
                        "raw_response": result,
                        "model": model,
                        "response_time": response_time,
                        "request_params": request_params,
                        "response_params": {
                            "status_code": response.status_code,
                            "response_time": response_time,
                            "model": model,
                        },
                    }
            else:
                return {
                    "success": False, 
                    "error": f"ローカルLLM エラー: {response.status_code} - {response.text}",
                    "model": model,
                    "response_time": response_time,
                    "request_params": request_params,
                    "response_params": {
                        "status_code": response.status_code,
                        "response_time": response_time,
                        "model": model,
                    },
                }
        except _requests_types.exceptions.ConnectionError:
            response_time = time.time() - start_time
            return {
                "success": False, 
                "error": "ローカルLLMサーバーに接続できません。Ollama等が起動しているか確認してください。",
                "model": model,
                "response_time": response_time,
                "request_params": request_params,
                "response_params": {
                    "response_time": response_time,
                    "model": model,
                },
            }
    
    def test_connection(self, provider: str) -> Dict[str, Any]:
        """指定されたプロバイダーとの接続をテスト"""
        test_prompt = "Hello, this is a connection test."
        models = self.get_models_for_provider(provider)
        
        if not models:
            return {"success": False, "error": f"{provider} のモデルが設定されていません"}
        
        default_model = self.get_default_model(provider) or models[0]
        return self.send_prompt(test_prompt, provider, default_model)
