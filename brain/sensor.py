"""Safe system-state sensors for autonomous RogueAI workflows."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from tools.system_tool import resolve_folder_alias


class RogueSensor:
    """Collect small, deterministic filesystem snapshots for the auto loop."""

    def __init__(
        self,
        downloads_path: Path | str | None = None,
        recent_window_seconds: int = 3600,
        max_recent_files: int = 10,
        recursive: bool = False,
        clock=None,
    ):
        default_downloads = resolve_folder_alias("downloads") or (Path.home() / "Downloads")
        self.downloads_path = Path(downloads_path) if downloads_path is not None else Path(default_downloads)
        self.recent_window_seconds = max(0, int(recent_window_seconds))
        self.max_recent_files = max(0, int(max_recent_files))
        self.recursive = bool(recursive)
        self.clock = clock or datetime.now

    def collect_state(self) -> dict:
        downloads = self.inspect_downloads()
        return {
            "collected_at": self._now().isoformat(timespec="seconds"),
            "downloads": downloads,
        }

    def collect(self) -> dict:
        return self.collect_state()

    def inspect_downloads(self) -> dict:
        folder = self.downloads_path.expanduser()
        now = self._now()
        recent_cutoff = now.timestamp() - self.recent_window_seconds
        entries = self._iter_file_entries(folder)

        total_size_bytes = 0
        recent_files = []

        for entry in entries:
            try:
                stat = entry.stat()
            except OSError:
                continue

            size_bytes = int(stat.st_size)
            modified_at = datetime.fromtimestamp(stat.st_mtime)
            total_size_bytes += size_bytes

            if stat.st_mtime >= recent_cutoff and self.max_recent_files:
                recent_files.append(
                    {
                        "name": entry.name,
                        "path": str(entry),
                        "modified": modified_at.isoformat(timespec="seconds"),
                        "size_bytes": size_bytes,
                    }
                )

        recent_files.sort(key=lambda item: item["modified"], reverse=True)
        recent_files = recent_files[: self.max_recent_files]

        return {
            "path": str(folder),
            "exists": folder.exists(),
            "is_dir": folder.is_dir(),
            "recursive": self.recursive,
            "file_count": len(entries),
            "total_size_bytes": total_size_bytes,
            "total_size_human": self._format_size(total_size_bytes),
            "recent_files": recent_files,
            "recent_file_count": len(recent_files),
        }

    def _iter_file_entries(self, folder: Path) -> list[Path]:
        if not folder.exists() or not folder.is_dir():
            return []

        iterator = folder.rglob("*") if self.recursive else folder.iterdir()
        entries = []
        for entry in iterator:
            if entry.is_file():
                entries.append(entry)
        return entries

    def _now(self) -> datetime:
        value = self.clock()
        if isinstance(value, datetime):
            return value
        raise TypeError("clock must return a datetime instance.")

    def _format_size(self, size_bytes: int) -> str:
        size = float(size_bytes)
        units = ["B", "KB", "MB", "GB", "TB"]
        unit_index = 0
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024.0
            unit_index += 1
        if unit_index == 0:
            return f"{int(size)} {units[unit_index]}"
        return f"{size:.1f} {units[unit_index]}"
