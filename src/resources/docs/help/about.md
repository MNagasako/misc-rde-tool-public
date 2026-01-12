# ARIM RDE Tool について

## アプリ概要

**ARIM RDE Tool** は DICE/RDE システムと ARIM データポータルを統合的に操作するためのデスクトップアプリケーションです。RDE からの情報取得、ポータルへの登録、AI を用いたテキスト支援、診断ツール群など、日常業務をまとめてカバーします。

- **現在のバージョン**: （アプリのタイトルに表示）
- **最終更新日**: 2026-01-11
- **対応 OS**: Windows 10 / 11 (FHD 1920×1080 推奨)

※ 更新点（リリースノート）は「更新履歴」タブに分離しました。


## 主な機能

### 🔐 認証・セッション管理
- PySide6 WebView による統合ログイン UI
- OAuth2 RefreshToken の自動更新 (60 秒監視 / 5 分前マージン)
- RDE / Material API のトークンを同時管理
- トークン状態タブで有効期限や残り時間を可視化

### 📊 基本情報・データ取得
- 課題番号単位の基本情報取得と JSON 永続化
- まとめ XLSX / 反映 XLSX の 2 系統レポート出力
- 並列ダウンロードとファイル単位プログレス表示
- groupOrganizations・subGroups データの完全性チェック

### 🤖 AI / 自動化
- データセット説明文の AI 提案とプロンプト編集
- ファイル内容の自動テキスト抽出 (Excel / CSV / JSON 等)
- 構造化 JSON を用いた AI テンプレート／装置チャンク連携

### 🌐 ネットワークと診断
- DIRECT / MANUAL / SOCKS5 / PAC / 自動検出モード
- truststore を利用した企業 CA / SSL 証明書統合
- 6 種類のプロキシ診断スクリプト＋統合ランナー
- MitM (Fiddler など) 環境での検証ユーティリティ

### 🎨 UI / UX
- ライト / ダークテーマ切り替え (OS テーマと連動)
- 標準ウインドウ枠のカラー連動 (Windows immersive dark mode)
- メニュー / ボタン / プログレスバーの統一スタイル
- Markdown で記述したヘルプドキュメントをそのまま表示

## 技術スタック

- **言語**: Python 3.13.5
- **UI**: PySide6 / QtWebEngine
- **HTTP**: `net.http_helpers` (requests + truststore)
- **データ処理**: pandas / openpyxl / numpy
- **ビルド**: PyInstaller (onedir / withtest プロファイル)

## プロジェクト体制

- **開発**: 個人開発 (MNagasako)
- **公開用リポジトリ**: [MNagasako/misc-rde-tool-public](https://github.com/MNagasako/misc-rde-tool-public)

### 問い合わせ

1. アプリ右上のログ出力ボタンから `output/log/` を開き、問題の前後ログを確認してください。
2. 不具合や要望は GitHub Issues へ。再現手順・ログ・スクリーンショットの添付を推奨します。

---

このヘルプは `src/resources/docs/help/about.md` を直接編集することで即時反映されます。ビルド後も PyInstaller バンドルへ同梱されます。