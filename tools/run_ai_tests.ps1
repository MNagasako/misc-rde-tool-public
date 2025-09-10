# AI性能テスト一括実行スクリプト (PowerShell) - ARIM RDE Tool v1.13.1
# 複数のモデルとパラメータでAI性能テストを自動実行

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "AI性能テスト一括実行スクリプト (PowerShell版)" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan

# 仮想環境のアクティベーション（存在する場合）
if (Test-Path ".venv\Scripts\Activate.ps1") {
    Write-Host "🔧 仮想環境をアクティベート中..." -ForegroundColor Yellow
    & .venv\Scripts\Activate.ps1
}

Write-Host ""
Write-Host "📋 テスト設定:" -ForegroundColor Green
Write-Host "  - OpenAI: gpt-5, gpt-5-mini, gpt-5-nano, gpt-4.1, gpt-4.1-mini, gpt-4.1-nano, gpt-3.5-turbo" -ForegroundColor White
Write-Host "  - Gemini: gemini-1.5-flash" -ForegroundColor White
Write-Host "  - Local LLM: llama3.2:3b" -ForegroundColor White
Write-Host "  - 文字数パターン: 100, 500, 1000, 2000" -ForegroundColor White
Write-Host "  - 各テスト3回実行" -ForegroundColor White
Write-Host ""

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$startTime = Get-Date

Write-Host "⏰ 開始時刻: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Blue
Write-Host "📂 結果保存先: output\log\ai_test_batch_$timestamp.json" -ForegroundColor Blue

# ログディレクトリ作成
if (!(Test-Path "output\log")) {
    New-Item -ItemType Directory -Path "output\log" -Force | Out-Null
}

Write-Host ""
Write-Host "🚀 テスト実行開始..." -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Cyan

# テスト実行関数
function Run-AITest {
    param(
        [string]$Provider,
        [string]$Model,
        [int]$Chars,
        [switch]$Padding,
        [string]$TestName
    )
    
    Write-Host ""
    Write-Host "📝 $TestName テスト実行中..." -ForegroundColor Yellow
    
    $args = @(
        "tools\ai_test_cli.py",
        "--provider", $Provider,
        "--model", $Model,
        "--chars", $Chars,
        "--repeat", "3",
        "--output", "ai_test_$($TestName.ToLower().Replace(' ', '_').Replace('-', '_'))_$($Chars)_$timestamp.json"
    )
    
    if ($Padding) {
        $args += "--padding"
    }
    
    try {
        & python @args
        Write-Host "✅ $TestName ($Chars文字) 完了" -ForegroundColor Green
    }
    catch {
        Write-Host "❌ $TestName ($Chars文字) エラー: $_" -ForegroundColor Red
    }
}

# OpenAI GPT-5 テスト
Run-AITest -Provider "openai" -Model "gpt-5" -Chars 100 -TestName "OpenAI GPT-5"
Run-AITest -Provider "openai" -Model "gpt-5" -Chars 500 -TestName "OpenAI GPT-5"
Run-AITest -Provider "openai" -Model "gpt-5" -Chars 1000 -TestName "OpenAI GPT-5"
Run-AITest -Provider "openai" -Model "gpt-5" -Chars 2000 -Padding -TestName "OpenAI GPT-5"

# OpenAI GPT-5-mini テスト
Run-AITest -Provider "openai" -Model "gpt-5-mini" -Chars 100 -TestName "OpenAI GPT-5-mini"
Run-AITest -Provider "openai" -Model "gpt-5-mini" -Chars 500 -TestName "OpenAI GPT-5-mini"
Run-AITest -Provider "openai" -Model "gpt-5-mini" -Chars 1000 -TestName "OpenAI GPT-5-mini"
Run-AITest -Provider "openai" -Model "gpt-5-mini" -Chars 2000 -Padding -TestName "OpenAI GPT-5-mini"

# OpenAI GPT-5-nano テスト
Run-AITest -Provider "openai" -Model "gpt-5-nano" -Chars 100 -TestName "OpenAI GPT-5-nano"
Run-AITest -Provider "openai" -Model "gpt-5-nano" -Chars 500 -TestName "OpenAI GPT-5-nano"
Run-AITest -Provider "openai" -Model "gpt-5-nano" -Chars 1000 -TestName "OpenAI GPT-5-nano"
Run-AITest -Provider "openai" -Model "gpt-5-nano" -Chars 2000 -Padding -TestName "OpenAI GPT-5-nano"

# OpenAI GPT-4.1 テスト
Run-AITest -Provider "openai" -Model "gpt-4.1" -Chars 100 -TestName "OpenAI GPT-4.1"
Run-AITest -Provider "openai" -Model "gpt-4.1" -Chars 500 -TestName "OpenAI GPT-4.1"
Run-AITest -Provider "openai" -Model "gpt-4.1" -Chars 1000 -TestName "OpenAI GPT-4.1"
Run-AITest -Provider "openai" -Model "gpt-4.1" -Chars 2000 -Padding -TestName "OpenAI GPT-4.1"

# OpenAI GPT-4.1-mini テスト
Run-AITest -Provider "openai" -Model "gpt-4.1-mini" -Chars 100 -TestName "OpenAI GPT-4.1-mini"
Run-AITest -Provider "openai" -Model "gpt-4.1-mini" -Chars 500 -TestName "OpenAI GPT-4.1-mini"
Run-AITest -Provider "openai" -Model "gpt-4.1-mini" -Chars 1000 -TestName "OpenAI GPT-4.1-mini"
Run-AITest -Provider "openai" -Model "gpt-4.1-mini" -Chars 2000 -Padding -TestName "OpenAI GPT-4.1-mini"

# OpenAI GPT-4.1-nano テスト
Run-AITest -Provider "openai" -Model "gpt-4.1-nano" -Chars 100 -TestName "OpenAI GPT-4.1-nano"
Run-AITest -Provider "openai" -Model "gpt-4.1-nano" -Chars 500 -TestName "OpenAI GPT-4.1-nano"
Run-AITest -Provider "openai" -Model "gpt-4.1-nano" -Chars 1000 -TestName "OpenAI GPT-4.1-nano"
Run-AITest -Provider "openai" -Model "gpt-4.1-nano" -Chars 2000 -Padding -TestName "OpenAI GPT-4.1-nano"

# OpenAI GPT-3.5-turbo テスト
Run-AITest -Provider "openai" -Model "gpt-3.5-turbo" -Chars 100 -TestName "OpenAI GPT-3.5-turbo"
Run-AITest -Provider "openai" -Model "gpt-3.5-turbo" -Chars 500 -TestName "OpenAI GPT-3.5-turbo"
Run-AITest -Provider "openai" -Model "gpt-3.5-turbo" -Chars 1000 -TestName "OpenAI GPT-3.5-turbo"
Run-AITest -Provider "openai" -Model "gpt-3.5-turbo" -Chars 2000 -Padding -TestName "OpenAI GPT-3.5-turbo"

# Gemini テスト
Run-AITest -Provider "gemini" -Model "gemini-1.5-flash" -Chars 100 -TestName "Gemini Flash"
Run-AITest -Provider "gemini" -Model "gemini-1.5-flash" -Chars 500 -TestName "Gemini Flash"
Run-AITest -Provider "gemini" -Model "gemini-1.5-flash" -Chars 1000 -TestName "Gemini Flash"
Run-AITest -Provider "gemini" -Model "gemini-1.5-flash" -Chars 2000 -Padding -TestName "Gemini Flash"

# Local LLM テスト
#Run-AITest -Provider "local_llm" -Model "llama3.2:3b" -Chars 100 -TestName "Local LLM"
#Run-AITest -Provider "local_llm" -Model "llama3.2:3b" -Chars 500 -TestName "Local LLM"
#Run-AITest -Provider "local_llm" -Model "llama3.2:3b" -Chars 1000 -TestName "Local LLM"
#Run-AITest -Provider "local_llm" -Model "llama3.2:3b" -Chars 2000 -Padding -TestName "Local LLM"

$endTime = Get-Date
$duration = $endTime - $startTime

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "✅ 全テスト完了!" -ForegroundColor Green
Write-Host "⏰ 開始時刻: $($startTime.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Blue
Write-Host "⏰ 終了時刻: $($endTime.ToString('yyyy-MM-dd HH:mm:ss'))" -ForegroundColor Blue
Write-Host "⌛ 実行時間: $($duration.ToString('hh\:mm\:ss'))" -ForegroundColor Blue
Write-Host "📂 結果ファイル: output\log\ 内を確認してください" -ForegroundColor Blue
Write-Host "================================================" -ForegroundColor Cyan

Read-Host "Enterキーを押して終了..."
