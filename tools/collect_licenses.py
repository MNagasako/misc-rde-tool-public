#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,shutil,sys
from pathlib import Path
from importlib import metadata as md
KEYWORDS=("license","copying","notice","licence"); TEXT_EXT={"",".txt",".md",".rst",".html"}; MAX_SIZE=5_000_000
def slug(s:str)->str: return re.sub(r"[^A-Za-z0-9_.-]","-",s)
def read_targets(p:Path|None): 
    if not p: return None
    names=set()
    for ln in p.read_text(encoding="utf-8",errors="ignore").splitlines():
        t=ln.strip(); 
        if t: names.add(t.lower())
    return names or None
def ensure_dir(p:Path): p.mkdir(parents=True,exist_ok=True)
def select_dists(targets:set[str]|None):
    d=[]
    for dist in md.distributions():
        try: name=dist.metadata["Name"].strip()
        except KeyError: continue
        name_l=(name or "").lower(); tops=set()
        try:
            tl=dist.read_text("top_level.txt")
            if tl: tops={x.strip().lower() for x in tl.splitlines() if x.strip()}
        except FileNotFoundError: pass
        if (targets is None) or ({name_l}|tops & targets): d.append(dist)
    return d
def copy_file(src:Path,dst:Path)->bool:
    try:
        if src.stat().st_size>MAX_SIZE: return False
        ensure_dir(dst.parent); shutil.copy2(src,dst); return True
    except Exception: return False
def collect_for_dist(dist,out_root:Path)->dict:
    name=dist.metadata.get("Name","unknown"); ver=dist.version or ""
    outdir=out_root/"packages"/f"{slug(name)}-{slug(ver)}"; ensure_dir(outdir)
    copied=[]; has=False
    for f in list(dist.files or []):
        fn=f.name.lower(); ext=Path(f.name).suffix.lower()
        if any(k in fn for k in KEYWORDS) and ext in TEXT_EXT:
            src=Path(dist.locate_file(f))
            if src.is_file() and copy_file(src,outdir/src.name): has=True; copied.append(src.name)
    (outdir/"METADATA").write_text(dist.read_text("METADATA") or "",encoding="utf-8",errors="ignore")
    if not has:
        lic=dist.metadata.get("License","").strip()
        cls=[c for c in dist.metadata.get_all("Classifier",[]) if c.startswith("License ::")]
        (outdir/"LICENSE-INFO.json").write_text(json.dumps({"name":name,"version":ver,"license":lic,"classifiers":cls,"note":"No LICENSE file found in dist-info; fell back to metadata."},ensure_ascii=False,indent=2),encoding="utf-8")
    return {"name":name,"version":ver,"copied":copied}
def copy_python_runtime_license(out_root:Path):
    import sys
    for c in [Path(sys.prefix)/"LICENSE.txt",Path(sys.prefix)/"LICENSE",Path(sys.base_prefix)/"LICENSE.txt",Path(sys.base_prefix)/"LICENSE"]:
        if c.is_file(): 
            copy_file(c,out_root/"python"/("LICENSE.txt" if c.suffix else "LICENSE")); break
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--targets-file",type=Path,default=None)
    ap.add_argument("--output",type=Path,default=Path("THIRD_PARTY_NOTICES"))
    ap.add_argument("--include-python",action="store_true")
    ap.add_argument("--include-pyinstaller",action="store_true")
    args=ap.parse_args()
    targets=read_targets(args.targets_file); out_root=args.output; ensure_dir(out_root)
    dists=select_dists(targets)
    if args.include_pyinstaller:
        targets=(targets or set())|{"pyinstaller","pyinstaller-hooks-contrib"}
        dists=select_dists(targets)
    idx=[]
    for dist in sorted(dists,key=lambda d:(d.metadata.get("Name",""))):
        try: idx.append(collect_for_dist(dist,out_root))
        except Exception as e: idx.append({"name":dist.metadata.get("Name","?"),"version":dist.version,"error":str(e)})
    if args.include_python: copy_python_runtime_license(out_root)
    (out_root/"licenses_index.json").write_text(json.dumps(idx,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Wrote {out_root}/licenses_index.json and copied licenses for {len(idx)} distributions.")
if __name__=="__main__": main()
