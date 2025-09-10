#!/usr/bin/env python3
# AST静的解析でトップレベルimportを列挙
import ast
from pathlib import Path
EXCLUDE_DIRS={".git",".hg",".svn","__pycache__",".venv","venv","build","dist","tests"}
ROOT=Path(".").resolve(); roots=set()
for p in ROOT.rglob("*.py"):
    if any(part in EXCLUDE_DIRS for part in p.parts): continue
    try: t=ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
    except Exception: continue
    for n in ast.walk(t):
        if isinstance(n, ast.Import):
            for a in n.names: roots.add(a.name.split(".")[0])
        elif isinstance(n, ast.ImportFrom) and n.module:
            roots.add(n.module.split(".")[0])
for name in sorted(roots): print(name)
