#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import ast,re
from typing import Iterable,Any
BUILD=Path("build")
if not BUILD.exists(): raise SystemExit("build ディレクトリが見つかりません。先に PyInstaller を実行してください。")
tocs=sorted(BUILD.rglob("COLLECT-*.toc")) or sorted(BUILD.rglob("*.toc"))
if not tocs: raise SystemExit(".toc が見つかりません。")
obj=ast.literal_eval(tocs[-1].read_text(encoding="utf-8",errors="ignore"))
SITE_RE=re.compile(r"site-packages[/\\]([^/\\]+)"); PKG_RE=re.compile(r"[A-Za-z0-9_]+")
def walk(o:Any):
    if isinstance(o,str): yield o
    elif isinstance(o,(list,tuple,set)):
        for i in o: yield from walk(i)
    elif isinstance(o,dict):
        for k,v in o.items(): yield from walk(k); yield from walk(v)
tops=set()
for s in walk(obj):
    m=SITE_RE.search(s.replace("\\","/"))
    if m:
        name=PKG_RE.findall(m.group(1))[0]
        if name and not name[0].isdigit(): tops.add(name)
for name in sorted(tops): print(name)
