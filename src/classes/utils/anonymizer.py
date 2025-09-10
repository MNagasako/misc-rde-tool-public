import json
import os
import re

class Anonymizer:
    """
    匿名化専用クラス。
    - データセットやJSONの匿名化処理を担当
    """
    UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

    def anonymize_json(self, data, grant_number):
        # attributes内のdatasetTypeがANALYSISなら特別処理
        if isinstance(data, dict):
            out = {}
            for k, v in data.items():
                kl = k.lower()
                # attributes特別処理
                if k == "attributes" and isinstance(v, dict):
                    attrs = v.copy()
                    if attrs.get("datasetType") == "ANALYSIS":
                        attrs["grantNumber"] = "JPMXP12********"
                        attrs["subjectTitle"] = "*******非開示*******"
                        attrs["name"] = "*******非開示*******"
                    else:
                        for key, val in [("grantNumber", "JPMXP12********"), ("subjectTitle", "*******非開示*******"), ("name", "*******非開示*******")]:
                            if key in attrs:
                                attrs[key] = val
                    out[k] = attrs
                # grantNumber/grant_number/subjectTitle/nameは再帰的に匿名化
                elif kl in ("grantnumber", "grant_number"):
                    out[k] = "***"
                elif kl == "subjecttitle":
                    out[k] = "*******非開示*******"
                elif kl == "name":
                    out[k] = "*******非開示*******"
                else:
                    out[k] = self.anonymize_json(v, grant_number)
            return out
        elif isinstance(data, list):
            return [self.anonymize_json(v, grant_number) for v in data]
        return data

    def anonymize_file(self, in_path, out_path, grant_number):
        # filelist.jsonは除外
        if os.path.basename(in_path) == "filelist.json":
            return
        # UUIDファイル名のみ対象
        fname = os.path.splitext(os.path.basename(in_path))[0]
        if not self.UUID_PATTERN.match(fname):
            return
        with open(in_path, encoding='utf-8') as f:
            data = json.load(f)
        anon = self.anonymize_json(data, grant_number)
        dirpath = os.path.dirname(out_path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        # プリフィックス追加
        out_dir = os.path.dirname(out_path)
        out_base = os.path.basename(out_path)
        if not out_base.startswith("非開示_"):
            out_base = "非開示_" + out_base
        out_path2 = os.path.join(out_dir, out_base)
        with open(out_path2, 'w', encoding='utf-8') as f:
            json.dump(anon, f, ensure_ascii=False, indent=2)
