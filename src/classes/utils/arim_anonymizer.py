# ARIMデータセット匿名化ロジック
import os
import sys
from config.common import OUTPUT_LOG_DIR

import logging

# ロガー設定
logger = logging.getLogger(__name__)

import json
from pathlib import Path

#WEBVIEW_MESSAGE_LOG = os.path.join(OUTPUT_DIR,'log', 'webview_message.log')
ARIM_ANONYMIZER_LOG = os.path.join(OUTPUT_LOG_DIR, 'arim_anonymizer.log')
ARIM_ANONYMIZER_DEBUG_LOG = os.path.join(OUTPUT_LOG_DIR, 'arim_anonymizer_debug.log')

class ARIMAnonymizer:
    def __init__(self, logger=None, set_webview_message=None):
        self.logger = logger
        self.set_webview_message = set_webview_message or (lambda msg: None)
    
    def _mask_grant_number(self, grant_number):
        """
        grantNumberをマスク処理
        例: JPMXP1223TU0172 -> JPMXP12********
        
        Args:
            grant_number: 課題番号文字列
            
        Returns:
            str: マスクされた課題番号
        """
        if not grant_number or not isinstance(grant_number, str):
            return "***"
        
        # JPMXP12 までを残して、それ以降を * でマスク
        if len(grant_number) > 7 and grant_number.startswith("JPMXP"):
            return grant_number[:7] + "*" * (len(grant_number) - 7)
        
        return "***"

    def anonymize_dataset_directory(self, dataset_path, grant_number, **kwargs):
        set_webview_message = kwargs.get('set_webview_message', self.set_webview_message)
        set_webview_message(f"[anonymize_dataset_directory] {dataset_path}")
        """
        指定ディレクトリ配下の全JSONファイルに対し匿名化処理を実施
        ※追加のキーワード引数は無視（互換性維持のため）
        """
        if not Path(dataset_path).exists():
            if self.logger:
                self.logger.warning(f"[ARIM] 匿名化対象ディレクトリが存在しません: {dataset_path}")
            return False
        json_files = list(Path(dataset_path).rglob("*.json"))
        set_webview_message(f"[json_file] {json_files}")
        if not json_files:
            if self.logger:
                self.logger.warning(f"[ARIM] 匿名化対象JSONが見つかりません: {dataset_path}")
            return False
        import difflib
        found = 0
        for json_file in json_files:
            basename = os.path.basename(json_file)
            # anonymized_ または diff_ で始まるファイルはスキップ
            if basename.startswith("anonymized_") or basename.startswith("diff_") or basename.startswith("非開示_") or basename.startswith("差分_") or basename.endswith("filelist.json"):
                if self.logger:
                    self.logger.info(f"[ARIM] スキップ: {json_file} (anonymized_ または diff_ ファイル)")
                else:
                    logger.info("スキップ: %s (anonymized_ または diff_ ファイル)", json_file)
                continue
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                before = json.dumps(data, ensure_ascii=False, indent=2)
                changed = self.anonymize_json(data, grant_number)
                after = json.dumps(data, ensure_ascii=False, indent=2)
                # 匿名化後ファイル名
                anonymized_path = os.path.join(os.path.dirname(json_file), f"非開示_{os.path.basename(json_file)}")
                # 差分ファイル名
                diff_path = os.path.join(os.path.dirname(json_file), f"差分_{os.path.splitext(os.path.basename(json_file))[0]}.txt")
                # 匿名化後ファイルを保存
                if changed:
                    with open(anonymized_path, "w", encoding="utf-8") as f:
                        f.write(after)
                    # 差分ファイルを保存
                    diff = difflib.unified_diff(
                        before.splitlines(keepends=True),
                        after.splitlines(keepends=True),
                        fromfile=os.path.basename(json_file),
                        tofile=f"anonymized_{os.path.basename(json_file)}"
                    )
                    with open(diff_path, "w", encoding="utf-8") as diff_f:
                        diff_f.writelines(diff)
                    if self.logger:
                        self.logger.info(f"[ARIM] 匿名化済: {anonymized_path}")
                        self.logger.info(f"[ARIM] 差分: {diff_path}")
                        #self.logger.info(f"[ARIM] 匿名化済: anonymized_{os.path.basename(json_file)} 差分: diff_{os.path.basename(json_file)}.txt")
                    else:
                        logger.info("匿名化済: %s", anonymized_path)
                        logger.info("差分: %s", diff_path)
                        #print(f"匿名化済: anonymized_{os.path.basename(json_file)} 差分: diff_{os.path.basename(json_file)}.txt")
                    found += 1
                    # 匿名化したファイルのディレクトリにログを出力（loggerに統一）
                    # ファイル書き込みは廃止
                else:
                    if self.logger:
                        self.logger.info(f"[ARIM] 匿名化不要: {json_file}")
                    else:
                        logger.info("匿名化不要: %s", json_file)
                # ログファイルにも出力
                if self.logger:
                    def _shorten_json(s, maxlen=300):
                        if len(s) > maxlen:
                            return s[:150] + f"...({len(s)} chars)..." + s[-100:]
                        return s
                    # PRETTYなJSONを一度パースしてminifyしてから文字数を詰める（160字）
                    def _shorten_json_oneline(s, maxlen=160):
                        try:
                            obj = json.loads(s)
                            s_min = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
                        except Exception:
                            s_min = s.replace('\n', ' ').replace('\r', ' ')
                        if len(s_min) > maxlen:
                            return s_min[:80] + f"...({len(s_min)} chars)..." + s_min[-40:]
                        return s_min
                    self.logger.debug(f"[ARIM] data_tree : {json_file}")
                    self.logger.debug(f"[ARIM] 匿名化前:{_shorten_json_oneline(before)}")
                    self.logger.debug(f"[ARIM] 匿名化後:{_shorten_json_oneline(after)}")
                    self.logger.debug(f"[ARIM] 匿名化変更有無: {changed}")
                # ファイル書き込みは廃止
            except Exception as e:
                if self.logger:
                    self.logger.error(f"[ARIM] 匿名化失敗: {json_file}: {e}")
                else:
                    logger.info("匿名化失敗: %s: %s", json_file, e)
        if found == 0:
            if self.logger:
                self.logger.info(f"[ARIM] 匿名化対象JSONが見つかりません（{dataset_path}以下）")
            else:
                logger.info("匿名化対象JSONが見つかりません（%s以下）", dataset_path)
        return True

    def anonymize_json(self, data, grant_number):
        """
        JSONデータの 'attributes' ブロック（datasetType=ANALYSIS）に匿名化フィールドを挿入
        """
        changed = False
        # ルートdata/attributes
        if isinstance(data, dict) and "data" in data:
            changed |= self.anonymize_attributes(data["data"], grant_number)
        # included配列（typeに関係なくattributesを持つものすべて）
        if isinstance(data, dict) and "included" in data and isinstance(data["included"], list):
            for inc in data["included"]:
                if isinstance(inc, dict) and "attributes" in inc:
                    changed |= self.anonymize_attributes(inc, grant_number)
        return changed

    def anonymize_attributes(self, obj, grant_number):
        """
        attributesブロック内の 'subjectTitle', 'name', 'grantNumber' を必ず匿名化値で上書き
        grantNumberは下4桁を除いてマスク（例: JPMXP1223TU0172 -> JPMXP12********）
        """
        if not (isinstance(obj, dict) and "attributes" in obj):
            return False
        attrs = obj["attributes"]
        changed = False
        
        # grantNumberのマスク処理
        masked_grant_number = self._mask_grant_number(grant_number)
        
        # 匿名化対象フィールド
        anonymize_fields = {
            "subjectTitle": "*******非開示*******",
            "name": "*******非開示*******",
            "grantNumber": masked_grant_number
        }
        for k, v in anonymize_fields.items():
            if attrs.get(k) != v:
                attrs[k] = v
                changed = True
        obj["attributes"] = attrs
        return changed
    
    def set_webview_message(self, msg):
        # 廃止: コールバックで渡す方式に変更
        pass