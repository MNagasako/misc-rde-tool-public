# ARIM RDE Tool について

## アプリ概要

**ARIM RDE Tool** は DICE/RDE システムと ARIM データポータルを統合的に操作するためのデスクトップアプリケーションです。RDE からの情報取得、ポータルへの登録、AI を用いたテキスト支援、診断ツール群など、日常業務をまとめてカバーします。

- **現在のバージョン**: v2.2.6
- **最終更新日**: 2025-12-13
- **対応 OS**: Windows 10 / 11 (FHD 1920×1080 推奨)

## 主な機能

### 🔐 認証・セッション管理
- PySide6 WebView による統合ログイン UI
 **現在のバージョン**: v2.2.7
 **最終更新日**: 2025-12-17

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

## v2.2.6 の主な更新点

| 分類 | 内容 |
| --- | --- |
| データポータル | データセットアップロード画面の取得済み画像一覧を4列テーブル化し、キャプション編集・ヘッダ固定・ソート・アップ済み表示に対応。 |
| データセット | TAGビルダーに「AI提案」タブを追加し、候補生成→採用/全て採用、リトライ提案、プロンプト/回答全文確認を実装。 |
| バージョン | REVISION/VERSION.txt/README/ヘルプ/配布物の表記を v2.2.6 に統一し、旧リリースノートを `doc_archives/release_notes_v2.2.x/` へ退避。 |

## v2.2.5 の主な更新点

| 分類 | 内容 |
| --- | --- |
| AIサジェスト | 管理ダイアログのリスト再描画を刷新し、再読込時にスペーサ破棄と内部リストの再初期化を行うことで「AI拡張設定の読み込みエラー」を根絶。 |
| テスト | `test_extension_buttons_reload_without_error` を追加し、設定保存後の再読込でボタン数・状態が完全に再構築されることをQtウィジェットテストで保証。 |
| ドキュメント | README / readme.txt / LICENSE-dist.txt / ヘルプ群 / セットアップスクリプトを v2.2.5 へ更新し、v2.2.4 リリースノートを `doc_archives/release_notes_v2.2.x/` へ退避。 |

## v2.2.4 の主な更新点

| 分類 | 内容 |
| --- | --- |
| UI | Equipment/Reports 各タブにフィルタ可能な Listing テーブルを追加し、最新JSONの再読込・件数表示・ツールチップ展開を実装 |
| Reports | ReportCacheManager/Mode を導入し、取得済みレポートのキャッシュ再利用と強制再取得をUIから切り替え可能に |
| Basic Info | `BasicInfoSearchDialog` で自分のデータセット/キーワード/機関ID+年度レンジの3モード検索を統合し、バッチ生成を高速化 |
| Equipment | FacilityListingScraper による全件ID収集と連続不在検知を実装し、設備JSON欠損の自動検出と再取得連携を強化 |

## 技術スタック

- **言語**: Python 3.13.5
- **UI**: PySide6 / QtWebEngine
- **HTTP**: `net.http_helpers` (requests + truststore)
- **データ処理**: pandas / openpyxl / numpy
- **ビルド**: PyInstaller (onedir / withtest プロファイル)

## プロジェクト体制

- **開発**: 個人開発 (MNagasako)
- **リポジトリ**: [MNagasako/misc-rde-access](https://github.com/MNagasako/misc-rde-access)

### 問い合わせ

1. アプリ右上のログ出力ボタンから `output/log/` を開き、問題の前後ログを確認してください。
2. 不具合や要望は GitHub Issues へ。再現手順・ログ・スクリーンショットの添付を推奨します。

---

このヘルプは `src/resources/docs/help/about.md` を直接編集することで即時反映されます。ビルド後も PyInstaller バンドルへ同梱されます。