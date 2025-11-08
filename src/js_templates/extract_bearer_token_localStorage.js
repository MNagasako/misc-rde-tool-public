// Bearer Token取得 - localStorage版（PySide6対応）
// sessionStorageの代わりにlocalStorageから取得
// PySide6ではJSON文字列として返すため、明示的にJSON.stringifyを使用
(function() {
    try {
        var result = [];
        
        // localStorageから取得
        for (var i = 0; i < localStorage.length; i++) {
            var key = localStorage.key(i);
            var value = localStorage.getItem(key);
            result.push({
                key: key,
                value: value
            });
        }
        
        // sessionStorageもバックアップとして確認
        for (var i = 0; i < sessionStorage.length; i++) {
            var key = sessionStorage.key(i);
            var value = sessionStorage.getItem(key);
            result.push({
                key: key,
                value: value,
                source: 'sessionStorage'
            });
        }
        
        // PySide6対応: JSON文字列として返す
        return JSON.stringify(result);
    } catch (e) {
        return JSON.stringify([{error: e.toString()}]);
    }
})();
