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

### The GPU timeout (fixed in build 181, confirmed on device)
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

### Build 181 result (log 2026-09-27 14:55, 800x600): the GPU timeout is GONE
No `GPU fault` line at all; the scene renders (banners, grass) at 50-60 FPS
before gameplay. The new wall is on the CPU: when gameplay starts,
`ExecuteCommandLists` per frame goes 25 ms -> 273 ms -> 2.3 s while the GPU
is 2-7 % busy (Metal HUD: "Detected high CPU encoding cost with encoders
spending an average of 100% of frame time encoding"; "Compiled Shaders 693 |
12.5 s"). Cause: lazy pipelines (`mad_pso_realize`) are compiled by Metal at
their first draw, on the submitting thread, one at a time, under one global
lock; the first gameplay seconds need hundreds. After ~2 s frames the game
stops itself at the same `int3` it uses for fatal errors (guest RIP ...9acd,
call chain ...b950 / ...63e5) — most likely its own hang watchdog.

**Build 183** (commit "build a batch's new pipelines in parallel"): a per-pipeline lock replaces the
global one, and before a batch is replayed the lazy pipelines its lists bind
are built on up to 4 threads (`mad_prebuild_lists`, madeira.cfg
`pso-parallel = 0` to disable; log line `pso-parallel: built N pipelines`).
Expected: the stall shrinks roughly by the core count. If frames still take
seconds, next steps (in order of payoff):
1. **Persist compiled pipelines across launches** with `MTLBinaryArchive`
   (or Metal 4 `MTL4Archive`): add winemetal calls to create/load an archive,
   add pipeline descriptors to it, serialize it next to the shader cache
   (`%LOCALAPPDATA%\Madeira\ShaderCache\<build>\`), and pass it as
   `binaryArchives` when creating pipelines. Second launch then compiles
   nothing. Needs changes in `research/dxmt/src/winemetal` (done at build
   time through a `tools/patch-dxmt-*.py`, like the fault-info patch).
2. Start building a lazy pipeline in the background at `CreatePipelineState`
   time at low priority, capped by Metal memory (eager creation of all
   ~14k pipelines hit 5.1 GB and jetsam before; do not go back to that).

### Build 183 result (log 2026-09-27 15:34)
Main menu much smoother (ExecuteCommandLists ~2 ms/frame, 45-48 FPS; parallel
builds working: `pso-parallel: built 20..69 pipelines on 4 threads`). Gameplay
start still froze: presents stopped right after the first large prebuild
batches, then the game tore itself down (workers faulted on memory another
worker freed — the usual teardown symptom). Two problems visible in the log:
* each prebuild batch CREATED 3 Wine threads: every one costs an 8 MB stack
  (floored), a TEB and FEX thread state — a storm of `init_thread_stack` lines
  and failing 8 MB reserves (`[va-scan] FAILED ... size=0x800000`).
* the 64-bit high-band fallback only searched 0x7200000000..0x73ffff0000,
  which is already occupied on device (every `[wow-window] #N ... NOT placed`),
  and a 1 MB FEX allocation still got STATUS_NO_MEMORY.
Also note: this run had 16,968 shader-cache misses because the cache key
includes the madeira_d3d12 build stamp — every new build re-converts every
shader once (first launch after an update is slow; second launch is not).

**Build 184**: a persistent pool of 3 prebuild threads (created once), and the
high-band fallback searches everything above the 32-bit windows up to the
user-space limit (still bounded by a caller's limit_high). If gameplay still
freezes, check whether presents stop while `pso-parallel` batches run
(pipeline compile time) or with no batches (then it is something else: look
at the game's worker threads / waits).

### Build 184 result (log 2026-09-27 17:02): crash DURING "Compiling shaders" (97 %)
No GPU fault, no pipeline stall. The crash is the same memory race seen in
every earlier run, now clearly independent of the GPU: the view history shows
a 1 MB + 64 KB block (`0x110000`) CREATED by the main thread 69 s earlier and
DELETED by a JobWorker 4 ms before the main thread (or another worker) faults
memcpy'ing 1 MB out of it (source = block + 0x40). Same size and shape in
four runs. That is one thread releasing a buffer another is still reading —
on Windows the game waits for its jobs first, so a wait here returned early
or a signal arrived too soon. Prime suspect: Madeira's in-process fast path
for events/waits ("fastsync", `MADEIRA_FASTSYNC`, auto-enabled after 20k ops/10 s,
see `build/ntdll-unix` sync code).

**Build 185**: per-game switch "Safe thread sync (no fastsync)" in the game's
Launch options (sets `MADEIRA_FASTSYNC=0` for that launch). Test GoT with it ON.
If the race disappears, the bug is in fastsync (look for a wake that is
delivered before the waiter's condition is really satisfied, or a
`WaitForMultipleObjects(waitAll)` / auto-reset event edge case). If it still
crashes, add a watch: `vmwatch` in madeira.cfg cannot help (addresses differ
per run); instead log the guest call stack of the thread that frees a
0x110000 view (NtFreeVirtualMemory caller RIP) and of the reader.

**About the Metal HUD suggestion "adopt MTL4Compiler"**: Metal 4
(iOS/macOS 26+) has `MTL4Compiler` (explicit compiler objects, async
compilation with QoS, `MTL4Archive`, flexible render pipeline states that
share compiled vertex/fragment code). Madeira's bridge (DXMT winemetal) is
written against the classic `MTLDevice newRenderPipelineState...` API and the
converter emits classic metallibs; moving to MTL4 means rewriting the
winemetal pipeline/command-buffer layer, a large job. The same benefits for
this problem (no main-thread compile stalls, reuse across launches) are
available with less risk via parallel builds (done) and `MTLBinaryArchive`
(item 1 above). The HUD's other hints ("high number of interleaved blit
encoders", "render passes with similar attachments") are performance notes,
not errors.

Note: `C:\madeira-cs\fault-shaders.txt` keeps hash 34c565ac8322ab2a, so every
launch logs that shader's bytecode once (harmless, ~8 log lines); delete the
file in the Wine prefix to stop it.

### Open issues, roughly in priority order
1. The freed-while-read memory race (build 184/185 notes above) — it kills
   the game even without GPU problems. Then pipeline persistence
   (MTLBinaryArchive). If GPU faults reappear, the fault machinery
   names the kernel.
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
