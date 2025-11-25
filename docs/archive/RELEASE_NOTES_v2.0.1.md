# RELEASE NOTES v2.0.1

リリース日: 2025-11-10

主な変更点

- トークン管理システム（TokenManager）新規実装
  - OAuth2 RefreshToken対応
  - 自動トークンリフレッシュ（QTimer 60秒間隔、5分前マージン）
  - 手動リフレッシュAPI
  - JWT有効期限解析・管理
  - マルチホスト対応（RDE/Material API）
- トークン状態表示タブ追加
  - 複数ホストのトークン一覧表示
  - 有効期限・残り時間表示
  - 手動リフレッシュボタン
  - 自動リフレッシュON/OFF切替
- DICEログイン調査ツール実装 (v1.2.0)
  - dice_login_flow_inspector.py（標準版・fragment mode）
  - dice_login_flow_inspector_query_mode.py（クエリモード版）
  - 自動ログイン機能・トークン抽出・JWT解析

移行・利用上の注意

- v2.0.0からの差分は主にトークン管理・認証機能の強化です。
- 旧バージョンの使用方法説明はREADMEに残していますが、v2.0.1の新機能は本リリースノート・CHANGELOGを参照してください。

問い合わせ

問題や不整合を発見した場合はリリースノートとREADMEを参照の上、配布元へご連絡ください。
