"""
XLSX書き出し専用ロジック
"""
import os
import time
import logging
import openpyxl
from dateutil.parser import parse as parse_datetime
from config.common import get_dynamic_file_path, INPUT_DIR, OUTPUT_DIR, OUTPUT_RDE_DIR, DATAFILES_DIR, SUBGROUP_JSON_PATH

# ロガー設定
logger = logging.getLogger(__name__)

def load_json(path):
    import json
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        print(f"[ERROR] {path}が存在しません: {abs_path}")
        return None
    with open(abs_path, "r", encoding="utf-8") as f:
        print(f"[XLSX] JSONロード成功: {abs_path}")
        return json.load(f)
def apply_basic_info_to_Xlsx_logic(bearer_token, parent=None, webview=None, ui_callback=None):
    """
    各種JSONを読み込み、XLSXの対応シートに反映（責務分離構造）
    """
    XLSX_PATH = os.path.join(INPUT_DIR, "data.xlsm")
    abs_xlsx = os.path.abspath(XLSX_PATH)
    if not os.path.exists(abs_xlsx):
        msg = f"XLSXファイルが存在しません: {abs_xlsx}"
        print(msg)
        return
    try:
        wb = openpyxl.load_workbook(abs_xlsx, keep_vba=True)
        # ... ここに各種JSONを読み込んでシートに反映する処理 ...
        wb.save(abs_xlsx)
        print(f"[INFO] XLSX書き出しに成功: {abs_xlsx}")
    except PermissionError:
        msg = (
            f"Excelファイルが他で開かれているため書き込みできません。\n"
            f"他のExcelウィンドウが開いていないか確認し、すべて閉じてから再実行してください。\n"
            f"対象: {abs_xlsx}"
        )
        try:
            from qt_compat.widgets import QMessageBox
            QMessageBox.information(None, "Excel書き込みエラー", msg)
        except Exception:
            print(msg)
        raise
    except Exception as e:
        msg = f"XLSX書き込み時に予期せぬエラーが発生しました: {e}"
        try:
            from qt_compat.widgets import QMessageBox
            QMessageBox.information(None, "Excel書き込みエラー", msg)
        except Exception:
            print(msg)
        raise


def summary_basic_info_to_Xlsx_logic(bearer_token, parent=None, webview=None, ui_callback=None, progress_callback=None):
    
    """
    各種JSONを読み込み、XLSXの対応シートに反映（責務分離構造）
    """
    import openpyxl
    from qt_compat.widgets import QMessageBox
    
    if progress_callback:
        if not progress_callback(0, 100, "XLSX書き出しを開始しています..."):
            return "キャンセルされました"
    
    XLSX_PATH = os.path.join(OUTPUT_DIR, "summary.xlsx")
    abs_xlsx = os.path.abspath(XLSX_PATH)
    logger.info(f"XLSX書き出し開始: {abs_xlsx}")
    
    def show_messagebox(method, *args, **kwargs):
        method(*args, **kwargs)
        
    if progress_callback:
        if not progress_callback(5, 100, "XLSXファイル準備中..."):
            return "キャンセルされました"
            
    if not os.path.exists(abs_xlsx):
        logger.info(f"ファイルが存在しないため新規作成: {abs_xlsx}")
        # ファイルがなければ新規作成し、シート1:概要、シート2:データ
        import openpyxl
        wb = openpyxl.Workbook()
        # 既定のシート名を「概要」に変更
        ws1 = wb.active
        ws1.title = "概要"
        # 2枚目「データ」
        ws2 = wb.create_sheet("データ")
        wb.save(abs_xlsx)
        msg = f"XLSXファイルが存在しなかったため新規作成しました: {abs_xlsx}\nシート: 概要, データ"
        #show_messagebox(QMessageBox.information, parent, "新規作成", msg)
        
    if progress_callback:
        if not progress_callback(10, 100, "ファイルアクセス権限チェック中..."):
            return "キャンセルされました"
    from qt_compat.widgets import QMessageBox
    import time
    def is_xlsx_writable(path):
        try:
            # 書き込みモードで一時的に開いてすぐ閉じる
            with open(path, 'a'):
                pass
            return True
        except PermissionError:
            return False
        except Exception:
            return True  # 存在しない場合などは書き込み可能とみなす

    def show_retry_dialog_sync():
        msg = f"Excelファイルが他で開かれているため書き込みできません。\nExcel等を閉じてから[再開]を押してください。\n対象: {abs_xlsx}"
        mbox = QMessageBox(parent)
        mbox.setIcon(QMessageBox.Warning)
        mbox.setWindowTitle("書き込みエラー")
        mbox.setText(msg)
        retry_btn = mbox.addButton("再開", QMessageBox.AcceptRole)
        cancel_btn = mbox.addButton("キャンセル", QMessageBox.RejectRole)
        mbox.setDefaultButton(retry_btn)
        mbox.exec()
        if mbox.clickedButton() == cancel_btn:
            return 'cancel'
        else:
            return 'retry'

    try:
        print(f"[XLSX] 書き込み処理開始: {abs_xlsx}")
        while True:
            if not os.path.exists(abs_xlsx) or is_xlsx_writable(abs_xlsx):
                print(f"[XLSX] 書き込み可能: {abs_xlsx}")
                # 書き込み可能になったら本処理へ
                try:
                    print(f"[XLSX] openpyxlでワークブック読込: {abs_xlsx}")
                    wb = openpyxl.load_workbook(abs_xlsx)
                    # 各種JSON→シート出力
                    print(f"[XLSX] write_summary_sheet 実行")
                    write_summary_sheet(wb, parent, False, progress_callback)  # 概要シートの書き込み

                    if progress_callback:
                        if not progress_callback(90, 100, "各シートの書き出しを実行中..."):
                            return "キャンセルされました"
                    
                    print(f"[XLSX] write_members_sheet 実行")
                    write_members_sheet(wb, parent)
                    print(f"[XLSX] write_organization_sheet 実行")
                    write_organization_sheet(wb, parent)
                    print(f"[XLSX] write_instrumentType_sheet 実行")
                    write_instrumentType_sheet(wb, parent)
                    print(f"[XLSX] write_datasets_sheet 実行")
                    write_datasets_sheet(wb, parent)
                    print(f"[XLSX] write_subgroups_sheet 実行")
                    write_subgroups_sheet(wb, parent)
                    print(f"[XLSX] write_groupDetail_sheet 実行")
                    write_groupDetail_sheet(wb, parent)

                    print(f"[XLSX] write_templates_sheet 実行")
                    write_templates_sheet(wb, parent)
                    print(f"[XLSX] write_instruments_sheet 実行")
                    write_instruments_sheet(wb, parent)
                    print(f"[XLSX] write_licenses_sheet 実行")
                    write_licenses_sheet(wb, parent)
                    print(f"[XLSX] write_entries_sheet 実行")
                    write_entries_sheet(wb, parent)

                    if progress_callback:
                        if not progress_callback(95, 100, "ファイル保存中..."):
                            return "キャンセルされました"

                    print(f"[XLSX] wb.save 実行: {abs_xlsx}")
                    wb.save(abs_xlsx)
                    
                    if progress_callback:
                        if not progress_callback(100, 100, "XLSX書き出し完了"):
                            return "キャンセルされました"
                    
                    # 完了メッセージはUI層で表示するためここでは出さない
                    print(f"[XLSX] summary_basic_info_to_Xlsx_logic: 正常終了")
                    return True
                except PermissionError:
                    print(f"[XLSX] PermissionError: ファイルが開かれている {abs_xlsx}")
                    msg = f"Excelファイルが他で開かれているため書き込みできません。\nExcelを閉じてから再実行してください。\n対象: {abs_xlsx}"
                    show_messagebox(QMessageBox.critical, parent, "書き込みエラー", msg)
                except Exception as e:
                    print(f"[XLSX] 予期せぬエラー: {e}")
                    import traceback
                    tb = traceback.format_exc()
                    msg = f"XLSX書き込み時に予期せぬエラーが発生しました:\n{e}\n{tb}"
                    show_messagebox(QMessageBox.critical, parent, "書き込みエラー", msg)
                    return False
                break
            # 開かれている場合はアラート
            print(f"[XLSX] ファイルが開かれているためリトライダイアログ表示: {abs_xlsx}")
            result = show_retry_dialog_sync()
            if result == 'cancel':
                print(f"[XLSX] ユーザーがキャンセルを選択: {abs_xlsx}")
                show_messagebox(QMessageBox.critical, parent, "書き込みエラー", "書き込みを中止しました。")
                return False
    except Exception as e:
        print(f"[XLSX] 致命的エラー: {e}")
        import traceback
        tb = traceback.format_exc()
        msg = f"まとめXLSX処理で致命的なエラーが発生しました:\n{e}\n{tb}"
        QMessageBox.critical(parent, "致命的エラー", msg)
        return False


def write_summary_sheet(wb, parent, load_data_entry_json=False, progress_callback=None):
    import json, os
    logger.info("write_summary_sheet called start")
    load_data_entry_json=False
    
    if progress_callback:
        if not progress_callback(15, 100, "JSONファイル読み込み中..."):
            return False
    def to_ymd(date_str):
        if not date_str:
            return ""
        try:
            dt = parse_datetime(date_str)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return date_str

    def get_dataset_related_info(dataset_datum):
        attr = dataset_datum.get("attributes", {})
        rel = dataset_datum.get("relationships", {})
        return {
            "id": dataset_datum.get("id", ""),
            "manager_id": rel.get("manager", {}).get("data", {}).get("id", ""),
            "owners": rel.get("dataOwners", {}).get("data", []),
            "applicant_id": rel.get("applicant", {}).get("data", {}).get("id", ""),
            "template_id": rel.get("template", {}).get("data", {}).get("id", ""),
            "instrument_id": rel.get("instruments", {}).get("data", [{}])[0].get("id", "") if rel.get("instruments", {}).get("data") else "",
            "embargoDate": to_ymd(attr.get("embargoDate", "")),
            "isAnonymized": attr.get("isAnonymized", ""),
            "description": attr.get("description", ""),
            "relatedLinks_str": "\n".join([link.get("url", "") for link in attr.get("relatedLinks", []) if isinstance(link, dict)]),
            "relatedDatasets_urls_str": "\n".join([f"https://rde.nims.go.jp/datasets/rde/{rd.get('id', '')}" for rd in rel.get("relatedDatasets", {}).get("data", []) if isinstance(rd, dict)]),
            "grantNumber": attr.get("grantNumber", ""),
            "name": attr.get("name", ""),
            "title": attr.get("subjectTitle", ""),
        }

    def write_row(value_dict, row_idx):
        dataset_id = value_dict.get("datasetId", "")
        data_entry_id = value_dict.get("dataEntryId", "")
        if data_entry_id and ("dataEntryId", data_entry_id) in manual_data_map:
            manual_restore = manual_data_map[("dataEntryId", data_entry_id)]
        elif dataset_id and ("datasetId", dataset_id) in manual_data_map:
            manual_restore = manual_data_map[("datasetId", dataset_id)]
        else:
            manual_restore = {}
        for id_ in header_ids:
            col = id_to_col[id_]
            if id_ in value_dict:
                ws.cell(row=row_idx, column=col, value=value_dict[id_])
            elif id_ in manual_restore:
                ws.cell(row=row_idx, column=col, value=manual_restore[id_])
        for id_ in value_dict:
            if id_ not in header_ids:
                header_ids.append(id_)
                col = len(header_ids)
                ws.cell(row=1, column=col, value=id_)
                ws.cell(row=2, column=col, value=id_to_label.get(id_, id_))
                ws.cell(row=row_idx, column=col, value=value_dict[id_])
                id_to_col[id_] = col

    import json, os
    print("[XLSX] write_summary_sheet called progress")

    # ワークシート取得
    ws = wb[wb.sheetnames[1]] if len(wb.sheetnames) > 1 else wb.active

    # 必要なデータのロード（parentから渡される想定。なければ適宜修正）
    # 例: subGroup_included, dataset_data, user_id_to_name, instrument_id_to_name, instrument_id_to_localid, manual_data_map, id_to_label
    # ここでは仮にparentから取得する例
    subGroup_included = getattr(parent, 'subGroup_included', [])
    dataset_data = getattr(parent, 'dataset_data', [])
    user_id_to_name = getattr(parent, 'user_id_to_name', {})
    instrument_id_to_name = getattr(parent, 'instrument_id_to_name', {})
    instrument_id_to_localid = getattr(parent, 'instrument_id_to_localid', {})
    manual_data_map = getattr(parent, 'manual_data_map', {})
    id_to_label = getattr(parent, 'id_to_label', {})

    header_ids = [
        "subGroupName", "dataset_manager_name", "dataset_applicant_name", "dataset_owner_names_str",
        "grantNumber", "title", "datasetName", "instrument_name", "instrument_local_id", "template_id",
        "datasetId", "dataEntryName", "dataEntryId", "number_of_files", "number_of_image_files",
        "date_of_dataEntry_creation", "total_file_size_MB", "dataset_embargoDate", "dataset_isAnonymized",
        "dataset_description", "dataset_relatedLinks", "dataset_relatedDatasets"
    ]
    id_to_col = {id_: idx+1 for idx, id_ in enumerate(header_ids)}

    def to_ymd(date_str):
        if not date_str:
            return ""
        try:
            dt = parse_datetime(date_str)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return date_str

    def get_dataset_related_info(dataset_datum):
        attr = dataset_datum.get("attributes", {})
        rel = dataset_datum.get("relationships", {})
        return {
            "id": dataset_datum.get("id", ""),
            "manager_id": rel.get("manager", {}).get("data", {}).get("id", ""),
            "owners": rel.get("dataOwners", {}).get("data", []),
            "applicant_id": rel.get("applicant", {}).get("data", {}).get("id", ""),
            "template_id": rel.get("template", {}).get("data", {}).get("id", ""),
            "instrument_id": rel.get("instruments", {}).get("data", [{}])[0].get("id", "") if rel.get("instruments", {}).get("data") else "",
            "embargoDate": to_ymd(attr.get("embargoDate", "")),
            "isAnonymized": attr.get("isAnonymized", ""),
            "description": attr.get("description", ""),
            "relatedLinks_str": "\n".join([link.get("url", "") for link in attr.get("relatedLinks", []) if isinstance(link, dict)]),
            "relatedDatasets_urls_str": "\n".join([f"https://rde.nims.go.jp/datasets/rde/{rd.get('id', '')}" for rd in rel.get("relatedDatasets", {}).get("data", []) if isinstance(rd, dict)]),
            "grantNumber": attr.get("grantNumber", ""),
            "name": attr.get("name", ""),
            "title": attr.get("subjectTitle", ""),
        }

    def write_row(value_dict, row_idx):
        dataset_id = value_dict.get("datasetId", "")
        data_entry_id = value_dict.get("dataEntryId", "")
        if data_entry_id and ("dataEntryId", data_entry_id) in manual_data_map:
            manual_restore = manual_data_map[("dataEntryId", data_entry_id)]
        elif dataset_id and ("datasetId", dataset_id) in manual_data_map:
            manual_restore = manual_data_map[("datasetId", dataset_id)]
        else:
            manual_restore = {}
        for id_ in header_ids:
            col = id_to_col[id_]
            if id_ in value_dict:
                ws.cell(row=row_idx, column=col, value=value_dict[id_])
            elif id_ in manual_restore:
                ws.cell(row=row_idx, column=col, value=manual_restore[id_])
        for id_ in value_dict:
            if id_ not in header_ids:
                header_ids.append(id_)
                col = len(header_ids)
                ws.cell(row=1, column=col, value=id_)
                ws.cell(row=2, column=col, value=id_to_label.get(id_, id_))
                ws.cell(row=row_idx, column=col, value=value_dict[id_])
                id_to_col[id_] = col

    # ヘッダー行の書き込み
    for idx, id_ in enumerate(header_ids):
        ws.cell(row=1, column=idx+1, value=id_)
        ws.cell(row=2, column=idx+1, value=id_to_label.get(id_, id_))

    row_idx = 3
    # --- 進捗集計用 ---
    # 事前に全データセットのdataEntry JSONファイル数・エントリ数を集計
    entry_json_files = []
    entry_total_count = 0
    for dataset in dataset_data:
        ds_info = get_dataset_related_info(dataset)
        dataEntry_path = os.path.join(OUTPUT_RDE_DIR, "data", "dataEntry", f"{ds_info['id']}.json")
        if load_data_entry_json and os.path.exists(dataEntry_path):
            entry_json_files.append(dataEntry_path)
            try:
                entry_json = load_json(dataEntry_path)
                entry_count = len(entry_json.get("data", []))
            except Exception:
                entry_count = 0
            entry_total_count += entry_count
        else:
            entry_total_count += 1
    print(f"[PROGRESS] 全データセット: {len(dataset_data)}、dataEntry JSONファイル: {len(entry_json_files)}、エントリ総数: {entry_total_count}")
    processed_entries = 0
    start_time = time.time()
    for subGroup in subGroup_included:
        if subGroup.get("type") != "group":
            continue
        subGroup_attr = subGroup.get("attributes", {})
        subGroup_name = subGroup_attr.get("name", "")
        subGroup_subjects = subGroup_attr.get("subjects", {})
        for subject in subGroup_subjects:
            grantNumber = subject.get("grantNumber", "") if isinstance(subject, dict) else ""
            title = subject.get("title", "") if isinstance(subject, dict) else ""
            for dataset in dataset_data:
                ds_info = get_dataset_related_info(dataset)
                if ds_info["grantNumber"] != grantNumber:
                    continue
                manager_name = user_id_to_name.get(ds_info["manager_id"], "未設定" if ds_info["manager_id"] in [None, ""] else "")
                applicant_name = user_id_to_name.get(ds_info["applicant_id"], "")
                owner_names = [user_id_to_name.get(owner.get("id", ""), "") for owner in ds_info["owners"] if owner.get("id", "")]
                owner_names_str = "\n".join([n for n in owner_names if n])
                instrument_name = instrument_id_to_name.get(ds_info["instrument_id"], "")
                instrument_local_id = instrument_id_to_localid.get(ds_info["instrument_id"], "")
                dataset_url = f"https://rde.nims.go.jp/datasets/rde/{ds_info['id']}"
                total_file_size_MB = ""
                dataEntry_data = []
                dataEntry_included = []
                if load_data_entry_json == True:
                    print(f"[XLSX] dataEntry JSONロード for subGroup: {ds_info['id']}")
                    dataEntry_path = os.path.join(OUTPUT_RDE_DIR, "data", "dataEntry", f"{ds_info['id']}.json")
                    dataEntry_json = load_json(dataEntry_path)
                    if not dataEntry_json:
                        print(f"[ERROR] dataEntry JSONが存在しません: {dataEntry_path} for dataset_id={ds_info['id']}")
                        continue
                    dataEntry_data = dataEntry_json.get("data", [])
                    dataEntry_included = dataEntry_json.get("included", [])
                    total_file_size = sum(
                        inc.get("attributes", {}).get("fileSize", 0)
                        for inc in dataEntry_included if inc.get("type") == "file"
                    )
                    total_file_size_MB = total_file_size / (1024 * 1024) if total_file_size else 0
                if dataEntry_data:
                    for entry in dataEntry_data:
                        entry_attr = entry.get("attributes", {})
                        dataEntry_name = entry_attr.get("name", "")
                        dataEntry_id = entry.get("id", "")
                        number_of_files = entry_attr.get("numberOfFiles", "")
                        number_of_image_files = entry_attr.get("numberOfImageFiles", "")
                        date_of_dataEntry_creation = entry_attr.get("created", "")
                        value_dict = {
                            "subGroupName": subGroup_name,
                            "dataset_manager_name": manager_name,
                            "dataset_applicant_name": applicant_name,
                            "dataset_owner_names_str": owner_names_str,
                            "grantNumber": grantNumber,
                            "title": title,
                            "datasetName": ds_info["name"],
                            "instrument_name": instrument_name,
                            "instrument_local_id": instrument_local_id,
                            "template_id": ds_info["template_id"],
                            "datasetId": dataset_url,
                            "dataEntryName": dataEntry_name,
                            "dataEntryId": dataEntry_id,
                            "number_of_files": number_of_files,
                            "number_of_image_files": number_of_image_files,
                            "date_of_dataEntry_creation": to_ymd(date_of_dataEntry_creation),
                            "total_file_size_MB": total_file_size_MB,
                            "dataset_embargoDate": ds_info["embargoDate"],
                            "dataset_isAnonymized": ds_info["isAnonymized"],
                            "dataset_description": ds_info["description"],
                            "dataset_relatedLinks": ds_info["relatedLinks_str"],
                            "dataset_relatedDatasets": ds_info["relatedDatasets_urls_str"],
                            # --- ファイルタイプ集計関連 ---
                            "filetype_MAIN_IMAGE_count": 0,
                            "filetype_MAIN_IMAGE_size": 0,
                            "filetype_STRUCTURED_count": 0,
                            "filetype_STRUCTURED_size": 0,
                            "filetype_THUMBNAIL_count": 0,
                            "filetype_THUMBNAIL_size": 0,
                            "filetype_META_count": 0,
                            "filetype_META_size": 0,
                            "filetype_OTHER_count": 0,
                            "filetype_OTHER_size": 0,
                            "filetype_total_count": 0,
                            "filetype_total_size": 0,
                        }
                        # ...existing code...
                        processed_entries += 1
                        if processed_entries % 10 == 0 or processed_entries == entry_total_count:
                            elapsed = time.time() - start_time
                            avg_time = elapsed / processed_entries if processed_entries else 0
                            remaining = entry_total_count - processed_entries
                            est_remaining = avg_time * remaining
                            print(f"[PROGRESS] {processed_entries}/{entry_total_count} entries processed ({elapsed:.1f}s elapsed, 残り推定 {est_remaining:.1f}s)")
                            # プログレスバー更新
                            ui_callback_func = None
                            if callable(locals().get('ui_callback', None)):
                                ui_callback_func = locals()['ui_callback']
                            elif hasattr(parent, 'ui_callback') and callable(parent.ui_callback):
                                ui_callback_func = parent.ui_callback
                            if ui_callback_func:
                                ui_callback_func(progress=processed_entries, total=entry_total_count, elapsed=elapsed, finished=False)
    print(f"[PROGRESS] 完了: {processed_entries}/{entry_total_count} entries ({time.time()-start_time:.1f}s)")
    # 完了時にプログレスバーを100%に
    elapsed = time.time() - start_time
    ui_callback_func = None
    if callable(locals().get('ui_callback', None)):
        ui_callback_func = locals()['ui_callback']
    elif hasattr(parent, 'ui_callback') and callable(parent.ui_callback):
        ui_callback_func = parent.ui_callback
    if ui_callback_func:
        ui_callback_func(progress=entry_total_count, total=entry_total_count, elapsed=elapsed, finished=True)
    
    if progress_callback:
        if not progress_callback(95, 100, "XLSX書き出し完了"):
            return "キャンセルされました"
    
    #logger.info("XLSX書き出し処理完了")
    #return "書き出し完了"

# --- 各シート出力関数 ---
    import json, os
    print("[XLSX] write_summary_sheet called")

    def load_json(path):
        abs_path = os.path.abspath(path)
        if not os.path.exists(abs_path):
            print(f"[ERROR] {path}が存在しません: {abs_path}")
            return None
        with open(abs_path, "r", encoding="utf-8") as f:
            print(f"[XLSX] JSONロード成功: {abs_path}")
            return json.load(f)

    # 各種JSONロード（静的定数を使用）
    from config.common import SUBGROUP_JSON_PATH, DATASET_JSON_PATH, INSTRUMENTS_JSON_PATH, TEMPLATE_JSON_PATH
    
    sub_group_json = load_json(SUBGROUP_JSON_PATH)
    dataset_json = load_json(DATASET_JSON_PATH)
    instruments_json = load_json(INSTRUMENTS_JSON_PATH)
    templates_json = load_json(TEMPLATE_JSON_PATH)
    if not all([sub_group_json, dataset_json, instruments_json, templates_json]):
        print
        return

    subGroup_included = sub_group_json.get("included", [])
    dataset_data = dataset_json.get("data", [])
    instruments_data = instruments_json.get("data", [])

    # --- 3層構造ヘッダ定義 ---
    HEADER_DEF = [
        {"id": "subGroupName", "label": "サブグループ名"},
        {"id": "dataset_manager_name", "label": "管理者名"},
        {"id": "dataset_applicant_name", "label": "申請者名"},
        {"id": "dataset_owner_names_str", "label": "オーナー名リスト"},
        {"id": "grantNumber", "label": "課題番号"},
        {"id": "title", "label": "課題名"},
        {"id": "datasetName", "label": "データセット名"},
        {"id": "instrument_name", "label": "装置名"},
        {"id": "instrument_local_id", "label": "装置 ID"},
        {"id": "template_id", "label": "テンプレートID"},
        {"id": "datasetId", "label": "データセットID"},
        {"id": "dataEntryName", "label": "データエントリ名"},
        {"id": "dataEntryId", "label": "データエントリID"},
        {"id": "number_of_files", "label": "ファイル数"},
        {"id": "number_of_image_files", "label": "画像ファイル数"},
        {"id": "date_of_dataEntry_creation", "label": "データエントリ作成日"},
        {"id": "total_file_size_MB", "label": "ファイル合計サイズ(MB)"},
        {"id": "dataset_embargoDate", "label": "エンバーゴ日"},
        {"id": "dataset_isAnonymized", "label": "匿名化"},
        {"id": "dataset_description", "label": "データセット説明"},
        {"id": "dataset_relatedLinks", "label": "関連リンク"},
        {"id": "dataset_relatedDatasets", "label": "関連データセット"},
        # --- ファイルタイプ集計ヘッダ ---
        {"id": "filetype_MAIN_IMAGE_count", "label": "MAIN_IMAGEファイル数"},
        {"id": "filetype_MAIN_IMAGE_size", "label": "MAIN_IMAGE合計サイズ"},
        {"id": "filetype_STRUCTURED_count", "label": "STRUCTUREDファイル数"},
        {"id": "filetype_STRUCTURED_size", "label": "STRUCTURED合計サイズ"},
        {"id": "filetype_THUMBNAIL_count", "label": "THUMBNAILファイル数"},
        {"id": "filetype_THUMBNAIL_size", "label": "THUMBNAIL合計サイズ"},
        {"id": "filetype_META_count", "label": "METAファイル数"},
        {"id": "filetype_META_size", "label": "META合計サイズ"},
        {"id": "filetype_OTHER_count", "label": "OTHERファイル数"},
        {"id": "filetype_OTHER_size", "label": "OTHER合計サイズ"},
        {"id": "filetype_total_count", "label": "ファイル総数"},
        {"id": "filetype_total_size", "label": "ファイル総サイズ"},
    ]
    # instrument_local_id列にはinstruments.jsonのattributes.programs[].localIdを出力
    print("[XLSX] instruments_dataからinstrument_id_to_localidを作成")
    instrument_id_to_localid = {}
    for inst in instruments_data:
        inst_id = inst.get("id")
        programs = inst.get("attributes", {}).get("programs", [])
        # 複数programsがある場合はカンマ区切りで連結
        local_ids = [prog.get("localId", "") for prog in programs if prog.get("localId")]
        if inst_id and local_ids:
            instrument_id_to_localid[inst_id] = ",".join(local_ids)
    SHEET_NAME = "summary"
    print(f"[XLSX] シート名: {SHEET_NAME}")
    
    if SHEET_NAME in wb.sheetnames:
        print(f"[XLSX] シートが既に存在: {SHEET_NAME}")
        ws = wb[SHEET_NAME]
        # 既存ヘッダー行（1行目）を取得
        existing_id_row = [cell.value for cell in ws[1]] if ws.max_row >= 1 else []
    else:
        print(f"[XLSX] シートが存在しないため新規作成: {SHEET_NAME}")
        ws = wb.create_sheet(SHEET_NAME)
        existing_id_row = []
    print(f"[XLSX] 既存ヘッダー行: {existing_id_row}")
    # 既存ID列の順番を優先し、なければHEADER_DEF順で追加（空文字列やNoneは除外）
    header_ids = []
    id_to_label = {coldef["id"]: coldef["label"] for coldef in HEADER_DEF}
    if existing_id_row and any(existing_id_row):
        # 既存ヘッダーの順番（空文字列やNoneは除外）
        header_ids = [id_ for id_ in existing_id_row if id_ not in (None, "") and str(id_).strip() != ""]
        # HEADER_DEFにあるが既存ヘッダーにないものを追加
        for coldef in HEADER_DEF:
            if coldef["id"] not in header_ids:
                header_ids.append(coldef["id"])
    else:
        header_ids = [coldef["id"] for coldef in HEADER_DEF]
    # 1行目:ID（空値列は除外済みだが念のため）
    for col_idx, id_ in enumerate(header_ids, 1):
        if id_ not in (None, "") and str(id_).strip() != "":
            ws.cell(row=1, column=col_idx, value=id_)
    # 2行目:ラベル
    for col_idx, id_ in enumerate(header_ids, 1):
        if id_ not in (None, "") and str(id_).strip() != "":
            ws.cell(row=2, column=col_idx, value=id_to_label.get(id_, id_))
    id_to_col = {id_: idx+1 for idx, id_ in enumerate(header_ids) if id_ not in (None, "") and str(id_).strip() != ""}
    print(f"[XLSX] ヘッダーID: {header_ids}")   
    # 既存データの保存（3行目以降）
    # datasetId, dataEntryId をキーに、手動列（HEADER_DEFにない列）の値を保存
    manual_col_ids = [id_ for id_ in header_ids if id_ not in [coldef["id"] for coldef in HEADER_DEF] and id_ not in (None, "") and str(id_).strip() != ""]
    manual_data_map = {}  # key: ("dataEntryId", id) or ("datasetId", id) -> {manual_col: value, ...}
    for row in ws.iter_rows(min_row=3, max_row=ws.max_row, max_col=len(header_ids)):
        # header_idsとrowの長さが異なる場合も安全にペア化
        row_dict = {id_: cell.value for id_, cell in zip(header_ids, row) if id_ not in (None, "") and str(id_).strip() != ""}
        dataset_id = row_dict.get("datasetId", "")
        data_entry_id = row_dict.get("dataEntryId", "")
        if data_entry_id:
            manual_data_map[("dataEntryId", data_entry_id)] = {col: row_dict.get(col, None) for col in manual_col_ids if col not in (None, "") and str(col).strip() != ""}
        elif dataset_id:
            manual_data_map[("datasetId", dataset_id)] = {col: row_dict.get(col, None) for col in manual_col_ids if col not in (None, "") and str(col).strip() != ""}
    # 既存データを一旦全削除（3行目以降）
    if ws.max_row >= 3:
        ws.delete_rows(3, ws.max_row - 2)
    print(f"[XLSX] 既存データを削除: 3行目以降")
    # ユーザーID→名前辞書
    user_id_to_name = {user.get("id"): user.get("attributes", {}).get("userName", "") for user in subGroup_included if user.get("type") == "user"}
    instrument_id_to_name = {inst.get("id"): inst.get("attributes", {}).get("nameJa", "") for inst in instruments_data}

    from dateutil.parser import parse as parse_datetime
    def to_ymd(date_str):
        if not date_str:
            return ""
        try:
            dt = parse_datetime(date_str)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return date_str

    def get_dataset_related_info(dataset_datum):
        attr = dataset_datum.get("attributes", {})
        rel = dataset_datum.get("relationships", {})
        return {
            "id": dataset_datum.get("id", ""),
            "manager_id": rel.get("manager", {}).get("data", {}).get("id", ""),
            "owners": rel.get("dataOwners", {}).get("data", []),
            "applicant_id": rel.get("applicant", {}).get("data", {}).get("id", ""),
            "template_id": rel.get("template", {}).get("data", {}).get("id", ""),
            "instrument_id": rel.get("instruments", {}).get("data", [{}])[0].get("id", "") if rel.get("instruments", {}).get("data") else "",
            "embargoDate": to_ymd(attr.get("embargoDate", "")),
            "isAnonymized": attr.get("isAnonymized", ""),
            "description": attr.get("description", ""),
            "relatedLinks_str": "\n".join([link.get("url", "") for link in attr.get("relatedLinks", []) if isinstance(link, dict)]),
            "relatedDatasets_urls_str": "\n".join([f"https://rde.nims.go.jp/datasets/rde/{rd.get('id', '')}" for rd in rel.get("relatedDatasets", {}).get("data", []) if isinstance(rd, dict)]),
            "grantNumber": attr.get("grantNumber", ""),
            "name": attr.get("name", ""),
            "title": attr.get("subjectTitle", ""),
            
        }
    
    row_idx = 3
    logger.info("サブグループとデータセットの関連情報を処理開始")
    
    # プログレス計算用
    total_subgroups = len([sg for sg in subGroup_included if sg.get("type") == "group"])
    total_datasets = len(dataset_data)
    processed_items = 0
    estimated_total = 0
    
    # 概算の処理件数を計算
    for subGroup in subGroup_included:
        if subGroup.get("type") != "group":
            continue
        subGroup_attr = subGroup.get("attributes", {})
        subGroup_subjects = subGroup_attr.get("subjects", {})
        for subject in subGroup_subjects:
            estimated_total += len(dataset_data)
    
    if progress_callback:
        if not progress_callback(20, 100, f"データ行処理開始 (推定処理数: {estimated_total})"):
            return False
    
    subgroup_idx = 0
    for subGroup in subGroup_included:
        if subGroup.get("type") != "group":
            continue
            
        subgroup_idx += 1
        subGroup_attr = subGroup.get("attributes", {})
        subGroup_name = subGroup_attr.get("name", "")
        subGroup_subjects = subGroup_attr.get("subjects", {})
        
        subject_idx = 0
        for subject in subGroup_subjects:
            subject_idx += 1
            grantNumber = subject.get("grantNumber", "") if isinstance(subject, dict) else ""
            title = subject.get("title", "") if isinstance(subject, dict) else ""
            
            # プログレス更新
            if progress_callback:
                progress_percent = 20 + int((processed_items / max(estimated_total, 1)) * 70)
                message = f"処理中... サブグループ {subgroup_idx}/{total_subgroups}, 課題 {subject_idx}, 行 {row_idx - 2}"
                if not progress_callback(progress_percent, 100, message):
                    return False
            
            for dataset in dataset_data:
                processed_items += 1
                ds_info = get_dataset_related_info(dataset)
                if ds_info["grantNumber"] != grantNumber:
                    continue
                manager_name = user_id_to_name.get(ds_info["manager_id"], "未設定" if ds_info["manager_id"] in [None, ""] else "")
                applicant_name = user_id_to_name.get(ds_info["applicant_id"], "")
                owner_names = [user_id_to_name.get(owner.get("id", ""), "") for owner in ds_info["owners"] if owner.get("id", "")]
                owner_names_str = "\n".join([n for n in owner_names if n])
                instrument_name = instrument_id_to_name.get(ds_info["instrument_id"], "")
                instrument_local_id = instrument_id_to_localid.get(ds_info["instrument_id"], "")
                dataset_url = f"https://rde.nims.go.jp/datasets/rde/{ds_info['id']}"

                dataEntry_path = os.path.join(OUTPUT_RDE_DIR, "data", "dataEntry", f"{ds_info['id']}.json")
                
                dataEntry_json = load_json(dataEntry_path)
                print(f"[XLSX] dataEntry JSONロード for dataset: {ds_info['id']}")

                if not dataEntry_json:
                    print(f"[ERROR] dataEntry JSONが存在しません: {dataEntry_path} for dataset_id={ds_info['id']}" )
                    continue
                dataEntry_data = dataEntry_json.get("data", [])

                dataEntry_included = dataEntry_json.get("included", [])
                # --- ファイルタイプごとの合計サイズ・ファイル数集計 ---
                # プリセットファイルタイプ
                PRESET_FILETYPES = [
                    "MAIN_IMAGE", "STRUCTURED", "THUMBNAIL", "META"
                ]
                filetype_stats = {ftype: {"count": 0, "size": 0} for ftype in PRESET_FILETYPES}
                filetype_stats["OTHER"] = {"count": 0, "size": 0}
                total_size = 0
                total_count = 0
                for inc in dataEntry_included:
                    if inc.get("type") != "file":
                        continue
                    attr = inc.get("attributes", {})
                    ftype = attr.get("fileType", "OTHER")
                    fsize = attr.get("fileSize", 0)
                    if ftype not in PRESET_FILETYPES:
                        ftype = "OTHER"
                    filetype_stats[ftype]["count"] += 1
                    filetype_stats[ftype]["size"] += fsize
                    total_size += fsize
                    total_count += 1
                filetype_stats["total"] = {"count": total_count, "size": total_size}
                # 既存のtotal_file_size_MBも維持
                total_file_size = total_size
                total_file_size_MB = total_file_size / (1024 * 1024) if total_file_size else 0
                # 必要ならwrite_rowのvalue_dictにfiletype_statsを追加可能

                def write_row(value_dict):
                    # 既存列にデータがなければ既存値を維持
                    # datasetId, dataEntryIdで手動列データを復元
                    dataset_id = value_dict.get("datasetId", "")
                    data_entry_id = value_dict.get("dataEntryId", "")
                    if data_entry_id and ("dataEntryId", data_entry_id) in manual_data_map:
                        manual_restore = manual_data_map[("dataEntryId", data_entry_id)]
                    elif dataset_id and ("datasetId", dataset_id) in manual_data_map:
                        manual_restore = manual_data_map[("datasetId", dataset_id)]
                    else:
                        manual_restore = {}
                    for id_ in header_ids:
                        col = id_to_col[id_]
                        if id_ in value_dict:
                            ws.cell(row=row_idx, column=col, value=value_dict[id_])
                        elif id_ in manual_restore:
                            ws.cell(row=row_idx, column=col, value=manual_restore[id_])
                        else:
                            # 既存値維持（openpyxlは新規行はNoneなので何もしない）
                            pass
                    # value_dictにのみ存在する新規IDは末尾に追加
                    for id_ in value_dict:
                        if id_ not in header_ids:
                            header_ids.append(id_)
                            col = len(header_ids)
                            ws.cell(row=1, column=col, value=id_)
                            ws.cell(row=2, column=col, value=id_to_label.get(id_, id_))
                            ws.cell(row=row_idx, column=col, value=value_dict[id_])
                            id_to_col[id_] = col

                # 複数データエントリ対応
                if dataEntry_data:
                    for entry in dataEntry_data:
                        entry_attr = entry.get("attributes", {})
                        dataEntry_name = entry_attr.get("name", "")
                        dataEntry_id = entry.get("id", "")
                        number_of_files = entry_attr.get("numberOfFiles", "")
                        number_of_image_files = entry_attr.get("numberOfImageFiles", "")
                        date_of_dataEntry_creation = entry_attr.get("created", "")
                        # entry_idに紐づくファイルのみ集計
                        PRESET_FILETYPES = ["MAIN_IMAGE", "STRUCTURED", "THUMBNAIL", "META"]
                        entry_filetype_stats = {ftype: {"count": 0, "size": 0} for ftype in PRESET_FILETYPES}
                        entry_filetype_stats["OTHER"] = {"count": 0, "size": 0}
                        total_size = 0
                        total_count = 0
                        for inc in dataEntry_included:
                            if inc.get("type") != "file":
                                continue
                            attr = inc.get("attributes", {})
                            ftype = attr.get("fileType", "OTHER")
                            fsize = attr.get("fileSize", 0)
                            file_id = inc.get("id", "")
                            # relationships.files.data の id リストに含まれるファイルのみ集計
                            entry_file_ids = [f.get("id", "") for f in entry.get("relationships", {}).get("files", {}).get("data", [])]
                            if file_id not in entry_file_ids:
                                continue
                            if ftype not in PRESET_FILETYPES:
                                ftype = "OTHER"
                            entry_filetype_stats[ftype]["count"] += 1
                            entry_filetype_stats[ftype]["size"] += fsize
                            total_size += fsize
                            total_count += 1
                        entry_filetype_stats["total"] = {"count": total_count, "size": total_size}
                        value_dict = {
                            "subGroupName": subGroup_name,
                            "dataset_manager_name": manager_name,
                            "dataset_applicant_name": applicant_name,
                            "dataset_owner_names_str": owner_names_str,
                            "grantNumber": grantNumber,
                            "title": title,
                            "datasetName": ds_info["name"],
                            "instrument_name": instrument_name,
                            "instrument_local_id": instrument_local_id,
                            "template_id": ds_info["template_id"],
                            "datasetId": dataset_url,
                            "dataEntryName": dataEntry_name,
                            "dataEntryId": dataEntry_id,
                            "number_of_files": number_of_files,
                            "number_of_image_files": number_of_image_files,
                            "date_of_dataEntry_creation": to_ymd(date_of_dataEntry_creation),
                            "total_file_size_MB": total_size / (1024 * 1024) if total_size else 0,
                            "dataset_embargoDate": ds_info["embargoDate"],
                            "dataset_isAnonymized": ds_info["isAnonymized"],
                            "dataset_description": ds_info["description"],
                            "dataset_relatedLinks": ds_info["relatedLinks_str"],
                            "dataset_relatedDatasets": ds_info["relatedDatasets_urls_str"],
                            # ファイルタイプごとの集計値を追加
                            "filetype_MAIN_IMAGE_count": entry_filetype_stats["MAIN_IMAGE"]["count"],
                            "filetype_MAIN_IMAGE_size": entry_filetype_stats["MAIN_IMAGE"]["size"],
                            "filetype_STRUCTURED_count": entry_filetype_stats["STRUCTURED"]["count"],
                            "filetype_STRUCTURED_size": entry_filetype_stats["STRUCTURED"]["size"],
                            "filetype_THUMBNAIL_count": entry_filetype_stats["THUMBNAIL"]["count"],
                            "filetype_THUMBNAIL_size": entry_filetype_stats["THUMBNAIL"]["size"],
                            "filetype_META_count": entry_filetype_stats["META"]["count"],
                            "filetype_META_size": entry_filetype_stats["META"]["size"],
                            "filetype_OTHER_count": entry_filetype_stats["OTHER"]["count"],
                            "filetype_OTHER_size": entry_filetype_stats["OTHER"]["size"],
                            "filetype_total_count": entry_filetype_stats["total"]["count"],
                            "filetype_total_size": entry_filetype_stats["total"]["size"],
                        }
                        write_row(value_dict)
                        row_idx += 1
                else:
                    # データエントリがない場合も空で1行出す
                    value_dict = {
                        "subGroupName": subGroup_name,
                        "dataset_manager_name": manager_name,
                        "dataset_applicant_name": applicant_name,
                        "dataset_owner_names_str": owner_names_str,
                        "grantNumber": grantNumber,
                        "title": title,
                        "datasetName": ds_info["name"],
                        "instrument_name": instrument_name,
                        "instrument_local_id": instrument_local_id,
                        "template_id": ds_info["template_id"],
                        "datasetId": dataset_url,
                        "dataEntryName": "",
                        "dataEntryId": "",
                        "number_of_files": "",
                        "number_of_image_files": "",
                        "date_of_dataEntry_creation": "",
                        "total_file_size_MB": total_file_size_MB,
                        "dataset_embargoDate": ds_info["embargoDate"],
                        "dataset_isAnonymized": ds_info["isAnonymized"],
                        "dataset_description": ds_info["description"],
                        "dataset_relatedLinks": ds_info["relatedLinks_str"],
                        "dataset_relatedDatasets": ds_info["relatedDatasets_urls_str"],
                        # ファイルタイプごとの集計値を追加
                        "filetype_MAIN_IMAGE_count": filetype_stats["MAIN_IMAGE"]["count"],
                        "filetype_MAIN_IMAGE_size": filetype_stats["MAIN_IMAGE"]["size"],
                        "filetype_STRUCTURED_count": filetype_stats["STRUCTURED"]["count"],
                        "filetype_STRUCTURED_size": filetype_stats["STRUCTURED"]["size"],
                        "filetype_THUMBNAIL_count": filetype_stats["THUMBNAIL"]["count"],
                        "filetype_THUMBNAIL_size": filetype_stats["THUMBNAIL"]["size"],
                        "filetype_META_count": filetype_stats["META"]["count"],
                        "filetype_META_size": filetype_stats["META"]["size"],
                        "filetype_OTHER_count": filetype_stats["OTHER"]["count"],
                        "filetype_OTHER_size": filetype_stats["OTHER"]["size"],
                        "filetype_total_count": filetype_stats["total"]["count"],
                        "filetype_total_size": filetype_stats["total"]["size"],
                    }
                    write_row(value_dict)
                    row_idx += 1



# --- 各シート出力関数 ---
def write_members_sheet(wb, parent):
    import json, os
    abs_json = os.path.abspath(SUBGROUP_JSON_PATH)
    if not os.path.exists(abs_json):
        return
    with open(abs_json, "r", encoding="utf-8") as f:
        sub_group = json.load(f)
    users = [item for item in sub_group.get("included", []) if item.get("type") == "user"]
    HEADER_ROW = ["userId", "userName", "familyName", "givenName", "familyNameKanji", "givenNameKanji", "organizationName", "emailAddress", "isDeleted"]
    if "member" in wb.sheetnames:
        ws = wb["member"]
        ws.delete_rows(1, ws.max_row)
        ws.append(HEADER_ROW)
    else:
        ws = wb.create_sheet("member")
        ws.append(HEADER_ROW)
    for user in users:
        attr = user.get("attributes", {})
        ws.append([
            user.get("id", ""),
            attr.get("userName", ""),
            attr.get("familyName", ""),
            attr.get("givenName", ""),
            attr.get("familyNameKanji", ""),
            attr.get("givenNameKanji", ""),
            attr.get("organizationName", ""),
            attr.get("emailAddress", ""),
            attr.get("isDeleted", False)
        ])

# 今後拡張用の関数枠
def write_datasets_sheet(wb, parent):
    import json, os
    JSON_PATH = os.path.join(OUTPUT_RDE_DIR, "data", "dataset.json")
    abs_json = os.path.abspath(JSON_PATH)
    print(f"[DEBUG] write_datasets_sheet: JSON_PATH={JSON_PATH}, abs_json={abs_json}")
    if not os.path.exists(abs_json):
        return
    with open(abs_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    datasets = data.get("data", [])
    HEADER_ROW = [
        "id", "datasetType", "grantNumber", "subjectTitle", "name", "description", "contact",
        "dataListingType", "usesInstrument", "isOpen", "openAt", "embargoDate", "isAnonymized",
        "created", "modified", "managerId", "ownerId", "templateId", "instrumentId"]
    SHEET_NAME = "datasets"
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        ws.delete_rows(1, ws.max_row)
        ws.append(HEADER_ROW)
    else:
        ws = wb.create_sheet(SHEET_NAME)
        ws.append(HEADER_ROW)
    import re
    def safe_str(val):
        try:
            if val is None:
                return "!!NULL!!"
            s = str(val)
            # 改行・制御文字（ASCII 0-31, 127）を除去
            s = re.sub(r"[\x00-\x1F\x7F]", " ", s)
            # 連続する空白を1つに
            s = re.sub(r" +", " ", s)
            # 先頭・末尾の空白除去
            return s.strip()
        except Exception:
            return "!!ERROR!!"

    for ds in datasets:
        try:
            attr = ds.get("attributes", {})
            rel = ds.get("relationships", {})
           

            templateId = ""
            template_data = rel.get("template", {}).get("data")
            if isinstance(template_data, dict):
                templateId = template_data.get("id", "")

            instrumentId = ""
            instruments = rel.get("instruments", {}).get("data", [])
            if isinstance(instruments, list) and instruments:
                instrument = instruments[0]
                if isinstance(instrument, dict):
                    instrumentId = instrument.get("id", "")

            # managerId（managerのid)
            managerId = "!!"
            m = rel.get("manager", {}).get("data")
            if isinstance(m, dict):
                managerId = m.get("id", "")

            # ownerId（dataOwners配列の最初のid）
            ownerId = "!!"
            owners = rel.get("dataOwners", {}).get("data", [])
            if isinstance(owners, list) and owners:
                owner = owners[0]
                if isinstance(owner, dict):
                    ownerId = owner.get("id", "")
            row = [
                safe_str(ds.get("id", "")),
                safe_str(attr.get("datasetType", "")),
                safe_str(attr.get("grantNumber", "")),
                safe_str(attr.get("subjectTitle", "")),
                safe_str(attr.get("name", "")),
                safe_str(attr.get("description", "")),
                safe_str(attr.get("contact", "")),
                safe_str(attr.get("dataListingType", "")),
                safe_str(attr.get("usesInstrument", "")),
                safe_str(attr.get("isOpen", "")),
                safe_str(attr.get("openAt", "")),
                safe_str(attr.get("embargoDate", "")),
                safe_str(attr.get("isAnonymized", "")),
                safe_str(attr.get("created", "")),
                safe_str(attr.get("modified", "")),
                
                safe_str(managerId),
                safe_str(ownerId),
                safe_str(templateId),
                safe_str(instrumentId)
            ]
            ws.append(row)
        except Exception as e:
            print(f"[ERROR] datasetsシート出力時エラー: id={ds.get('id','')} : {e}")
            ws.append(["" for _ in range(len(HEADER_ROW))])
def write_templates_sheet(wb, parent):
    import json, os
    JSON_PATH = os.path.join(OUTPUT_RDE_DIR, "data", "template.json")
    abs_json = os.path.abspath(JSON_PATH)
    if not os.path.exists(abs_json):
        return
    with open(abs_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    templates = data.get("data", [])
    HEADER_ROW = [
        "id", "nameJa", "nameEn", "version", "datasetType", "description", "isPrivate", "workflowEnabled", "usesInstrument", "created"
    ]
    SHEET_NAME = "templates"
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        ws.delete_rows(1, ws.max_row)
        ws.append(HEADER_ROW)
    else:
        ws = wb.create_sheet(SHEET_NAME)
        ws.append(HEADER_ROW)
    for tpl in templates:
        attr = tpl.get("attributes", {})
        ws.append([
            tpl.get("id", ""),
            attr.get("nameJa", ""),
            attr.get("nameEn", ""),
            attr.get("version", ""),
            attr.get("datasetType", ""),
            attr.get("description", ""),
            attr.get("isPrivate", ""),
            attr.get("workflowEnabled", ""),
            attr.get("usesInstrument", ""),
            attr.get("created", "")
        ])
    import json, os
    JSON_PATH = os.path.join(OUTPUT_RDE_DIR, "data", "instruments.json")
    abs_json = os.path.abspath(JSON_PATH)
    if not os.path.exists(abs_json):
        return
    with open(abs_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    instruments = data.get("data", [])
    HEADER_ROW = [
        "id", "organizationId", "organizationNameJa", "organizationNameEn", "nameJa", "nameEn", "modelNumber", "manufacturerJa", "manufacturerEn"
    ]
    SHEET_NAME = "instruments"
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        ws.delete_rows(1, ws.max_row)
        ws.append(HEADER_ROW)
    else:
        ws = wb.create_sheet(SHEET_NAME)
        ws.append(HEADER_ROW)
    for inst in instruments:
        attr = inst.get("attributes", {})
        ws.append([
            inst.get("id", ""),
            attr.get("organizationId", ""),
            attr.get("organizationNameJa", ""),
            attr.get("organizationNameEn", ""),
            attr.get("nameJa", ""),
            attr.get("nameEn", ""),
            attr.get("modelNumber", ""),
            attr.get("manufacturerJa", ""),
            attr.get("manufacturerEn", "")
        ])
def write_group_sheet(wb, parent):
    pass
def write_instrumentType_sheet(wb, parent):
    import json, os
    JSON_PATH = os.path.join(OUTPUT_RDE_DIR, "data", "instrumentType.json")
    abs_json = os.path.abspath(JSON_PATH)
    if not os.path.exists(abs_json):
        return
    with open(abs_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    type_terms = data.get("typeTerms", [])
    HEADER_ROW = ["termId", "termNameJa", "termNameEn", "narrowerTerms"]
    SHEET_NAME = "instrumentType"
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        ws.delete_rows(1, ws.max_row)
        ws.append(HEADER_ROW)
    else:
        ws = wb.create_sheet(SHEET_NAME)
        ws.append(HEADER_ROW)
    for term in type_terms:
        narrower = term.get("narrowerTerms", [])
        # Noneを除外しstr化
        narrower_str = ", ".join([str(x) for x in narrower if x is not None])
        ws.append([
            term.get("termId", ""),
            term.get("termNameJa", ""),
            term.get("termNameEn", ""),
            narrower_str
        ])
def write_groupDetail_sheet(wb, parent):
    pass
def write_organization_sheet(wb, parent):
    import json, os
    JSON_PATH = os.path.join(OUTPUT_RDE_DIR, "data", "organization.json")
    abs_json = os.path.abspath(JSON_PATH)
    if not os.path.exists(abs_json):
        return
    with open(abs_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    orgs = data.get("data", [])
    HEADER_ROW = ["id", "nameJa", "nameEn"]
    SHEET_NAME = "organization"
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        ws.delete_rows(1, ws.max_row)
        ws.append(HEADER_ROW)
    else:
        ws = wb.create_sheet(SHEET_NAME)
        ws.append(HEADER_ROW)
    for org in orgs:
        attr = org.get("attributes", {})
        ws.append([
            org.get("id", ""),
            attr.get("nameJa", ""),
            attr.get("nameEn", "")
        ])

def write_instruments_sheet(wb, parent):
    import json, os
    JSON_PATH = os.path.join(OUTPUT_RDE_DIR, "data", "instruments.json")
    abs_json = os.path.abspath(JSON_PATH)
    if not os.path.exists(abs_json):
        return
    with open(abs_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    instruments = data.get("data", [])
    HEADER_ROW = [
        "id", "organizationId", "organizationNameJa", "organizationNameEn", "nameJa", "nameEn", "modelNumber", "manufacturerJa", "manufacturerEn"
    ]
    SHEET_NAME = "instruments"
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        ws.delete_rows(1, ws.max_row)
        ws.append(HEADER_ROW)
    else:
        ws = wb.create_sheet(SHEET_NAME)
        ws.append(HEADER_ROW)
    for inst in instruments:
        attr = inst.get("attributes", {})
        ws.append([
            inst.get("id", ""),
            attr.get("organizationId", ""),
            attr.get("organizationNameJa", ""),
            attr.get("organizationNameEn", ""),
            attr.get("nameJa", ""),
            attr.get("nameEn", ""),
            attr.get("modelNumber", ""),
            attr.get("manufacturerJa", ""),
            attr.get("manufacturerEn", "")
        ])

def write_licenses_sheet(wb, parent):
    """利用ライセンス情報をlicensesシートに出力"""
    import json, os
    JSON_PATH = os.path.join(OUTPUT_RDE_DIR, "data", "licenses.json")
    abs_json = os.path.abspath(JSON_PATH)
    if not os.path.exists(abs_json):
        return
    with open(abs_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    licenses = data.get("data", [])
    HEADER_ROW = ["id", "fullName", "url"]
    SHEET_NAME = "licenses"
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        ws.delete_rows(1, ws.max_row)
        ws.append(HEADER_ROW)
    else:
        ws = wb.create_sheet(SHEET_NAME)
        ws.append(HEADER_ROW)
    for license_item in licenses:
        attr = license_item.get("attributes", {})
        ws.append([
            license_item.get("id", ""),
            attr.get("fullName", ""),
            attr.get("url", "")
        ])


def write_subgroups_sheet(wb, parent):
    import json, os
    abs_json = os.path.abspath(SUBGROUP_JSON_PATH)
    if not os.path.exists(abs_json):
        return
    with open(abs_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    included = data.get("included", [])
    subgroups = [item for item in included if item.get("type") == "group"]
    HEADER_ROW = ["groupId", "name", "groupType", "description", "ownerId"]
    SHEET_NAME = "subgroups"
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        ws.delete_rows(1, ws.max_row)
        ws.append(HEADER_ROW)
    else:
        ws = wb.create_sheet(SHEET_NAME)
        ws.append(HEADER_ROW)
    for group in subgroups:
        attr = group.get("attributes", {})
        owner_id = ""
        for role in attr.get("roles", []):
            if role.get("role") == "OWNER":
                owner_id = role.get("userId", "")
                break
        ws.append([
            group.get("id", ""),
            attr.get("name", ""),
            attr.get("groupType", ""),
            attr.get("description", ""),
            owner_id
        ])

def write_groupDetail_sheet(wb, parent):
    import json, os
    JSON_PATH = os.path.join(OUTPUT_RDE_DIR, "data", "groupDetail.json")
    abs_json = os.path.abspath(JSON_PATH)
    if not os.path.exists(abs_json):
        return
    with open(abs_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    # data本体
    d = data.get("data", {})
    attr = d.get("attributes", {})
    HEADER_ROW = ["id", "groupType", "name", "description"]
    SHEET_NAME = "groupDetail"
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        ws.delete_rows(1, ws.max_row)
        ws.append(HEADER_ROW)
    else:
        ws = wb.create_sheet(SHEET_NAME)
        ws.append(HEADER_ROW)
    ws.append([
        d.get("id", ""),
        attr.get("groupType", ""),
        attr.get("name", ""),
        attr.get("description", "")
    ])
    # included配列のgroupも出力
    included = data.get("included", [])
    for group in included:
        if group.get("type") == "group":
            attr = group.get("attributes", {})
            ws.append([
                group.get("id", ""),
                attr.get("groupType", ""),
                attr.get("name", ""),
                attr.get("description", "")
            ])        

def write_entries_sheet(wb, parent):
    import os, json, glob
    DATA_ENTRY_DIR = os.path.join(OUTPUT_RDE_DIR, "data", "dataEntry")
    files = glob.glob(os.path.join(DATA_ENTRY_DIR, "*.json"))
    HEADER_ROW = [
        "entryId", "datasetId", "dataNumber", "name", "description", "experimentId","numberOfFiles", "numberOfImageFiles",
        "instrument.name", "instrument.organization", "invoice.basic.data_owner", "invoice.basic.date_submitted", "sample.name"
    ]
    SHEET_NAME = "entries"
    if SHEET_NAME in wb.sheetnames:
        ws = wb[SHEET_NAME]
        ws.delete_rows(1, ws.max_row)
        ws.append(HEADER_ROW)
    else:
        ws = wb.create_sheet(SHEET_NAME)
        ws.append(HEADER_ROW)
    for file in files:
        dataset_id = os.path.splitext(os.path.basename(file))[0]
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
        for entry in data.get("data", []):
            attr = entry.get("attributes", {})
            meta = attr.get("metadata", {})
            def get_meta(key):
                v = meta.get(key, {}).get("value")
                if isinstance(v, list):
                    return v[0] if v else ""
                return v if v is not None else ""
            ws.append([
                entry.get("id", ""),
                dataset_id,
                attr.get("dataNumber", ""),
                attr.get("name", ""),
                attr.get("description", ""),
                attr.get("experimentId", ""),
                attr.get("numberOfFiles", ""),
                attr.get("numberOfImageFiles", ""),
                get_meta("instrument.name"),
                get_meta("instrument.organization"),
                get_meta("invoice.basic.data_owner"),
                get_meta("invoice.basic.date_submitted"),
                get_meta("sample.name")
            ])


# ========================================
# UIController用ラッパー関数
# ========================================

def apply_basic_info_to_xlsx(ui_controller):
    """XLSX反映 - UIController用ラッパー（プログレス表示対応）"""
    try:
        from ..ui.ui_basic_info import apply_basic_info_to_Xlsx as ui_apply_basic_info_to_xlsx
        ui_apply_basic_info_to_xlsx(ui_controller)
    except Exception as e:
        ui_controller.show_error(f"XLSX反映でエラーが発生しました: {e}")
        logger.error(f"apply_basic_info_to_xlsx エラー: {e}")


def summary_basic_info_to_xlsx(ui_controller):
    """まとめXLSX作成 - UIController用ラッパー（プログレス表示対応）"""
    try:
        from ..ui.ui_basic_info import summary_basic_info_to_Xlsx as ui_summary_basic_info_to_xlsx
        ui_summary_basic_info_to_xlsx(ui_controller)
    except Exception as e:
        ui_controller.show_error(f"まとめXLSX作成でエラーが発生しました: {e}")
        logger.error(f"summary_basic_info_to_xlsx エラー: {e}")
