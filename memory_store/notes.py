from datetime import datetime
from pathlib import Path


def save_note(memory_folder, text):

    try:
        memory_folder = Path(memory_folder)
        memory_folder.mkdir(parents=True, exist_ok=True)

        notes_file = memory_folder / "notes.md"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        with open(notes_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {text}\n")

        return "Listo. Ya guardé esa nota en tu memoria."

    except Exception as e:
        return f"No pude guardar la nota: {e}"