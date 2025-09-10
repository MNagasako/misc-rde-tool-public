@echo off
REM RDE Dataset Creation Analyzer - GUI起動スクリプト
REM RDEデータセット開設機能調査ツール

echo =====================================
echo RDE Dataset Creation Analyzer
echo =====================================
echo.

cd /d "%~dp0"
cd ..

REM Python環境確認
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Pythonが見つかりません。
    echo Pythonをインストールしてください。
    pause
    exit /b 1
)

REM 必要なライブラリ確認
python -c "import PyQt5" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] PyQt5が見つかりません。
    echo pip install PyQt5 を実行してください。
    pause
    exit /b 1
)

echo [INFO] Python環境確認完了
echo.

REM GUI起動
echo [INFO] RDE Dataset Creation Analyzer GUI を起動中...
echo.
python src\tools\rde_dataset_creation_gui.py

echo.
echo [INFO] プログラムが終了しました。
pause
