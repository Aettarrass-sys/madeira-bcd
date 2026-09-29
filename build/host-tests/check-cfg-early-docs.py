#!/usr/bin/env python3
"""Exercise the production madeira.cfg lookup after Wine changes HOME."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
cc = os.environ.get("CC") or shutil.which("cc") or shutil.which("clang")
if not cc:
    raise SystemExit("A C compiler is required")

source = r'''
#include <stdio.h>
#include "madeira_cfg.h"
int main(void) {
    printf("%d %s\n", madeira_cfg_bool("inproc-sync", 0), madeira_cfg_dir_source());
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix="madeira-early-cfg-") as directory:
    tmp = Path(directory)
    src, exe = tmp / "check.c", tmp / "check"
    src.write_text(source, encoding="utf-8")
    subprocess.run([cc, "-std=gnu11", "-I", str(root / "build"), str(src), "-o", str(exe)], check=True)

    container = tmp / "container"
    docs = container / "Documents"
    prefix = docs / "wine"
    prefix.mkdir(parents=True)
    (docs / "madeira.cfg").write_text("inproc-sync = 1\n", encoding="utf-8")
    (prefix / "Documents").mkdir()
    (prefix / "Documents" / "madeira.cfg").write_text("inproc-sync = 0\n", encoding="utf-8")

    def run(extra):
        env = {k: v for k, v in os.environ.items()
               if k not in ("MADEIRA_DOCS_DIR", "CFFIXED_USER_HOME", "MADEIRA_CFG_EARLY_DOCS")}
        env["HOME"] = str(prefix)  # the wineserver's changed HOME
        env.update(extra)
        return subprocess.check_output([str(exe)], env=env, text=True).strip()

    assert run({"CFFIXED_USER_HOME": str(container)}) == "1 container"
    assert run({"MADEIRA_DOCS_DIR": str(docs), "CFFIXED_USER_HOME": str(container)}) == "1 env"
    assert run({"CFFIXED_USER_HOME": str(container), "MADEIRA_CFG_EARLY_DOCS": "0"}) == "0 home"
    assert run({}) == "0 home"
print("PASS: early config lookup survives Wine's HOME change and preserves the off default")
