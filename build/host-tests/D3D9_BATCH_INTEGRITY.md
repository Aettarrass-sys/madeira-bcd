# Native D3D9 batch integrity and recording synchronization

## Follow-up: timing bounds and scheduling

The 0.1.40 playthrough had no batch-integrity rejection, and the user quit
manually. Investigation of impossible timing counters found a separate bug
in our `dxmt-d9-encode-detail.patch`: its six-stage loop also indexed the
five-entry flush totals and input arrays. `dxmt-d9-timing-bounds.patch` splits
those loops. The production accumulation is tested under ASan/UBSan for 1,000
windows, and the original implementation must fail the same test.

Two upstream BCD scheduling changes are ported together:

- `d25478311b`: on iOS, preserve pthread QoS below the Windows realtime band,
  with `env.MADEIRA_WIN_THREAD_PRIORITY=1` restoring the original wineserver
  priority mapping. The existing realtime policy remains active.
- `5b7448ad9f`: create the guest main pthread with a USER_INTERACTIVE QoS
  attribute instead of `sched_priority=20`, which can prevent later QoS changes
  on Darwin. The existing ECO path can therefore change its class.

Priority diagnostics are bounded and follow `MADEIRA_DIAG`. Main-thread QoS is
reported once with diagnostics enabled, or on an actual QoS API failure.
Host tests exercise the inserted policy for default/rollback and iOS/non-iOS
builds; they do not simulate Darwin's scheduling decisions. iPhone tests must
establish PTDE's benefit. This build retains native device locking, early-commit
configuration and optional diagnostic behavior. It does not change the default
sync engine: `inproc-sync=1` remains a separate A/B test against fastsync.

## Follow-up: 0.1.39 hang

The device log rejected batch 61994 with 84 operation references and 85
payloads (11 draws, 22 blits, 52 reference updates). It was invalid at
publication and encoding entry, with unchanged storage and fingerprint.
The guard called `MarkDeviceError`, stopping rendering while the app remained
responsive. This is containment, not a successful fix of the original writer.

Source inspection found generated shim setters and getters making direct
native calls outside the shim device lock. The previous native creation patch
XORed `D3DCREATE_MULTITHREADED`, disabling native protection when the guest
requested it. That assumption about shim lock coverage was incorrect.

Both native `CreateDevice` and `CreateDeviceEx` now OR that flag, keeping the
native recursive device lock enabled regardless of guest flags or diagnostic
settings. The existing behavior-flags map still restores the original guest
flags in `GetCreationParameters`. No new per-call logging is added.

`check-d9-native-lock.py` reproduces a payload/reference split using ordered
handshakes without undefined concurrent vector access, then exercises the
production recursive lock and batch helper with four producers and a concurrent
batch publisher. ASan/UBSan checks 160,000 operations across two rounds. Only
Windows API and logging/environment dependencies are stubbed. The workflow runs
this test after applying the full patch sequence. This verifies synchronization
under the modeled interleaving; actual PTDE stability and lock overhead still
need an iPhone run.

## Evidence and limits

The diagnostic-on PTDE run faults in `FlushDrawBatch` on the DXMT encoding
thread. The ARM64 instructions calculate `blits_base + index * 168`, then read
the kind byte at offset 104. The fault address gives index `0x41d0f313`.
The earlier diagnostic-off run faults in the same lambda while dereferencing
a null pointer. These locate the failures; they do not prove the original
writer of the corrupted data, an allocation failure, or a device-lock race.

## Changes

- Reserve space in both vectors before appending a payload and its stream
  reference. A failed allocation cannot publish a reference without a payload.
- Swap all four vectors into one detached batch before emitting its closure.
  The next recorder batch has separate storage, without copying payloads or
  allocating a separate batch object.
- Check tags, monotonic per-kind indices, payload counts, and captured storage
  identity before encoding. Copy each stream reference before invoking code
  that resolves or emits the operation; check again at consumption.
- Reject missing source/destination textures according to the blit kind.
  A detected inconsistency reports a device error rather than dereferencing
  an invalid record. This can stop rendering; it is not permission to discard
  arbitrary rendering work and continue as if the batch were correct.
- Optional fingerprints compare stream tags/indices and blit kinds/texture
  pointer values at publication, encoding entry, and encoding exit. They do
  not hash every byte of draw data or prove every resource pointer is live.

## Configuration

```ini
# Diagnostic reproduction:
env.MADEIRA_DIAG=1
env.MADEIRA_D3D9_NATIVE_CENSUS=1
env.MADEIRA_D3D9_BATCH_CHECK=1
```

`MADEIRA_D3D9_BATCH_CHECK` accepts the existing D3D9 diagnostic truth values
(`1`, `true`, `yes`, `on`). When omitted it follows `MADEIRA_DIAG`; an explicit
`0` disables fingerprints even with shared diagnostics enabled. Normal play
with `MADEIRA_DIAG=0` and no batch-check override performs no fingerprints.
Cheap bounds/ownership checks are correctness checks and remain enabled.

## Validation

The production helper is exercised with the production `Rc` implementation
under AddressSanitizer and UndefinedBehaviorSanitizer. Tests cover either
allocation failing, preservation of the caller's payload, resource pin
lifetimes, mixed FIFO streams, recording while an encoder owns an older batch,
and invalid tags, indices, pointers, or missing payloads. Existing configuration,
navigation, upload-pressure, scene-ordering, and BCn tests also pass locally.

The workflow applies the tracked patch after `dxmt-d9-native-batch-safety.patch`
and runs the new host test before the expensive build. Device confirmation is
still required: the repaired allocation-failure path is a concrete flaw, but
the observed PTDE memory corruption may have another source.
