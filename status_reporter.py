"""Markdown status reporter for implementation and runtime validation."""

from __future__ import annotations

from pathlib import Path


SECTION_TITLES = (
    "Completed Work",
    "Remaining Work",
    "Blockers",
    "Validation Results",
)


class StatusReporter:
    def __init__(self, status_file: Path):
        self.status_file = Path(status_file)
        self.sections = self._load_sections()

    def add_completed(self, item: str):
        self._append_unique("Completed Work", item)
        self._remove_item("Remaining Work", item)
        self.save()

    def add_remaining(self, item: str):
        self._append_unique("Remaining Work", item)
        self.save()

    def add_blocker(self, item: str):
        self._append_unique("Blockers", item)
        self.save()

    def add_validation(self, item: str):
        self._append_unique("Validation Results", item)
        self.save()

    def save(self):
        lines = ["# RogueAI Status", ""]
        for title in SECTION_TITLES:
            lines.append(f"## {title}")
            lines.append("")
            items = self.sections.get(title, [])
            if items:
                lines.extend(f"- {item}" for item in items)
            else:
                lines.append("- None")
            lines.append("")
        self.status_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def _append_unique(self, title: str, item: str):
        bucket = self.sections.setdefault(title, [])
        if item not in bucket:
            bucket.append(item)

    def _remove_item(self, title: str, item: str):
        bucket = self.sections.setdefault(title, [])
        if item in bucket:
            bucket.remove(item)

    def _load_sections(self):
        if not self.status_file.exists():
            return {title: [] for title in SECTION_TITLES}

        sections = {title: [] for title in SECTION_TITLES}
        current = None
        for raw_line in self.status_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if line.startswith("## "):
                heading = line[3:].strip()
                current = heading if heading in sections else None
                continue
            if current and line.startswith("- "):
                value = line[2:].strip()
                if value and value.lower() != "none":
                    sections[current].append(value)
        return sections
