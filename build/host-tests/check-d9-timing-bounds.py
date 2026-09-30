"""Compile the production timing accumulation with sanitizers and known inputs."""
from pathlib import Path
import os
import re
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / "research/dxmt/src/d3d9/d3d9_device.cpp").read_text()
header = (root / "research/dxmt/src/d3d9/d3d9_device.hpp").read_text()
context = (root / "research/dxmt/src/dxmt/dxmt_context.hpp").read_text()
start = source.index("    for (size_t i = 0; i < stage_us.size(); ++i)")
end = source.index("    m_targetInitializerWaits +=", start)
body = source[start:end]
members = "\n".join(re.findall(
    r"  std::array<uint64_t, \d+> m_target(?:StageUs|StageMaxUs|FlushNs|FlushCounts|FineNs)\{\};", header))
assert len(members.splitlines()) == 5
flush = re.search(r"struct FlushDiagnostics \{.*?\n\};", context, re.S).group()
code = r'''
#include <array>
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstddef>
''' + flush + '\nstruct Totals {\n' + members + r'''
  void add() {
    std::array<uint64_t, 6> stage_us{10,20,30,40,50,60};
    struct { FlushDiagnostics flush; } timing;
    timing.flush.nanoseconds = {100,200,300,400,500};
    timing.flush.counts = {1,2,3,4,5};
    timing.flush.fine_nanoseconds = {11,22,33,44,55,66,77,88,99,110};
''' + body + r'''
  }
};
int main() {
  Totals totals;
  for (int round=1; round<=1000; ++round) {
    totals.add();
    for (size_t i=0; i<6; ++i) {
      assert(totals.m_targetStageUs[i] == round*(i+1)*10);
      assert(totals.m_targetStageMaxUs[i] == (i+1)*10);
    }
    for (size_t i=0; i<5; ++i) {
      assert(totals.m_targetFlushNs[i] == round*(i+1)*100);
      assert(totals.m_targetFlushCounts[i] == round*(i+1));
    }
    for (size_t i=0; i<10; ++i)
      assert(totals.m_targetFineNs[i] == round*(i+1)*11);
  }
}
'''
split = """    }
    // Stage timings have six entries; encoder buckets have only five.
    // Never index the flush arrays using stage_us.size().
    for (size_t i = 0; i < m_targetFlushNs.size(); ++i) {
"""
assert split in body
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp)
    for name, contents in [("fixed", code), ("old", code.replace(split, ""))]:
        src = path / f"{name}.cpp"
        src.write_text(contents)
        binary = path / name
        subprocess.run([os.environ.get("CXX", "g++"), "-std=c++20", "-O1", "-g",
                        "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                        str(src), "-o", str(binary)], check=True)
        result = subprocess.run([str(binary)], capture_output=True, timeout=15)
        if name == "fixed":
            assert result.returncode == 0, result.stderr.decode(errors="replace")
        else:
            assert result.returncode != 0, "old six/five overrun was not detected"
print("PASS: original overrun rejected; production stage, bucket and fine totals correct for 1000 windows")
