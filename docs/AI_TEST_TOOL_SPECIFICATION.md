# AI機能テストツール - 技術仕様書

## 概要

ARIM RDE Tool v1.12.4で新たに追加されたAI機能の性能テストとベンチマークを行うためのコマンドラインツール群です。GUI版で使用されるAI機能と同等のリクエストを送信し、レスポンス時間、成功率、トークン使用量などの詳細な分析を提供します。

## アーキテクチャ

### コンポーネント構成

```
tools/
├── ai_test_cli.py           # メインテストツール
├── ai_result_analyzer.py    # 結果分析・可視化ツール
├── ai_help.py              # ヘルプ・クイックスタートツール
├── run_ai_tests.bat        # Windows一括実行スクリプト
└── run_ai_tests.ps1        # PowerShell一括実行スクリプト
```

### データフロー

```
input/ai_config.json
       ↓
ai_test_cli.py → API呼び出し → output/log/results.json
       ↓
ai_result_analyzer.py → 分析・可視化 → レポート・グラフ
```

## AITestCLI クラス仕様

### 主要メソッド

#### `__init__()`
- AI設定ファイルの読み込み
- HTTPセッションの初期化
- 結果格納用リストの初期化

#### `_generate_test_text(target_chars, add_padding=False)`
材料研究関連のテストプロンプトを生成：
- **ベーステンプレート**: 材料の機械的特性、結晶構造、熱処理等
- **パディング機能**: 指定文字数に達するまで自然な文章で拡張
- **文字数制御**: 正確な文字数での出力保証

#### `_call_openai_api(model, prompt)`
OpenAI API呼び出し：
- **認証**: Bearer token方式
- **パラメータ**: モデル別最適化（GPT-5系では`max_completion_tokens`使用）
- **エラーハンドリング**: HTTPエラー、レート制限対応

#### `_call_gemini_api(model, prompt)`
Google Gemini API呼び出し：
- **認証**: API key方式
- **エンドポイント**: generateContent API使用
- **レスポンス解析**: 階層構造からcontentを抽出

#### `_call_local_llm_api(model, prompt)`
ローカルLLM API呼び出し（Ollama準拠）：
- **プロトコル**: OpenAI互換API
- **接続処理**: ConnectionError時の適切なハンドリング
- **設定**: カスタムベースURL対応

#### `run_test(provider, model, chars, add_padding, repeat)`
テスト実行の統合制御：
- **進捗表示**: リアルタイム実行状況表示
- **結果集計**: 成功・失敗の詳細情報収集
- **時間測定**: 高精度レスポンス時間計測

### パフォーマンス測定項目

| 項目 | 説明 | 単位 |
|------|------|------|
| response_time | API呼び出し～レスポンス受信時間 | 秒 |
| tokens_used | 入力+出力トークン総数 | トークン |
| success_rate | 全テスト中の成功割合 | % |
| prompt_length | 送信プロンプトの文字数 | 文字 |
| content_length | レスポンス内容の文字数 | 文字 |

## AIResultAnalyzer クラス仕様

### 分析機能

#### 基本統計
- **記述統計**: 平均、中央値、標準偏差、最小・最大値
- **成功率分析**: プロバイダー・モデル別成功率
- **トークン分析**: 使用量パターンとコスト推定

#### 可視化機能
- **レスポンス時間分布**: ヒストグラム表示
- **モデル別比較**: ボックスプロット
- **プロンプト長相関**: 散布図
- **成功率比較**: 棒グラフ

#### レポート生成
- **Markdown形式**: 詳細分析レポート
- **推奨事項**: パフォーマンス最適化提案
- **可視化統合**: グラフとテキストの組み合わせ

### データ形式

#### 入力JSON形式
```json
{
  "success": true,
  "content": "AIレスポンス内容",
  "response_time": 2.34,
  "tokens_used": 650,
  "model": "gpt-4",
  "test_number": 1,
  "prompt_length": 500,
  "timestamp": "2025-08-18T10:30:00"
}
```

#### 出力レポート形式
```markdown
# AI性能テスト分析レポート

**生成日時**: 2025-08-18 10:30:00
**分析対象**: 12 件のテスト結果

## 📊 全体サマリ
- **総テスト数**: 12
- **成功テスト数**: 11
- **成功率**: 91.7%

## ⏱️ レスポンス時間統計
- **平均**: 2.45秒
- **中央値**: 2.12秒
```

## 設定仕様

### ai_config.json スキーマ
```json
{
  "ai_providers": {
    "openai": {
      "enabled": boolean,
      "api_key": string,
      "base_url": string (optional),
      "models": string[]
    },
    "gemini": {
      "enabled": boolean,
      "api_key": string,
      "models": string[]
    },
    "local_llm": {
      "enabled": boolean,
      "base_url": string,
      "models": string[]
    }
  },
  "default_provider": string,
  "timeout": number,
  "max_tokens": number,
  "temperature": number
}
```

## 使用例・シナリオ

### シナリオ1: 基本性能測定
```bash
python tools/ai_test_cli.py --model gpt-4 --chars 500 --repeat 5
```
**目的**: 標準的な条件でのベースライン性能測定

### シナリオ2: スケーラビリティテスト
```bash
python tools/ai_test_cli.py --model gpt-4 --chars 100 --repeat 3
python tools/ai_test_cli.py --model gpt-4 --chars 500 --repeat 3
python tools/ai_test_cli.py --model gpt-4 --chars 1000 --repeat 3
python tools/ai_test_cli.py --model gpt-4 --chars 2000 --padding --repeat 3
```
**目的**: プロンプト長増加に伴う性能変化の測定

### シナリオ3: モデル比較テスト
```bash
python tools/ai_test_cli.py --provider openai --model gpt-4 --chars 500 --repeat 3
python tools/ai_test_cli.py --provider openai --model gpt-3.5-turbo --chars 500 --repeat 3
python tools/ai_test_cli.py --provider gemini --model gemini-1.5-flash --chars 500 --repeat 3
```
**目的**: 異なるモデル間での性能比較

### シナリオ4: 安定性テスト
```bash
python tools/ai_test_cli.py --model gpt-4 --chars 500 --repeat 50
```
**目的**: 長時間実行での安定性・一貫性確認

## エラーハンドリング

### 対応エラータイプ
- **認証エラー**: APIキー無効・期限切れ
- **レート制限**: API呼び出し頻度制限
- **ネットワークエラー**: 接続タイムアウト・切断
- **モデルエラー**: 指定モデル未対応・無効
- **設定エラー**: 設定ファイル不正・不完全

### 復旧機能
- **リトライ機構**: 一時的なエラーの自動復旧
- **グレースフルデグラデーション**: 部分的な失敗での継続実行
- **詳細ログ**: 問題診断のための情報収集

## パフォーマンス最適化

### 推奨設定
- **並列実行**: 複数プロバイダーの同時テスト回避
- **バッチサイズ**: 1回あたり3-5回のリピートテスト
- **タイムアウト**: ネットワーク環境に応じた調整（推奨30秒）

### 最適化指標
- **レスポンス時間**: < 5秒（一般的なケース）
- **成功率**: > 95%（安定運用基準）
- **トークン効率**: 入力対出力比率の最適化

## 拡張性

### 新しいプロバイダー追加
1. `_call_*_api()` メソッドの実装
2. `ai_config.json` スキーマ拡張
3. 認証・エンドポイント設定の追加

### カスタムメトリクス追加
1. 測定項目の定義
2. 収集ロジックの実装
3. 分析・可視化機能の拡張

---

**更新履歴**:
- 2025-08-18: v1.12.4 - 初版作成、基本機能実装
