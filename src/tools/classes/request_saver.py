import os
import json
from datetime import datetime

class RequestSaver:
    @staticmethod
    def save_request_result_to_file(result):
        """リクエスト結果をファイルに保存"""
        try:
            # 出力ディレクトリを確保
            from config.common import get_dynamic_file_path
            output_dir = get_dynamic_file_path('output/log')
            os.makedirs(output_dir, exist_ok=True)

            # ファイル名生成（タイムスタンプ付き）
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(output_dir, f"request_result_{timestamp}.json")

            # 結果をJSON形式で保存
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2, default=str)

            return filename
        except Exception as e:
            # 呼び出し元でログ出力することを推奨
            return None
