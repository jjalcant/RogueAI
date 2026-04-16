import json
from pathlib import Path


DEFAULT_SETTINGS = {
    "app_name": "Rogue Local",
    "max_memory_turns": 12,
    "theme": "Light",
}

DEFAULT_MODULES = {
    "memory": True,
    "projects": True,
    "agents": True,
    "tools": True,
    "autonomy": True,
}

REQUIRED_SETTINGS_TYPES = {
    "app_name": str,
    "max_memory_turns": int,
    "theme": str,
}

REQUIRED_MODULE_KEYS = tuple(DEFAULT_MODULES.keys())


class ConfigError(Exception):
    pass


class StartupCheckError(Exception):
    pass


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _load_json_dict(path):
    path = Path(path)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise ConfigError(f"Missing config file: {path}") from e
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in {path}: {e.msg}") from e

    if not isinstance(data, dict):
        raise ConfigError(f"Config file must contain an object: {path}")

    return data


def ensure_required_folders(folders):
    created = []
    for folder in folders:
        folder = Path(folder)
        if not folder.exists():
            folder.mkdir(parents=True, exist_ok=True)
            created.append(folder)
    return created


def load_or_create_settings(path):
    path = Path(path)
    if not path.exists():
        write_json(path, DEFAULT_SETTINGS)
        return dict(DEFAULT_SETTINGS)

    data = _load_json_dict(path)
    normalized = dict(data)

    if "app_name" not in normalized:
        legacy_name = normalized.get("assistant_name")
        normalized["app_name"] = legacy_name if isinstance(legacy_name, str) else DEFAULT_SETTINGS["app_name"]

    if "max_memory_turns" not in normalized:
        normalized["max_memory_turns"] = DEFAULT_SETTINGS["max_memory_turns"]

    if "theme" not in normalized:
        normalized["theme"] = DEFAULT_SETTINGS["theme"]

    for key, expected_type in REQUIRED_SETTINGS_TYPES.items():
        if not isinstance(normalized[key], expected_type):
            raise ConfigError(
                f"Invalid type for '{key}' in {path}: expected {expected_type.__name__}"
            )

    if normalized["max_memory_turns"] <= 0:
        raise ConfigError(f"'max_memory_turns' must be greater than 0 in {path}")

    return normalized


def load_or_create_modules(path):
    path = Path(path)
    if not path.exists():
        write_json(path, DEFAULT_MODULES)
        return dict(DEFAULT_MODULES)

    data = _load_json_dict(path)
    for key in REQUIRED_MODULE_KEYS:
        if key not in data:
            raise ConfigError(f"Missing key '{key}' in {path}")
        if not isinstance(data[key], bool):
            raise ConfigError(f"Invalid type for '{key}' in {path}: expected bool")

    return data


def run_startup_checks(required_folders, settings_path, modules_path):
    created_folders = ensure_required_folders(required_folders)

    try:
        settings = load_or_create_settings(settings_path)
        modules = load_or_create_modules(modules_path)
    except ConfigError as e:
        raise StartupCheckError(str(e)) from e

    return {
        "created_folders": created_folders,
        "settings": settings,
        "modules": modules,
    }
