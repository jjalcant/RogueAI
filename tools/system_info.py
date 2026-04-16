"""Verified local system information helpers for RogueAI."""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import subprocess
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


def _get_windows_memory_total():
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
        return int(status.ullTotalPhys)
    return None


def _get_total_memory_bytes():
    if psutil is not None:
        try:
            return int(psutil.virtual_memory().total)
        except Exception:
            pass

    if os.name == "nt":
        try:
            return _get_windows_memory_total()
        except Exception:
            return None

    page_size = getattr(os, "sysconf", lambda *_args: None)("SC_PAGE_SIZE")
    page_count = getattr(os, "sysconf", lambda *_args: None)("SC_PHYS_PAGES")
    if isinstance(page_size, int) and isinstance(page_count, int):
        return page_size * page_count
    return None


def _get_cpu_label():
    values = [
        platform.processor(),
        platform.uname().processor,
        os.environ.get("PROCESSOR_IDENTIFIER", ""),
        platform.machine(),
    ]
    for value in values:
        cleaned = str(value or "").strip()
        if cleaned:
            return cleaned
    return "Unknown CPU"


def _get_gpu_names():
    if os.name != "nt":
        return []

    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    except Exception:
        return []

    names = []
    for line in (completed.stdout or "").splitlines():
        cleaned = str(line).strip()
        if cleaned and cleaned not in names:
            names.append(cleaned)
    return names


def _get_disk_summary():
    root = Path.home().anchor or str(Path.home())
    usage = shutil.disk_usage(root)
    total = int(usage.total)
    used = total - int(usage.free)
    return {
        "path": root,
        "total_bytes": total,
        "free_bytes": int(usage.free),
        "used_bytes": used,
        "label": f"{root} | { _format_bytes(used) } used of { _format_bytes(total) }",
    }


def _build_system_info():
    operating_system = " ".join(
        part
        for part in [platform.system(), platform.release()]
        if str(part or "").strip()
    ).strip() or platform.platform()
    cpu = _get_cpu_label()
    total_memory = _get_total_memory_bytes()
    ram = _format_bytes(total_memory) if total_memory is not None else None
    gpu_names = _get_gpu_names()
    disk = _get_disk_summary()

    return {
        "Operating System": operating_system,
        "CPU": cpu,
        "RAM": ram,
        "GPU": gpu_names,
        "Disk summary": disk["label"],
        "platform": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "cwd": str(Path.cwd()),
        "disk": disk,
    }


def _build_payload(action_name):
    info = _build_system_info()
    observed = [
        f"Operating System: {info['Operating System']}",
        f"CPU: {info['CPU']}",
        f"Disk summary: {info['Disk summary']}",
    ]
    if info.get("RAM"):
        observed.append(f"RAM: {info['RAM']}")
    gpu_names = info.get("GPU") or []
    if gpu_names:
        observed.append(f"GPU: {gpu_names[0]}")

    return build_result(
        True,
        action_name,
        result=str(info),
        observed=observed,
        info=info,
    )


def system_info():
    return _build_payload("system_info")


def get_system_info():
    return _build_payload("get_system_info")
