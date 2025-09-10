// 機能: sessionStorageからBearerトークンを抽出します。
// 呼び出し元: try_get_bearer_token 関数 (arim_rde_tool.py)

(function() {
    var result = [];
    for (var k in window.sessionStorage) {
        try {
            var v = window.sessionStorage.getItem(k);
            result.push({ key: k, value: v });
        } catch (e) {}
    }
    return result;
})();