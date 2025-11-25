# ARIM RDE Tool v1.17.0 - モジュールライセンス情報

## サードパーティモジュールライセンス一覧

### 必須依存モジュール

#### GUI・ウィンドウシステム
- **PyQt5 (5.15.11)** - GPL v3 / Commercial License
  - PyQt5-Qt5 (5.15.2) - GPL v3
  - PyQt5_sip (12.17.0) - GPL v3
  - PyQtWebEngine (5.15.7) - GPL v3
  - PyQtWebEngine-Qt5 (5.15.2) - GPL v3
  - ライセンス: GPL v3 (商用利用にはCommercial Licenseが必要)
  
#### データ処理・分析
- **pandas (2.3.1)** - BSD 3-Clause License
- **numpy (2.3.2)** - BSD 3-Clause License
- **openpyxl (3.1.5)** - MIT License

#### 画像処理
- **Pillow (11.3.0)** - PIL Software License (BSD-like)

#### HTTP通信・ネットワーク
- **requests (2.32.4)** - Apache License 2.0
- **urllib3 (2.5.0)** - MIT License
- **certifi (2025.7.14)** - Mozilla Public License 2.0
- **charset-normalizer (3.4.2)** - MIT License
- **idna (3.10)** - BSD 3-Clause License

#### Web スクレイピング・パース
- **beautifulsoup4 (4.13.4)** - MIT License
- **soupsieve (2.7)** - MIT License

#### プロキシ対応・セキュリティ
- **truststore (0.9.2)** - MIT License
- **pypac (0.16.1)** - Apache License 2.0
- **PyYAML (6.0.2)** - MIT License

#### 暗号化・セキュリティ
- **pycryptodomex (3.23.0)** - BSD 2-Clause License
- **browser-cookie3 (0.20.1)** - GPL v3

#### システム・OS操作
- **psutil (7.0.0)** - BSD 3-Clause License
- **WMI (1.5.1)** - MIT License (Windows専用)
- **pywin32 (311)** - Python Software Foundation License (Windows専用)
- **pywin32-ctypes (0.2.3)** - BSD 3-Clause License

#### 日時処理
- **python-dateutil (2.9.0.post0)** - Apache License 2.0 / BSD 3-Clause
- **pytz (2025.2)** - MIT License
- **tzdata (2025.2)** - Apache License 2.0


#### 設定・環境・認証ストア
- **python-dotenv (1.1.1)** - BSD 3-Clause License
- **keyring (25.6.0)** - MIT License

#### ビルド・パッケージング
- **pyinstaller (6.15.0)** - GPL v2
- **pyinstaller-hooks-contrib (2025.8)** - GPL v2
- **altgraph (0.17.4)** - MIT License
- **pefile (2023.2.7)** - MIT License

#### 圧縮・アーカイブ
- **lz4 (4.4.4)** - BSD 3-Clause License
- **shadowcopy (0.0.4)** - MIT License

#### ユーティリティ
- **six (1.17.0)** - MIT License
- **setuptools (80.9.0)** - MIT License
- **packaging (25.0)** - Apache License 2.0 / BSD 2-Clause
- **typing_extensions (4.14.0)** - Python Software Foundation License
- **et_xmlfile (2.0.0)** - MIT License

## ライセンス分類

### ⚠️ **GPL v3 (商用利用制限あり)**
- PyQt5関連モジュール (GUI)
- browser-cookie3 (Cookieアクセス)

### ⚠️ **GPL v2 (商用利用制限あり)**
- PyInstaller関連モジュール (ビルド)

- pandas, numpy, Pillow, requests, keyring等の大部分のモジュール

## 商用利用時の注意事項

1. **PyQt5**: GPL v3のため、商用利用にはRiverbank Computing社からのCommercial Licenseの購入が必要
2. **PyInstaller**: GPL v2のため、商用配布時にはソースコード公開が必要、またはライセンス購入
3. **browser-cookie3**: GPL v3のため、商用利用時は注意が必要

## 推奨対応

### 商用利用を想定する場合
1. PyQt5 → **PySide6** (LGPL、商用利用可)への移行検討
2. PyInstaller → **cx_Freeze** / **Nuitka** (商用利用可)への移行検討
3. browser-cookie3の機能を独自実装またはMIT/BSDライセンスの代替ライブラリ使用

### オープンソース利用の場合
- 現状のライセンス構成で問題なし
- GPL準拠でソースコード公開を前提とした配布が可能
