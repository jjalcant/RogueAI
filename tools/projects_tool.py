from pathlib import Path
import os

from result_contract import build_result, make_artifact


def _structured_result(success, action, result="", error=None, observed=None, artifacts=None, warnings=None, errors=None, **extra):
    return build_result(
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


def create_project(projects_folder, project_name):
    action = "create_project"
    try:
        projects_folder = Path(projects_folder)
        projects_folder.mkdir(parents=True, exist_ok=True)

        project_path = projects_folder / project_name

        if project_path.exists():
            return _structured_result(
                True,
                action,
                result=f'Project already exists: "{project_name}".',
                observed=[f"Verified project path already exists: {project_path}"],
                artifacts=[make_artifact("project_folder", path=str(project_path), description="Project folder", exists=True, verified=True)],
                project={"name": project_name, "path": str(project_path)},
            )

        project_path.mkdir(parents=True, exist_ok=True)
        return _structured_result(
            True,
            action,
            result=f'Created project "{project_name}".',
            observed=[f"Verified project folder exists after create request: {project_path}"],
            artifacts=[make_artifact("project_folder", path=str(project_path), description="Project folder", exists=project_path.exists(), verified=True)],
            project={"name": project_name, "path": str(project_path)},
        )
    except Exception as e:
        return _structured_result(False, action, error=f"No pude crear el proyecto: {e}")


def list_projects(projects_folder):
    action = "list_projects"
    try:
        projects_folder = Path(projects_folder)

        if not projects_folder.exists():
            return _structured_result(False, action, error="No encontré la carpeta de proyectos.")

        items = [item.name for item in projects_folder.iterdir()]
        if not items:
            return _structured_result(
                True,
                action,
                result="Ahora mismo no tienes proyectos creados.",
                observed=[f"Verified projects folder exists and contains 0 items: {projects_folder}"],
                artifacts=[make_artifact("projects_folder", path=str(projects_folder), description="Projects folder", exists=True, verified=True)],
                projects=[],
            )

        items.sort()
        return _structured_result(
            True,
            action,
            result=f"Tienes {len(items)} proyectos ahora mismo:\n" + ", ".join(items),
            observed=[f"Verified projects folder exists: {projects_folder}", f"Verified project count: {len(items)}"],
            artifacts=[make_artifact("projects_folder", path=str(projects_folder), description="Projects folder", exists=True, verified=True)],
            projects=items,
        )
    except Exception as e:
        return _structured_result(False, action, error=f"No pude leer tus proyectos: {e}")


def open_projects_folder(projects_folder):
    action = "open_projects_folder"
    try:
        projects_folder = Path(projects_folder)
        projects_folder.mkdir(parents=True, exist_ok=True)
        os.startfile(str(projects_folder))
        return _structured_result(
            True,
            action,
            result=f"Open request sent for projects folder: {projects_folder}",
            observed=[
                f"Verified projects folder exists: {projects_folder}",
                f"An OS open request was issued for the projects folder without an immediate exception: {projects_folder}",
            ],
            artifacts=[make_artifact("projects_folder", path=str(projects_folder), description="Projects folder", exists=True, verified=True)],
            warnings=["I cannot confirm that the File Explorer window is visible."],
        )
    except Exception as e:
        return _structured_result(False, action, error=f"No pude abrir la carpeta de proyectos: {e}")
