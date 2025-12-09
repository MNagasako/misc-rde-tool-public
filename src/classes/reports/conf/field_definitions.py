"""
報告書機能 - フィールド定義

報告書データのExcel列定義、URL、エンドポイントなどの定数を定義します。

Version: 2.1.0
"""

# ========================================
# Excel列定義
# ========================================

EXCEL_COLUMNS = [
    "課題番号 / Project Issue Number",
    "利用課題名 / Title",
    "利用した実施機関 / Support Institute",
    "機関外・機関内の利用 / External or Internal Use",
    "横断技術領域・主",
    "横断技術領域・副",
    "重要技術領域・主",
    "重要技術領域・副",
    "キーワード / Keywords",
    "利用者名（課題申請者）/ User Name (Project Applicant)",
    "所属名 / Affiliation",
    "共同利用者氏名 / Names of Collaborators in Other Institutes Than Hub and Spoke Institutes",
    "ARIM実施機関支援担当者 / Names of Collaborators in The Hub and Spoke Institutes",
    "利用形態・主",
    "利用形態・副",
    "利用した主な設備 / Equipment Used in This Project",
    "概要（目的・用途・実施内容）/ Abstract (Aim, Use Applications and Contents)",
    "実験 / Experimental",
    "結果と考察 / Results and Discussion",
    "その他・特記事項（参考文献・謝辞等） / Remarks(References and Acknowledgements)",
    "論文・プロシーディング（DOIのあるもの） / DOI (Publication and Proceedings)",
    "口頭発表、ポスター発表および、その他の論文 / Oral Presentations etc.",
    "特許出願件数",
    "特許登録件数",
    "code",
    "key"
]

# ========================================
# URL定義
# ========================================

# ベースURL
BASE_URL = "https://nanonet.go.jp"

# 報告書一覧ページ（既存実装と整合: user_report.php）
REPORT_LIST_URL = f"{BASE_URL}/user_report.php"

# 報告書一覧ページのデフォルトクエリ（100件表示モード）
REPORT_LIST_DEFAULT_QUERY = {
    "mode": "",
    "mode2": "",
    "code": "0",
    "display_result": "2",
}

# 報告書詳細ページ（パラメータ: code, key）
REPORT_DETAIL_URL = f"{BASE_URL}/user_report.php?mode=detail&code={{code}}&key={{key}}"

# ========================================
# スクレイピング設定
# ========================================

# 並列実行数（デフォルト）
DEFAULT_MAX_WORKERS = 5

# チャンクサイズ（Excel保存の頻度）
SAVE_CHUNK_SIZE = 10

# ページネーションのCSSセレクタ
PAGINATION_SELECTOR = ".pageNavBox .pageNav a[href*='page=']"

# 1ページあたりの表示件数（display_result=2 => 100件）
REPORTS_PER_PAGE = 100

# ========================================
# 出力設定
# ========================================

# 出力ディレクトリ名
OUTPUT_DIR_NAME = "reports"

# 出力ファイル名
DEFAULT_EXCEL_FILENAME = "output.xlsx"
DEFAULT_JSON_DIRNAME = "json_data"

# バックアップディレクトリ名
BACKUP_DIR_NAME = "backups"
