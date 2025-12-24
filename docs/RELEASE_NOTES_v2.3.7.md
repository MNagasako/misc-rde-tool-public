# ARIM RDE Tool - Release Notes v2.3.7

**リリース日**: 2025年12月24日

---

## 概要

v2.3.7 は、AI連携（特に Gemini）の不安定レスポンスに対する復旧性を高め、設定画面でのSSL警告を抑制しつつ、テーマ/パス規約の準拠を進めたリリースです。

---

## 変更点（概要）

### 🤖 AI安定化 / デバッグ性向上

- Gemini: `finishReason=MAX_TOKENS` で本文 (`content.parts[].text`) が欠落/空となるケースに対し、`maxOutputTokens` を自動増量して再試行し失敗を抑制。
- AI: 実際に送受信した本文以外パラメータ（provider/model含む）を `request_params` / `response_params` として可視化し、デバッグ性を向上。

### 🌐 ネットワーク

- 設定タブの外部疎通系で `verify=False` を強制しないよう統一し、truststore/CAバンドル設定に追従。

### 🎨 UI/テーマ/パス

- 一部ハードコード色と `__file__` 依存を解消し、規約準拠とテーマ追従を改善。

---

## テスト状況

- 全テストスイートを実行し合格（環境依存の skip は継続）。

---

## ドキュメント/配布物の版数表記

- `VERSION.txt` / `README.md` / `docs/CHANGELOG.md` / `docs/RELEASE_NOTES_v2.3.7.md` 等 → v2.3.7
