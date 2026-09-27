# Handoff: state of the madeira-bcd fork (2026-09-27)

> **Türkçe özet:** Bu dosya, Claude ile bu depoda yapılan bütün işin devir
> notudur; başka bir asistan (ör. ChatGPT Codex) buradan devam edebilsin diye
> yazıldı. Kullanıcıya Türkçe yanıt verilir. Teknik ayrıntıların tamamı
> `docs/madeira-bcd.md` içinde; bu dosya "nerede kaldık, kurallar neler,
> sırada ne var" sorularını cevaplar.

This file is for whoever continues the work (another coding agent or a
person). Read it first, then `docs/madeira-bcd.md` (every change this fork
makes, with the reason and the evidence), `docs/WOW64.md`, `docs/BUILDING.md`.

---

## 1. What this repository is

`bahacan16/madeira-bcd` is a personal fork of `willfaust/Madeira`: Wine + FEX
(x86-64 JIT, ARM64EC) + DXMT (D3D11/D3D9 over Metal) + `madeira_d3d12` (a D3D12
runtime over Metal that converts DXIL with Apple's Metal Shader Converter and
DXBC with DXMT's airconv) packaged as an iOS app. The owner runs Windows games
on an **iPhone 17 Pro Max, iOS 27.0**, sideloaded with Feather. Personal use
only; the bundle id stays `com.willfaust.mythicemu`.

Upstream PRs merged into the fork (not yet merged upstream):
* **#28 (125hz)** WoW64 32-bit guests + DXMT D3D9. Needs the companion
  submodule forks: `wine` -> `125hz/wine` branch `pr/wow64-core`,
  `research/dxmt` -> `125hz/dxmt` branch `pr/d3d9` (see `.gitmodules`).
  The prebuilt DLLs from #28/#29 (i386 farm, ntdll, xtajit64) were committed
  with the owner's explicit approval.
* **#29 (125hz)** named touch-control layouts.

## 2. Working conventions the owner expects

* **Reply in Turkish.** Owner's clock is UTC+3.
* Work autonomously: diagnose from the log, fix, build, hand over an IPA link.
  The owner dislikes being asked things the agent can decide itself.
* Develop on branch **`claude/madeira-bcd-repo-ymg5cb`**, push there.
* Build: dispatch `.github/workflows/build-ipa.yml` on that branch
  (workflow_dispatch). When it is green, fast-forward `main`
  (`git push origin <sha>:main`); if that starts an automatic push build on
  `main`, cancel it (it is a duplicate).
* Version = `0.1.<run_number>` (Info.plist stamped in CI). The artifact is
  `madeira-0.1.<N>-unsigned-ipa`; link format
  `https://github.com/bahacan16/madeira-bcd/actions/runs/<run id>`.
  Downloading artifacts needs a signed-in GitHub account (GitHub rule).
* CI failures: read annotations with
  `curl -s https://api.github.com/repos/bahacan16/madeira-bcd/check-runs/<job id>/annotations`;
  full logs via the Actions UI / API job logs.
* Commit messages: say what was wrong, the evidence, and the fix (see
  `git log`). Keep `docs/madeira-bcd.md` updated for every change.
* A 12-hour "upstream sync" routine existed on the Claude side (merge
  `willfaust/Madeira` main into the dev branch, keep 125hz's submodule
  commits). It will not run elsewhere; do it by hand if needed:
  `git fetch upstream main` (remote = willfaust/Madeira), merge, keep this
  fork's additions, build, fast-forward main.

## 3. Hard rules (do not break)

* **Never commit Microsoft VC++ runtime DLLs** (`app/Madeira/x86_64-vcruntime/*.dll`
  is gitignored; CI fetches them).
* **Apple's Metal Shader Converter** installer lives ONLY as an asset of a
  **DRAFT** release tagged **`msc-private`** (`Metal_Shader_Converter_4.0_beta_2.pkg`).
  CI extracts headers + the iOS library at build time into gitignored
  `build/madeira-d3d12/msc-include/`. Never commit the pkg, headers or library,
  never publish that release. Since build 181 CI **fails** if the release is
  missing (build 180 silently shipped a stub: black screen in every D3D12 game).
* Do not publish IPAs as public releases without the owner's decision (the IPA
  contains Microsoft redistributables and Apple's converter library).
* Do not commit externally supplied binaries (exception already granted: the
  125hz PR #28/#29 DLLs).
* The owner's Ghost of Tsushima / Crysis copies are cracked (RUNE / Steam
  emulator). Fix Madeira-side bugs only; **do not help configure crack or
  Steam-emulator files** (e.g. `steam_api.ini`).
* A GitHub PAT was once pasted in chat; the owner was told to revoke it. Never
  use tokens from chat. A signing `.p12` (+password) and `.mobileprovision`
  were shared read-only; never commit or use them.

## 4. Current focus: Ghost of Tsushima (D3D12, Nixxes port)

### Progress so far (each item is a commit; details in docs/madeira-bcd.md)
Save folder -> D3D12 use-after-free -> display config crash -> GPU driver info
(NVAPI entry points + a registry display adapter, "Report an NVIDIA GPU"
per-game switch) -> `GetAdapterLuid` -> `GetDeviceRemovedReason` -> DXBC
static samplers (black screen) -> intros + main menu work -> New Game OOM
(30k Metal libraries) fixed by lazy pipelines + shared libraries + a
persistent disk shader cache -> game reaches gameplay (~20-40 FPS) ->
**GPU timeout a few seconds into gameplay** (the remaining blocker).

### The GPU timeout (build 181 should fix it — verify)
Every run: 2-5 s into gameplay FPS sinks from ~40 to ~20, then Metal ends a
command buffer with `MTLCommandBufferError` code 2 (timeout), ignores the queue,
and the game tears itself down (its workers then fault copying freed memory,
its crash handler `crs-handler.exe` crashes — both are consequences).
Found with the fault-attribution machinery (below): the kernel (DXIL hash
`34c565ac8322ab2a`, 3948 bytes, `Dispatch(221,1,1)`, 64 threads/group) is a
vertex-normal recompute. Each thread reads a `[first,last)` adjacency range
from a StructuredBuffer at its thread id and loops `until i == last`. The
dispatch is rounded up to the group size, so the extra threads read past the
buffer. D3D12 returns 0 there; the converter did not bounds-check
(`IRCompatibilityFlagBoundsCheck` was off), read garbage and looped forever.
**Build 181 converts with `IRCompatibilityFlagBoundsCheck`**
(`research/madeira-d3d12/src/unix/madeira_ir_unix.mm`; opt out with
`MADEIRA_IR_NO_BOUNDS_CHECK=1`). The shader-cache key changed, so the first
launch re-converts everything (the "Compiling shaders" screen takes a few
minutes and looks frozen — do not close it).

**Next step:** have the owner run build 181 (AVX on, "Report an NVIDIA GPU"
on, press Enter at the dark launcher, New Game) and check the log: there
should be no `GPU fault` line and FPS should stay flat.

### Open issues, roughly in priority order
1. Verify the timeout fix (above). If faults remain, the machinery names the
   next kernel.
2. **Black squares** on screen (menu and gameplay, fixed grid positions).
   Not explained yet. Candidates: a tiled full-screen compute pass that skips
   tiles, the missing R32G32B32_FLOAT texture format (`texture format 6 has no
   Metal mapping`), tessellation placeholders. A frame capture
   (`madeira.cfg` capture keys, `Documents/capture/`) would settle it.
3. **Tessellation with DXIL**: 23 hull/domain pipelines are placeholders whose
   draws are skipped (terrain/water missing). `mad_tess_build` only handles the
   DXBC backend; DXIL needs the converter's tessellation emulation.
4. **"Compiling shaders" takes ~1.5-2 min every launch** even with 100 % cache
   hits: 30k small cache files opened through Wine plus ~11k Metal library
   creations. Idea: pack the cache into one mapped file with an index.
5. The launcher window stays dark until Enter is pressed.
6. `DXGIFactory::EnumAdapterByLuid` not implemented (Streamline only);
   non-occlusion queries resolve to zero; `ResolveQueryData` into GPU-only
   buffers is not delivered.
7. 32-bit games through WoW64: Crysis runs with small problems (not looked
   at yet); Crysis 3 (32-bit) exhausts the 4 GB guest window (advise Bin64 /
   lower settings).

## 5. Debugging toolkit built during this work

Log = the file the owner uploads (`GhostOfTsushima.exe-<date>.txt`). Useful greps:

| grep | meaning |
|---|---|
| `GPU fault encoders: code N` | failed command buffer; code 2 = timeout, 3/4 = page fault/ignored; `[FAULTED] C#<seq> <kernel> fn=...` names the encoder |
| `GPU fault dispatch C#` | bindings of the faulted dispatch (root params, descriptors resolved to resources, `RUNS PAST THE END`) |
| `[b64 <hash>]` | bytecode of a faulting compute shader, logged at the NEXT launch (also `C:\madeira-cs\fault_<hash>.dxil`) |
| `shader cache: N hits` / `shared shader libraries` | disk cache / library sharing |
| `currentAllocatedSize`, `[footprint]`, `[proc-mem]` | Metal memory and process footprint (limit 8192 MB) |
| `[fault-rgn]   history:` | who created/deleted the view at a faulting address (1 MB+ views) |
| `[stack-quarantine]` | a dead thread's stack was touched while quarantined |
| `[va-scan] FAILED ... STATUS_NO_MEMORY` | address-space exhaustion |
| `[wow-window] ... placed above them` | 64-bit views placed above the 32-bit slots |
| `skips by site` | draws/dispatches skipped (L<line> in madeira_d3d12.c) |

Disassembling a captured shader:
```
grep -a "^\[b64 <hash>\]" log.txt | sed 's/^\[b64 [0-9a-f]*\] //' | tr -d '\n' | base64 -d > s.dxil
pip install llvmlite
python3 tools/dxil-disasm.py s.dxil > s.ll
```

madeira.cfg keys added here: `shader-cache` (default 1), `pso-lazy` (1),
`gpu-fault-info` (1), `gpu-fault-skip` (1), `encoder-labels` (0),
`vmwatch = 0x<addr>` (existing). Env: `MADEIRA_IR_NO_BOUNDS_CHECK=1`.

Metal Shader Converter headers for reading (never commit): download the pkg
from the draft release through the API, unpack xar -> Payload (pbzx/cpio) ->
`usr/local/include/metal_irconverter{,_runtime}/`. Key facts learned there:
descriptor heap bind point 0, sampler heap 1, top-level argument buffer 2;
UAV counters are an R32Uint texture-buffer view in the descriptor's texture
id word with the element offset in metadata bits 32..39
(`IRRuntimeCreateAppendBufferView`); buffer metadata = size | texview offset
<<32 | typed<<63.

Local compile check of `madeira_d3d12` (no device needed): llvm-mingw
`arm64ec-w64-mingw32-clang -shared -O2 -Wall madeira_d3d12.c d3d12.def -I...
-lwinemetal -luuid -lole32` with an import lib generated from
`research/dxmt/src/winemetal` exports (gendef/dlltool). The Wine unix side
(`build/ntdll-unix/*_ios.c`) only compiles in CI (Darwin/Mach headers).

## 6. Where things live

* `research/madeira-d3d12/src/pe/madeira_d3d12.c` — the D3D12 runtime (PE,
  ARM64EC). Most GoT fixes are here.
* `research/madeira-d3d12/src/unix/madeira_ir_unix.mm` — shader conversion
  service (Metal Shader Converter / airconv), unix side.
* `research/dxmt` (submodule, 125hz fork) — winemetal bridge; patched at build
  time by `tools/patch-dxmt-*.py` (the submodule itself is not modified).
* `build/ntdll-unix/virtual_ios.c`, `thread_ios.c` — Wine VM/threads on iOS
  (address-space windows, swap tier, view history, stack quarantine).
* `build/win32u-unix/sysparams_ios.c` — display devices / virtual GPU registry.
* `app/Madeira/*.swift` — the app (library, per-game settings incl. AVX and
  "Report an NVIDIA GPU").
* `.github/workflows/build-ipa.yml` — the whole build.
