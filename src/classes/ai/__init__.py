"""AI機能パッケージ - ARIM RDE Tool (REFACTOR_PLAN_01準拠)

指示書準拠の標準構造:
- core/: メインロジック(AI処理、データ管理等)
- ui/: Widget作成・画面構築
- util/: 便利機能やヘルパー（AI専用）
- conf/: 設定・デザイン・文言などの定義
"""

# 最小限の公開API - 段階的実装
__all__ = []
from config.common import REVISION as __version__

# 必要に応じて遅延インポートで実装
