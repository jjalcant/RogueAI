import shutil
from pathlib import Path

desktop = Path.home() / "Desktop"

skip_folders = [
    "School",
    "Projects",
    "Games",
    "Tools",
    "Work",
    "Other"
]

folders = {
    "Images": [".png", ".jpg", ".jpeg", ".gif"],
    "Documents": [".pdf", ".docx", ".txt"],
    "Code": [".py", ".js", ".html", ".css"],
    "Audio": [".mp3", ".wav"]
}

for item in desktop.iterdir():

    if item.is_dir():
        if item.name in skip_folders:
            continue

    if item.is_file():

        moved = False

        for folder, extensions in folders.items():

            if item.suffix.lower() in extensions:

                target = desktop / folder
                target.mkdir(exist_ok=True)

                shutil.move(str(item), target / item.name)

                print(f"Moved {item.name} → {folder}")

                moved = True
                break

        if not moved:

            target = desktop / "Other"
            target.mkdir(exist_ok=True)

            shutil.move(str(item), target / item.name)

            print(f"Moved {item.name} → Other")