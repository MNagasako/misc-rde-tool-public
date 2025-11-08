// 機能: blob画像のbase64表現とファイル名を抽出します。
// 呼び出し元: process_next 関数 (arim_rde_tool.py)

// PySide6対応: JSON文字列化方式
var __processBlobResult__ = (function(src) {
    var img = Array.prototype.slice.call(document.querySelectorAll('img')).find(function(img) { return img.src === src; });
    var debug = [];
    var filename = null;
    if (!img) {
        debug.push("[JS] img要素が見つかりません: " + src);
        return JSON.stringify({ b64: null, debug: debug, filename: filename });
    }
    try {
        var canvas = document.createElement('canvas');
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        var ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0);
        var b64 = canvas.toDataURL('image/png').split(',')[1];
        debug.push("[JS] canvas→base64成功: " + src);
        var parent = img.closest('.thumbnail-position');
        if (parent) {
            var filenameElement = parent.querySelector('.image-box-width');
            filename = filenameElement ? filenameElement.textContent.trim() : "default_filename.png";
        }
        return JSON.stringify({ b64: b64, debug: debug, filename: filename });
    } catch (e) {
        debug.push("[JS] canvas処理失敗: " + e);
        return JSON.stringify({ b64: null, debug: debug, filename: filename });
    }
})("{src}");
