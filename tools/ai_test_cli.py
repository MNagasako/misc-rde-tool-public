#!/usr/bin/env python3
"""
AI性能テストツール - ARIM RDE Tool v1.13.1

概要:
AI機能のテストとベンチマークを行う独立したコマンドラインツール。
GUI版と同様のリクエストを送信し、レスポンス時間とパフォーマンスを測定します。

使用例:
python tools/ai_test_cli.py --model gpt-4.1 --chars 1000
python tools/ai_test_cli.py --provider gemini --model gemini-1.5-flash --chars 500 --repeat 3
python tools/ai_test_cli.py --provider local_llm --model llama3.2:3b --chars 2000 --padding
"""

import os
import sys
import json
import time
import random
import string
import argparse
import requests
from typing import Dict, List, Any
from datetime import datetime

# パス管理システムを使用（CWD非依存）
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.config.common import get_dynamic_file_path, get_base_dir

class AITestCLI:
    """AI機能テストコマンドラインツール"""
    
    def __init__(self):
        self.config_path = get_dynamic_file_path("input/ai_config.json")
        self.config = self._load_config()
        self.session = requests.Session()
        self.results = []
        self.verbose = False  # デフォルトはFalse
        
    def _load_config(self) -> Dict[str, Any]:
        """AI設定ファイルを読み込み"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                print(f"⚠️ AI設定ファイルが見つかりません: {self.config_path}")
                return self._get_default_config()
        except Exception as e:
            print(f"❌ AI設定ファイルの読み込みに失敗: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """デフォルト設定を返す"""
        return {
            "ai_providers": {
                "openai": {"enabled": False, "api_key": "", "models": ["gpt-4.1-mini", "gpt-4.1", "gpt-3.5-turbo"]},
                "gemini": {"enabled": False, "api_key": "", "models": ["gemini-1.5-flash", "gemini-1.5-pro"]},
                "local_llm": {"enabled": False, "base_url": "http://localhost:11434/v1", "models": ["llama3.2:3b"]}
            },
            "default_provider": "openai",
            "timeout": 30,
            "max_tokens": 1000,
            "temperature": 0.7
        }
    
    def _generate_test_text(self, target_chars: int, add_padding: bool = False) -> str:
        """テスト用のダミーテキストを生成"""
        # ベースとなる材料研究関連のテキストテンプレート
        base_templates = [
            "この材料の機械的特性について詳細に説明してください。",
            "結晶構造と電気的性質の関係性を分析してください。",
            "熱処理条件が材料組織に与える影響を評価してください。",
            "X線回折パターンから相同定を行い、格子定数を計算してください。",
            "走査電子顕微鏡観察結果に基づいて組織解析を実施してください。",
            "引張試験データから降伏強度と破断伸びを求めてください。",
            "示差熱分析結果を用いて相変態温度を特定してください。",
            "腐食試験における重量減少率と腐食機構を考察してください。"
        ]
        
        # ランダムにテンプレートを選択してベースとする
        base_text = random.choice(base_templates)
        
        if add_padding:
            # パディング用の追加テキスト
            padding_sentences = [
                "さらに詳細な解析が必要です。",
                "実験条件を変更して追加検証を行います。",
                "統計的解析により信頼性を確認します。",
                "過去の研究事例との比較検討を実施します。",
                "理論値との乖離について考察します。",
                "測定誤差の範囲内での評価を行います。"
            ]
            
            current_text = base_text
            
            # 目標文字数に達するまで追加
            while len(current_text) < target_chars:
                remaining_chars = target_chars - len(current_text)
                
                if remaining_chars > 50:
                    # 十分な余裕がある場合は文を追加
                    current_text += " " + random.choice(padding_sentences)
                else:
                    # 残り文字数が少ない場合はランダム文字で調整
                    current_text += " " + "".join(random.choices(string.ascii_letters + string.digits, k=remaining_chars))
                    break
            
            return current_text[:target_chars]
        else:
            # パディングなしの場合は、ベーステキストを基準文字数に調整
            if len(base_text) > target_chars:
                return base_text[:target_chars]
            else:
                # 不足分を追加の説明で補う
                additional = "具体的なデータと解析手法を含めて詳細に説明してください。"
                repeat_count = (target_chars - len(base_text)) // len(additional) + 1
                extended_text = base_text + " " + (additional + " ") * repeat_count
                return extended_text[:target_chars]
    
    def _call_openai_api(self, model: str, prompt: str) -> Dict[str, Any]:
        """OpenAI APIを呼び出し"""
        config = self.config["ai_providers"]["openai"]
        api_key = config.get("api_key")
        
        if not api_key:
            raise ValueError("OpenAI API keyが設定されていません")
        
        url = "https://api.openai.com/v1/chat/completions"
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
            # まずパラメータなしで試してみる
            if model.startswith("gpt-5"):
                # GPT-5系はパラメータを最小限に
                pass  # max_completion_tokensを指定しない
            elif "nano" in model.lower():
                data["max_completion_tokens"] = 50  # nanoは極めて小さな値
            else:
                data["max_completion_tokens"] = max(1000, self.config.get("max_tokens", 1000))
            # GPT-5系およびGPT-4.1系では temperature はデフォルト値のため省略
        else:
            # GPT-4以前では従来のパラメータを使用
            data["max_tokens"] = self.config.get("max_tokens", 1000)
            data["temperature"] = self.config.get("temperature", 0.7)
        
        start_time = time.time()
        
        try:
            response = self.session.post(url, headers=headers, json=data, timeout=self.config.get("timeout", 120))
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": f"タイムアウト ({self.config.get('timeout', 120)}秒)",
                "response_time": time.time() - start_time
            }
        except requests.exceptions.RequestException as e:
            return {
                "success": False,
                "error": f"リクエストエラー: {str(e)}",
                "response_time": time.time() - start_time
            }
        
        end_time = time.time()
        
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            return {
                "success": True,
                "content": content,
                "response_time": end_time - start_time,
                "tokens_used": result.get("usage", {}).get("total_tokens", 0),
                "model": model
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}",
                "response_time": end_time - start_time,
                "model": model
            }
    
    def _call_gemini_api(self, model: str, prompt: str) -> Dict[str, Any]:
        """Gemini APIを呼び出し"""
        config = self.config["ai_providers"]["gemini"]
        api_key = config.get("api_key")
        
        if not api_key:
            raise ValueError("Gemini API keyが設定されていません")
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        
        data = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": self.config.get("max_tokens", 1000),
                "temperature": self.config.get("temperature", 0.7)
            }
        }
        
        start_time = time.time()
        response = self.session.post(url, headers=headers, json=data, timeout=self.config.get("timeout", 30))
        end_time = time.time()
        
        if response.status_code == 200:
            result = response.json()
            content = result["candidates"][0]["content"]["parts"][0]["text"]
            
            return {
                "success": True,
                "content": content,
                "response_time": end_time - start_time,
                "tokens_used": result.get("usageMetadata", {}).get("totalTokenCount", 0),
                "model": model
            }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}",
                "response_time": end_time - start_time,
                "model": model
            }
    
    def _call_local_llm_api(self, model: str, prompt: str) -> Dict[str, Any]:
        """ローカルLLM APIを呼び出し（Ollama形式）"""
        config = self.config["ai_providers"]["local_llm"]
        base_url = config.get("base_url", "http://localhost:11434/v1")
        
        url = f"{base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": self.config.get("max_tokens", 1000),
            "temperature": self.config.get("temperature", 0.7)
        }
        
        start_time = time.time()
        try:
            response = self.session.post(url, headers=headers, json=data, timeout=self.config.get("timeout", 30))
            end_time = time.time()
            
            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                
                return {
                    "success": True,
                    "content": content,
                    "response_time": end_time - start_time,
                    "tokens_used": result.get("usage", {}).get("total_tokens", 0),
                    "model": model
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "response_time": end_time - start_time,
                    "model": model
                }
        except requests.ConnectionError:
            end_time = time.time()
            return {
                "success": False,
                "error": "ローカルLLMサーバーに接続できません",
                "response_time": end_time - start_time,
                "model": model
            }
    
    def run_test(self, provider: str, model: str, chars: int, add_padding: bool = False, repeat: int = 1) -> List[Dict[str, Any]]:
        """AIテストを実行"""
        print(f"🚀 AIテスト開始")
        print(f"📋 設定: Provider={provider}, Model={model}, 文字数={chars}, 繰り返し={repeat}")
        print(f"⏰ 開始時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 60)
        
        results = []
        
        for i in range(repeat):
            print(f"\n📝 テスト {i+1}/{repeat} 実行中...")
            
            # テストプロンプト生成
            test_prompt = self._generate_test_text(chars, add_padding)
            print(f"📏 生成されたプロンプト長: {len(test_prompt)} 文字")
            print(f"🔤 プロンプト（先頭100文字）: {test_prompt[:100]}...")
            
            try:
                # API呼び出し
                if provider == "openai":
                    result = self._call_openai_api(model, test_prompt)
                elif provider == "gemini":
                    result = self._call_gemini_api(model, test_prompt)
                elif provider == "local_llm":
                    result = self._call_local_llm_api(model, test_prompt)
                else:
                    raise ValueError(f"サポートされていないプロバイダー: {provider}")
                
                # 結果表示
                if result["success"]:
                    print(f"✅ 成功: {result['response_time']:.2f}秒")
                    print(f"📊 トークン使用量: {result.get('tokens_used', 'N/A')}")
                    print(f"📝 レスポンス長: {len(result['content'])} 文字")
                    print(f"🔤 レスポンス（先頭200文字）: {result['content'][:200]}...")
                else:
                    print(f"❌ 失敗: {result['error']}")
                    print(f"⏱️ 失敗までの時間: {result['response_time']:.2f}秒")
                
                # 結果をリストに追加
                result["test_number"] = i + 1
                result["prompt_length"] = len(test_prompt)
                result["timestamp"] = datetime.now().isoformat()
                results.append(result)
                
            except Exception as e:
                print(f"❌ エラー: {e}")
                results.append({
                    "success": False,
                    "error": str(e),
                    "test_number": i + 1,
                    "prompt_length": len(test_prompt),
                    "timestamp": datetime.now().isoformat(),
                    "model": model
                })
        
        return results
    
    def print_summary(self, results: List[Dict[str, Any]]):
        """テスト結果のサマリを表示"""
        print("\n" + "=" * 60)
        print("📊 テスト結果サマリ")
        print("=" * 60)
        
        successful_tests = [r for r in results if r.get("success", False)]
        failed_tests = [r for r in results if not r.get("success", False)]
        
        print(f"🎯 総テスト数: {len(results)}")
        print(f"✅ 成功: {len(successful_tests)}")
        print(f"❌ 失敗: {len(failed_tests)}")
        
        if successful_tests:
            response_times = [r["response_time"] for r in successful_tests]
            avg_time = sum(response_times) / len(response_times)
            min_time = min(response_times)
            max_time = max(response_times)
            
            print(f"\n⏱️ レスポンス時間統計:")
            print(f"   平均: {avg_time:.2f}秒")
            print(f"   最短: {min_time:.2f}秒")
            print(f"   最長: {max_time:.2f}秒")
            
            tokens_used = [r.get("tokens_used", 0) for r in successful_tests if r.get("tokens_used", 0) > 0]
            if tokens_used:
                avg_tokens = sum(tokens_used) / len(tokens_used)
                print(f"🪙 平均トークン使用量: {avg_tokens:.0f}")
        
        if failed_tests:
            print(f"\n❌ 失敗理由:")
            error_counts = {}
            for test in failed_tests:
                error = test.get("error", "Unknown error")
                error_counts[error] = error_counts.get(error, 0) + 1
            
            for error, count in error_counts.items():
                print(f"   {error}: {count}回")
    
    def save_results(self, results: List[Dict[str, Any]], output_file: str = None):
        """結果をJSONファイルに保存"""
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"ai_test_results_{timestamp}.json"
        
        output_path = get_dynamic_file_path(f"output/log/{output_file}")
        
        # ディレクトリが存在しない場合は作成
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"💾 結果を保存しました: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="AI性能テストツール")
    parser.add_argument("--provider", choices=["openai", "gemini", "local_llm"], 
                       default="openai", help="AIプロバイダー (default: openai)")
    parser.add_argument("--model", type=str, required=True, help="使用するモデル名")
    parser.add_argument("--chars", type=int, default=500, help="テストプロンプトの文字数 (default: 500)")
    parser.add_argument("--padding", action="store_true", help="文字数かさ増し機能を有効化")
    parser.add_argument("--repeat", type=int, default=1, help="テスト繰り返し回数 (default: 1)")
    parser.add_argument("--output", type=str, help="結果保存ファイル名 (default: auto)")
    parser.add_argument("--verbose", action="store_true", help="詳細ログを表示")
    
    args = parser.parse_args()
    
    # テストツール初期化
    cli = AITestCLI()
    cli.verbose = args.verbose  # verboseフラグを設定
    
    # テスト実行
    try:
        results = cli.run_test(args.provider, args.model, args.chars, args.padding, args.repeat)
        
        # サマリ表示
        cli.print_summary(results)
        
        # 結果保存
        cli.save_results(results, args.output)
        
    except Exception as e:
        print(f"❌ テスト実行中にエラーが発生しました: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
