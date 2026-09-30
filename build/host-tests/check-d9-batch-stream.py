"""Exercise the production batch helper, including allocation failure and ownership."""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
code = r'''
#include "d3d9_batch_stream.hpp"
#include "util_rc_ptr.hpp"
#include <cassert>
#include <atomic>
#include <iostream>
#include <thread>

struct Object {
  static inline int alive = 0;
  int refs = 0;
  Object() { ++alive; }
  ~Object() { --alive; }
  void incRef() { ++refs; }
  void decRef() { if (!--refs) delete this; }
};
struct Op { enum Kind : uint8_t { Draw, Blit, SetRef }; Kind kind; uint32_t index; };
struct Draw { dxmt::Rc<Object> pin; int value; };
struct Blit {
  enum class Kind : uint8_t { Copy, GenerateMipmaps };
  Kind kind;
  dxmt::Rc<Object> src_tex, dst_tex;
};
using Batch = dxmt::D9SealedBatch<Op, Draw, Blit, int>;
struct Failure { static inline int remaining = -1; };
template<class T> struct Allocator {
  using value_type = T;
  Allocator() = default;
  template<class U> Allocator(const Allocator<U>&) {}
  T *allocate(size_t n) {
    if (Failure::remaining == 0) throw std::bad_alloc();
    if (Failure::remaining > 0) --Failure::remaining;
    return std::allocator<T>{}.allocate(n);
  }
  void deallocate(T *p, size_t n) { std::allocator<T>{}.deallocate(p,n); }
  bool operator==(const Allocator&) const { return true; }
};
int main() {
  // Either allocation can fail. Neither may publish a dangling reference,
  // move the caller's payload, or lose a resource pin.
  for (int fail : {0,1}) {
    std::vector<Op, Allocator<Op>> ops;
    std::vector<Draw, Allocator<Draw>> draws;
    Draw input{new Object, 7};
    Failure::remaining = fail;
    try { dxmt::d9AppendBatchOp(ops, draws, Op::Draw, std::move(input)); assert(false); }
    catch (const std::bad_alloc&) {}
    assert(ops.empty() && draws.empty() && input.pin && Object::alive == 1);
    Failure::remaining = -1;
    dxmt::d9AppendBatchOp(ops, draws, Op::Draw, std::move(input));
    assert(ops.size()==1 && draws.size()==1 && ops[0].index==0);
  }
  assert(Object::alive==0);
  for (int round=0;round<1000;++round) {
    std::vector<Op> ops;
    std::vector<Draw> draws;
    std::vector<Blit> blits;
    std::vector<int> refs;
    for(int i=0;i<257;++i) {
      dxmt::d9AppendBatchOp(ops,draws,Op::Draw,Draw{new Object,i});
      dxmt::d9AppendBatchOp(ops,blits,Op::Blit,Blit{Blit::Kind::Copy,new Object,new Object});
      dxmt::d9AppendBatchOp(ops,refs,Op::SetRef,int(i));
    }
    Batch detached(ops,draws,blits,refs);
    assert(ops.empty() && draws.empty() && blits.empty() && refs.empty());
    assert(detached.valid());
    const auto hash=detached.fingerprint();
    // Encoder owns the old vectors while the recorder reuses all its vectors.
    std::thread encode([batch=std::move(detached),hash]() mutable {
      assert(batch.valid() && batch.fingerprint()==hash);
      for(int i=0;i<257;++i) {
        assert(batch.ops[i*3].kind==Op::Draw && batch.ops[i*3].index==unsigned(i));
        assert(batch.draws[i].value==i && batch.ref_ops[i]==i);
      }
      batch.ops[0].index=0x41d0f313u;
      assert(!batch.valid() && batch.fingerprint()!=hash);
      batch.ops[0].index=0;
      batch.ops[0].kind=static_cast<Op::Kind>(255);
      assert(!batch.valid());
      batch.ops[0].kind=Op::Draw;
      batch.blits[0].dst_tex=nullptr;
      assert(batch.fingerprint()!=hash);
      batch.ops.back().index=0;
      assert(!batch.valid());
    });
    for(int i=0;i<1024;++i) dxmt::d9AppendBatchOp(ops,refs,Op::SetRef,int(i));
    encode.join();
    assert(Object::alive==0);
  }
  std::vector<Op> ops{{Op::Draw,0}};
  std::vector<Draw> draws;
  std::vector<Blit> blits;
  std::vector<int> refs;
  Batch missing(ops,draws,blits,refs);
  assert(!missing.valid());
  std::cout << "PASS: atomic append failure, pin lifetime, detached FIFO, concurrent recorder, corrupt index/tag/pointer detection\n";
}
'''
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp)
    source = path / "batch-stream.cpp"
    source.write_text(code)
    output = path / "batch-stream"
    subprocess.run([
        os.environ.get("CXX", "g++"), "-std=c++20", "-O1", "-g", "-pthread",
        "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
        "-I", str(root / "research/dxmt/src/d3d9"),
        "-I", str(root / "research/dxmt/src/util/rc"),
        str(source), "-o", str(output),
    ], check=True)
    subprocess.run([str(output)], check=True)

device = (root / "research/dxmt/src/d3d9/d3d9_device.cpp").read_text()
assert device.count("d9AppendBatchOp(m_pendingOps,") == 3
assert "D9SealedBatch<PendingOpRef, BatchedDraw, PendingBlitOp, PendingRefOp>" in device
assert "const PendingOpRef ref = entry;" in device
assert "[d9-batch-integrity]" in device
assert "batch_check ? batch.fingerprint() : 0" in device
print("PASS: production append, detached capture, consumption checks and opt-in checksum wiring")
