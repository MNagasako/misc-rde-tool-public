#!/usr/bin/env python3
"""
ImageProcessor - 画像処理・管理クラス

概要:
画像ファイルのダウンロード、変換、最適化を専門に行うクラスです。
効率的な画像管理とストレージ最適化を実現します。

主要機能:
- 画像ファイルの自動ダウンロード
- 画像形式の変換・最適化
- ファイルサイズの圧縮
- 画像メタデータの管理
- プレビュー画像の生成
- 重複画像の検出・除去

責務:
画像処理を専門化し、メインクラスからメディア処理ロジックを分離します。
"""

# src/classes/image_processor.py - ARIM RDE Tool v1.13.1
# 画像処理・blob画像取得・重複チェック・保存処理を専門に扱うクラス
# 大容量画像対応・効率的な処理アルゴリズム実装
# 【注意】バージョン更新時はconfig/common.py のREVISIONも要確認

from PyQt5.QtCore import QEventLoop, QTimer, QUrl
from PyQt5.QtWidgets import QApplication
# === セッション管理ベースのプロキシ対応 ===
from classes.utils.api_request_helper import fetch_binary
import json
import base64
import hashlib
import os
import logging
from config.site_rde import URLS
from config.common import OUTPUT_DIR, DATASETS_DIR, IMAGE_LOAD_WAIT_TIME, MAX_POLL, POLL_INTERVAL
from functions.common_funcs import load_js_template
from classes.utils.debug_log import debug_log

logger = logging.getLogger("RDE_WebView")

class ImageProcessor:
    """
    WebViewでのblob画像取得・保存処理を専門に扱うクラス
    """
    
    def __init__(self, browser):
        """
        ImageProcessorの初期化
        
        Args:
            browser: 親のBrowserインスタンス（WebViewや各種マネージャーにアクセスするため）
        """
        self.browser = browser
        self.logger = logger
    
    @debug_log
    def save_webview_blob_images(self, data_id, subdir, headers):
        """
        WebViewでblob:URL画像が動的生成された場合に、その画像を保存する。
        - ページ内のimgタグのsrc属性にblob:で始まるものが現れるまで待機し、JSでfetch→base64化→Python側で保存
        - fetchで失敗した場合はcanvas+toDataURLでbase64化を試みる
        - ページ表示完了後、まず5秒待機し、その後10秒間ポーリング
        - デバッグ出力を強化
        - ページが閉じられた場合は即座に中断
        """
        # 正しいsubdirパスを保存（data_id -> subdir のマッピング）
        if not hasattr(self.browser, '_data_id_subdir_mapping'):
            self.browser._data_id_subdir_mapping = {}
        self.browser._data_id_subdir_mapping[data_id] = subdir
        
        # data_idが現在のgrantNumberに属するかチェック（混入防止の強化）- 一時的に緩和
        expected_grant_path = self.browser.datatree_manager.get_subdir_from_new_datatree(data_id, grant_number=self.browser.grant_number)
        if not expected_grant_path:
            # 現在のgrantNumber内でdata_idが見つからない場合、他のgrantNumberで確認
            other_grant_path = self.browser.datatree_manager.get_subdir_from_new_datatree(data_id, grant_number=None)
            if other_grant_path:
                logger.warning(f"[BLOB] data_id={data_id}は他のgrantNumberに属していますが、画像取得を継続: 現在={self.browser.grant_number}, 実際の所属パス={other_grant_path}")
                # return  # 一時的にコメントアウト
        
        # 現在のgrantNumberと一致するかチェック（混入防止）- 一時的に緩和
        if hasattr(self.browser, '_current_image_grant_number') and self.browser._current_image_grant_number:
            if self.browser.grant_number != self.browser._current_image_grant_number:
                logger.warning(f"[BLOB] grantNumber不一致ですが画像取得を継続: data_id={data_id}, 現在={self.browser.grant_number}, 期待={self.browser._current_image_grant_number}")
                # return  # 一時的にコメントアウト
        
        logger.info(f"[BLOB] 画像取得開始: data_id={data_id}, subdir={subdir}, grant_number={getattr(self.browser, 'grant_number', 'Unknown')}")
        
        # 進行中の処理として記録
        if hasattr(self.browser, '_active_image_processes'):
            self.browser._active_image_processes.add(data_id)
        
        # ファイル名リストを取得・保存（DataManagerへ委譲）
        self._start_blob_image_polling(data_id, subdir, headers)

    def _start_blob_image_polling(self, data_id, subdir, headers):
        """
        blob画像のポーリング処理を開始する
        """
        import base64

        # ファイルリストを取得
        filelist_url = URLS["api"]["data_detail"].format(id=data_id)
        from classes.utils.api_request_helper import api_request
        response = api_request('GET', filelist_url, headers=headers)
        try:
            filelist_json = response.json()  # JSONデータをパース
        except ValueError as e:
            logger.error(f"JSONパース失敗: {e}")
            return

        # "included"セクションから"type"が"file"の要素を抽出
        files = [file for file in filelist_json.get("included", []) if file.get("type") == "file"]
        if not files:
            logger.warning("ファイルリストが空です")
            return

        for file in files:
            try:
                # ファイル情報をDataTreeManagerに追加
                self.browser.datatree_manager.add_image_to_detail(
                    grant_id=self.browser.datatree_manager.get_grant_id_by_detail_id(data_id),  # 課題番号（grantNumber, 例: "JPMXP1222TU0195"）
                    dataset_id=self.browser.datatree_manager.get_dataset_id_by_detail_id(data_id),  # データセットID
                    detail_id=data_id,          # detailノードID
                    image_id=file.get("id"),    # 画像ID
                    name=file.get("attributes", {}).get("fileName", "unknown"),  # ファイル名
                    type_name="image"           # タイプ名（画像の場合は"image"）
                )
            except Exception as e:
                logger.warning(f"ファイル追加失敗: {file.get('attributes', {}).get('fileName', 'unknown')} - {e}")

        try:
            loop = QEventLoop()
            dataset_url = URLS["web"]["data_detail_page"].format(id=data_id)
            logger.debug(f"save_webview_blob_images: url : {dataset_url}")
            logger.debug(f"save_webview_blob_images: subdir : {subdir}")
            self.browser.webview.show()

            def poll_for_blob_imgs():
                nonlocal poll_count
                # data_idをローカル変数として使用（インスタンス変数に依存しない）
                current_data_id = data_id
                
                # 処理が中断されているかチェック
                if hasattr(self.browser, '_active_image_processes') and data_id not in self.browser._active_image_processes:
                    logger.warning(f"[BLOB] 画像取得がキャンセルされました: data_id={data_id}")
                    try:
                        self.browser.webview.loadFinished.disconnect(after_load)
                    except Exception:
                        pass
                    loop.quit()
                    return
                
                # grantNumber一致チェック - 一時的に緩和
                if hasattr(self.browser, '_current_image_grant_number') and self.browser._current_image_grant_number:
                    if self.browser.grant_number != self.browser._current_image_grant_number:
                        logger.warning(f"[BLOB] grantNumber不一致ですが画像取得を継続: data_id={data_id}, 現在={self.browser.grant_number}, 期待={self.browser._current_image_grant_number}")
                        # 継続処理（中断しない）
                        # try:
                        #     self.browser.webview.loadFinished.disconnect(after_load)
                        # except Exception:
                        #     pass
                        # loop.quit()
                        # return
                
                self.browser.set_webview_message(f"[blob画像ポーリング中] {current_data_id}")
                logger.debug(f"poll_for_blob_imgs: polling for blob images..{current_data_id}.")
                if not self.browser.webview.isVisible():
                    logger.debug(f"WebViewが閉じられたためポーリング中断")
                    try:
                        self.browser.webview.loadFinished.disconnect(after_load)
                    except Exception:
                        pass
                    logger.debug("loop.quit() called (WebView非表示)")
                    loop.quit()
                    return
                logger.debug(f"poll_for_blob_imgs: poll_count={poll_count}")

                js_code = load_js_template('poll_blob_imgs.js')

                def handle_count(results):
                    nonlocal poll_count
                    if results and len(results) > 0:
                        self._extract_and_save_blob_images(results, loop, data_id=data_id)
                    else:
                        poll_count += 1
                        if poll_count < max_poll:
                            QTimer.singleShot(poll_interval, poll_for_blob_imgs)
                        else:
                            logger.warning(f"blob:画像が見つからずタイムアウト: {dataset_url}")
                            try:
                                self.browser.webview.loadFinished.disconnect(after_load)
                            except Exception:
                                pass
                            logger.debug("loop.quit() called (timeout)")
                            loop.quit()

                self.browser.webview.page().runJavaScript(js_code, handle_count)

            def after_load(ok):
                self.browser.set_webview_message(f"[after_load] ok={ok} dataset_url={dataset_url}")
                logger.debug(f"after_load: ok={ok}")
                if ok:
                    logger.debug(f"ページロード完了。10秒待機後にポーリング開始")
                    QTimer.singleShot(IMAGE_LOAD_WAIT_TIME, poll_for_blob_imgs)
                else:
                    logger.warning(f"WebViewロード失敗: {dataset_url}")
                    try:
                        self.browser.webview.loadFinished.disconnect(after_load)
                    except Exception:
                        pass
                    loop.quit()

            poll_count = 0
            max_poll = MAX_POLL
            poll_interval = POLL_INTERVAL
            self.browser.webview.loadFinished.connect(after_load)
            self.browser.webview.load(QUrl(dataset_url))
            logger.debug(f"WebViewロード開始: {dataset_url}")
            self.browser.set_webview_message(f"[WebViewロード開始] {dataset_url}")
            loop.exec_()
        except Exception as e:
            logger.warning(f"WebViewでのblob画像保存処理例外: {e}")

    def _extract_and_save_blob_images(self, blob_srcs, loop, max_images=None, data_id=None):
        """
        blob画像のベース64データを抽出して保存する
        """
        if max_images is None:
            from config.common import MAX_IMAGES_PER_DATASET
            max_images = MAX_IMAGES_PER_DATASET  # 最新の値を取得
        
        # data_idが渡されていない場合の安全対策
        if data_id is None:
            logger.error("[BLOB] data_idが指定されていません。画像保存を中断します。")
            loop.quit()
            return
            
        self.browser.set_webview_message(f"[extract_blob_imgs] data_id={data_id}, {len(blob_srcs)}件")
        if not self.browser.webview.isVisible():
            logger.debug(f"WebViewが閉じられたため画像抽出中断")
            return

        logger.debug(f"extract_blob_imgs: extracting blob images for data_id={data_id}...")

        def process_next(idx, b64_list, debug_logs, filenames):
            # data_id単位の画像取得件数を確認
            current_count = self.browser._data_id_image_counts.get(data_id, 0)
            
            # 画像取得件数の制御ロジックを強化（data_id単位）
            if max_images is not None and current_count >= max_images:
                logger.info(f"[BLOB] data_id={data_id} 画像上限に達したため処理終了: max_images={max_images}, 現在の件数={current_count}")
                self.handle_blob_images(self.browser.image_dir, {'b64_list': b64_list, 'debug_logs': debug_logs, 'filenames': filenames, 'blob_srcs': blob_srcs}, data_id=data_id)
                loop.quit()
                return

            if idx >= len(blob_srcs):
                logger.debug(f"[BLOB] 全画像処理完了: data_id={data_id}, grant_number={getattr(self.browser, 'grant_number', None)} (合計{len(b64_list)}件)")
                self.handle_blob_images(self.browser.image_dir, {'b64_list': b64_list, 'debug_logs': debug_logs, 'filenames': filenames, 'blob_srcs': blob_srcs}, data_id=data_id)
                self.browser.set_webview_message(f"[process_next] end [{idx}] data_id={data_id}")
                logger.debug("loop.quit() called (全件完了)")
                loop.quit()
                return

            src = blob_srcs[idx]['src']
            filename = blob_srcs[idx].get('filename', 'default_filename.png')
            logger.debug(f"[BLOB] process_next: idx={idx}, src={src[:60]}..., filename={filename}")

            js_code = load_js_template('process_blob_image.js').replace('{src}', src)

            def handle_result(result):
                nonlocal filename
                # BLOBのbase64は切り詰めてログ出力
                if isinstance(result, dict):
                    b64 = result.get('b64')
                    b64_short = (b64[:40] + f"...({len(b64)} chars)..." + b64[-10:]) if b64 and len(b64) > 60 else b64
                    # b64以外の値はそのまま、b64だけ短縮してjson化
                    result_log = {k: (b64_short if k == 'b64' else v) for k, v in result.items()}
                    logger.debug(f"[BLOB] handle_result: idx={idx}, filename={filename}, b64(short)={b64_short}")
                    logger.debug(f"[BLOB] result_json={json.dumps(result_log, ensure_ascii=False, separators=(',', ':'))}")
                else:
                    logger.debug(f"[BLOB] handle_result: idx={idx}, filename={filename}, result_type={type(result)}")
                b64 = result.get('b64') if isinstance(result, dict) else None
                debug = result.get('debug') if isinstance(result, dict) else []
                filename = result.get('filename') if isinstance(result, dict) else None
                if not filename:
                    filename = blob_srcs[idx].get('filename')
                if not filename:
                    filename = 'unnamed.png'
                blob_hash = self._hash_blob(b64, filename)
                # data_id毎のユニークキーを作成（同一data_id内での重複チェック）
                unique_key = f"{data_id}_{blob_hash}"
                if unique_key in self.browser._recent_blob_hashes:
                    logger.debug(f"[BLOB] duplicate image detected, skipping: idx={idx}, filename={filename}, data_id={data_id}")
                    process_next(idx + 1, b64_list, debug_logs, filenames)
                    return
                
                # data_id単位の画像カウンタを更新
                current_count = self.browser._data_id_image_counts.get(data_id, 0)
                if max_images is not None and current_count >= max_images:
                    logger.info(f"[BLOB] data_id={data_id} 画像上限に達したため処理終了: max_images={max_images}, 現在の件数={current_count}")
                    self.handle_blob_images(self.browser.image_dir, {'b64_list': b64_list, 'debug_logs': debug_logs, 'filenames': filenames, 'blob_srcs': blob_srcs}, data_id=data_id)
                    loop.quit()
                    return
                
                self.browser._recent_blob_hashes.add(unique_key)
                self.browser._data_id_image_counts[data_id] = current_count + 1
                logger.debug(f"[BLOB] data_id={data_id} 画像カウンタ更新: {current_count} -> {current_count + 1}")
                
                # ハッシュセットのサイズ制限（メモリ効率）
                if len(self.browser._recent_blob_hashes) > 100:  # data_id毎に管理するため上限を増加
                    # 古いエントリを削除（セットなので適当に削除）
                    self.browser._recent_blob_hashes.pop()
                b64_list.append(b64)
                debug_logs.extend(debug)
                filenames.append(filename)
                process_next(idx + 1, b64_list, debug_logs, filenames)

            self.browser.webview.page().runJavaScript(js_code, handle_result)

        process_next(0, [], [], [])

    @debug_log
    def handle_blob_images(self, dir_path, result, data_id=None):
        """
        取得したblob画像データを実際にファイルに保存する
        """
        logger.debug(f'[DEBUG] handle_blob_image: data_id={data_id}')
        
        # data_idが渡されていない場合の安全対策
        if data_id is None:
            logger.error("[BLOB] handle_blob_images: data_idが指定されていません。画像保存を中断します。")
            return
        
        # data_idが現在のgrantNumberに属するかチェック（二重確認）
        expected_grant_path = self.browser.datatree_manager.get_subdir_from_new_datatree(data_id, grant_number=self.browser.grant_number)
        if not expected_grant_path:
            # 現在のgrantNumber内でdata_idが見つからない場合、他のgrantNumberで確認
            other_grant_path = self.browser.datatree_manager.get_subdir_from_new_datatree(data_id, grant_number=None)
            if other_grant_path:
                logger.warning(f"[BLOB] data_id={data_id}は他のgrantNumberに属しているため画像保存をスキップ: 現在={self.browser.grant_number}, 実際の所属パス={other_grant_path}")
                # 進行中処理リストから削除
                if hasattr(self.browser, '_active_image_processes') and data_id in self.browser._active_image_processes:
                    self.browser._active_image_processes.remove(data_id)
                return
            else:
                logger.error(f"[BLOB] data_id={data_id}がどのgrantNumberにも属していません。画像保存を中断します。")
                # 進行中処理リストから削除
                if hasattr(self.browser, '_active_image_processes') and data_id in self.browser._active_image_processes:
                    self.browser._active_image_processes.remove(data_id)
                return
        
        if isinstance(result, dict) and 'b64_list' in result and 'debug_logs' in result and 'blob_srcs' in result:
            b64_list = result['b64_list']
            debug_logs = result['debug_logs']
            filenames = result.get('filenames', [])
            blob_srcs = result['blob_srcs']
            logger.debug('[DEBUG] JSデバッグログ:')
            for log in debug_logs:
                logger.debug(log)
        else:
            b64_list = result.get('b64_list', []) if isinstance(result, dict) else result
            debug_logs = result.get('debug_logs', []) if isinstance(result, dict) else None
            filenames = result.get('filenames', []) if isinstance(result, dict) else []
            logger.debug('[DEBUG] JSデバッグログが取得できません (result型:', type(result), ')')
            logger.debug('[DEBUG] JS result内容:', result)
        if not b64_list:
            logger.debug('[DEBUG] blob画像のbase64リストが空です')
            return
        outpath_list = []
        for filename in filenames:
            if not filename:
                logger.warning('[WARN] filenameがNoneまたは空文字のためunnamed.pngに置換')
                filename = 'unnamed.png'
            
            logger.debug(f'[DEBUG] handle_blob_images : data_id: {data_id}')
            
            # 正しいsubdirパスを使用（data_idマッピングから取得）
            outdir = None
            if hasattr(self.browser, '_data_id_subdir_mapping') and data_id in self.browser._data_id_subdir_mapping:
                outdir = self.browser._data_id_subdir_mapping[data_id]
                logger.info(f'[BLOB] 正しいフォルダパス使用: data_id={data_id} -> outdir={outdir}')
            else:
                # フォールバック：従来の方法
                outdir = self.browser.datatree_manager.get_subdir_from_new_datatree(data_id, grant_number=self.browser.grant_number)
                logger.warning(f'[BLOB] フォールバック：DataTreeからパス取得: data_id={data_id}, grant_number={self.browser.grant_number} -> outdir={outdir}')
            
            if not outdir:
                logger.warning(f"[WARN] outdirが取得できませんでした: data_id={data_id}, grant_number={self.browser.grant_number}")
                # フォルダパスが取得できない場合は、data_idをフォルダ名として使用
                fallback_dir = os.path.join(self.browser.grant_number, f"data_{data_id}")
                logger.warning(f"[WARN] フォールバックディレクトリを使用: {fallback_dir}")
                outpath = os.path.join(DATASETS_DIR, fallback_dir, filename)
                outpath_list.append(outpath)
            else:
                # outdirは相対パスの場合があるので、DATASETS_DIRとの結合処理を調整
                if os.path.isabs(outdir):
                    # 絶対パスの場合はそのまま使用
                    outpath = os.path.join(outdir, filename)
                else:
                    # 相対パスの場合はDATASETS_DIRと結合
                    outpath = os.path.join(DATASETS_DIR, outdir, filename)
                outpath_list.append(outpath)
        for outpath in outpath_list:
            logger.info(f"[BLOB] 画像保存: {outpath}")
        # 画像保存は旧機能のみで実施
        self.browser.data_manager.save_blob_images_fullpath(b64_list, outpath_list)
        
        # 進行中の処理リストから削除
        if hasattr(self.browser, '_active_image_processes') and data_id in self.browser._active_image_processes:
            self.browser._active_image_processes.remove(data_id)
            logger.debug(f"[BLOB] 進行中処理リストから削除: data_id={data_id}")
        
        # 新データツリーへの格納は完全に分離してtry/exceptで副作用なしに実行
        # 旧処理側で新データツリーに格納する部分はここ以外からは呼ばない
        try:
            if hasattr(self.browser, 'datatree_manager'):
                for idx, filename in enumerate(filenames):
                    image_id = f"{data_id}_{idx}"
                    self.browser.datatree_manager.add_image_to_detail(
                        self.browser.grant_number,
                        data_id,
                        data_id,
                        image_id,
                        name=filename or 'unnamed.png',
                        type_name="image"
                    )
        except Exception as e:
            logger.warning(f"[新データツリー] images階層データツリー格納失敗: {e}")

    def _hash_blob(self, b64, filename):
        """
        blob画像のハッシュ値を計算する
        """
        h = hashlib.sha256()
        if b64:
            h.update(b64.encode())
        if filename:
            h.update(filename.encode())
        return h.hexdigest()
