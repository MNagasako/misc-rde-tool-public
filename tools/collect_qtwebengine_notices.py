#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse, shutil
TEXT_EXT={"",".txt",".md",".rst",".html"}; MAX_SIZE=5_000_000
def ensure_dir(p:Path): p.mkdir(parents=True,exist_ok=True)
def copy_file(src:Path,dst:Path)->bool:
    try:
        if src.stat().st_size>MAX_SIZE: return False
        ensure_dir(dst.parent); shutil.copy2(src,dst); return True
    except Exception: return False
def find_qt_root()->Path|None:
    try:
        import PyQt5
        base=Path(PyQt5.__file__).parent
        for cand in ("Qt","Qt5","Qt6"):
            qt=base/cand
            if qt.exists(): return qt
    except Exception: pass
    return None
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,default=Path("THIRD_PARTY_NOTICES"))
    ap.add_argument("--dist",type=Path,default=None,help="PyInstaller の dist 出力を指定して探索するフォールバック")
    args=ap.parse_args()
    out_root=args.output; qt_root=find_qt_root()
    if not qt_root and args.dist:
        for p in args.dist.rglob("*"):
            if p.is_dir() and p.name in {"Qt","Qt5","Qt6"}: qt_root=p; break
    if not qt_root: raise SystemExit("Qt ディレクトリが見つかりません。PyQt5 がインストール済みの環境で実行するか、--dist で dist/… を指定してください。")
    qt_out=out_root/"qt"; web_out=out_root/"qtwebengine"; ensure_dir(qt_out); ensure_dir(web_out)
    for pat in ("LICENSE*","*.LICENSE*","*License*","*license*"):
        for p in qt_root.glob(pat):
            if p.is_file() and p.suffix.lower() in TEXT_EXT: copy_file(p,qt_out/p.name)
    patterns=["**/LICENSES.chromium.html","**/chromium*LICENSE*","**/third_party/**/LICENSE*","**/ffmpeg*LICENSE*","**/icu*LICENSE*","**/harfbuzz*LICENSE*","**/freetype*LICENSE*","**/skia*LICENSE*","**/angle*LICENSE*","**/libpng*LICENSE*","**/libjpeg*LICENSE*","**/zlib*LICENSE*","**/*NOTICE*"]
    seen=set(); count=0
    for pat in patterns:
        for p in qt_root.rglob(pat):
            if p.is_file() and p.suffix.lower() in TEXT_EXT:
                key=(p.name.lower(),p.stat().st_size)
                if key in seen: continue
                seen.add(key)
                if copy_file(p,web_out/p.name): count+=1
    (web_out/"README.md").write_text(
        "# Qt WebEngine Third-Party Notices\n\n"
        "このフォルダには、Qt WebEngine (Chromium ベース) に由来する Third-Party のライセンス/NOTICE 文書を同梱しています。\n"
        "Chromium および関連コンポーネント（FFmpeg, ICU, HarfBuzz, FreeType, Skia, ANGLE, zlib, libpng, libjpeg など）の条項に従います。\n"
        f"\n収集ファイル数: {count}\n", encoding="utf-8")
    print(f"Collected Qt/QtWebEngine notices into {web_out} (files: {count})")
if __name__=="__main__": main()
