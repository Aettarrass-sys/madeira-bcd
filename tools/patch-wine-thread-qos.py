#!/usr/bin/env python3
"""Preserve iOS pthread QoS below the Windows realtime priority band.

Adapted from bahacan16/madeira-bcd d25478311b. The companion bridge change
from 5b7448ad9f removes the fixed-priority attribute on the guest main thread.
Realtime policies remain intact; MADEIRA_WIN_THREAD_PRIORITY=1 restores the
original wineserver mapping. Logging follows MADEIRA_DIAG and is bounded.
"""
from pathlib import Path

PATH = Path("wine/server/thread.c")
MARKER = "madeira-bcd: thread priority keeps the pthread QoS"
OLD = """    int effective_priority = get_effective_thread_priority( thread );

    if (!process_port) return;
"""
NEW = """    int effective_priority = get_effective_thread_priority( thread );

#ifdef WINE_IOS
    /* madeira-bcd: thread priority keeps the pthread QoS.
     * Keep the guest's requested scheduling class below the realtime band.
     * Fixed Mach tiers can otherwise override pthread QoS on iOS. */
    if (effective_priority < LOW_REALTIME_PRIORITY)
    {
        static int keep = -1, diag = -1, logged;
        if (keep < 0)
        {
            const char *e = getenv( "MADEIRA_WIN_THREAD_PRIORITY" );
            keep = !(e && e[0] == '1');
        }
        if (diag < 0)
        {
            const char *e = getenv( "MADEIRA_DIAG" );
            diag = e && e[0] == '1';
        }
        if (diag && logged < 24)
        {
            logged++;
            fprintf( stderr, "[thread-prio] madeira-bcd tid=%04x base=%d effective=%d -> %s\\n",
                     thread->id, thread->base_priority, effective_priority,
                     keep ? "kept at pthread QoS" : "original Mach policies" );
        }
        if (keep) return;
    }
#endif

    if (!process_port) return;
"""


def apply(path=PATH):
    source = path.read_text()
    if MARKER in source:
        if NEW not in source:
            raise RuntimeError(f"partial or incompatible QoS patch in {path}")
        return
    if source.count(OLD) != 1:
        raise RuntimeError(f"QoS anchor must occur once in {path}")
    path.write_text(source.replace(OLD, NEW))


if __name__ == "__main__":
    apply()
    print("PASS: wineserver thread QoS policy patched")
