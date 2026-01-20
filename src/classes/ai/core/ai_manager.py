"""
AI Manager - ARIM RDE Tool AI機能テスト（パス管理修正版）
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
                "gemini": {
                    "enabled": False,
                    "api_key": "",
                    "models": ["gemini-1.5-flash"],
                    # 認証方式: 'api_key' または 'vertex_sa'
                    "auth_mode": "api_key",
                    # Vertex AI（サービスアカウントJSON）利用時
                    # - vertex_service_account_json: input配下などの相対パスを推奨
                    # - vertex_project_id: 空の場合はJSON内 project_id を使用
                    # - vertex_location: 例) asia-northeast1, us-central1
                    "vertex_service_account_json": "",
                    "vertex_project_id": "",
                    "vertex_location": "asia-northeast1",
                },
                "local_llm": {"enabled": False, "base_url": "http://localhost:11434/v1", "models": ["llama3.2:3b"]}
            },
            "default_provider": "gemini",
            "timeout": 30,
            "max_tokens": 1000,
            "temperature": 0.7,
            # AI APIリクエストの最大試行回数（失敗時に再試行）
            # 既定: 3回（1回目 + リトライ2回） / 最大: 5回
            "request_max_attempts": 3,
        }
        return normalize_ai_config_inplace(config)

    def _get_request_max_attempts(self) -> int:
        """AI APIリクエストの最大試行回数（既定3、最大5）"""
        try:
            raw = self.config.get("request_max_attempts", 3)
            value = int(raw)
        except Exception:
            value = 3
        if value < 1:
            value = 1
        if value > 5:
            value = 5
        return value
    
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
            provider_config = self.config["ai_providers"][provider]

            # Geminiは認証方式（APIキー / Vertex SA）ごとにモデル一覧を分離できる
            if provider == 'gemini':
                try:
                    auth_mode = (provider_config.get('auth_mode') or 'api_key').strip().lower()
                except Exception:
                    auth_mode = 'api_key'

                models_by_auth = provider_config.get('models_by_auth')
                if isinstance(models_by_auth, dict):
                    models = models_by_auth.get(auth_mode)
                    if isinstance(models, list):
                        return models

            return provider_config.get("models", [])
        return []
    
    def get_default_provider(self) -> str:
        """デフォルトプロバイダーを取得"""
        return self.config.get("default_provider", "openai")
    
    def get_default_model(self, provider: str) -> str:
        """指定されたプロバイダーのデフォルトモデルを取得"""
        if provider in self.config["ai_providers"]:
            provider_config = self.config["ai_providers"][provider]

            # Geminiは認証方式（APIキー / Vertex SA）ごとにデフォルトモデルを分離できる
            if provider == 'gemini':
                try:
                    auth_mode = (provider_config.get('auth_mode') or 'api_key').strip().lower()
                except Exception:
                    auth_mode = 'api_key'

                default_by_auth = provider_config.get('default_model_by_auth')
                if isinstance(default_by_auth, dict):
                    v = default_by_auth.get(auth_mode)
                    if isinstance(v, str) and v.strip():
                        return v.strip()

            default_model = provider_config.get("default_model", "")
            
            # default_modelが設定されていない場合は最初のモデルを返す
            if not default_model:
                models = self.get_models_for_provider(provider)
                if models:
                    return models[0]
            
            return default_model
        return ""
    
    def send_prompt(self, prompt: str, provider: str, model: str) -> Dict[str, Any]:
        """プロンプトをAIに送信して応答を取得"""
        import datetime as _dt

        # プロンプト長の制限チェック（文字数ベース）
        max_prompt_length = 50000  # 約12,500トークン相当（4文字=1トークン想定）
        if len(prompt) > max_prompt_length:
            truncated_prompt = prompt[:max_prompt_length]
            truncated_prompt += "\n\n[注意: プロンプトが長すぎるため切り詰められました]"
            logger.debug("プロンプトが長すぎます。元の長さ: %s, 切り詰め後: %s", len(prompt), len(truncated_prompt))
            prompt = truncated_prompt

        started_at = _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec='seconds')
        started_perf = time.perf_counter()

        def _attach_timing(res: Dict[str, Any]) -> Dict[str, Any]:
            try:
                finished_at = _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec='seconds')
            except Exception:
                finished_at = None
            try:
                elapsed = round(time.perf_counter() - started_perf, 3)
            except Exception:
                elapsed = None

            if isinstance(res, dict):
                res.setdefault('started_at', started_at)
                res.setdefault('finished_at', finished_at)
                res.setdefault('elapsed_seconds', elapsed)
            return res

        max_attempts = self._get_request_max_attempts()
        last_result: Dict[str, Any] = {"success": False, "error": "AI呼び出し失敗（未実行）"}

        # Gemini は内部でリトライを完結させる（外側で再試行すると試行回数が二重化する）
        if provider == "gemini":
            try:
                result = self._send_gemini_request(prompt, model, retry_count=0, max_retries=max_attempts - 1)
            except Exception as e:
                logger.error("AI API呼び出し例外 (%s): %s", provider, e)
                result = {"success": False, "error": str(e)}

            if isinstance(result, dict):
                result.setdefault("provider", provider)
                result.setdefault("model", model)
                result.setdefault("retry_count", 0)

                req_params = result.get("request_params")
                if isinstance(req_params, dict):
                    req_params.setdefault("provider", provider)
                    req_params.setdefault("model", model)
                    req_params.setdefault("max_attempts", max_attempts)

                resp_params = result.get("response_params")
                if isinstance(resp_params, dict):
                    resp_params.setdefault("provider", provider)
                    resp_params.setdefault("model", model)
                    resp_params.setdefault("max_attempts", max_attempts)

            if isinstance(result, dict):
                return _attach_timing(result)
            return _attach_timing({"success": False, "error": "AI応答形式が不正です", "provider": provider, "model": model})

        for attempt_index in range(max_attempts):
            try:
                if provider == "openai":
                    result = self._send_openai_request(prompt, model)
                elif provider == "local_llm":
                    result = self._send_local_llm_request(prompt, model)
                else:
                    result = {"success": False, "error": f"未対応のプロバイダー: {provider}"}
            except Exception as e:
                logger.error("AI API呼び出し例外 (%s): %s", provider, e)
                result = {"success": False, "error": str(e)}

            # 呼び出し側で参照できるように provider/model を常に付与
            if isinstance(result, dict):
                result.setdefault("provider", provider)
                result.setdefault("model", model)
                result.setdefault("retry_count", attempt_index)

                req_params = result.get("request_params")
                if isinstance(req_params, dict):
                    req_params.setdefault("provider", provider)
                    req_params.setdefault("model", model)
                    req_params.setdefault("attempt", attempt_index + 1)
                    req_params.setdefault("max_attempts", max_attempts)

                resp_params = result.get("response_params")
                if isinstance(resp_params, dict):
                    resp_params.setdefault("provider", provider)
                    resp_params.setdefault("model", model)
                    resp_params.setdefault("attempt", attempt_index + 1)
                    resp_params.setdefault("max_attempts", max_attempts)

            last_result = result if isinstance(result, dict) else {"success": False, "error": "AI応答形式が不正です"}

            if isinstance(result, dict) and result.get("success") is True:
                return _attach_timing(result)

            # 失敗時: 次の試行へ
            if attempt_index < max_attempts - 1 and provider != "gemini":
                # UIフリーズを避けるため、短い待ち時間のみ入れる（pytestではスキップ）
                if not os.environ.get("PYTEST_CURRENT_TEST"):
                    time.sleep(0.2)

        if isinstance(last_result, dict):
            return _attach_timing(last_result)
        return _attach_timing({"success": False, "error": "AI応答形式が不正です", "provider": provider, "model": model})

    @staticmethod
    def _b64url(data: bytes) -> str:
        import base64

        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    def _load_service_account_json(self, path_or_rel: str) -> Dict[str, Any]:
        import os

        raw = (path_or_rel or "").strip()
        if not raw:
            raise ValueError("サービスアカウントJSONが未設定です")

        # 相対パスは input/.. のように指定される想定
        path = raw
        try:
            if not os.path.isabs(path):
                path = get_dynamic_file_path(path)
        except Exception:
            # get_dynamic_file_path が失敗しても、raw を試す
            path = raw

        if not os.path.exists(path):
            raise FileNotFoundError(f"サービスアカウントJSONが見つかりません: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("サービスアカウントJSONの形式が不正です")
        return data

    def _get_vertex_access_token(self, sa_info: Dict[str, Any]) -> str:
        """サービスアカウントJSONからOAuthアクセストークンを取得（キャッシュあり）。"""
        import time

        # キャッシュ
        cache = getattr(self, "_vertex_token_cache", None)
        now = int(time.time())
        if isinstance(cache, dict):
            token = cache.get("access_token")
            exp = cache.get("exp")
            try:
                if token and int(exp) - 60 > now:
                    return str(token)
            except Exception:
                pass

        token_uri = str(sa_info.get("token_uri") or "https://oauth2.googleapis.com/token")
        client_email = str(sa_info.get("client_email") or "").strip()
        private_key = str(sa_info.get("private_key") or "").strip()
        if not client_email or not private_key:
            raise ValueError("サービスアカウントJSONに client_email/private_key がありません")

        scope = "https://www.googleapis.com/auth/cloud-platform"

        # JWT assertion
        iat = now
        exp = now + 3600
        header = {"alg": "RS256", "typ": "JWT"}
        payload = {
            "iss": client_email,
            "scope": scope,
            "aud": token_uri,
            "iat": iat,
            "exp": exp,
        }

        signing_input = (
            f"{self._b64url(json.dumps(header, separators=(',', ':')).encode('utf-8'))}."
            f"{self._b64url(json.dumps(payload, separators=(',', ':')).encode('utf-8'))}"
        ).encode("ascii")

        try:
            from Cryptodome.PublicKey import RSA  # type: ignore
            from Cryptodome.Signature import pkcs1_15  # type: ignore
            from Cryptodome.Hash import SHA256  # type: ignore
        except Exception as e:
            raise RuntimeError(f"pycryptodomex が利用できません: {e}")

        try:
            key = RSA.import_key(private_key)
            h = SHA256.new(signing_input)
            signature = pkcs1_15.new(key).sign(h)
        except Exception as e:
            raise RuntimeError(f"サービスアカウント鍵での署名に失敗しました: {e}")

        assertion = signing_input.decode("ascii") + "." + self._b64url(signature)

        # Token request
        body = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        }

        # NOTE: ここはフォームで送る
        resp = self.session.post(token_uri, data=body, timeout=self.config.get("timeout", 120))
        if resp.status_code != 200:
            raise RuntimeError(f"OAuthトークン取得に失敗: {resp.status_code} - {resp.text}")
        try:
            token_json = resp.json()
        except Exception as e:
            raise RuntimeError(f"OAuthトークン応答JSONの解析に失敗: {type(e).__name__}")

        access_token = token_json.get("access_token")
        if not access_token:
            raise RuntimeError("OAuthトークン応答に access_token がありません")

        # 応答のexpires_in（秒）を優先
        try:
            expires_in = int(token_json.get("expires_in") or 3600)
        except Exception:
            expires_in = 3600
        exp_cache = now + max(60, min(expires_in, 3600))
        try:
            self._vertex_token_cache = {"access_token": access_token, "exp": exp_cache}
        except Exception:
            pass

        return str(access_token)
    
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
    
    def _send_gemini_request(self, prompt: str, model: str, retry_count: int = 0, max_retries: int = None) -> Dict[str, Any]:
        """Gemini APIにリクエストを送信（リトライ対応）
        
        Args:
            prompt: 送信するプロンプト
            model: 使用するモデル名
            retry_count: 現在のリトライ回数（内部使用）
        
        Returns:
            APIレスポンスの辞書
        """        
        config = self.config["ai_providers"]["gemini"]

        def _safe_error_detail(err: Exception, max_len: int = 500) -> str:
            try:
                msg = str(err)
            except Exception:
                msg = ""
            msg = (msg or "").strip()
            if not msg:
                return type(err).__name__
            if len(msg) > max_len:
                msg = msg[:max_len] + "..."
            return f"{type(err).__name__}: {msg}"

        def _safe_request_url_for_log(url: str) -> str:
            # APIキーがクエリに含まれる場合があるため、ログ用途はクエリを除去
            try:
                return (url or "").split("?", 1)[0]
            except Exception:
                return url
        auth_mode = (config.get("auth_mode") or "api_key").strip().lower()
        use_vertex = auth_mode == "vertex_sa"
        api_key = "" if use_vertex else config.get("api_key", "")
        if max_retries is None:
            max_retries = max(0, self._get_request_max_attempts() - 1)
        try:
            max_retries = int(max_retries)
        except Exception:
            max_retries = 2
        if max_retries < 0:
            max_retries = 0
        if max_retries > 4:
            max_retries = 4

        def _build_vertex_generate_url(project_id: str, location: str, model: str) -> str:
            loc = (location or "").strip()
            host = "https://aiplatform.googleapis.com" if loc == "global" else f"https://{loc}-aiplatform.googleapis.com"
            return (
                f"{host}/v1/projects/{project_id}"
                f"/locations/{loc}/publishers/google/models/{model}:generateContent"
            )

        # 認証モード: api_key (従来) / vertex_sa
        if use_vertex:
            sa_json_path = (config.get("vertex_service_account_json") or "").strip()
            project_id = (config.get("vertex_project_id") or "").strip()
            location = (config.get("vertex_location") or "").strip()

            if not sa_json_path:
                return {"success": False, "error": "Vertex AI サービスアカウントJSONが設定されていません"}
            if not location:
                return {"success": False, "error": "Vertex AI Locationが設定されていません"}

            try:
                sa = self._load_service_account_json(sa_json_path)
            except Exception as e:
                return {"success": False, "error": f"Vertex AI サービスアカウントJSONの読み込みに失敗しました: {_safe_error_detail(e)}"}

            # project_id が未設定の場合は、サービスアカウントJSON内の project_id をフォールバック
            if not project_id:
                try:
                    project_id = str(sa.get("project_id") or "").strip()
                except Exception:
                    project_id = ""
            if not project_id:
                return {"success": False, "error": "Vertex AI Project IDが設定されていません（設定値またはサービスアカウントJSONの project_id を確認してください）"}

            try:
                access_token = self._get_vertex_access_token(sa)
            except Exception as e:
                return {"success": False, "error": f"Vertex AI アクセストークン取得に失敗しました: {_safe_error_detail(e)}"}

            url = _build_vertex_generate_url(project_id=project_id, location=location, model=model)
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            }
            request_url = url
        else:
            if not api_key:
                return {"success": False, "error": "Gemini APIキーが設定されていません"}

            base_url = config.get("base_url", "https://generativelanguage.googleapis.com/v1")
            url = f"{base_url}/models/{model}:generateContent"
            headers = {"Content-Type": "application/json"}
            request_url = f"{url}?key={api_key}"

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
        fallback_vertex_location_used = False
        for attempt_index in range(max_retries + 1):
            # 表示/デバッグ用: 本文（contents）以外のリクエストパラメータ
            request_params = {k: v for k, v in data.items() if k != "contents"}
            request_params["contents_count"] = len(data.get("contents", []) or [])
            request_params["auth_mode"] = "vertex_sa" if use_vertex else "api_key"
            if use_vertex:
                request_params["vertex_project_id"] = project_id
                request_params["vertex_location"] = location
                request_params["vertex_endpoint"] = _safe_request_url_for_log(request_url)
            else:
                request_params["gemini_endpoint"] = _safe_request_url_for_log(request_url)
            if adjustments:
                request_params["auto_adjustments"] = adjustments

            last_request_params = request_params

            start_time = time.time()
            try:
                response = self.session.post(
                    request_url,
                    headers=headers,
                    json=data,
                    timeout=self.config.get("timeout", 120)
                )
            except _requests_types.exceptions.RequestException as e:
                # 企業ネットワーク等で regional endpoint がDNS/プロキシ制限されるケースがあるため、Vertex時のみ global endpoint を1回だけ試す
                if use_vertex:
                    try:
                        regional_prefix = f"https://{location}-aiplatform.googleapis.com"
                        if isinstance(request_url, str) and request_url.startswith(regional_prefix):
                            alt_url = "https://aiplatform.googleapis.com" + request_url[len(regional_prefix):]
                            adjustments.append({"kind": "fallback_vertex_endpoint", "from": regional_prefix, "to": "https://aiplatform.googleapis.com"})
                            response = self.session.post(
                                alt_url,
                                headers=headers,
                                json=data,
                                timeout=self.config.get("timeout", 120)
                            )
                            request_url = alt_url
                        else:
                            raise
                    except Exception:
                        last_response_time = time.time() - start_time
                        return {
                            "success": False,
                            "error": f"通信エラー: {_safe_error_detail(e)}",
                            "model": model,
                            "response_time": last_response_time,
                            "request_params": last_request_params,
                            "response_params": {
                                "status_code": 0,
                                "response_time": last_response_time,
                                "model": model,
                                "retry_count": attempt_index,
                            },
                        }
                else:
                    last_response_time = time.time() - start_time
                    return {
                        "success": False,
                        "error": f"通信エラー: {_safe_error_detail(e)}",
                        "model": model,
                        "response_time": last_response_time,
                        "request_params": last_request_params,
                        "response_params": {
                            "status_code": 0,
                            "response_time": last_response_time,
                            "model": model,
                            "retry_count": attempt_index,
                        },
                    }

            last_response_time = time.time() - start_time
            last_status_code = response.status_code

            # Vertex: locationによって publisher model が見つからない場合があるため、404(NOT_FOUND)時は locations/global へ1回だけフォールバック
            if (
                use_vertex
                and response.status_code == 404
                and not fallback_vertex_location_used
                and str(location or "").strip() != "global"
            ):
                try:
                    text_lower = (response.text or "").lower()
                except Exception:
                    text_lower = ""
                if "publisher model" in text_lower and "not found" in text_lower:
                    try:
                        prev_location = location
                        location = "global"
                        request_url = _build_vertex_generate_url(project_id=project_id, location=location, model=model)
                        adjustments.append({"kind": "fallback_vertex_location", "from": prev_location, "to": "global"})

                        # 表示/ログ用のリクエストパラメータも更新
                        try:
                            last_request_params["vertex_location"] = location
                            last_request_params["vertex_endpoint"] = _safe_request_url_for_log(request_url)
                        except Exception:
                            pass

                        retry_resp = self.session.post(
                            request_url,
                            headers=headers,
                            json=data,
                            timeout=self.config.get("timeout", 120),
                        )
                        response = retry_resp
                        last_status_code = response.status_code
                        fallback_vertex_location_used = True
                    except Exception:
                        # フォールバック中の例外は通常のエラー処理へ
                        fallback_vertex_location_used = True

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
                        request_url,
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
