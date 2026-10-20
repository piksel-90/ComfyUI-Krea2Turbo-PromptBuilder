"""OS commit guard and safe ComfyUI -> local-VLM memory handoff."""
from __future__ import annotations

import ctypes
import gc
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


def _windows_process_memory_bytes() -> tuple[int | None, int | None]:
    """Return current-process (working set, private bytes) without psutil."""
    if sys.platform != "win32":
        return None, None
    try:
        from ctypes import wintypes

        SIZE_T = ctypes.c_size_t

        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", SIZE_T),
                ("WorkingSetSize", SIZE_T),
                ("QuotaPeakPagedPoolUsage", SIZE_T),
                ("QuotaPagedPoolUsage", SIZE_T),
                ("QuotaPeakNonPagedPoolUsage", SIZE_T),
                ("QuotaNonPagedPoolUsage", SIZE_T),
                ("PagefileUsage", SIZE_T),
                ("PeakPagefileUsage", SIZE_T),
                ("PrivateUsage", SIZE_T),
            ]

        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(counters)
        handle = kernel32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return int(counters.WorkingSetSize), int(counters.PrivateUsage)
    except (AttributeError, OSError, TypeError, ValueError):
        pass
    return None, None


def _linux_rss_bytes() -> int | None:
    if not sys.platform.startswith("linux"):
        return None
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def _cuda_memory_bytes() -> tuple[int | None, int | None]:
    try:
        import torch
        if not torch.cuda.is_available():
            return None, None
        free, total = torch.cuda.mem_get_info()
        return int(free), int(total)
    except (ImportError, RuntimeError, OSError):
        return None, None


def memory_snapshot() -> dict[str, int | None]:
    rss, private = _windows_process_memory_bytes()
    if rss is None:
        rss = _linux_rss_bytes()
    free, total = _cuda_memory_bytes()
    return {
        "python_rss": rss,
        "python_private": private,
        "vram_free": free,
        "vram_total": total,
    }


def format_memory_snapshot(snapshot: dict[str, int | None]) -> str:
    def gib(value):
        return "n/a" if value is None else f"{value / GIB:.2f} GiB"

    used = None
    if snapshot.get("vram_total") is not None and snapshot.get("vram_free") is not None:
        used = snapshot["vram_total"] - snapshot["vram_free"]
    return (
        f"Python RSS {gib(snapshot.get('python_rss'))}; "
        f"private {gib(snapshot.get('python_private'))}; "
        f"VRAM used {gib(used)}; free {gib(snapshot.get('vram_free'))}"
    )


def perform_comfy_memory_handoff() -> tuple[dict[str, int | None], dict[str, int | None]]:
    """Unload ComfyUI-managed models before launching the disposable VLM.

    Important: never mutate current_loaded_models/loaded_models directly.
    The official unload path detaches dynamic models and releases their pinned/
    offloaded buffers correctly. Node execution cache is intentionally NOT reset
    here because this function runs inside an active prompt.
    """
    import comfy.model_management as mm

    before = memory_snapshot()
    mm.unload_all_models()
    gc.collect()
    mm.soft_empty_cache()
    gc.collect()
    after = memory_snapshot()
    return before, after


def schedule_post_prompt_free() -> bool:
    """Request ComfyUI's full model + execution-cache cleanup after this prompt.

    main.py consumes this queue flag only after PromptExecutor.execute() returns,
    so e.reset() never runs while the current node graph is active.
    """
    try:
        from server import PromptServer
        instance = getattr(PromptServer, "instance", None)
        queue = getattr(instance, "prompt_queue", None)
        if queue is None or not hasattr(queue, "set_flag"):
            return False
        queue.set_flag("free_memory", True)
        return True
    except (ImportError, AttributeError, RuntimeError):
        return False
