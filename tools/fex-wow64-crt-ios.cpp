// SPDX-License-Identifier: MIT
// WoW64's CPU entry is called by Wine before its normal DLL startup has run.
// Keep MinGW's startup for the builds that use it, and run the GNU constructor
// list ourselves only when it was skipped. The list contains Module.cpp's
// constructor for the global Threads unordered_map; without it the map has a
// zero max_load_factor and its first emplace throws overflow_error.
#include <cstdio>
#include <cstdlib>
#include <rpmalloc/rpmalloc.h>

extern "C" void (*__CTOR_LIST__[])();

namespace {
volatile unsigned ConstructorsRan = 0;
struct ConstructorProbe {
  ConstructorProbe() { ConstructorsRan = 1; }
};
ConstructorProbe Probe;

void RunConstructorsIfNeeded() {
  if (ConstructorsRan) {
    std::fprintf(stderr, "[wow64-crt] constructors already ran\n");
    return;
  }

  // GNU's constructor list starts with -1 and ends with NULL. CRT.cpp in
  // this same FEX revision walks it in reverse order, so mirror that order.
  auto begin = &__CTOR_LIST__[1];
  auto end = begin;
  while (*end) ++end;
  while (end != begin) (*--end)();
  if (!ConstructorsRan) {
    std::fputs("[wow64-crt] constructor probe absent from list\n", stderr);
    std::abort();
  }
  std::fprintf(stderr, "[wow64-crt] ran skipped constructors\n");
}
} // namespace

namespace FEX::Windows {
void InitCRTProcess() {
  // Global constructors may allocate through rpmalloc.
  rpmalloc_initialize(nullptr);
  RunConstructorsIfNeeded();
}
void InitCRTThread() { rpmalloc_thread_initialize(); }
void DeinitCRTThread() { rpmalloc_thread_finalize(); }
} // namespace FEX::Windows
