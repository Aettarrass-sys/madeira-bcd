# Native D3D9 batch repair (next build after 0.1.38)

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
