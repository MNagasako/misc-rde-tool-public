#!/usr/bin/env python3
"""
バックアップファイル安全整理スクリプト
v2.0 - 2025年8月24日
"""
import os
import shutil
from datetime import datetime
from pathlib import Path

def cleanup_backup_files():
    """バックアップファイルの安全整理"""
    project_root = Path.cwd()
    
    # 整理対象ファイル
    backup_files = [
        'BACKUP_phase_9_2_methods.py',
        'BACKUP_phase_9_3_prepare_methods.py', 
        'BACKUP_phase_9_4_create_widget.py',
        'BACKUP_ui_ai_test_phase9.py',
        'test_phase_43_data_separation.py',
        'test_phase_43_detailed.py',
        'test_phase_43_simple.py',
        'test_phase_44_fix.py',
        'test_phase_44_forms_separation.py'
    ]
    
    # アーカイブディレクトリ作成
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_dir = project_root / 'docs' / 'archive' / f'backup_cleanup_{timestamp}'
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    moved_files = []
    
    for backup_file in backup_files:
        file_path = project_root / backup_file
        if file_path.exists():
            dest_path = archive_dir / backup_file
            shutil.move(str(file_path), str(dest_path))
            moved_files.append(backup_file)
            print(f"✅ {backup_file} を {archive_dir.name} に移動")
    
    # 整理レポート作成
    report_content = f"""# バックアップファイル整理レポート
作成日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}

## 整理実行内容
- 整理対象: {len(backup_files)} ファイル
- 実際移動: {len(moved_files)} ファイル
- 移動先: {archive_dir.relative_to(project_root)}

## 移動済みファイル一覧
"""
    for file in moved_files:
        report_content += f"- {file}\n"
    
    report_content += f"""
## 整理理由
これらのファイルは以下の理由により一時的なバックアップと判断:
1. BACKUP_ プレフィックス付きファイル
2. test_phase_* 命名の一時テストファイル
3. リファクタリング作業中の重複コード削除対象

## 復元方法
必要に応じて以下の場所から復元可能:
{archive_dir.relative_to(project_root)}/
"""
    
    report_path = archive_dir / 'CLEANUP_REPORT.md'
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_content)
    
    print(f"\n📋 整理レポート作成: {report_path.relative_to(project_root)}")
    print(f"🎯 整理完了: {len(moved_files)} ファイル移動")
    
    return moved_files, archive_dir

if __name__ == "__main__":
    print("🧹 バックアップファイル安全整理開始")
    print("=" * 50)
    
    moved_files, archive_dir = cleanup_backup_files()
    
    print("=" * 50)
    print("整理完了")
