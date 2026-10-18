"""Best-effort OS commit headroom check; no psutil dependency."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys

GIB = 1024 ** 3


def committed_headroom_bytes() -> int | None:
    if sys.platform == "win32":
        from ctypes import wintypes

        SIZE_T = ctypes.c_size_t

        class PERFORMANCE_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("CommitTotal", SIZE_T), ("CommitLimit", SIZE_T),
                ("CommitPeak", SIZE_T), ("PhysicalTotal", SIZE_T),
                ("PhysicalAvailable", SIZE_T), ("SystemCache", SIZE_T),
                ("KernelTotal", SIZE_T), ("KernelPaged", SIZE_T),
                ("KernelNonpaged", SIZE_T), ("PageSize", SIZE_T),
                ("HandleCount", wintypes.DWORD), ("ProcessCount", wintypes.DWORD),
                ("ThreadCount", wintypes.DWORD),
            ]

        info = PERFORMANCE_INFORMATION()
        info.cb = ctypes.sizeof(info)
        if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(info), info.cb):
            return None
        return max(0, (info.CommitLimit - info.CommitTotal) * info.PageSize)
    if sys.platform.startswith("linux"):
        try:
            entries = {}
            for line in Path("/proc/meminfo").read_text().splitlines():
                k, _, v = line.partition(":")
                entries[k] = int(v.strip().split()[0])
            return max(0, (entries["CommitLimit"] - entries["Committed_AS"]) * 1024)
        except (OSError, KeyError, ValueError, IndexError):
            return None
    return None


def enforce_headroom(minimum_gb: float, getter=committed_headroom_bytes) -> str:
    available = getter()
    if available is None:
        return "OS committed-memory metric unavailable; guard not enforced"
    if available < minimum_gb * GIB:
        raise MemoryError(
            f"Insufficient OS commit headroom: {available/GIB:.1f} GiB; "
            f"minimum {minimum_gb:.1f} GiB. Check the Windows 'Committed' metric/pagefile."
        )
    return f"Commit headroom: {available/GIB:.1f} GiB"
