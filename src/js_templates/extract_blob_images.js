// 機能: ページ内のblob画像URLを抽出します。
// 呼び出し元: handle_blob_images 関数 (arim_rde_tool.py)

(function() {
    const blobImages = document.querySelectorAll('img[src^="blob:"]');
    const blobUrls = Array.from(blobImages).map(img => img.src);
    return blobUrls;
})();
