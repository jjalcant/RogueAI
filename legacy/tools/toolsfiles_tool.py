from pathlib import Path
import os
import hashlib


def get_downloads_folder():
    return Path.home() / "Downloads"


def open_folder(folder_path):
    try:
        folder = Path(folder_path)
        if not folder.exists():
            return f"No encontré la carpeta: {folder}"
        os.startfile(str(folder))
        return f"Listo. Ya abrí la carpeta:\n{folder}"
    except Exception as e:
        return f"No pude abrir la carpeta: {e}"


def list_files(folder_path, limit=50):
    try:
        folder = Path(folder_path)
        if not folder.exists():
            return f"No encontré la carpeta: {folder}"

        items = sorted(folder.iterdir(), key=lambda x: x.name.lower())

        if not items:
            return f"La carpeta está vacía:\n{folder}"

        lines = [f"Contenido de:\n{folder}\n"]
        for item in items[:limit]:
            kind = "[DIR]" if item.is_dir() else "[FILE]"
            lines.append(f"{kind} {item.name}")

        if len(items) > limit:
            lines.append(f"\nMostrando {limit} de {len(items)} elementos.")

        return "\n".join(lines)

    except Exception as e:
        return f"No pude listar archivos: {e}"


def _file_hash(path, chunk_size=1024 * 1024):
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def scan_duplicates(folder_path):
    try:
        folder = Path(folder_path)
        if not folder.exists():
            return {"ok": False, "message": f"No encontré la carpeta: {folder}"}

        files = [p for p in folder.rglob("*") if p.is_file()]

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
                "duplicates": []
            }

        total_duplicate_files = sum(len(group) for group in duplicates)
        lines = [
            f"Escaneo completado en:\n{folder}",
            f"Grupos de duplicados encontrados: {len(duplicates)}",
            f"Archivos duplicados totales: {total_duplicate_files}\n"
        ]

        for idx, group in enumerate(duplicates, start=1):
            lines.append(f"Grupo {idx}:")
            for file_path in group:
                lines.append(f" - {file_path}")
            lines.append("")

        return {
            "ok": True,
            "message": "\n".join(lines).strip(),
            "duplicates": duplicates
        }

    except Exception as e:
        return {"ok": False, "message": f"No pude escanear duplicados: {e}", "duplicates": []}