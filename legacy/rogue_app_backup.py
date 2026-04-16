import tkinter as tk
from tkinter import scrolledtext
from pathlib import Path
from datetime import datetime
import json
import os
from Code.api_brain import ask_llm

BASE = Path(__file__).resolve().parent
MEMORY = BASE / "memory"
PROJECTS = BASE / "projects"
AGENTS = BASE / "agents"
AUTONOMY = BASE / "autonomy"
CONFIG = BASE / "config"
LOGS = BASE / "logs"

NOTES_FILE = MEMORY / "notes.md"
BRAIN_LOG = LOGS / "brain.log"


class RogueApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Rogue Local")
        self.root.geometry("950x700")

        self.pending_action = None
        self.conversation_memory = []

        self.build_ui()
        self.ensure_folders()
        self.add_message(
            "Rogue",
            "Rogue Local online.\n\n"
            "Puedes escribirme cosas como:\n"
            "muestrame mis proyectos\n"
            "recuérdame llamar al vet\n"
            "crea un proyecto llamado uber_ai\n"
            "cuál es mi estado\n"
            "quiero pensar\n"
            "haz un plan"
        )

    def build_ui(self):
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.chat_box = scrolledtext.ScrolledText(
            self.main_frame,
            wrap=tk.WORD,
            font=("Segoe UI", 11),
            state=tk.DISABLED
        )
        self.chat_box.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.input_frame = tk.Frame(self.main_frame)
        self.input_frame.pack(fill=tk.X)

        self.entry = tk.Entry(self.input_frame, font=("Segoe UI", 12))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self.entry.bind("<Return>", self.handle_enter)

        self.send_button = tk.Button(
            self.input_frame,
            text="Send",
            width=12,
            command=self.send_message
        )
        self.send_button.pack(side=tk.RIGHT)

        self.entry.focus_set()

    def ensure_folders(self):
        for folder in [MEMORY, PROJECTS, AGENTS, AUTONOMY, CONFIG, LOGS]:
            folder.mkdir(parents=True, exist_ok=True)

    def add_message(self, sender, message):
        self.chat_box.config(state=tk.NORMAL)
        self.chat_box.insert(tk.END, f"{sender}: {message}\n\n")
        self.chat_box.config(state=tk.DISABLED)
        self.chat_box.see(tk.END)

    def handle_enter(self, event):
        self.send_message()

    def send_message(self):
        user_text = self.entry.get().strip()
        if not user_text:
            return

        self.add_message("Tú", user_text)
        self.entry.delete(0, tk.END)

        self.remember_turn("user", user_text)
        response = self.process_input(user_text)
        self.remember_turn("assistant", response)

        self.add_message("Rogue", response)
        self.entry.focus_set()

    def remember_turn(self, role, content):
        self.conversation_memory.append({"role": role, "content": content})
        self.conversation_memory = self.conversation_memory[-10:]

    def process_input(self, text):
        t = text.lower().strip()

        if self.pending_action:
            return self.handle_confirmation(t)

        intent = self.detect_intent(t)

        if intent == "project_list":
            return self.get_projects_response()

        if intent == "project_create":
            project_name = self.extract_project_name(text)
            if not project_name:
                return "Dime el nombre del proyecto que quieres crear."
            self.pending_action = {
                "type": "create_project",
                "name": project_name
            }
            return f'Voy a crear el proyecto "{project_name}" en tu carpeta projects.\nEscribe SI para confirmar.'

        if intent == "note":
            note_text = self.extract_note_text(text)
            if not note_text:
                return "Dime qué quieres guardar."
            return self.save_note(note_text)

        if intent == "status":
            return self.get_status_response()

        if intent == "think":
            return self.get_think_response()

        if intent == "plan":
            return self.get_plan_response()

        if intent == "open_projects_folder":
            return self.open_projects_folder()

        if intent == "help":
            return self.get_help_response()

        return self.fallback_response(text)

    def detect_intent(self, text):
        if self.matches_any(text, [
            "crea un proyecto",
            "crear proyecto",
            "nuevo proyecto",
            "haz un proyecto"
        ]):
            return "project_create"

        if self.matches_any(text, [
            "que proyectos tengo",
            "qué proyectos tengo",
            "muestrame mis proyectos",
            "muéstrame mis proyectos",
            "ver proyectos",
            "mostrar proyectos",
            "mis proyectos",
            "lista de proyectos",
            "projects"
        ]):
            return "project_list"

        if self.matches_any(text, [
            "recuerda",
            "recuérdame",
            "recuerdame",
            "guarda esto",
            "guardar nota",
            "nota",
            "apunta",
            "anota"
        ]):
            return "note"

        if self.matches_any(text, [
            "estado",
            "status",
            "cual es mi estado",
            "cuál es mi estado",
            "como estas",
            "cómo estás",
            "system status"
        ]):
            return "status"

        if self.matches_any(text, [
            "quiero pensar",
            "ayudame a pensar",
            "ayúdame a pensar",
            "piensa conmigo",
            "pensar",
            "think"
        ]):
            return "think"

        if self.matches_any(text, [
            "haz un plan",
            "planea",
            "planifica",
            "plan",
            "organiza mis pasos"
        ]):
            return "plan"

        if self.matches_any(text, [
            "abre proyectos",
            "abre la carpeta de proyectos",
            "open projects folder"
        ]):
            return "open_projects_folder"

        if self.matches_any(text, [
            "ayuda",
            "help",
            "que puedes hacer",
            "qué puedes hacer"
        ]):
            return "help"

        return "unknown"

    def matches_any(self, text, patterns):
        return any(pattern in text for pattern in patterns)

    def extract_project_name(self, text):
        lowered = text.lower()

        markers = ["llamado", "llamada", "named"]
        for marker in markers:
            if marker in lowered:
                idx = lowered.find(marker)
                name = text[idx + len(marker):].strip(" :,-")
                return self.clean_project_name(name)

        parts = text.strip().split()
        if len(parts) >= 4:
            return self.clean_project_name(parts[-1])

        return ""

    def clean_project_name(self, name):
        name = name.strip().lower().replace(" ", "_")
        valid = []
        for ch in name:
            if ch.isalnum() or ch in ["_", "-"]:
                valid.append(ch)
        return "".join(valid)

    def extract_note_text(self, text):
        cleaned = text

        removable_phrases = [
            "recuérdame",
            "recuerdame",
            "recuerda",
            "guardar nota",
            "guarda esto",
            "nota",
            "apunta",
            "anota"
        ]

        for phrase in removable_phrases:
            cleaned = cleaned.replace(phrase, "")
            cleaned = cleaned.replace(phrase.capitalize(), "")

        return cleaned.strip(" :,-")

    def handle_confirmation(self, text):
        if text in ["si", "sí", "yes"]:
            action = self.pending_action
            self.pending_action = None

            if action["type"] == "create_project":
                return self.create_project(action["name"])

            return "Acción confirmada, pero no reconocida."

        if text in ["no", "cancelar", "cancel"]:
            self.pending_action = None
            return "Listo. Acción cancelada."

        return "Tengo una acción pendiente. Escribe SI para confirmar o NO para cancelar."

    def create_project(self, project_name):
        try:
            project_path = PROJECTS / project_name

            if project_path.exists():
                return f'Ese proyecto ya existe: "{project_name}".'

            project_path.mkdir(parents=True, exist_ok=True)
            self.log_action(f"Project created: {project_name}")
            return f'Listo. Ya creé el proyecto "{project_name}".'
        except Exception as e:
            return f"No pude crear el proyecto: {e}"

    def get_projects_response(self):
        try:
            if not PROJECTS.exists():
                return "No encontré la carpeta de proyectos."

            items = [item.name for item in PROJECTS.iterdir()]
            if not items:
                return "Ahora mismo no tienes proyectos creados."

            items.sort()
            return f"Tienes {len(items)} proyectos ahora mismo:\n" + ", ".join(items)
        except Exception as e:
            return f"No pude leer tus proyectos: {e}"

    def save_note(self, text):
        try:
            MEMORY.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

            with open(NOTES_FILE, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {text}\n")

            self.log_action(f"Note saved: {text}")
            return "Listo. Ya guardé esa nota en tu memoria."
        except Exception as e:
            return f"No pude guardar la nota: {e}"

    def get_status_response(self):
        try:
            memory_count = self.count_items(MEMORY)
            projects_count = self.count_items(PROJECTS)
            agents_count = self.count_items(AGENTS)
            autonomy_count = self.count_items(AUTONOMY)

            return (
                "Estado actual de Rogue:\n"
                f"- memoria: {memory_count} items\n"
                f"- proyectos: {projects_count} items\n"
                f"- agentes: {agents_count} items\n"
                f"- autonomía: {autonomy_count} items"
            )
        except Exception as e:
            return f"No pude leer el estado: {e}"

    def get_think_response(self):
        return (
            "Vamos a pensar.\n\n"
            "Respóndeme esto:\n"
            "1. qué quieres resolver\n"
            "2. qué te está frenando\n"
            "3. cuál es el siguiente paso más pequeño"
        )

    def get_plan_response(self):
        return (
            "Vamos a planearlo.\n\n"
            "Dime:\n"
            "1. el proyecto\n"
            "2. el resultado que quieres\n"
            "3. lo que ya tienes hecho"
        )

    def get_help_response(self):
        return (
            "Ahora mismo puedo ayudarte con:\n"
            "- ver proyectos\n"
            "- crear proyectos\n"
            "- guardar notas\n"
            "- ver estado\n"
            "- pensar\n"
            "- planear\n"
            "- abrir la carpeta de proyectos"
        )

    def open_projects_folder(self):
        try:
            PROJECTS.mkdir(parents=True, exist_ok=True)
            os.startfile(str(PROJECTS))
            self.log_action("Projects folder opened")
            return "Listo. Ya abrí tu carpeta de proyectos."
        except Exception as e:
            return f"No pude abrir la carpeta de proyectos: {e}"

    def fallback_response(self, text):
        recent = self.get_recent_context_list()
        return ask_llm(text, recent)

        return (
            "Todavía no soy un LLM completo local, pero sí una base conversacional.\n\n"
            "Entendí tu mensaje, pero aún no tengo una acción clara para eso.\n"
            "Prueba reformularlo como:\n"
            "- muestrame mis proyectos\n"
            "- crea un proyecto llamado x\n"
            "- recuérdame x\n"
            "- cuál es mi estado\n"
            "- quiero pensar\n"
            "- haz un plan\n\n"
            f"Contexto reciente:\n{recent}"
        )

    def get_recent_context_text(self):
    def get_recent_context_list(self):
    if not self.conversation_memory:
    return []

    lines = []
    for item in self.conversation_memory[-6:]:
        role = "User" if item["role"] == "user" else "Assistant"
        lines.append(f"{role}: {item['content']}")
    return lines
        if not self.conversation_memory:
            return "sin contexto reciente"

        last_items = self.conversation_memory[-4:]
        lines = []
        for item in last_items:
            role = "Tú" if item["role"] == "user" else "Rogue"
            lines.append(f"- {role}: {item['content'][:80]}")
        return "\n".join(lines)

    def count_items(self, folder):
        if folder.exists() and folder.is_dir():
            return len(list(folder.iterdir()))
        return 0

    def log_action(self, action):
        try:
            LOGS.mkdir(parents=True, exist_ok=True)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(BRAIN_LOG, "a", encoding="utf-8") as f:
                f.write(f"[{now}] {action}\n")
        except Exception:
            pass


if __name__ == "__main__":
    root = tk.Tk()
    app = RogueApp(root)
    root.mainloop()