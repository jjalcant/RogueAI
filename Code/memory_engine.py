from pathlib import Path
from datetime import datetime
import sys

BASE = Path(__file__).resolve().parent.parent
MEMORY = BASE / "memory"
NOTES_FILE = MEMORY / "notes.md"

def save_note(text):
    MEMORY.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(NOTES_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {text}\n")

    print("Note saved.")
    print(f"Saved to: {NOTES_FILE}")

if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print("No note provided.")
        sys.exit()

    note = " ".join(args).strip()

    if not note:
        print("No note provided.")
        sys.exit()

    save_note(note)