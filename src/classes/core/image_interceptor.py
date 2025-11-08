from qt_compat.webengine import QWebEngineUrlRequestInterceptor
import os
import logging
# === セッション管理ベースのプロキシ対応 ===
from classes.utils.api_request_helper import fetch_binary

logger = logging.getLogger("RDE_WebView")

class ImageInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        logger.debug('ImageInterceptor.interceptRequest called')
        url = info.requestUrl().toString()
        if any(url.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']):
            logger.info(f"[PROXY] Intercepted image request: {url}")
            try:
                img_data = fetch_binary(url)
                if img_data:
                    outdir = os.path.join(os.environ.get('OUTPUT_DIR', 'output'), 'proxy_images')
                    os.makedirs(outdir, exist_ok=True)
                    fname = url.split('/')[-1].split('?')[0]
                    outpath = os.path.join(outdir, fname)
                    with open(outpath, 'wb') as f:
                        f.write(img_data)
                    logger.info(f"[PROXY] Saved image: {outpath}")
                else:
                    logger.warning(f"[PROXY] Failed to fetch image data: {url}")
            except Exception as e:
                logger.warning(f"[PROXY] Failed to save image: {e}")
