#!/usr/bin/env python3
"""Let madeira_d3d12 learn WHICH encoder a GPU fault or hang came from.

Metal only says "Caused GPU Hang Error" for a command buffer unless the buffer
was created with MTLCommandBufferErrorOptionEncoderExecutionStatus; then the
error carries one MTLCommandBufferEncoderInfo per encoder (its label, its
debug signposts and whether it faulted). winemetal exposes neither, so this
adds two ops to its runtime-control entry (_madeira_ctl, winemetal.h's
struct madeira_ctl_args):

  8  ptr = MTLCommandQueue: len = a new command buffer created with encoder
     execution status (autoreleased, exactly like commandBuffer); ret = 1
  9  ptr -> { uint64 cb, buf, size }: writes the faulted, affected and unknown
     encoders of cb's error into buf ("[FAULTED] <label> {signposts}; ...")
     plus a count of the completed and pending ones; ret = 1

Both are local-mode only (ret stays 0 in remote mode) and the wow64 entry does
not forward them. Idempotent; fails by name if the anchor moves (the dxmt pin
changed). Run from the repository root.
"""
import pathlib
import sys

PATH = pathlib.Path("research/dxmt/src/winemetal/unix/winemetal_unix.c")
MARKER = "madeira-bcd: GPU fault attribution"

ANCHOR = """  case 2: {
    char v[512];
    if (madeira_cfg_get(a->name, v, sizeof v)) {"""

ADDITION = """  case 8: {   /* madeira-bcd: GPU fault attribution (tools/patch-dxmt-gpu-fault-info.py) */
    MTLCommandBufferDescriptor *desc;
    id<MTLCommandBuffer> cb;
    if (wmtr_enabled() || !a->ptr) break;
    desc = [MTLCommandBufferDescriptor new];
    desc.errorOptions = MTLCommandBufferErrorOptionEncoderExecutionStatus;
    cb = [(id<MTLCommandQueue>)(uintptr_t)a->ptr commandBufferWithDescriptor:desc];
    [desc release];
    a->len = (uint64_t)(uintptr_t)cb;
    a->ret = cb ? 1u : 0u;
    break;
  }
  case 9: {   /* madeira-bcd: which encoders of a failed command buffer faulted */
    struct { uint64_t cb, buf, size; } *t = (void *)(uintptr_t)a->ptr;
    char *out; size_t cap, n = 0;
    unsigned completed = 0, pending = 0;
    if (wmtr_enabled() || !t || !t->cb || !t->buf || t->size < 64) break;
    out = (char *)(uintptr_t)t->buf; cap = (size_t)t->size; out[0] = 0;
    @autoreleasepool {
      NSError *err = [(id<MTLCommandBuffer>)(uintptr_t)t->cb error];
      NSArray *infos = err ? err.userInfo[MTLCommandBufferEncoderInfoErrorKey] : nil;
      for (int pass = 0; pass < 2; pass++) {
        for (id<MTLCommandBufferEncoderInfo> info in infos) {
          MTLCommandEncoderErrorState st = info.errorState;
          const char *sn;
          int w;
          if (pass == 0) {
            if (st == MTLCommandEncoderErrorStateCompleted) completed++;
            if (st == MTLCommandEncoderErrorStatePending) pending++;
            if (st != MTLCommandEncoderErrorStateFaulted) continue;
            sn = "FAULTED";
          } else {
            if (st == MTLCommandEncoderErrorStateAffected) sn = "affected";
            else if (st == MTLCommandEncoderErrorStateUnknown) sn = "unknown";
            else continue;
          }
          if (n + 32 >= cap) break;
          w = snprintf(out + n, cap - n, "%s[%s] %s", n ? "; " : "", sn,
                       info.label.length ? info.label.UTF8String : "(no label)");
          if (w < 0 || (size_t)w >= cap - n) { n = cap - 1; break; }
          n += (size_t)w;
          for (NSString *sp in info.debugSignposts) {
            w = snprintf(out + n, cap - n, " {%s}", sp.UTF8String);
            if (w < 0 || (size_t)w >= cap - n) { n = cap - 1; break; }
            n += (size_t)w;
          }
        }
      }
      if (n + 48 < cap)
        snprintf(out + n, cap - n, "%s(%u completed, %u pending, %u encoders)", n ? "; " : "",
                 completed, pending, (unsigned)infos.count);
    }
    a->ret = 1;
    break;
  }
"""


def main():
    s = PATH.read_text()
    if MARKER in s:
        print("winemetal_unix.c: GPU fault attribution already present")
        return 0
    if s.count(ANCHOR) != 1:
        print(f"::error::{PATH}: madeira_ctl op 2 anchor not found once -- dxmt moved, review this patch")
        return 1
    s = s.replace(ANCHOR, ADDITION + ANCHOR)
    PATH.write_text(s)
    print("winemetal_unix.c: madeira_ctl ops 8/9 (GPU fault attribution) added")
    return 0


if __name__ == "__main__":
    sys.exit(main())
