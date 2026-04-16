import os
import platform
import subprocess
from datetime import datetime
from pathlib import Path
import shlex

from result_contract import build_result, make_artifact
from tools.system_info import get_system_info as collect_system_info


BASE = Path(__file__).resolve().parent.parent
LOGS = BASE / "logs"
LOG_FILE = LOGS / "brain.log"

DANGEROUS_TOKENS = {
    "shutdown",
    "restart-computer",
    "stop-computer",
    "format",
    "diskpart",
    "del /f /s /q",
    "rmdir /s /q",
    "rd /s /q",
    "rm -rf",
    "mkfs",
    "dd ",
}

NETWORK_TOKENS = {
    "http://",
    "https://",
    "curl ",
    "wget ",
    "invoke-webrequest",
    "irm ",
}

APP_ALIASES = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
}

FOLDER_ALIASES = {}


def _log_action(action, success, details):
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{now}] system_tool action={action} success={success} details={details}\n")
    except Exception:
        pass


def _structured_result(success, action, result="", error=None, stdout="", stderr="", observed=None, artifacts=None, warnings=None, errors=None, **extra):
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
    if stdout:
        payload["stdout"] = stdout
    if stderr:
        payload["stderr"] = stderr
    return payload


def _normalize_alias(value):
    cleaned = str(value).strip().lower()
    for prefix in ("my ",):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return cleaned


def _build_folder_aliases():
    home = Path.home()
    desktop_paths = [home / "Desktop", home / "OneDrive" / "Desktop"]
    desktop = next((path for path in desktop_paths if path.exists()), home / "Desktop")
    return {
        "download": home / "Downloads",
        "download folder": home / "Downloads",
        "downloads": home / "Downloads",
        "downloads folder": home / "Downloads",
        "my downloads": home / "Downloads",
        "documents": home / "Documents",
        "documentos": home / "Documents",
        "documents folder": home / "Documents",
        "my documents": home / "Documents",
        "desktop": desktop,
        "desktop folder": desktop,
        "my desktop": desktop,
        "escritorio": desktop,
        "pictures": home / "Pictures",
        "pictures folder": home / "Pictures",
        "images": home / "Pictures",
        "music": home / "Music",
        "music folder": home / "Music",
        "videos": home / "Videos",
        "videos folder": home / "Videos",
        "workspace": BASE,
        "workspace folder": BASE,
        "this folder": BASE,
        "current folder": BASE,
        "projects": BASE / "projects",
        "projects folder": BASE / "projects",
    }


FOLDER_ALIASES = _build_folder_aliases()


def resolve_folder_alias(name_or_path):
    value = str(name_or_path).strip()
    if not value:
        return None

    lowered = _normalize_alias(value)
    if lowered in FOLDER_ALIASES:
        return FOLDER_ALIASES[lowered]

    if lowered.endswith(" folder") and lowered[:-7].strip() in FOLDER_ALIASES:
        return FOLDER_ALIASES[lowered[:-7].strip()]

    return None


def resolve_application_alias(name_or_path):
    value = str(name_or_path).strip()
    if not value:
        return None
    return APP_ALIASES.get(_normalize_alias(value))


def is_folder_alias(name_or_path):
    return resolve_folder_alias(name_or_path) is not None


def is_application_alias(name_or_path):
    return resolve_application_alias(name_or_path) is not None


def _resolve_special_folder(name_or_path):
    value = str(name_or_path).strip()
    if not value:
        return None

    alias_folder = resolve_folder_alias(value)
    if alias_folder is not None:
        return alias_folder

    return Path(value).expanduser()


def _start_path(target):
    os.startfile(str(target))


def _run_process(command_parts):
    return subprocess.run(
        command_parts,
        capture_output=True,
        text=True,
        shell=False,
        timeout=30,
    )


def _spawn_process(command_parts):
    return subprocess.Popen(
        command_parts,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
    )


def _command_is_blocked(command):
    lowered = command.lower().strip()
    if any(token in lowered for token in DANGEROUS_TOKENS):
        return "Command blocked for safety."
    if any(token in lowered for token in NETWORK_TOKENS):
        return "Only local commands are allowed."
    return None


def open_application(name_or_path):
    action = "open_application"
    try:
        raw_value = str(name_or_path).strip()
        app_value = resolve_application_alias(raw_value) or raw_value

        if not app_value:
            result = _structured_result(False, action, error="No application provided.")
            _log_action(action, False, result["error"])
            return result

        target_path = Path(app_value).expanduser()
        if target_path.exists():
            _start_path(target_path)
            result = _structured_result(
                True,
                action,
                result=f"Open request sent for application path: {target_path}",
                observed=[
                    f"Verified application path exists: {target_path}",
                    f"An OS open request was issued for the application path without an immediate exception: {target_path}",
                ],
                artifacts=[make_artifact("application_path", path=str(target_path), description="Application path", exists=True, verified=True)],
                warnings=["I cannot confirm that the application window is visible."],
            )
        else:
            _spawn_process([app_value])
            result = _structured_result(
                True,
                action,
                result=f"Launch command started for application alias: {app_value}",
                observed=[f"A local process launch request was issued without an immediate exception: {app_value}"],
                warnings=["I cannot confirm that the application became visible."],
            )

        _log_action(action, result["success"], result["result"] or result["error"])
        return result
    except FileNotFoundError:
        result = _structured_result(False, action, error=f"Application not found: {name_or_path}")
        _log_action(action, False, result["error"])
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e))
        _log_action(action, False, result["error"])
        return result


def open_folder(path):
    action = "open_folder"
    try:
        folder = _resolve_special_folder(path)
        if folder is None or not folder.exists():
            result = _structured_result(False, action, error=f"Folder not found: {path}")
            _log_action(action, False, result["error"])
            return result
        if not folder.is_dir():
            result = _structured_result(False, action, error=f"Path is not a folder: {folder}")
            _log_action(action, False, result["error"])
            return result

        _start_path(folder)
        result = _structured_result(
            True,
            action,
            result=f"Open request sent for folder: {folder}",
            observed=[
                f"Verified folder exists: {folder}",
                f"An OS open request was issued for the folder without an immediate exception: {folder}",
            ],
            artifacts=[make_artifact("folder", path=str(folder), description="Folder path", exists=True, verified=True)],
            warnings=["I cannot confirm that the File Explorer window is visible."],
        )
        _log_action(action, True, result["result"])
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e))
        _log_action(action, False, result["error"])
        return result


def run_shell_command(command):
    action = "run_shell_command"
    try:
        raw_command = str(command).strip()
        if not raw_command:
            result = _structured_result(False, action, error="No command provided.")
            _log_action(action, False, result["error"])
            return result

        blocked_reason = _command_is_blocked(raw_command)
        if blocked_reason:
            result = _structured_result(False, action, error=blocked_reason)
            _log_action(action, False, f"{blocked_reason} command={raw_command}")
            return result

        command_parts = shlex.split(raw_command, posix=False)
        completed = _run_process(command_parts)
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        success = completed.returncode == 0
        result_text = stdout or (f"Command exited with code {completed.returncode} and produced no stdout." if success else "")
        observed = [f"Command exit code: {completed.returncode}"]
        if stdout:
            observed.append("Command produced stdout.")
        if stderr:
            observed.append("Command produced stderr.")
        warnings = []
        if success and not stdout:
            warnings.append("No stdout was returned.")
        result = _structured_result(
            success,
            action,
            result=result_text,
            error=None if success else (stderr or f"Command failed with exit code {completed.returncode}."),
            stdout=stdout,
            stderr=stderr,
            observed=observed,
            warnings=warnings,
        )
        _log_action(action, success, f"command={raw_command} result={result['result'] or result['error']}")
        return result
    except Exception as e:
        result = _structured_result(False, action, error=str(e))
        _log_action(action, False, f"command={command} error={e}")
        return result


def get_system_info():
    result = collect_system_info()
    _log_action(result["action"], result["success"], result.get("result") or result.get("error"))
    return result
