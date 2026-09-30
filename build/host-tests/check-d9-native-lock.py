"""Exercise the production recursive lock and batch helper with concurrent callers.

Only Windows thread/yield APIs and logging/environment dependencies are stubbed.
The lock, batch append and detach implementations are the production headers.
"""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
dxmt = root / "research/dxmt/src"
glue = (dxmt / "d3d9/unix/d3d9_native_glue.cpp").read_text()
assert glue.count("(flags | (DWORD)D3DCREATE_MULTITHREADED)") == 2
assert "flags ^ (DWORD)D3DCREATE_MULTITHREADED" not in glue
assert "remember_behavior_flags(static_cast<void *>(created), flags)" in glue
assert "static_cast<void *>(static_cast<IDirect3DDevice9Ex *>(created)), flags" in glue
assert "parameters->BehaviorFlags = it->second" in glue

code = r'''
#include "d3d9_multithread.hpp"
#include "d3d9_batch_stream.hpp"
#include <cassert>
#include <iostream>
#include <thread>
#include <vector>

struct Op { enum Kind : uint8_t { Draw, Blit, SetRef }; Kind kind; uint32_t index; };
struct Blit { enum class Kind : uint8_t { Copy }; Kind kind; void *src_tex, *dst_tex; };
using Batch = dxmt::D9SealedBatch<Op, int, Blit, int>;

// Deterministically detach between payload and reference publication, with
// ordered atomic handshakes. No concurrent vector access/undefined behavior.
// This models the interleaving possible when recording has no device lock.
struct PausedPayloads : std::vector<int> {
  std::atomic<int> *stage;
  explicit PausedPayloads(std::atomic<int> &s) : stage(&s) {}
  void push_back(int &&value) {
    std::vector<int>::push_back(std::move(value));
    stage->store(1, std::memory_order_release);
    while (stage->load(std::memory_order_acquire) != 2) std::this_thread::yield();
  }
};
int main() {
  {
    std::atomic<int> stage{0};
    std::vector<Op> ops;
    PausedPayloads refs(stage);
    std::vector<int> draws;
    std::vector<Blit> blits;
    std::thread producer([&] {
      dxmt::d9AppendBatchOp(ops, refs, Op::SetRef, int(7));
    });
    while (stage.load(std::memory_order_acquire) != 1) std::this_thread::yield();
    Batch detached(ops, draws, blits, static_cast<std::vector<int>&>(refs));
    assert(!detached.valid()); // payload without operation, as in the hang
    stage.store(2, std::memory_order_release);
    producer.join();
    Batch next(ops, draws, blits, static_cast<std::vector<int>&>(refs));
    assert(!next.valid()); // operation referring into the detached payloads
  }
  for (int round=0; round<2; ++round) {
    dxmt::D9Multithread device(true);
    std::vector<Op> ops;
    std::vector<int> draws, refs;
    std::vector<Blit> blits;
    std::atomic<int> finished{0};
    size_t consumed = 0;
    auto drain = [&] {
      auto lock = device.AcquireLock();
      Batch batch(ops, draws, blits, refs);
      assert(batch.valid());
      consumed += batch.ops.size();
    };
    std::vector<std::thread> producers;
    for (int worker=0; worker<4; ++worker) producers.emplace_back([&,worker] {
      for (int i=0; i<20000; ++i) {
        auto lock = device.AcquireLock();
        // Public API forwarding can re-enter the lock on the same thread.
        auto nested = device.AcquireLock();
        if (worker & 1) dxmt::d9AppendBatchOp(ops, draws, Op::Draw, int(i));
        else dxmt::d9AppendBatchOp(ops, refs, Op::SetRef, int(i));
      }
      finished.fetch_add(1, std::memory_order_release);
    });
    while (finished.load(std::memory_order_acquire) != 4) drain();
    for (auto &producer : producers) producer.join();
    drain();
    assert(consumed == 80000);
  }
  std::cout << "PASS: unprotected split reproduction; recursive native lock, four producers and concurrent detach preserve 160000 operations\n";
}
'''
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp)
    (path / "log").mkdir()
    (path / "windows.h").write_text(r'''
#pragma once
#include <atomic>
#include <chrono>
#include <thread>
inline unsigned GetCurrentThreadId() {
  static std::atomic<unsigned> next{1};
  thread_local unsigned id = next.fetch_add(1);
  return id;
}
inline void YieldProcessor() { std::atomic_signal_fence(std::memory_order_seq_cst); }
inline void SwitchToThread() { std::this_thread::yield(); }
inline void Sleep(unsigned ms) { std::this_thread::sleep_for(std::chrono::milliseconds(ms)); }
''')
    (path / "log/log.hpp").write_text(
        '#pragma once\nnamespace dxmt { struct Logger { template<class... T> static void warn(T&&...) {} }; }\n')
    (path / "util_env.hpp").write_text(
        '#pragma once\n#include <string>\nnamespace dxmt::env { inline std::string getEnvVar(const char*) { return "0"; } }\n')
    (path / "util_string.hpp").write_text(
        '#pragma once\n#include <string>\nnamespace dxmt::str { template<class... T> std::string format(T&&...) { return {}; } }\n')
    source = path / "native-lock.cpp"
    source.write_text(code)
    output = path / "native-lock"
    subprocess.run([
        os.environ.get("CXX", "g++"), "-std=c++20", "-O1", "-g", "-pthread",
        "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
        "-I", str(path), "-I", str(dxmt / "d3d9"),
        str(source), "-o", str(output),
    ], check=True)
    subprocess.run([str(output)], check=True, timeout=60)
print("PASS: both creation paths force protection and report the original guest flags")
