# Diagnostics in the iOS 18 PTDE build

Normal play is the default. Leave `MADEIRA_DIAG` unset, or put this in
`Documents/madeira.cfg`:

```ini
env.MADEIRA_DIAG = 0
```

To capture the full performance report, change it to `1` and restart Madeira
before launching Wine or the game:

```ini
env.MADEIRA_DIAG = 1
```

The switch enables Wine frame, file-system, VM, window-tree, input, audio and
event-history diagnostics, plus DXMT D3D9 submit, readback, pipeline-wait and
GetRenderTargetData timing. Normal play skips their hot-path timers, census
updates and trace collection. Error and device-fault messages still appear.

Individual opt-ins are also supported when a narrower log is needed:

```ini
env.MADEIRA_FRAME_STATS = 1
env.MADEIRA_FSSTATS = 1
env.MADEIRA_PERF_STATS = 1
env.DXMT_D9_SUBMIT_STATS = 1
env.DXMT_D9_READBACK_STATS = 1
env.DXMT_D9_PIPELINE_STATS = 1
env.DXMT_D9_TARGET_TIME = 1
```

These settings are read when the affected subsystem starts. Restart Madeira
after editing the file. The D3D9 trace knobs affect the `d3d9-emulated.dll`
frontend used by PTDE; the build workflow checks that this rebuilt DLL reaches
the IPA.
