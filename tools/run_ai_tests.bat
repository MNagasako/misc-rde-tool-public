@echo off
REM AI性能テスト一括実行スクリプト - ARIM RDE Tool v1.13.1
REM 複数のモデルとパラメータでAI性能テストを自動実行

echo ================================================
echo AI性能テスト一括実行スクリプト
echo ================================================

REM 仮想環境のアクティベーション（存在する場合）
if exist ".venv\Scripts\activate.bat" (
    echo 🔧 仮想環境をアクティベート中...
    call .venv\Scripts\activate.bat
)

echo.
echo 📋 テスト設定:
echo   - OpenAI: gpt-5, gpt-5-mini, gpt-5-nano, gpt-4.1, gpt-4.1-mini, gpt-4.1-nano, gpt-3.5-turbo
echo   - Gemini: gemini-1.5-flash
echo   - Local LLM: llama3.2:3b
echo   - 文字数パターン: 100, 500, 1000, 2000
echo   - 各テスト3回実行
echo.

set TIMESTAMP=%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TIMESTAMP=%TIMESTAMP: =0%

echo ⏰ 開始時刻: %date% %time%
echo 📂 結果保存先: output\log\ai_test_batch_%TIMESTAMP%.json

REM ログディレクトリ作成
if not exist "output\log" mkdir "output\log"

echo.
echo 🚀 テスト実行開始...
echo ================================================

REM OpenAI GPT-4.1 テスト
echo.
echo 📝 OpenAI GPT-4.1 テスト実行中...
python tools\ai_test_cli.py --provider openai --model gpt-4.1 --chars 100 --repeat 3 --output ai_test_gpt41_100_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-4.1 --chars 500 --repeat 3 --output ai_test_gpt41_500_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-4.1 --chars 1000 --repeat 3 --output ai_test_gpt41_1000_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-4.1 --chars 2000 --padding --repeat 3 --output ai_test_gpt41_2000_%TIMESTAMP%.json

REM OpenAI GPT-4.1-mini テスト
echo.
echo 📝 OpenAI GPT-4.1-mini テスト実行中...
python tools\ai_test_cli.py --provider openai --model gpt-4.1-mini --chars 100 --repeat 3 --output ai_test_gpt41mini_100_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-4.1-mini --chars 500 --repeat 3 --output ai_test_gpt41mini_500_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-4.1-mini --chars 1000 --repeat 3 --output ai_test_gpt41mini_1000_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-4.1-mini --chars 2000 --padding --repeat 3 --output ai_test_gpt41mini_2000_%TIMESTAMP%.json

REM OpenAI GPT-4.1-nano テスト
echo.
echo 📝 OpenAI GPT-4.1-nano テスト実行中...
python tools\ai_test_cli.py --provider openai --model gpt-4.1-nano --chars 100 --repeat 3 --output ai_test_gpt41nano_100_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-4.1-nano --chars 500 --repeat 3 --output ai_test_gpt41nano_500_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-4.1-nano --chars 1000 --repeat 3 --output ai_test_gpt41nano_1000_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-4.1-nano --chars 2000 --padding --repeat 3 --output ai_test_gpt41nano_2000_%TIMESTAMP%.json

REM OpenAI GPT-5 テスト
echo.
echo 📝 OpenAI GPT-5 テスト実行中...
python tools\ai_test_cli.py --provider openai --model gpt-5 --chars 100 --repeat 3 --output ai_test_gpt5_100_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-5 --chars 500 --repeat 3 --output ai_test_gpt5_500_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-5 --chars 1000 --repeat 3 --output ai_test_gpt5_1000_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-5 --chars 2000 --padding --repeat 3 --output ai_test_gpt5_2000_%TIMESTAMP%.json

REM OpenAI GPT-5-mini テスト
echo.
echo 📝 OpenAI GPT-5-mini テスト実行中...
python tools\ai_test_cli.py --provider openai --model gpt-5-mini --chars 100 --repeat 3 --output ai_test_gpt5mini_100_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-5-mini --chars 500 --repeat 3 --output ai_test_gpt5mini_500_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-5-mini --chars 1000 --repeat 3 --output ai_test_gpt5mini_1000_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-5-mini --chars 2000 --padding --repeat 3 --output ai_test_gpt5mini_2000_%TIMESTAMP%.json

REM OpenAI GPT-5-nano テスト
echo.
echo 📝 OpenAI GPT-5-nano テスト実行中...
python tools\ai_test_cli.py --provider openai --model gpt-5-nano --chars 100 --repeat 3 --output ai_test_gpt5nano_100_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-5-nano --chars 500 --repeat 3 --output ai_test_gpt5nano_500_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-5-nano --chars 1000 --repeat 3 --output ai_test_gpt5nano_1000_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-5-nano --chars 2000 --padding --repeat 3 --output ai_test_gpt5nano_2000_%TIMESTAMP%.json

REM OpenAI GPT-3.5-turbo テスト
echo.
echo 📝 OpenAI GPT-3.5-turbo テスト実行中...
python tools\ai_test_cli.py --provider openai --model gpt-3.5-turbo --chars 100 --repeat 3 --output ai_test_gpt35_100_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-3.5-turbo --chars 500 --repeat 3 --output ai_test_gpt35_500_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-3.5-turbo --chars 1000 --repeat 3 --output ai_test_gpt35_1000_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider openai --model gpt-3.5-turbo --chars 2000 --padding --repeat 3 --output ai_test_gpt35_2000_%TIMESTAMP%.json

REM Gemini テスト
echo.
echo 📝 Gemini テスト実行中...
python tools\ai_test_cli.py --provider gemini --model gemini-1.5-flash --chars 100 --repeat 3 --output ai_test_gemini_100_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider gemini --model gemini-1.5-flash --chars 500 --repeat 3 --output ai_test_gemini_500_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider gemini --model gemini-1.5-flash --chars 1000 --repeat 3 --output ai_test_gemini_1000_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider gemini --model gemini-1.5-flash --chars 2000 --padding --repeat 3 --output ai_test_gemini_2000_%TIMESTAMP%.json

REM Local LLM テスト（エラーハンドリング付き）
echo.
echo 📝 Local LLM テスト実行中...
python tools\ai_test_cli.py --provider local_llm --model llama3.2:3b --chars 100 --repeat 3 --output ai_test_local_100_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider local_llm --model llama3.2:3b --chars 500 --repeat 3 --output ai_test_local_500_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider local_llm --model llama3.2:3b --chars 1000 --repeat 3 --output ai_test_local_1000_%TIMESTAMP%.json
python tools\ai_test_cli.py --provider local_llm --model llama3.2:3b --chars 2000 --padding --repeat 3 --output ai_test_local_2000_%TIMESTAMP%.json

echo.
echo ================================================
echo ✅ 全テスト完了!
echo ⏰ 終了時刻: %date% %time%
echo 📂 結果ファイル: output\log\ 内を確認してください
echo ================================================

pause
