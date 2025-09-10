// 機能: ページの横幅を取得してズーム調整に使用します。
// 呼び出し元: adjust_zoom 関数 (arim_rde_tool.py)

(function() {
    var w = document.body ? document.body.scrollWidth : document.documentElement.scrollWidth;
    return w;
})();
