#!/usr/bin/env python3
"""
プロキシ対応パフォーマンス測定ツール

ネットワーク設定変更時の性能影響を定量評価
起動時間・メモリ使用量・HTTP接続性能の測定
"""

import sys
import os
import time
import psutil
import gc
import statistics
from typing import Dict, List, Any, Optional
from pathlib import Path
from datetime import datetime
import json

# パス設定
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

class PerformanceProfiler:
    """プロキシ対応パフォーマンス測定クラス"""
    
    def __init__(self):
        self.results: Dict[str, Any] = {}
        self.process = psutil.Process()
        self.baseline_memory = self.process.memory_info().rss
        
    def measure_startup_time(self, import_func, iterations: int = 5) -> Dict[str, float]:
        """モジュール読み込み時間を測定"""
        times = []
        
        for i in range(iterations):
            # ガベージコレクション実行
            gc.collect()
            
            start_time = time.perf_counter()
            import_func()
            end_time = time.perf_counter()
            
            times.append(end_time - start_time)
            
            # モジュールキャッシュを一部クリア（実際の起動をシミュレート）
            if 'net.http' in sys.modules:
                del sys.modules['net.http']
            if 'net.config' in sys.modules:
                del sys.modules['net.config']
        
        return {
            "average": statistics.mean(times),
            "median": statistics.median(times),
            "min": min(times),
            "max": max(times),
            "std_dev": statistics.stdev(times) if len(times) > 1 else 0,
            "samples": times
        }
    
    def measure_memory_usage(self) -> Dict[str, int]:
        """メモリ使用量を測定"""
        memory_info = self.process.memory_info()
        
        return {
            "rss_bytes": memory_info.rss,
            "vms_bytes": memory_info.vms,
            "rss_mb": round(memory_info.rss / 1024 / 1024, 2),
            "vms_mb": round(memory_info.vms / 1024 / 1024, 2),
            "increase_from_baseline_bytes": memory_info.rss - self.baseline_memory,
            "increase_from_baseline_mb": round((memory_info.rss - self.baseline_memory) / 1024 / 1024, 2)
        }
    
    def measure_http_performance(self, test_urls: List[str], iterations: int = 3) -> Dict[str, Any]:
        """HTTP接続性能を測定"""
        from net import http as requests
        
        results = {}
        
        for url in test_urls:
            url_results = {
                "successful_requests": 0,
                "failed_requests": 0,
                "response_times": [],
                "status_codes": [],
                "errors": []
            }
            
            for i in range(iterations):
                try:
                    start_time = time.perf_counter()
                    response = requests.get(url, timeout=10)
                    end_time = time.perf_counter()
                    
                    url_results["successful_requests"] += 1
                    url_results["response_times"].append(end_time - start_time)
                    url_results["status_codes"].append(response.status_code)
                    
                except Exception as e:
                    url_results["failed_requests"] += 1
                    url_results["errors"].append(str(e))
            
            # 統計計算
            if url_results["response_times"]:
                times = url_results["response_times"]
                url_results["avg_response_time"] = statistics.mean(times)
                url_results["median_response_time"] = statistics.median(times)
                url_results["min_response_time"] = min(times)
                url_results["max_response_time"] = max(times)
            
            results[url] = url_results
        
        return results
    
    def benchmark_network_modes(self) -> Dict[str, Any]:
        """各ネットワークモードでのベンチマーク"""
        modes = ["DIRECT", "STATIC", "PAC"]
        benchmark_results = {}
        
        test_urls = [
            "https://httpbin.org/ip",
            "https://www.google.com",
            "https://github.com"
        ]
        
        for mode in modes:
            print(f"\n🔄 {mode}モードでベンチマーク実行中...")
            
            # 設定変更
            config = {
                "network": {
                    "mode": mode,
                    "proxies": {"http": "", "https": "", "no_proxy": "localhost,127.0.0.1"},
                    "pac_url": "http://127.0.0.1:8080/proxy.pac" if mode == "PAC" else "",
                    "cert": {"use_os_store": True, "verify": True, "ca_bundle": ""},
                    "timeouts": {"connect": 10, "read": 30},
                    "retries": {"total": 3, "backoff_factor": 0.5, "status_forcelist": [429, 500, 502, 503, 504]}
                }
            }
            
            try:
                from net import http as requests
                requests.configure(config)
                
                # メモリ使用量測定
                memory_before = self.measure_memory_usage()
                
                # HTTP性能測定
                http_results = self.measure_http_performance(test_urls, iterations=2)
                
                # メモリ使用量測定（HTTP後）
                memory_after = self.measure_memory_usage()
                
                benchmark_results[mode] = {
                    "memory_before": memory_before,
                    "memory_after": memory_after,
                    "http_performance": http_results,
                    "status": "success"
                }
                
                print(f"✅ {mode}モード完了")
                
            except Exception as e:
                benchmark_results[mode] = {
                    "status": "error",
                    "error": str(e)
                }
                print(f"❌ {mode}モード失敗: {e}")
        
        return benchmark_results
    
    def save_results(self, results: Dict[str, Any], filename: str) -> None:
        """結果をJSONファイルに保存"""
        results["timestamp"] = datetime.now().isoformat()
        results["python_version"] = sys.version
        results["platform"] = os.name
        
        output_dir = Path(__file__).parent / "performance_results"
        output_dir.mkdir(exist_ok=True)
        
        output_file = output_dir / f"{filename}_{int(time.time())}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"📊 結果を保存: {output_file}")


def test_baseline_import():
    """ベースライン: requestsの直接インポート"""
    import requests


def test_wrapper_import():
    """プロキシ対応: net.httpラッパーのインポート"""
    from net import http as requests
    requests.configure()  # 設定初期化


def main():
    """メインベンチマーク実行"""
    print("🚀 プロキシ対応パフォーマンス測定開始")
    print("=" * 60)
    
    profiler = PerformanceProfiler()
    all_results = {}
    
    # 1. 起動時間測定
    print("\n📈 起動時間測定...")
    
    baseline_times = profiler.measure_startup_time(test_baseline_import)
    wrapper_times = profiler.measure_startup_time(test_wrapper_import)
    
    startup_results = {
        "baseline_requests": baseline_times,
        "wrapper_net_http": wrapper_times,
        "overhead_ms": (wrapper_times["average"] - baseline_times["average"]) * 1000,
        "overhead_percentage": ((wrapper_times["average"] - baseline_times["average"]) / baseline_times["average"] * 100)
    }
    
    all_results["startup_performance"] = startup_results
    
    print(f"  ベースライン平均: {baseline_times['average']*1000:.2f}ms")
    print(f"  ラッパー平均: {wrapper_times['average']*1000:.2f}ms")
    print(f"  オーバーヘッド: {startup_results['overhead_ms']:.2f}ms ({startup_results['overhead_percentage']:.1f}%)")
    
    # 2. ネットワークモード別ベンチマーク
    print("\n🌐 ネットワークモード別ベンチマーク...")
    network_results = profiler.benchmark_network_modes()
    all_results["network_mode_benchmarks"] = network_results
    
    # 3. 最終メモリ使用量
    final_memory = profiler.measure_memory_usage()
    all_results["final_memory_usage"] = final_memory
    
    print(f"\n💾 最終メモリ使用量: {final_memory['rss_mb']}MB")
    print(f"   ベースラインからの増加: {final_memory['increase_from_baseline_mb']}MB")
    
    # 4. 結果保存
    profiler.save_results(all_results, "proxy_performance_benchmark")
    
    # 5. サマリー表示
    print("\n" + "=" * 60)
    print("📊 パフォーマンス測定完了")
    
    if startup_results["overhead_ms"] < 100:  # 100ms未満
        print("✅ 起動時間: 許容範囲内")
    else:
        print("⚠️ 起動時間: オーバーヘッド大")
    
    if final_memory["increase_from_baseline_mb"] < 10:  # 10MB未満
        print("✅ メモリ使用量: 許容範囲内")
    else:
        print("⚠️ メモリ使用量: 増加量大")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
