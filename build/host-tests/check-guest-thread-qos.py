"""Exercise the inserted production policy guard; Darwin runtime needs a device."""
from pathlib import Path
import importlib.util
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("qos_patch", root / "tools/patch-wine-thread-qos.py")
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)
source = (root / "wine/server/thread.c").read_text()
assert patch.NEW in source
guard = patch.NEW[patch.NEW.index("#ifdef WINE_IOS"):patch.NEW.index("\n    if (!process_port)")]
bridge = (root / "app/Madeira/WineProcessBridge.m").read_text()
assert "pthread_attr_set_qos_class_np(&attr, QOS_CLASS_USER_INTERACTIVE, 0)" in bridge
assert "pthread_attr_setschedparam(&attr" not in bridge
assert "int qrc = pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0)" in bridge
assert "if (qrc || (diag && diag[0] == '1'))" in bridge
code = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#define LOW_REALTIME_PRIORITY 16
struct Thread { int id, base_priority; };
static int mach_policies;
static void apply(struct Thread *thread, int effective_priority) {
''' + guard + r'''
  ++mach_policies;
}
int main(int argc, char **argv) {
  int preserve = atoi(argv[1]);
  struct Thread thread = {42,0};
  for (int i=-15;i<32;++i) {
    int before = mach_policies;
    apply(&thread,i);
    assert(mach_policies-before == !(preserve && i<LOW_REALTIME_PRIORITY));
  }
}
'''
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp)
    mock = path / "policy.c"
    mock.write_text(code)
    # Exercise the actual idempotent patcher against a baseline and then reject
    # an unknown source, without changing the checkout.
    target = path / "thread.c"
    target.write_text(source.replace(patch.NEW, patch.OLD))
    patch.apply(target)
    assert target.read_text() == source
    patch.apply(target)
    target.write_text("unknown source")
    try:
        patch.apply(target)
        raise AssertionError("missing anchor accepted")
    except RuntimeError:
        pass
    for ios in [True, False]:
        binary = path / ("ios" if ios else "desktop")
        subprocess.run([os.environ.get("CC", "cc"), "-std=c11", "-O1",
                        *(["-DWINE_IOS=1"] if ios else []), str(mock), "-o", str(binary)], check=True)
        for rollback in [False, True]:
            for diag in [False, True]:
                env = dict(os.environ, MADEIRA_WIN_THREAD_PRIORITY="1" if rollback else "0",
                           MADEIRA_DIAG="1" if diag else "0")
                result = subprocess.run([str(binary), "1" if ios and not rollback else "0"],
                                        env=env, capture_output=True, check=True, timeout=10)
                assert bool(result.stderr) == (ios and diag)
                assert result.stderr.count(b"[thread-prio]") == (24 if ios and diag else 0)
print("PASS: realtime preserved, iOS default/rollback, quiet/bounded diagnostics, non-iOS unchanged, idempotent patch")
print("PASS: guest main uses QoS attributes rather than fixed priority; Darwin scheduling needs device validation")
