"""Verified local system health diagnostics for RogueAI."""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import time
from pathlib import Path

from result_contract import build_result

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None


def _format_bytes(value):
    size = float(max(0, int(value or 0)))
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if size < 1024 or unit == "PB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{int(value or 0)} B"


def _format_percent(value):
    if value is None:
        return None
    return f"{int(round(float(value)))}%"


def _safe_round_percent(numerator, denominator):
    if denominator in (None, 0):
        return None
    try:
        return round((float(numerator) / float(denominator)) * 100, 1)
    except Exception:
        return None


def _get_windows_memory_status():
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
        return {
            "total_bytes": int(status.ullTotalPhys),
            "available_bytes": int(status.ullAvailPhys),
            "used_bytes": int(status.ullTotalPhys - status.ullAvailPhys),
            "usage_percent": float(status.dwMemoryLoad),
        }
    return {}


def _get_memory_snapshot():
    if psutil is not None:
        try:
            memory = psutil.virtual_memory()
            return {
                "total_bytes": int(memory.total),
                "available_bytes": int(memory.available),
                "used_bytes": int(memory.used),
                "usage_percent": float(memory.percent),
            }
        except Exception:
            pass

    if os.name == "nt":
        return _get_windows_memory_status()

    try:
        page_size = int(os.sysconf("SC_PAGE_SIZE"))
        page_count = int(os.sysconf("SC_PHYS_PAGES"))
        available_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
    except Exception:
        return {}

    total_bytes = page_size * page_count
    available_bytes = page_size * available_pages
    used_bytes = max(0, total_bytes - available_bytes)
    return {
        "total_bytes": total_bytes,
        "available_bytes": available_bytes,
        "used_bytes": used_bytes,
        "usage_percent": _safe_round_percent(used_bytes, total_bytes),
    }


def _get_windows_cpu_percent(sample_seconds=0.2):
    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", ctypes.c_ulong),
            ("dwHighDateTime", ctypes.c_ulong),
        ]

    def _read_times():
        idle = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(  # type: ignore[attr-defined]
            ctypes.byref(idle),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return None

        def _to_int(value):
            return (value.dwHighDateTime << 32) | value.dwLowDateTime

        return _to_int(idle), _to_int(kernel), _to_int(user)

    start = _read_times()
    if start is None:
        return None
    time.sleep(max(0.05, float(sample_seconds)))
    end = _read_times()
    if end is None:
        return None

    idle_delta = end[0] - start[0]
    kernel_delta = end[1] - start[1]
    user_delta = end[2] - start[2]
    total_delta = kernel_delta + user_delta
    if total_delta <= 0:
        return None
    active_delta = max(0, total_delta - idle_delta)
    return round((active_delta / total_delta) * 100, 1)


def _get_cpu_usage_percent():
    if psutil is not None:
        try:
            return float(psutil.cpu_percent(interval=0.2))
        except Exception:
            pass

    if os.name == "nt":
        return _get_windows_cpu_percent()

    try:
        load_avg = os.getloadavg()[0]
        cpu_count = os.cpu_count() or 1
        return round(min(100.0, max(0.0, (load_avg / cpu_count) * 100)), 1)
    except Exception:
        return None


def _get_disk_snapshot():
    root = Path.home().anchor or str(Path.home())
    usage = shutil.disk_usage(root)
    total_bytes = int(usage.total)
    free_bytes = int(usage.free)
    used_bytes = max(0, total_bytes - free_bytes)
    return {
        "path": root,
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "free_bytes": free_bytes,
        "usage_percent": _safe_round_percent(used_bytes, total_bytes),
    }


def _build_health_snapshot():
    cpu_usage = _get_cpu_usage_percent()
    memory = _get_memory_snapshot()
    disk = _get_disk_snapshot()

    memory_usage = memory.get("usage_percent")
    disk_usage = disk.get("usage_percent")
    high_disk_usage = disk_usage is not None and disk_usage > 85
    high_memory_usage = memory_usage is not None and memory_usage > 85

    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "cpu_usage_percent": cpu_usage,
        "memory_usage_percent": memory_usage,
        "memory_total_bytes": memory.get("total_bytes"),
        "memory_used_bytes": memory.get("used_bytes"),
        "memory_available_bytes": memory.get("available_bytes"),
        "disk_path": disk.get("path"),
        "disk_usage_percent": disk_usage,
        "disk_total_bytes": disk.get("total_bytes"),
        "disk_used_bytes": disk.get("used_bytes"),
        "disk_free_bytes": disk.get("free_bytes"),
        "high_disk_usage": bool(high_disk_usage),
        "high_memory_usage": bool(high_memory_usage),
    }


def system_health():
    health = _build_health_snapshot()

    observed = []
    cpu_usage = _format_percent(health.get("cpu_usage_percent"))
    memory_usage = _format_percent(health.get("memory_usage_percent"))
    disk_usage = _format_percent(health.get("disk_usage_percent"))

    if cpu_usage:
        observed.append(f"CPU usage: {cpu_usage}")
    if memory_usage:
        observed.append(f"Memory usage: {memory_usage}")
    if disk_usage:
        observed.append(f"Disk usage: {disk_usage}")

    warnings = []
    details = []

    if health.get("high_disk_usage"):
        warnings.append("Disk usage is high")
        details.append("Storage pressure detected on the system drive")

    if health.get("high_memory_usage"):
        warnings.append("Memory usage is high")
        details.append("Memory pressure detected")

    if not warnings and observed:
        details.extend(
            [
                "No critical performance issues detected",
                "System operating within normal ranges",
            ]
        )

    suggestions = ["Run System Info"]
    if health.get("disk_usage_percent") is not None:
        suggestions.append("Run Scan Downloads")

    return build_result(
        True,
        "system_health",
        result=str(health),
        observed=observed,
        warnings=warnings,
        inferences=details,
        suggestions=suggestions,
        health=health,
    )
