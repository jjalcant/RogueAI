"""Verified local storage overview for RogueAI."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from result_contract import build_result

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psutil = None


DEFAULT_LARGE_FILE_THRESHOLD_BYTES = 100 * 1024 * 1024
DEFAULT_TOP_FOLDER_LIMIT = 5
DEFAULT_LARGE_FILE_LIMIT = 5
DEFAULT_MAX_SCANNED_FILES = 50000


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


def _is_relative_to(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _normalize_roots(scan_roots=None):
    candidates = list(scan_roots or [Path.home(), Path.cwd()])
    normalized = []
    for candidate in candidates:
        try:
            path = Path(candidate).expanduser().resolve()
        except Exception:
            continue
        if not path.exists() or not path.is_dir():
            continue
        if any(path == existing or _is_relative_to(path, existing) for existing in normalized):
            continue
        normalized = [existing for existing in normalized if not _is_relative_to(existing, path)]
        normalized.append(path)
    return normalized


def _get_drive_snapshot(drive_path):
    target = Path(drive_path)
    if psutil is not None:
        try:
            usage = psutil.disk_usage(str(target))
            return {
                "path": str(target),
                "total_bytes": int(usage.total),
                "used_bytes": int(usage.used),
                "free_bytes": int(usage.free),
                "usage_percent": float(usage.percent),
            }
        except Exception:
            pass

    usage = shutil.disk_usage(target)
    total_bytes = int(usage.total)
    free_bytes = int(usage.free)
    used_bytes = max(0, total_bytes - free_bytes)
    return {
        "path": str(target),
        "total_bytes": total_bytes,
        "used_bytes": used_bytes,
        "free_bytes": free_bytes,
        "usage_percent": _safe_round_percent(used_bytes, total_bytes),
    }


def _scan_storage_roots(scan_roots, *, large_file_threshold_bytes, top_folder_limit, large_file_limit, max_scanned_files):
    top_folder_sizes = {}
    large_files = []
    scanned_files = 0
    truncated = False
    permission_denied_count = 0

    for root in scan_roots:
        try:
            root_children = {
                child.name: child
                for child in root.iterdir()
                if child.is_dir()
            }
        except Exception:
            root_children = {}

        for current_root, dir_names, file_names in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current_root)
            filtered_dir_names = []
            for name in dir_names:
                candidate = current_path / name
                try:
                    if candidate.is_symlink():
                        continue
                except Exception:
                    continue
                filtered_dir_names.append(name)
            dir_names[:] = filtered_dir_names

            for file_name in file_names:
                if scanned_files >= max_scanned_files:
                    truncated = True
                    break

                file_path = current_path / file_name
                try:
                    if file_path.is_symlink():
                        continue
                    size_bytes = int(file_path.stat().st_size)
                except PermissionError:
                    permission_denied_count += 1
                    continue
                except OSError:
                    continue

                scanned_files += 1
                relative = file_path.relative_to(root)
                if relative.parts:
                    top_name = relative.parts[0]
                    top_dir = root_children.get(top_name)
                    if top_dir is not None:
                        top_folder_sizes[str(top_dir)] = top_folder_sizes.get(str(top_dir), 0) + size_bytes

                if size_bytes >= large_file_threshold_bytes:
                    large_files.append(
                        {
                            "path": str(file_path),
                            "name": file_path.name,
                            "size_bytes": size_bytes,
                            "size_human": _format_bytes(size_bytes),
                            "root": str(root),
                        }
                    )

            if truncated:
                break
        if truncated:
            break

    largest_folders = [
        {
            "path": path_text,
            "name": Path(path_text).name or path_text,
            "size_bytes": size_bytes,
            "size_human": _format_bytes(size_bytes),
        }
        for path_text, size_bytes in sorted(top_folder_sizes.items(), key=lambda item: item[1], reverse=True)[:top_folder_limit]
    ]

    largest_files = sorted(large_files, key=lambda item: item["size_bytes"], reverse=True)[:large_file_limit]
    return {
        "largest_folders": largest_folders,
        "large_files": largest_files,
        "large_file_threshold_bytes": int(large_file_threshold_bytes),
        "large_file_threshold_human": _format_bytes(large_file_threshold_bytes),
        "scanned_roots": [str(path) for path in scan_roots],
        "scanned_file_count": scanned_files,
        "scan_truncated": truncated,
        "permission_denied_count": permission_denied_count,
    }


def _build_storage_snapshot(scan_roots, *, drive_path, large_file_threshold_bytes, top_folder_limit, large_file_limit, max_scanned_files):
    drive = _get_drive_snapshot(drive_path)
    scan_data = _scan_storage_roots(
        scan_roots,
        large_file_threshold_bytes=large_file_threshold_bytes,
        top_folder_limit=top_folder_limit,
        large_file_limit=large_file_limit,
        max_scanned_files=max_scanned_files,
    )
    drive_usage = drive.get("usage_percent")
    return {
        "drive_path": drive.get("path"),
        "drive_total_bytes": drive.get("total_bytes"),
        "drive_total_human": _format_bytes(drive.get("total_bytes")),
        "drive_used_bytes": drive.get("used_bytes"),
        "drive_used_human": _format_bytes(drive.get("used_bytes")),
        "drive_free_bytes": drive.get("free_bytes"),
        "drive_free_human": _format_bytes(drive.get("free_bytes")),
        "drive_usage_percent": drive_usage,
        "high_disk_usage": bool(drive_usage is not None and drive_usage > 85),
        **scan_data,
    }


def storage_overview(
    *,
    scan_roots=None,
    drive_path=None,
    large_file_threshold_bytes=DEFAULT_LARGE_FILE_THRESHOLD_BYTES,
    top_folder_limit=DEFAULT_TOP_FOLDER_LIMIT,
    large_file_limit=DEFAULT_LARGE_FILE_LIMIT,
    max_scanned_files=DEFAULT_MAX_SCANNED_FILES,
):
    roots = _normalize_roots(scan_roots)
    if not roots:
        return build_result(
            False,
            "storage_overview",
            errors=["No readable storage roots are available."],
        )

    target_drive = Path(drive_path) if drive_path is not None else Path.home().anchor or Path.home()
    storage = _build_storage_snapshot(
        roots,
        drive_path=target_drive,
        large_file_threshold_bytes=large_file_threshold_bytes,
        top_folder_limit=top_folder_limit,
        large_file_limit=large_file_limit,
        max_scanned_files=max_scanned_files,
    )

    observed = []
    drive_usage = _format_percent(storage.get("drive_usage_percent"))
    if drive_usage:
        observed.append(f"Drive usage: {drive_usage}")
    free_space = storage.get("drive_free_human")
    if free_space:
        observed.append(f"Free space: {free_space}")
    total_space = storage.get("drive_total_human")
    if total_space:
        observed.append(f"Total disk size: {total_space}")

    details = []
    largest_folders = storage.get("largest_folders", [])
    if largest_folders:
        folder_text = ", ".join(
            f"{item['name']} ({item['size_human']})"
            for item in largest_folders
            if item.get("name") and item.get("size_human")
        )
        if folder_text:
            details.append(f"Largest folders: {folder_text}")

    large_files = storage.get("large_files", [])
    if large_files:
        file_text = ", ".join(
            f"{item['name']} ({item['size_human']})"
            for item in large_files[:3]
            if item.get("name") and item.get("size_human")
        )
        if file_text:
            details.append(
                f"Large files above {storage.get('large_file_threshold_human')}: {file_text}"
            )

    if storage.get("scan_truncated"):
        details.append(
            f"Scan reached the verification limit after {storage.get('scanned_file_count', 0):,} files"
        )

    warnings = []
    if storage.get("high_disk_usage"):
        warnings.append("Disk usage is high")

    recommendations = []
    folder_names = {str(item.get("name", "")).lower() for item in largest_folders}
    if "downloads" in folder_names:
        recommendations.append("Run Scan Downloads")
    if "desktop" in folder_names:
        recommendations.append("Run Scan Desktop")
    if large_files:
        recommendations.append("Review the largest files listed above")
    elif largest_folders:
        recommendations.append("Review the largest folders listed above")

    if not recommendations:
        recommendations.append("Run System Health")

    return build_result(
        True,
        "storage_overview",
        result=str(storage),
        observed=observed,
        warnings=warnings,
        inferences=details,
        suggestions=recommendations,
        storage=storage,
    )
