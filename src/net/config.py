"""
Network Configuration Module

ネットワーク設定の管理とヘルスチェック機能を提供
"""

import logging
import os
import json  # YAML の代わりに JSON を使用
from typing import Dict, Any, Optional, List
from config.common import get_dynamic_file_path

logger = logging.getLogger("net.config")

# YAML サポートの確認
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    logger.warning("PyYAML が見つかりません。JSON形式の設定ファイルを使用します")


def load_network_config() -> Dict[str, Any]:
    """ネットワーク設定ファイルを読み込み（YAML または JSON）"""
    try:
        # まず YAML を試行
        if YAML_AVAILABLE:
            config_path = get_dynamic_file_path("config/network.yaml")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    logger.info(f"ネットワーク設定(YAML)を読み込み: {config_path}")
                    return config
        
        # 次に JSON を試行
        config_path = get_dynamic_file_path("config/network.json")
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.info(f"ネットワーク設定(JSON)を読み込み: {config_path}")
                return config
        
        logger.info("ネットワーク設定ファイルが見つかりません。デフォルト設定を使用")
        return get_default_config()
            
    except Exception as e:
        logger.error(f"ネットワーク設定の読み込みエラー: {e}")
        return get_default_config()


def get_default_config() -> Dict[str, Any]:
    """デフォルトネットワーク設定"""
    return {
        "network": {
            "mode": "DIRECT",
            "proxies": {"http": "", "https": "", "no_proxy": ""},
            "pac_url": "",
            "cert": {"use_os_store": True, "verify": True, "ca_bundle": ""},
            "timeouts": {"connect": 10, "read": 30},
            "retries": {"total": 3, "backoff_factor": 0.5, "status_forcelist": [429, 500, 502, 503, 504]}
        },
        "webview": {"auto_proxy_from_network": True, "additional_args": []}
    }


def save_network_config(config: Dict[str, Any], use_yaml: bool = True) -> bool:
    """ネットワーク設定をファイルに保存"""
    try:
        if use_yaml and YAML_AVAILABLE:
            config_path = get_dynamic_file_path("config/network.yaml")
            
            # ディレクトリが存在しない場合は作成
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            
            logger.info(f"ネットワーク設定(YAML)を保存: {config_path}")
        else:
            config_path = get_dynamic_file_path("config/network.json")
            
            # ディレクトリが存在しない場合は作成
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"ネットワーク設定(JSON)を保存: {config_path}")
        
        return True
        
    except Exception as e:
        logger.error(f"ネットワーク設定の保存エラー: {e}")
        return False


def validate_config(config: Dict[str, Any]) -> List[str]:
    """設定の検証を行い、エラーメッセージのリストを返す"""
    errors = []
    
    try:
        network = config.get("network", {})
        mode = network.get("mode", "")
        
        # モード検証
        if mode not in ["DIRECT", "STATIC", "PAC"]:
            errors.append(f"無効なモード: {mode} (DIRECT, STATIC, PAC のいずれかを指定)")
        
        # STATIC モードの検証
        if mode == "STATIC":
            proxies = network.get("proxies", {})
            if not proxies.get("http") and not proxies.get("https"):
                errors.append("STATIC モードではhttp または https プロキシの指定が必要")
        
        # PAC モードの検証
        if mode == "PAC":
            pac_url = network.get("pac_url", "")
            if not pac_url:
                errors.append("PAC モードでは pac_url の指定が必要")
            elif not pac_url.startswith(("http://", "https://", "file://")):
                errors.append("PAC URL は http://, https://, file:// のいずれかで開始する必要があります")
        
        # SSL設定検証
        cert = network.get("cert", {})
        ca_bundle = cert.get("ca_bundle", "")
        if ca_bundle and not os.path.exists(ca_bundle):
            errors.append(f"CA Bundle ファイルが見つかりません: {ca_bundle}")
        
        # タイムアウト設定検証
        timeouts = network.get("timeouts", {})
        for key in ["connect", "read"]:
            value = timeouts.get(key, 0)
            if not isinstance(value, (int, float)) or value <= 0:
                errors.append(f"タイムアウト設定 '{key}' は正の数値である必要があります")
        
        # リトライ設定検証
        retries = network.get("retries", {})
        total = retries.get("total", 0)
        if not isinstance(total, int) or total < 0:
            errors.append("リトライ回数は0以上の整数である必要があります")
        
        backoff = retries.get("backoff_factor", 0)
        if not isinstance(backoff, (int, float)) or backoff < 0:
            errors.append("バックオフ係数は0以上の数値である必要があります")
            
    except Exception as e:
        errors.append(f"設定検証中にエラー: {e}")
    
    return errors
