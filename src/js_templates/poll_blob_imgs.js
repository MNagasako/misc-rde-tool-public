// 機能: ページ内のblob画像をポーリングして情報を収集します。
// 呼び出し元: poll_for_blob_imgs 関数 (arim_rde_tool.py)

// PySide6対応: JSON文字列化方式（配列オブジェクトは取得できないため）
// グローバル変数にJSON文字列として結果を格納
var __pollBlobResults__ = (function() {
    try {
        console.log('[BLOB-JS] ===== JavaScript実行開始 =====');
        
        const results = [];
        const imgs = Array.from(document.querySelectorAll('img[src^="blob:"]'));
        
        // デバッグ: 全img要素を確認
        const allImgs = document.querySelectorAll('img');
        console.log('[BLOB-JS] 全img要素: ' + allImgs.length + '件');
        console.log('[BLOB-JS] blob:画像: ' + imgs.length + '件');
        
        // blob以外の画像もログ出力
        if (imgs.length === 0 && allImgs.length > 0) {
            const sampleSrcs = Array.from(allImgs).slice(0, 5).map(img => img.src.substring(0, 100));
            console.log('[BLOB-JS] サンプルsrc (最初の5件): ' + JSON.stringify(sampleSrcs));
        }
        
        imgs.forEach(img => {
            const parent = img.closest('.thumbnail-position');
            if (parent) {
                const filenameElement = parent.querySelector('.image-box-width');
                const filename = filenameElement ? filenameElement.textContent.trim() : "default_filename.png";
                results.push({ src: img.src, filename: filename });
                console.log('[BLOB-JS] 画像検出: filename=' + filename + ', src=' + img.src.substring(0, 50) + '...');
            } else {
                console.log('[BLOB-JS] 親要素(.thumbnail-position)が見つかりません: src=' + img.src.substring(0, 50) + '...');
            }
        });
        
        console.log('[BLOB-JS] 収集結果: ' + results.length + '件');
        
        // PySide6対応: JSON文字列化して返す（配列オブジェクトは取得不可）
        const jsonString = JSON.stringify(results);
        console.log('[BLOB-JS] JSON文字列長: ' + jsonString.length + '文字');
        console.log('[BLOB-JS] ===== JavaScript実行終了 =====');
        
        return jsonString;
    } catch (error) {
        console.error('[BLOB-JS] エラー発生: ' + error.toString());
        return '[]';  // 空配列のJSON文字列
    }
})();

