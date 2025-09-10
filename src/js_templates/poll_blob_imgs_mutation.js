// poll_blob_imgs_mutation.js
// MutationObserverでblob:画像の出現を即座に検出し、base64化して返す
(function() {
    // すでに監視中なら何もしない
    if (window._poll_blob_imgs_mutation_observing) {
        return window._poll_blob_imgs_mutation_result || {};
    }
    window._poll_blob_imgs_mutation_observing = true;
    const debugSteps = [];
    function getBlobImgs() {
        const imgs = Array.from(document.images).filter(img => img.src && img.src.startsWith('blob:'));
        debugSteps.push(`[getBlobImgs] found ${imgs.length} blob images.`);
        return imgs.map(img => ({src: img.src, filename: img.getAttribute('data-filename') || img.alt || img.title || ''}));
    }
    function toDataURL(img) {
        return new Promise((resolve, reject) => {
            try {
                const canvas = document.createElement('canvas');
                canvas.width = img.naturalWidth;
                canvas.height = img.naturalHeight;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0);
                debugSteps.push(`[toDataURL] Converted image ${img.src}`);
                resolve(canvas.toDataURL('image/png'));
            } catch (e) {
                debugSteps.push(`[toDataURL] Error: ${e}`);
                reject(e);
            }
        });
    }
    function finish(result) {
        window._poll_blob_imgs_mutation_result = result;
        window._poll_blob_imgs_mutation_observing = false;
    }
    function observeAndReturn() {
        debugSteps.push('[observeAndReturn] Start');
        try {
            const found = getBlobImgs();
            if (found.length > 0) {
                debugSteps.push(`[observeAndReturn] Initial blob images found: ${found.length}`);
                Promise.all(found.map(async (info) => {
                    const img = Array.from(document.images).find(i => i.src === info.src);
                    let b64 = null;
                    try {
                        b64 = await toDataURL(img);
                    } catch (e) {
                        debugSteps.push(`[observeAndReturn] toDataURL error: ${e}`);
                    }
                    return {src: info.src, filename: info.filename, b64};
                })).then(images => {
                    debugSteps.push('[observeAndReturn] Returning initial images');
                    finish({images, debug: debugSteps});
                }).catch(e => {
                    debugSteps.push(`[observeAndReturn] Promise.all error: ${e}`);
                    finish({images: [], debug: debugSteps, error: String(e)});
                });
                return;
            }
            debugSteps.push('[observeAndReturn] No initial blob images, setting up MutationObserver');
            // MutationObserverで新規blob画像を監視
            const observer = new MutationObserver((mutations, obs) => {
                debugSteps.push(`[MutationObserver] Mutation detected`);
                const imgs = getBlobImgs();
                if (imgs.length > 0) {
                    debugSteps.push(`[MutationObserver] Blob images found: ${imgs.length}`);
                    Promise.all(imgs.map(async (info) => {
                        const img = Array.from(document.images).find(i => i.src === info.src);
                        let b64 = null;
                        try {
                            b64 = await toDataURL(img);
                        } catch (e) {
                            debugSteps.push(`[MutationObserver] toDataURL error: ${e}`);
                        }
                        return {src: info.src, filename: info.filename, b64};
                    })).then(images => {
                        debugSteps.push('[MutationObserver] Returning images and disconnecting');
                        obs.disconnect();
                        finish({images, debug: debugSteps});
                    }).catch(e => {
                        debugSteps.push(`[MutationObserver] Promise.all error: ${e}`);
                        obs.disconnect();
                        finish({images: [], debug: debugSteps, error: String(e)});
                    });
                }
            });
            observer.observe(document.body, {childList: true, subtree: true, attributes: true, attributeFilter: ['src']});
            // タイムアウト（10秒）
            setTimeout(() => {
                debugSteps.push('[Timeout] No blob images found within 10s, disconnecting observer');
                observer.disconnect();
                finish({images: [], debug: debugSteps});
            }, 10000);
        } catch (e) {
            debugSteps.push(`[observeAndReturn] JS top-level error: ${e}`);
            finish({images: [], debug: debugSteps, error: String(e)});
        }
    }
    observeAndReturn();
    return {};
})();
