// 機能: ページ内のblob画像をポーリングして情報を収集します。
// 呼び出し元: poll_for_blob_imgs 関数 (arim_rde_tool.py)

(function() {
    const results = [];
    const imgs = Array.from(document.querySelectorAll('img[src^="blob:"]'));
    imgs.forEach(img => {
        const parent = img.closest('.thumbnail-position');
        if (parent) {
            const filenameElement = parent.querySelector('.image-box-width');
            const filename = filenameElement ? filenameElement.textContent.trim() : "default_filename.png";
            results.push({ src: img.src, filename });
        }
    });
    return results;
})();
