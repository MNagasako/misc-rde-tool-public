// sessionStorage の内容をデバッグ
(function() {
    try {
        var result = {
            storageLength: sessionStorage.length,
            storageKeys: [],
            urlInfo: {
                href: window.location.href,
                protocol: window.location.protocol,
                host: window.location.host,
                pathname: window.location.pathname,
                hash: window.location.hash
            },
            documentState: document.readyState
        };
        
        // すべてのキーを取得
        for (var i = 0; i < sessionStorage.length; i++) {
            var key = sessionStorage.key(i);
            result.storageKeys.push({
                key: key,
                valueLength: sessionStorage.getItem(key) ? sessionStorage.getItem(key).length : 0
            });
        }
        
        return result;
    } catch (e) {
        return { error: e.toString() };
    }
})();
