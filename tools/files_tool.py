from datetime import datetime
from pathlib import Path
import hashlib
import os
import shutil
import uuid

from memory.move_history import make_history_entries, record_moves
from result_contract import build_result, make_artifact


BASE = Path(__file__).resolve().parent.parent
LOGS = BASE / "logs"
LOG_FILE = LOGS / "brain.log"

DOWNLOAD_CATEGORY_TARGETS = {
    "Music": lambda downloads: downloads / "Organized" / "Music",
    "Pictures": lambda downloads: downloads / "Organized" / "Pictures",
    "Videos": lambda downloads: downloads / "Organized" / "Videos",
    "Documents": lambda downloads: downloads / "Organized" / "Documents",
    "Archives": lambda downloads: downloads / "Organized" / "Archives",
    "Code": lambda downloads: downloads / "Organized" / "Code",
}

HOME_WORKSPACE_TARGETS = {
    "Models": lambda home: home / "OrganizedWorkspace" / "Models",
    "Configs": lambda home: home / "OrganizedWorkspace" / "Configs",
    "Temp": lambda home: home / "OrganizedWorkspace" / "Temp",
    "Notes": lambda home: home / "OrganizedWorkspace" / "Notes",
    "LooseFiles": lambda home: home / "OrganizedWorkspace" / "LooseFiles",
}

DOWNLOAD_FILE_CATEGORY_MAP = {
    "Music": {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg"},
    "Pictures": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"},
    "Videos": {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".xls", ".xlsx", ".ppt", ".pptx", ".md"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
    "Code": {".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml", ".yml", ".html", ".css", ".java", ".c", ".cpp", ".cs", ".go", ".rs", ".ipynb"},
}

HOME_WORKSPACE_FILE_CATEGORY_MAP = {
    "Models": {".pt", ".pth", ".onnx", ".ckpt", ".bin", ".safetensors"},
    "Configs": {".ini", ".cfg", ".conf", ".toml"},
    "Temp": {".tmp", ".bak", ".old"},
    "Notes": {".txt", ".log", ".md"},
}

HOME_WORKSPACE_PROTECTED_DIRS = {
    "AppData",
    "OneDrive",
    "Desktop",
    "Documents",
    "Downloads",
    "Pictures",
    "Music",
    "Videos",
    ".anaconda",
    ".conda",
    ".android",
    ".ollama",
    ".vscode",
    "VirtualBox",
}

HOME_WORKSPACE_PROTECTED_FILES = {
    ".gitconfig": "Configs",
    ".python_history": "Configs",
}

MAX_DUPLICATE_SCAN_FILES = 2000


def _log_file_action(action, success, details):
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{now}] files_tool action={action} success={success} details={details}\n")
    except Exception:
        pass


def _structured_result(success, action, result="", error=None, observed=None, artifacts=None, warnings=None, errors=None, **extra):
    payload = build_result(
        success=success,
        action=action,
        result=result,
        error=error,
        observed=observed,
        artifacts=artifacts,
        warnings=warnings,
        errors=errors,
        **extra,
    )
    payload.update(extra)
    return payload


def resolve_special_path(name):
    name = name.lower().strip()
    home = Path.home()

    desktop_paths = [
        home / "Desktop",
        home / "OneDrive" / "Desktop",
    ]

    desktop = next((path for path in desktop_paths if path.exists()), home / "Desktop")

    mapping = {
        "downloads": home / "Downloads",
        "download": home / "Downloads",
        "descargas": home / "Downloads",
        "my downloads": home / "Downloads",
        "documents": home / "Documents",
        "documentos": home / "Documents",
        "my documents": home / "Documents",
        "desktop": desktop,
        "my desktop": desktop,
        "escritorio": desktop,
        "pictures": home / "Pictures",
        "imagenes": home / "Pictures",
        "music": home / "Music",
        "musica": home / "Music",
        "videos": home / "Videos",
        "home": home,
        "home workspace": home,
        "my home workspace": home,
        "workspace": BASE,
        "my workspace": BASE,
        "this folder": BASE,
        "current folder": BASE,
        "projects": BASE / "projects",
        "project folder": BASE / "projects",
        "projects folder": BASE / "projects",
    }

    return mapping.get(name)


def normalize_path(path_str):
    if not path_str:
        return None

    special = resolve_special_path(path_str)
    if special:
        return special

    return Path(path_str).expanduser()


def open_path(path_str):
    try:
        path = normalize_path(path_str)
        if path is None or not path.exists():
            return f"No encontré la ruta: {path_str}"

        os.startfile(str(path))
        _log_file_action("open_path", True, str(path))
        return f"Listo. Ya abrí:\n{path}"
    except Exception as e:
        _log_file_action("open_path", False, f"{path_str}: {e}")
        return f"No pude abrir la ruta: {e}"


def list_path(path_str, limit=100):
    try:
        path = normalize_path(path_str)
        if path is None or not path.exists():
            return f"No encontré la ruta: {path_str}"

        if path.is_file():
            return f"La ruta es un archivo, no una carpeta:\n{path}"

        items = sorted(path.iterdir(), key=lambda x: x.name.lower())

        if not items:
            return f"La carpeta está vacía:\n{path}"

        lines = [f"Contenido de:\n{path}\n"]
        for item in items[:limit]:
            kind = "[DIR]" if item.is_dir() else "[FILE]"
            lines.append(f"{kind} {item.name}")

        if len(items) > limit:
            lines.append(f"\nMostrando {limit} de {len(items)} elementos.")

        return "\n".join(lines)
    except Exception as e:
        return f"No pude listar la ruta: {e}"


def create_folder(path_str):
    try:
        path = normalize_path(path_str)
        if path is None:
            return "Ruta inválida."

        path.mkdir(parents=True, exist_ok=True)
        _log_file_action("create_folder", True, str(path))
        return f"Listo. Carpeta creada o ya existente:\n{path}"
    except Exception as e:
        _log_file_action("create_folder", False, f"{path_str}: {e}")
        return f"No pude crear la carpeta: {e}"


def copy_path(src_str, dst_str):
    try:
        src = normalize_path(src_str)
        dst = normalize_path(dst_str)

        if src is None or not src.exists():
            return f"No encontré el origen:\n{src_str}"
        if dst is None:
            return f"Destino inválido:\n{dst_str}"

        if src.is_file():
            target = dst / src.name if dst.exists() and dst.is_dir() else dst
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            _log_file_action("copy_path", True, f"{src} -> {target}")
            return f"Listo. Copié el archivo a:\n{target}"

        if src.is_dir():
            if dst.exists() and dst.is_file():
                return "No puedo copiar una carpeta dentro de un archivo."
            target = dst / src.name if dst.exists() and dst.is_dir() else dst
            shutil.copytree(src, target, dirs_exist_ok=True)
            _log_file_action("copy_path", True, f"{src} -> {target}")
            return f"Listo. Copié la carpeta a:\n{target}"

        return "No pude copiar esa ruta."
    except Exception as e:
        _log_file_action("copy_path", False, f"{src_str} -> {dst_str}: {e}")
        return f"No pude copiar la ruta: {e}"


def move_path(src_str, dst_str):
    try:
        src = normalize_path(src_str)
        dst = normalize_path(dst_str)

        if src is None or not src.exists():
            return f"No encontré el origen:\n{src_str}"
        if dst is None:
            return f"Destino inválido:\n{dst_str}"

        dst.parent.mkdir(parents=True, exist_ok=True)
        result = shutil.move(str(src), str(dst))
        _log_file_action("move_path", True, f"{src} -> {dst}")
        return f"Listo. Moví la ruta a:\n{result}"
    except Exception as e:
        _log_file_action("move_path", False, f"{src_str} -> {dst_str}: {e}")
        return f"No pude mover la ruta: {e}"


def delete_path(path_str):
    try:
        path = normalize_path(path_str)
        if path is None or not path.exists():
            return f"No encontré la ruta: {path_str}"

        if path.is_file():
            path.unlink()
            _log_file_action("delete_path", True, str(path))
            return f"Listo. Eliminé el archivo:\n{path}"

        if path.is_dir():
            shutil.rmtree(path)
            _log_file_action("delete_path", True, str(path))
            return f"Listo. Eliminé la carpeta:\n{path}"

        return "No pude eliminar esa ruta."
    except Exception as e:
        _log_file_action("delete_path", False, f"{path_str}: {e}")
        return f"No pude eliminar la ruta: {e}"


def open_path(path_str):
    action = "open_path"
    try:
        path = normalize_path(path_str)
        if path is None or not path.exists():
            return _structured_result(False, action, error=f"No encontré la ruta: {path_str}")

        os.startfile(str(path))
        _log_file_action(action, True, str(path))
        return _structured_result(
            True,
            action,
            result=f"Open request sent for path: {path}",
            observed=[
                f"Verified path exists: {path}",
                f"An OS open request was issued without an immediate exception: {path}",
            ],
            artifacts=[make_artifact("path", path=str(path), description="Requested path", exists=True, verified=True)],
            warnings=["I cannot confirm that the target window is visible."],
        )
    except Exception as e:
        _log_file_action(action, False, f"{path_str}: {e}")
        return _structured_result(False, action, error=f"No pude abrir la ruta: {e}")


def list_path(path_str, limit=100):
    action = "list_path"
    try:
        path = normalize_path(path_str)
        if path is None or not path.exists():
            return _structured_result(False, action, error=f"No encontré la ruta: {path_str}")

        if path.is_file():
            return _structured_result(False, action, error=f"La ruta es un archivo, no una carpeta:\n{path}")

        items = sorted(path.iterdir(), key=lambda x: x.name.lower())
        artifact = make_artifact("folder", path=str(path), description="Listed folder", exists=True, verified=True)
        if not items:
            return _structured_result(
                True,
                action,
                result=f"La carpeta está vacía:\n{path}",
                observed=[f"Verified folder exists and contains 0 visible entries: {path}"],
                artifacts=[artifact],
                entries=[],
            )

        lines = [f"Contenido de:\n{path}\n"]
        for item in items[:limit]:
            kind = "[DIR]" if item.is_dir() else "[FILE]"
            lines.append(f"{kind} {item.name}")

        if len(items) > limit:
            lines.append(f"\nMostrando {limit} de {len(items)} elementos.")

        return _structured_result(
            True,
            action,
            result="\n".join(lines),
            observed=[f"Verified folder exists: {path}", f"Listed {min(len(items), limit)} of {len(items)} entries."],
            artifacts=[artifact],
            entries=[str(item) for item in items[:limit]],
        )
    except Exception as e:
        return _structured_result(False, action, error=f"No pude listar la ruta: {e}")


def create_folder(path_str):
    action = "create_folder"
    try:
        path = normalize_path(path_str)
        if path is None:
            return _structured_result(False, action, error="Ruta inválida.")

        path.mkdir(parents=True, exist_ok=True)
        exists_after = path.exists() and path.is_dir()
        _log_file_action(action, exists_after, str(path))
        return _structured_result(
            exists_after,
            action,
            result=f"Carpeta creada o ya existente:\n{path}" if exists_after else "",
            error=None if exists_after else f"No verified folder was created: {path}",
            observed=[f"Verified folder exists after create request: {path}"] if exists_after else ["No verified folder was created."],
            artifacts=[make_artifact("folder", path=str(path), description="Requested folder", exists=exists_after, verified=True)],
        )
    except Exception as e:
        _log_file_action(action, False, f"{path_str}: {e}")
        return _structured_result(False, action, error=f"No pude crear la carpeta: {e}")


def copy_path(src_str, dst_str):
    action = "copy_path"
    try:
        src = normalize_path(src_str)
        dst = normalize_path(dst_str)

        if src is None or not src.exists():
            return _structured_result(False, action, error=f"No encontré el origen:\n{src_str}")
        if dst is None:
            return _structured_result(False, action, error=f"Destino inválido:\n{dst_str}")

        if src.is_file():
            target = dst / src.name if dst.exists() and dst.is_dir() else dst
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            copied = target.exists() and target.is_file()
            _log_file_action(action, copied, f"{src} -> {target}")
            return _structured_result(
                copied,
                action,
                result=f"Copié el archivo a:\n{target}" if copied else "",
                error=None if copied else f"No verified copy was created: {target}",
                observed=[
                    f"Verified source file exists: {src}",
                    f"Verified copied file exists: {target}" if copied else "No verified copy was created.",
                ],
                artifacts=[
                    make_artifact("source_file", path=str(src), description="Copy source", exists=True, verified=True),
                    make_artifact("copied_file", path=str(target), description="Copied file", exists=copied, verified=True),
                ],
            )

        if src.is_dir():
            if dst.exists() and dst.is_file():
                return _structured_result(False, action, error="No puedo copiar una carpeta dentro de un archivo.")
            target = dst / src.name if dst.exists() and dst.is_dir() else dst
            shutil.copytree(src, target, dirs_exist_ok=True)
            copied = target.exists() and target.is_dir()
            _log_file_action(action, copied, f"{src} -> {target}")
            return _structured_result(
                copied,
                action,
                result=f"Copié la carpeta a:\n{target}" if copied else "",
                error=None if copied else f"No verified folder copy was created: {target}",
                observed=[
                    f"Verified source folder exists: {src}",
                    f"Verified copied folder exists: {target}" if copied else "No verified folder copy was created.",
                ],
                artifacts=[
                    make_artifact("source_folder", path=str(src), description="Copy source", exists=True, verified=True),
                    make_artifact("copied_folder", path=str(target), description="Copied folder", exists=copied, verified=True),
                ],
            )

        return _structured_result(False, action, error="No pude copiar esa ruta.")
    except Exception as e:
        _log_file_action(action, False, f"{src_str} -> {dst_str}: {e}")
        return _structured_result(False, action, error=f"No pude copiar la ruta: {e}")


def move_path(src_str, dst_str):
    action = "move_path"
    try:
        src = normalize_path(src_str)
        dst = normalize_path(dst_str)

        if src is None or not src.exists():
            return _structured_result(False, action, error=f"No encontré el origen:\n{src_str}")
        if dst is None:
            return _structured_result(False, action, error=f"Destino inválido:\n{dst_str}")

        dst.parent.mkdir(parents=True, exist_ok=True)
        source_before = src.exists()
        result_path = Path(shutil.move(str(src), str(dst)))
        moved = result_path.exists() and not src.exists()
        _log_file_action(action, moved, f"{src} -> {dst}")
        return _structured_result(
            moved,
            action,
            result=f"Moví la ruta a:\n{result_path}" if moved else "",
            error=None if moved else f"Move result could not be verified: {result_path}",
            observed=[
                f"Verified source existed before move: {src}" if source_before else f"Source could not be verified before move: {src}",
                f"Verified target exists after move: {result_path}" if result_path.exists() else "No verified moved target exists.",
                f"Verified source no longer exists after move: {src}" if not src.exists() else f"Source still exists after move request: {src}",
            ],
            artifacts=[
                make_artifact("moved_target", path=str(result_path), description="Moved target", exists=result_path.exists(), verified=True),
                make_artifact("source_after_move", path=str(src), description="Original source after move", exists=src.exists(), verified=True),
            ],
        )
    except Exception as e:
        _log_file_action(action, False, f"{src_str} -> {dst_str}: {e}")
        return _structured_result(False, action, error=f"No pude mover la ruta: {e}")


def delete_path(path_str):
    action = "delete_path"
    try:
        path = normalize_path(path_str)
        if path is None or not path.exists():
            return _structured_result(False, action, error=f"No encontré la ruta: {path_str}")

        if path.is_file():
            path.unlink()
            deleted = not path.exists()
            _log_file_action(action, deleted, str(path))
            return _structured_result(
                deleted,
                action,
                result=f"Eliminé el archivo:\n{path}" if deleted else "",
                error=None if deleted else f"File still exists after delete request: {path}",
                observed=[f"Verified file no longer exists: {path}" if deleted else f"File still exists after delete request: {path}"],
                artifacts=[make_artifact("deleted_file", path=str(path), description="Deleted file path", exists=path.exists(), verified=True)],
            )

        if path.is_dir():
            shutil.rmtree(path)
            deleted = not path.exists()
            _log_file_action(action, deleted, str(path))
            return _structured_result(
                deleted,
                action,
                result=f"Eliminé la carpeta:\n{path}" if deleted else "",
                error=None if deleted else f"Folder still exists after delete request: {path}",
                observed=[f"Verified folder no longer exists: {path}" if deleted else f"Folder still exists after delete request: {path}"],
                artifacts=[make_artifact("deleted_folder", path=str(path), description="Deleted folder path", exists=path.exists(), verified=True)],
            )

        return _structured_result(False, action, error="No pude eliminar esa ruta.")
    except Exception as e:
        _log_file_action(action, False, f"{path_str}: {e}")
        return _structured_result(False, action, error=f"No pude eliminar la ruta: {e}")


def _file_hash(path, chunk_size=1024 * 1024):
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _collect_bounded_files(folder, max_files):
    files = []
    truncated = False
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        files.append(path)
        if len(files) >= max_files:
            truncated = True
            break
    return files, truncated


def scan_duplicates(path_str):
    try:
        folder = normalize_path(path_str)
        if folder is None or not folder.exists():
            return {"ok": False, "message": f"No encontré la carpeta: {path_str}"}

        if folder.is_file():
            return {"ok": False, "message": f"La ruta es un archivo, no una carpeta:\n{folder}"}

        files = [path for path in folder.rglob("*") if path.is_file()]

        if not files:
            return {"ok": True, "message": f"No encontré archivos en:\n{folder}", "duplicates": []}

        size_map = {}
        for file_path in files:
            try:
                size = file_path.stat().st_size
                size_map.setdefault(size, []).append(file_path)
            except Exception:
                continue

        candidate_groups = [group for group in size_map.values() if len(group) > 1]

        hash_map = {}
        for group in candidate_groups:
            for file_path in group:
                try:
                    file_hash = _file_hash(file_path)
                    key = (file_path.stat().st_size, file_hash)
                    hash_map.setdefault(key, []).append(file_path)
                except Exception:
                    continue

        duplicates = [group for group in hash_map.values() if len(group) > 1]

        if not duplicates:
            return {
                "ok": True,
                "message": f"No encontré duplicados en:\n{folder}",
                "duplicates": [],
            }

        total_duplicate_files = sum(len(group) for group in duplicates)
        lines = [
            f"Escaneo completado en:\n{folder}",
            f"Grupos de duplicados encontrados: {len(duplicates)}",
            f"Archivos duplicados totales: {total_duplicate_files}\n",
        ]

        for idx, group in enumerate(duplicates, start=1):
            lines.append(f"Grupo {idx}:")
            for file_path in group:
                lines.append(f" - {file_path}")
            lines.append("")

        return {
            "ok": True,
            "message": "\n".join(lines).strip(),
            "duplicates": duplicates,
        }

    except Exception as e:
        return {"ok": False, "message": f"No pude escanear duplicados: {e}", "duplicates": []}


def scan_duplicates(path_str, max_files=MAX_DUPLICATE_SCAN_FILES):
    action = "scan_duplicates"
    try:
        folder = normalize_path(path_str)
        if folder is None or not folder.exists():
            return _structured_result(False, action, error=f"No encontré la carpeta: {path_str}", duplicates=[])

        if folder.is_file():
            return _structured_result(False, action, error=f"La ruta es un archivo, no una carpeta:\n{folder}", duplicates=[])

        files, truncated = _collect_bounded_files(folder, max(1, int(max_files)))
        folder_artifact = make_artifact("folder", path=str(folder), description="Scanned folder", exists=True, verified=True)
        warnings = []
        if truncated:
            warnings.append(f"Duplicate scan stopped after {len(files)} files to keep the desktop responsive.")

        if not files:
            return _structured_result(
                True,
                action,
                result=f"No encontré archivos en:\n{folder}",
                observed=[f"Verified folder exists and contains 0 files: {folder}"],
                artifacts=[folder_artifact],
                warnings=warnings,
                duplicates=[],
            )

        size_map = {}
        for file_path in files:
            try:
                size = file_path.stat().st_size
                size_map.setdefault(size, []).append(file_path)
            except Exception:
                continue

        candidate_groups = [group for group in size_map.values() if len(group) > 1]
        hash_map = {}
        for group in candidate_groups:
            for file_path in group:
                try:
                    file_hash = _file_hash(file_path)
                    key = (file_path.stat().st_size, file_hash)
                    hash_map.setdefault(key, []).append(file_path)
                except Exception:
                    continue

        duplicates = [group for group in hash_map.values() if len(group) > 1]

        if not duplicates:
            return _structured_result(
                True,
                action,
                result=f"No encontré duplicados en:\n{folder}",
                observed=[f"Scanned {len(files)} files and found 0 duplicate groups."],
                artifacts=[folder_artifact],
                warnings=warnings,
                duplicates=[],
            )

        total_duplicate_files = sum(len(group) for group in duplicates)
        lines = [
            f"Escaneo completado en:\n{folder}",
            f"Grupos de duplicados encontrados: {len(duplicates)}",
            f"Archivos duplicados totales: {total_duplicate_files}\n",
        ]
        for idx, group in enumerate(duplicates, start=1):
            lines.append(f"Grupo {idx}:")
            for file_path in group:
                lines.append(f" - {file_path}")
            lines.append("")
        if truncated:
            lines.append(f"Scan limit reached after {len(files)} files.")

        return _structured_result(
            True,
            action,
            result="\n".join(lines).strip(),
            observed=[f"Scanned {len(files)} files.", f"Verified duplicate groups found: {len(duplicates)}"],
            artifacts=[folder_artifact],
            warnings=warnings,
            duplicates=[[str(path) for path in group] for group in duplicates],
        )
    except Exception as e:
        return _structured_result(False, action, error=f"No pude escanear duplicados: {e}", duplicates=[])


def _categorize_download_file(file_path):
    suffix = file_path.suffix.lower()
    for category, suffixes in DOWNLOAD_FILE_CATEGORY_MAP.items():
        if suffix in suffixes:
            return category
    return None


def _categorize_home_workspace_file(file_path):
    name = file_path.name.lower()
    if name in HOME_WORKSPACE_PROTECTED_FILES:
        return HOME_WORKSPACE_PROTECTED_FILES[name]

    suffix = file_path.suffix.lower()
    for category, suffixes in HOME_WORKSPACE_FILE_CATEGORY_MAP.items():
        if suffix in suffixes:
            return category
    return "LooseFiles"


def _download_target_for_category(category, downloads_folder):
    return DOWNLOAD_CATEGORY_TARGETS[category](downloads_folder)


def _home_target_for_category(category, home_folder):
    return HOME_WORKSPACE_TARGETS[category](home_folder)


def _safe_target_path(target_folder, source_name):
    candidate = target_folder / source_name
    if not candidate.exists():
        return candidate

    stem = Path(source_name).stem
    suffix = Path(source_name).suffix
    counter = 1
    while True:
        candidate = target_folder / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _preview_result(action, source_folder, items, summary, confirmation_phrase, skipped_protected=None):
    skipped_protected = skipped_protected or []
    if not items:
        return _structured_result(
            True,
            action,
            result=(
                f"Preview for:\n{source_folder}\n\n"
                "No files matched the safe organization rules.\n"
                "No files were moved yet."
            ),
            items=[],
            summary={},
            source=str(source_folder),
            confirmation_phrase=confirmation_phrase,
            skipped_protected=skipped_protected,
        )

    lines = [f"Preview for:\n{source_folder}", ""]
    lines.append("Destination categories:")
    for category, count in sorted(summary.items()):
        lines.append(f"- {category}: {count}")
    lines.append("")
    lines.append("Example files:")
    for item in items[:12]:
        lines.append(f"- {Path(item['source']).name} -> {item['category']} ({item['target_folder']})")
    if len(items) > 12:
        lines.append(f"... and {len(items) - 12} more files")
    if skipped_protected:
        lines.append("")
        lines.append("Protected paths skipped:")
        for name in skipped_protected:
            lines.append(f"- {name}")
    lines.append("")
    lines.append("No files were moved yet.")
    lines.append(f"Confirm with: {confirmation_phrase}")

    return _structured_result(
        True,
        action,
        result="\n".join(lines),
        items=items,
        summary=summary,
        source=str(source_folder),
        confirmation_phrase=confirmation_phrase,
        skipped_protected=skipped_protected,
    )


def preview_download_organization(path_str="downloads"):
    action = "preview_download_organization"
    try:
        downloads = normalize_path(path_str)
        if downloads is None or not downloads.exists():
            result = _structured_result(False, action, error=f"No encontré la carpeta: {path_str}", items=[], summary={})
            _log_file_action(action, False, result["error"])
            return result
        if downloads.is_file():
            result = _structured_result(False, action, error=f"La ruta no es una carpeta: {downloads}", items=[], summary={})
            _log_file_action(action, False, result["error"])
            return result

        items = []
        summary = {}
        for file_path in sorted(downloads.iterdir(), key=lambda x: x.name.lower()):
            if not file_path.is_file():
                continue

            category = _categorize_download_file(file_path)
            if not category:
                continue

            target_folder = _download_target_for_category(category, downloads)
            items.append(
                {
                    "source": str(file_path),
                    "target_folder": str(target_folder),
                    "category": category,
                }
            )
            summary[category] = summary.get(category, 0) + 1

        result = _preview_result(
            action=action,
            source_folder=downloads,
            items=items,
            summary=summary,
            confirmation_phrase="confirm organize downloads",
        )
        _log_file_action(action, True, f"previewed={len(items)} source={downloads}")
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e), items=[], summary={})
        _log_file_action(action, False, result["error"])
        return result


def apply_download_organization(path_str="downloads"):
    action = "apply_download_organization"
    preview = preview_download_organization(path_str)
    if not preview["success"]:
        return _structured_result(False, action, error=preview["error"], moved=[], summary={})
    if not preview["items"]:
        return _structured_result(True, action, result="No files needed to be moved.", moved=[], summary={})

    moved = []
    errors = []
    batch_id = f"downloads-{uuid.uuid4().hex[:12]}"
    for item in preview["items"]:
        source = Path(item["source"])
        target_folder = Path(item["target_folder"])
        try:
            target_folder.mkdir(parents=True, exist_ok=True)
            target_path = _safe_target_path(target_folder, source.name)
            shutil.move(str(source), str(target_path))
            moved_item = {
                "source": str(source),
                "target": str(target_path),
                "category": item["category"],
            }
            moved.append(moved_item)
            _log_file_action(action, True, f"{source} -> {target_path}")
        except Exception as e:
            errors.append(f"{source}: {e}")
            _log_file_action(action, False, f"{source}: {e}")

    if moved:
        record_moves(make_history_entries("downloads", batch_id, moved))

    if errors:
        return _structured_result(
            False,
            action,
            result=f"Moved {len(moved)} files, but some items failed.",
            error="\n".join(errors),
            moved=moved,
            summary=preview["summary"],
            batch_id=batch_id,
        )

    return _structured_result(
        True,
        action,
        result=f"Moved {len(moved)} files into Downloads\\Organized folders.",
        moved=moved,
        summary=preview["summary"],
        batch_id=batch_id,
    )


def preview_home_workspace_organization(path_str="home workspace"):
    action = "preview_home_workspace_organization"
    try:
        home = normalize_path(path_str)
        if home is None or not home.exists():
            result = _structured_result(False, action, error=f"No encontré la carpeta: {path_str}", items=[], summary={})
            _log_file_action(action, False, result["error"])
            return result
        if home.is_file():
            result = _structured_result(False, action, error=f"La ruta no es una carpeta: {home}", items=[], summary={})
            _log_file_action(action, False, result["error"])
            return result

        skipped_protected = sorted(
            item.name
            for item in home.iterdir()
            if item.is_dir() and item.name in HOME_WORKSPACE_PROTECTED_DIRS
        )

        items = []
        summary = {}
        for file_path in sorted(home.iterdir(), key=lambda x: x.name.lower()):
            if not file_path.is_file():
                continue

            category = _categorize_home_workspace_file(file_path)
            target_folder = _home_target_for_category(category, home)
            items.append(
                {
                    "source": str(file_path),
                    "target_folder": str(target_folder),
                    "category": category,
                }
            )
            summary[category] = summary.get(category, 0) + 1

        result = _preview_result(
            action=action,
            source_folder=home,
            items=items,
            summary=summary,
            confirmation_phrase="confirm organize home workspace",
            skipped_protected=skipped_protected,
        )
        _log_file_action(action, True, f"previewed={len(items)} source={home}")
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e), items=[], summary={})
        _log_file_action(action, False, result["error"])
        return result


def apply_home_workspace_organization(path_str="home workspace"):
    action = "apply_home_workspace_organization"
    preview = preview_home_workspace_organization(path_str)
    if not preview["success"]:
        return _structured_result(False, action, error=preview["error"], moved=[], summary={})
    if not preview["items"]:
        return _structured_result(True, action, result="No loose files needed to be moved.", moved=[], summary={})

    moved = []
    errors = []
    batch_id = f"home-{uuid.uuid4().hex[:12]}"
    for item in preview["items"]:
        source = Path(item["source"])
        target_folder = Path(item["target_folder"])
        try:
            target_folder.mkdir(parents=True, exist_ok=True)
            target_path = _safe_target_path(target_folder, source.name)
            shutil.move(str(source), str(target_path))
            moved_item = {
                "source": str(source),
                "target": str(target_path),
                "category": item["category"],
            }
            moved.append(moved_item)
            _log_file_action(action, True, f"{source} -> {target_path}")
        except Exception as e:
            errors.append(f"{source}: {e}")
            _log_file_action(action, False, f"{source}: {e}")

    if moved:
        record_moves(make_history_entries("home_workspace", batch_id, moved))

    if errors:
        return _structured_result(
            False,
            action,
            result=f"Moved {len(moved)} files, but some items failed.",
            error="\n".join(errors),
            moved=moved,
            summary=preview["summary"],
            batch_id=batch_id,
            skipped_protected=preview.get("skipped_protected", []),
        )

    return _structured_result(
        True,
        action,
        result=f"Moved {len(moved)} loose home workspace files into OrganizedWorkspace folders.",
        moved=moved,
        summary=preview["summary"],
        batch_id=batch_id,
        skipped_protected=preview.get("skipped_protected", []),
    )
