"""
Network Health Check Tool

ネットワーク接続とプロキシ設定の動作確認を行う
"""

import sys
import time
import logging
from typing import Dict, Any, List, Tuple
from dataclasses import dataclass

# パス管理
sys.path.insert(0, 'src')
from config.common import get_dynamic_file_path

# ネットワークモジュール
try:
    from net import http as requests
    from net.config import load_network_config, validate_config
except ImportError:
    # フォールバック: 標準requests
    import requests
    requests.configure = lambda x=None: None
    print("警告: net.httpモジュールが見つかりません。標準requestsを使用")

@dataclass
class HealthCheckResult:
    """ヘルスチェック結果"""
    name: str
    success: bool
    response_time: float
    status_code: int
    error_message: str
    details: Dict[str, Any]


class NetworkHealthChecker:
    """ネットワーク接続ヘルスチェッカー"""
    
    def __init__(self):
        self.logger = logging.getLogger("healthcheck")
        
        # ロガーの設定
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def check_all(self) -> List[HealthCheckResult]:
        """全ヘルスチェックを実行"""
        results = []
        
        self.logger.info("=== ネットワークヘルスチェック開始 ===")
        
        # 1. 設定ファイル検証
        results.append(self._check_config())
        
        # 2. 基本接続確認（httpbin.org）
        results.append(self._check_httpbin())
        
        # 3. PAC設定確認（PAC モードの場合のみ）
        config = load_network_config()
        if config.get("network", {}).get("mode") == "PAC":
            results.append(self._check_pac())
        
        # 4. 主要ターゲット確認（RDE/ARIM）
        results.append(self._check_main_targets())
        
        # 結果サマリー
        self._print_summary(results)
        
        return results
    
    def _check_config(self) -> HealthCheckResult:
        """設定ファイルの検証"""
        start_time = time.time()
        
        try:
            config = load_network_config()
            errors = validate_config(config)
            
            if errors:
                return HealthCheckResult(
                    name="設定ファイル検証",
                    success=False,
                    response_time=time.time() - start_time,
                    status_code=0,
                    error_message="; ".join(errors),
                    details={"config": config, "errors": errors}
                )
            
            # ネットワークモジュールの初期化
            requests.configure(config)
            
            return HealthCheckResult(
                name="設定ファイル検証",
                success=True,
                response_time=time.time() - start_time,
                status_code=200,
                error_message="",
                details={
                    "mode": config.get("network", {}).get("mode", "UNKNOWN"),
                    "proxy_config": requests.get_proxy_config()
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                name="設定ファイル検証",
                success=False,
                response_time=time.time() - start_time,
                status_code=0,
                error_message=str(e),
                details={"error": str(e)}
            )
    
    def _check_httpbin(self) -> HealthCheckResult:
        """httpbin.org への接続確認"""
        start_time = time.time()
        
        try:
            url = "https://httpbin.org/ip"
            response = requests.get(url, timeout=15)
            
            return HealthCheckResult(
                name="基本接続確認 (httpbin.org)",
                success=response.status_code == 200,
                response_time=time.time() - start_time,
                status_code=response.status_code,
                error_message="" if response.status_code == 200 else f"HTTP {response.status_code}",
                details={
                    "url": url,
                    "response_json": response.json() if response.status_code == 200 else None,
                    "headers": dict(response.headers)
                }
            )
            
        except requests.exceptions.ProxyError as e:
            return HealthCheckResult(
                name="基本接続確認 (httpbin.org)",
                success=False,
                response_time=time.time() - start_time,
                status_code=407,
                error_message=f"プロキシエラー: {e}",
                details={"error_type": "ProxyError", "suggestion": "プロキシ設定を確認してください"}
            )
        except requests.exceptions.SSLError as e:
            return HealthCheckResult(
                name="基本接続確認 (httpbin.org)",
                success=False,
                response_time=time.time() - start_time,
                status_code=0,
                error_message=f"SSL証明書エラー: {e}",
                details={"error_type": "SSLError", "suggestion": "証明書設定またはca_bundleを確認してください"}
            )
        except requests.exceptions.ConnectTimeout as e:
            return HealthCheckResult(
                name="基本接続確認 (httpbin.org)",
                success=False,
                response_time=time.time() - start_time,
                status_code=0,
                error_message=f"接続タイムアウト: {e}",
                details={"error_type": "ConnectTimeout", "suggestion": "ネットワーク接続またはプロキシ設定を確認してください"}
            )
        except Exception as e:
            return HealthCheckResult(
                name="基本接続確認 (httpbin.org)",
                success=False,
                response_time=time.time() - start_time,
                status_code=0,
                error_message=str(e),
                details={"error_type": type(e).__name__, "error": str(e)}
            )
    
    def _check_pac(self) -> HealthCheckResult:
        """PAC設定の確認"""
        start_time = time.time()
        
        try:
            config = load_network_config()
            pac_url = config.get("network", {}).get("pac_url", "")
            
            if not pac_url:
                return HealthCheckResult(
                    name="PAC設定確認",
                    success=False,
                    response_time=time.time() - start_time,
                    status_code=0,
                    error_message="PAC URLが設定されていません",
                    details={"suggestion": "network.yaml の pac_url を設定してください"}
                )
            
            # PAC ファイルの取得
            response = requests.get(pac_url, timeout=10)
            
            success = response.status_code == 200
            pac_content = response.text if success else ""
            
            return HealthCheckResult(
                name="PAC設定確認",
                success=success,
                response_time=time.time() - start_time,
                status_code=response.status_code,
                error_message="" if success else f"PAC取得失敗: HTTP {response.status_code}",
                details={
                    "pac_url": pac_url,
                    "pac_content_length": len(pac_content) if success else 0,
                    "has_FindProxyForURL": "FindProxyForURL" in pac_content if success else False
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                name="PAC設定確認",
                success=False,
                response_time=time.time() - start_time,
                status_code=0,
                error_message=str(e),
                details={"error": str(e), "suggestion": "PAC URLとネットワーク接続を確認してください"}
            )
    
    def _check_main_targets(self) -> HealthCheckResult:
        """主要ターゲット（RDE/ARIM等）への接続確認"""
        start_time = time.time()
        
        # 主要ターゲットURL（実際のプロジェクトに合わせて調整）
        targets = [
            "https://example.com",  # 汎用テストサイト
            # "https://rde.your-domain.com",  # 実際のRDE URL
            # "https://arim.your-domain.com", # 実際のARIM URL
        ]
        
        results = []
        for url in targets:
            try:
                response = requests.get(url, timeout=10)
                results.append({
                    "url": url,
                    "status_code": response.status_code,
                    "success": response.status_code < 400,
                    "response_time": response.elapsed.total_seconds()
                })
            except Exception as e:
                results.append({
                    "url": url,
                    "status_code": 0,
                    "success": False,
                    "error": str(e)
                })
        
        # 全体の成功判定
        success = all(r.get("success", False) for r in results)
        errors = [f"{r['url']}: {r.get('error', f'HTTP {r['status_code']}')}" 
                 for r in results if not r.get("success", False)]
        
        return HealthCheckResult(
            name="主要ターゲット接続確認",
            success=success,
            response_time=time.time() - start_time,
            status_code=200 if success else 0,
            error_message="; ".join(errors) if errors else "",
            details={"targets": results}
        )
    
    def _print_summary(self, results: List[HealthCheckResult]) -> None:
        """結果サマリーを出力"""
        print("\n" + "="*60)
        print("ネットワークヘルスチェック結果")
        print("="*60)
        
        for result in results:
            status = "✓ PASS" if result.success else "✗ FAIL"
            print(f"{status:8} {result.name:30} ({result.response_time:.2f}s)")
            
            if not result.success:
                print(f"         エラー: {result.error_message}")
                if "suggestion" in result.details:
                    print(f"         対策: {result.details['suggestion']}")
            elif result.name == "設定ファイル検証":
                mode = result.details.get("mode", "UNKNOWN")
                proxy_config = result.details.get("proxy_config", {})
                print(f"         モード: {mode}")
                if proxy_config:
                    print(f"         プロキシ: {proxy_config}")
        
        # 総合判定
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.success)
        
        print(f"\n総合結果: {passed_tests}/{total_tests} テスト合格")
        
        if passed_tests == total_tests:
            print("✓ すべてのネットワークテストが成功しました")
        else:
            print("✗ 一部のテストが失敗しました。設定を確認してください")


def main():
    """メイン実行関数"""
    checker = NetworkHealthChecker()
    results = checker.check_all()
    
    # 終了コード（失敗があれば1）
    exit_code = 0 if all(r.success for r in results) else 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
