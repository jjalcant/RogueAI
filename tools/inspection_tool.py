"""Read-only environment inspection helpers for RogueAI."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from memory_manager import MemoryManager
from tools.files_tool import resolve_special_path
from tools.system_tool import FOLDER_ALIASES, get_system_info


CONFIG_FILENAMES = {
    "requirements.txt",
    "pyproject.toml",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.toml",
    "go.mod",
    "setup.py",
    "setup.cfg",
    "Makefile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "Dockerfile",
    ".env",
}

LANGUAGE_MAP = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".json": "JSON",
    ".toml": "TOML",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".md": "Markdown",
    ".html": "HTML",
    ".css": "CSS",
    ".java": "Java",
    ".c": "C",
    ".cpp": "C++",
    ".cs": "C#",
    ".go": "Go",
    ".rs": "Rust",
    ".sh": "Shell",
    ".ps1": "PowerShell",
}

ORGANIZATION_CATEGORY_MAP = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic", ".tiff"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".xls", ".xlsx", ".ppt", ".pptx", ".md", ".csv", ".tsv"},
    "Audio": {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"},
    "Video": {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
    "Code": {".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".html", ".css", ".java", ".c", ".cpp", ".cs", ".go", ".rs", ".ipynb", ".toml", ".ini", ".cfg", ".conf", ".ps1", ".sh"},
    "Installers": {".exe", ".msi", ".pkg", ".dmg", ".iso", ".appx", ".msix"},
    "Shortcuts": {".lnk", ".url"},
}


def _structured_result(success, action, result="", error=None, **extra):
    payload = {
        "success": success,
        "action": action,
        "result": result,
        "error": error,
    }
    payload.update(extra)
    return payload


def _format_bytes(size_bytes: int):
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024
    return f"{size_bytes} B"


def _safe_aliases(workspace_root: Path, projects_path: Path):
    aliases = {name: str(path) for name, path in FOLDER_ALIASES.items()}
    aliases["workspace"] = str(workspace_root)
    aliases["project workspace"] = str(projects_path)
    aliases["projects"] = str(projects_path)
    return dict(sorted(aliases.items(), key=lambda item: item[0]))


def resolve_safe_folder(path_name: str, workspace_root: Path, projects_path: Path):
    raw = (path_name or "").strip()
    if not raw:
        return None

    lowered = raw.lower()
    aliases = _safe_aliases(workspace_root, projects_path)
    if lowered in aliases:
        return Path(aliases[lowered])

    special = resolve_special_path(lowered)
    if special is not None:
        return Path(special)

    candidate = Path(raw).expanduser()
    try:
        resolved = candidate.resolve()
    except Exception:
        return None

    safe_roots = [workspace_root.resolve(), projects_path.resolve(), Path.home().resolve()]
    if any(str(resolved).startswith(str(root)) for root in safe_roots):
        return resolved
    return None


def _resolve_safe_folder(path_name: str, workspace_root: Path, projects_path: Path):
    return resolve_safe_folder(path_name=path_name, workspace_root=workspace_root, projects_path=projects_path)


def _scan_directory(folder: Path, limit_largest: int = 5, limit_newest: int = 5, max_entries: int = 10000):
    total_files = 0
    total_directories = 0
    total_size_bytes = 0
    file_types = Counter()
    largest_files = []
    newest_files = []
    truncated = False
    visited = 0

    for path in sorted(folder.rglob("*"), key=lambda item: str(item).lower()):
        visited += 1
        if visited > max_entries:
            truncated = True
            break

        if path.is_dir():
            total_directories += 1
            continue

        if not path.is_file():
            continue

        total_files += 1
        try:
            stat = path.stat()
        except OSError:
            continue

        total_size_bytes += stat.st_size
        suffix = path.suffix.lower() or "<no_ext>"
        file_types[suffix] += 1
        largest_files.append(
            {
                "path": str(path),
                "name": path.name,
                "size_bytes": stat.st_size,
            }
        )
        newest_files.append(
            {
                "path": str(path),
                "name": path.name,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                "modified_ts": stat.st_mtime,
            }
        )

    largest_files = sorted(largest_files, key=lambda item: (-item["size_bytes"], item["name"].lower()))[:limit_largest]
    newest_files = sorted(newest_files, key=lambda item: (-item["modified_ts"], item["name"].lower()))[:limit_newest]
    for item in newest_files:
        item.pop("modified_ts", None)

    top_file_types = [
        {"extension": extension, "count": count}
        for extension, count in sorted(file_types.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]

    return {
        "path": str(folder),
        "total_files": total_files,
        "total_directories": total_directories,
        "total_size_bytes": total_size_bytes,
        "total_size_human": _format_bytes(total_size_bytes),
        "top_file_types": top_file_types,
        "largest_files": largest_files,
        "newest_files": newest_files,
        "truncated": truncated,
    }


def summarize_folder(path_name: str, workspace_root: Path, projects_path: Path):
    action = "summarize_folder"
    folder = _resolve_safe_folder(path_name, workspace_root, projects_path)
    if folder is None or not folder.exists():
        return _structured_result(False, action, error=f"Safe folder not found or unavailable: {path_name}")
    if not folder.is_dir():
        return _structured_result(False, action, error=f"Path is not a folder: {folder}")

    summary = _scan_directory(folder)
    lines = [
        f"Folder summary: {folder}",
        f"- Total files: {summary['total_files']}",
        f"- Total directories: {summary['total_directories']}",
        f"- Total size: {summary['total_size_human']}",
        "- Top file types:",
    ]
    for item in summary["top_file_types"] or [{"extension": "<none>", "count": 0}]:
        lines.append(f"  {item['extension']}: {item['count']}")
    lines.append("- Largest files:")
    for item in summary["largest_files"] or [{"name": "<none>", "size_bytes": 0}]:
        lines.append(f"  {item['name']}: {item['size_bytes']} bytes")
    lines.append("- Newest files:")
    for item in summary["newest_files"] or [{"name": "<none>", "modified": "n/a"}]:
        lines.append(f"  {item['name']}: {item['modified']}")
    if summary["truncated"]:
        lines.append("- Scan truncated: True")

    return _structured_result(True, action, result="\n".join(lines), summary=summary, path=str(folder))


def _categorize_organization_file(file_path: Path):
    suffix = file_path.suffix.lower()
    for category, suffixes in ORGANIZATION_CATEGORY_MAP.items():
        if suffix in suffixes:
            return category
    return "Other"


def _iter_preview_entries(folder: Path, recursive: bool, max_entries: int):
    if recursive:
        entries = sorted(folder.rglob("*"), key=lambda item: str(item).lower())
    else:
        entries = sorted(folder.iterdir(), key=lambda item: item.name.lower())
    return entries[:max_entries], len(entries) > max_entries


def preview_folder_organization(path_name: str, workspace_root: Path, projects_path: Path, recursive: bool = False, max_entries: int = 5000):
    action = "preview_folder_organization"
    folder = _resolve_safe_folder(path_name, workspace_root, projects_path)
    if folder is None or not folder.exists():
        return _structured_result(False, action, error=f"Safe folder not found or unavailable: {path_name}")
    if not folder.is_dir():
        return _structured_result(False, action, error=f"Path is not a folder: {folder}")

    entries, truncated = _iter_preview_entries(folder, recursive=recursive, max_entries=max_entries)
    category_counts = Counter()
    sample_filenames = {}
    reviewed_files = 0
    nested_files_analyzed = 0
    folder_entries_seen = 0

    for entry in entries:
        if entry.is_dir():
            folder_entries_seen += 1
            category_counts["Folders"] += 1
            sample_filenames.setdefault("Folders", [])
            if len(sample_filenames["Folders"]) < 3:
                sample_filenames["Folders"].append(entry.name)
            continue
        if not entry.is_file():
            continue

        reviewed_files += 1
        try:
            relative = entry.relative_to(folder)
        except ValueError:
            relative = Path(entry.name)
        if len(relative.parts) > 1:
            nested_files_analyzed += 1

        category = _categorize_organization_file(entry)
        category_counts[category] += 1
        sample_filenames.setdefault(category, [])
        if len(sample_filenames[category]) < 3:
            sample_filenames[category].append(entry.name)

    top_categories = [
        {"category": category, "count": count}
        for category, count in sorted(category_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    ]

    preview = {
        "path": str(folder),
        "recursive": recursive,
        "scope": "recursive" if recursive else "top_level_only",
        "included_subfolders": recursive,
        "total_files_analyzed": reviewed_files,
        "nested_files_analyzed": nested_files_analyzed,
        "folder_entries_seen": folder_entries_seen,
        "category_counts": dict(sorted(category_counts.items(), key=lambda item: item[0])),
        "top_categories": top_categories,
        "sample_filenames": {category: names for category, names in sorted(sample_filenames.items(), key=lambda item: item[0])},
        "truncated": truncated,
    }

    lines = [
        f"Organization preview: {folder}",
        f"- Preview scope: {'recursive' if recursive else 'top-level only'}",
        f"- Included subfolders: {recursive}",
        f"- Total files analyzed: {reviewed_files}",
        f"- Nested files analyzed: {nested_files_analyzed}",
        f"- Folder entries seen: {folder_entries_seen}",
        "- Top categories:",
    ]
    for item in preview["top_categories"] or [{"category": "<none>", "count": 0}]:
        lines.append(f"  {item['category']}: {item['count']}")
    lines.append("- Sample filenames:")
    for category, names in preview["sample_filenames"].items() or {"<none>": ["<none>"]}.items():
        lines.append(f"  {category}: {', '.join(names)}")
    if truncated:
        lines.append(f"- Preview truncated: True (max entries={max_entries})")
    lines.append("- Category counts:")
    for category, count in preview["category_counts"].items() or {"<none>": 0}.items():
        lines.append(f"  {category}: {count}")
    lines.append("- No files were modified.")

    return _structured_result(True, action, result="\n".join(lines), preview=preview, path=str(folder))


def inspect_project(project_name: str, workspace_root: Path, projects_path: Path):
    action = "inspect_project"
    requested = (project_name or "").strip()
    if not requested:
        return _structured_result(False, action, error="Project name is required.")

    candidates = []
    if requested.lower() == workspace_root.name.lower():
        candidates.append(workspace_root)
    candidates.append(projects_path / requested)
    candidates.append(projects_path / requested.lower())
    candidates.append(projects_path / requested.replace(" ", "_"))

    project_path = next((candidate for candidate in candidates if candidate.exists() and candidate.is_dir()), None)
    if project_path is None:
        return _structured_result(False, action, error=f"Project folder not found: {requested}")

    summary = _scan_directory(project_path, max_entries=12000)
    top_level_entries = sorted(item.name for item in project_path.iterdir())[:20]
    readme_files = sorted(item.name for item in project_path.iterdir() if item.is_file() and item.name.lower().startswith("readme"))
    config_files = sorted(item.name for item in project_path.iterdir() if item.is_file() and item.name in CONFIG_FILENAMES)

    language_counter = Counter()
    for type_entry in summary["top_file_types"]:
        language = LANGUAGE_MAP.get(type_entry["extension"])
        if language:
            language_counter[language] += type_entry["count"]

    inspection = {
        "project_name": project_path.name,
        "path": str(project_path),
        "total_files": summary["total_files"],
        "total_directories": summary["total_directories"],
        "top_level_entries": top_level_entries,
        "languages": [
            {"language": language, "count": count}
            for language, count in sorted(language_counter.items(), key=lambda item: (-item[1], item[0]))
        ],
        "readme_files": readme_files,
        "config_files": config_files,
        "largest_files": summary["largest_files"],
        "newest_files": summary["newest_files"],
        "truncated": summary["truncated"],
    }

    lines = [
        f"Project inspection: {inspection['project_name']}",
        f"- Path: {inspection['path']}",
        f"- Total files: {inspection['total_files']}",
        f"- Total directories: {inspection['total_directories']}",
        "- Top-level entries:",
    ]
    for name in top_level_entries or ["<none>"]:
        lines.append(f"  {name}")
    lines.append("- Languages detected:")
    for item in inspection["languages"] or [{"language": "<none>", "count": 0}]:
        lines.append(f"  {item['language']}: {item['count']}")
    lines.append(f"- README files: {', '.join(readme_files) if readme_files else '<none>'}")
    lines.append(f"- Config files: {', '.join(config_files) if config_files else '<none>'}")

    return _structured_result(True, action, result="\n".join(lines), inspection=inspection, path=str(project_path))


def build_workspace_summary(workspace_root: Path, projects_path: Path, memory_dir: Path):
    action = "build_workspace_summary"
    system_info = get_system_info()
    if not system_info.get("success"):
        return _structured_result(False, action, error=system_info.get("error") or "System info unavailable.")

    memory = MemoryManager(memory_dir)
    preferences = memory.get_preferences()
    aliases = preferences.get("safe_folder_aliases") or list(_safe_aliases(workspace_root, projects_path).keys())
    recent_entries = memory.get_recent_session(limit=5)
    projects = sorted(item.name for item in projects_path.iterdir()) if projects_path.exists() else []
    downloads_summary = summarize_folder("downloads", workspace_root, projects_path)
    workspace_folder_summary = summarize_folder("workspace", workspace_root, projects_path)

    if not downloads_summary.get("success"):
        return _structured_result(False, action, error=downloads_summary["error"])
    if not workspace_folder_summary.get("success"):
        return _structured_result(False, action, error=workspace_folder_summary["error"])

    report = {
        "system_info": system_info,
        "safe_folder_aliases": aliases,
        "recent_agent_memory": recent_entries,
        "known_projects": projects,
        "folder_summaries": {
            "downloads": downloads_summary["summary"],
            "workspace": workspace_folder_summary["summary"],
        },
    }

    lines = [
        "Workspace summary:",
        f"- Platform: {system_info.get('result', '')}",
        f"- Safe folder aliases available: {', '.join(aliases[:10])}",
        f"- Known projects: {', '.join(projects[:10]) if projects else '<none>'}",
        f"- Recent agent memory entries: {len(recent_entries)}",
        f"- Downloads files: {downloads_summary['summary']['total_files']} | size: {downloads_summary['summary']['total_size_human']}",
        f"- Workspace files: {workspace_folder_summary['summary']['total_files']} | size: {workspace_folder_summary['summary']['total_size_human']}",
    ]

    return _structured_result(True, action, result="\n".join(lines), report=report)
