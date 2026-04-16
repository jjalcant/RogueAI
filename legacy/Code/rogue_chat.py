import tkinter as tk
from tkinter import scrolledtext
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent.parent
PROJECTS = BASE / "projects"

class RogueChatApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Rogue Chat")
        self.root.geometry("900x650")

        self.pending_action = None

        self.main_frame = tk.Frame(root)
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

        self.send_button = tk.Button(
            self.input_frame,
            text="Send",
            width=12,
            command=self.send_message
        )
        self.send_button.pack(side=tk.RIGHT)

        self.entry.bind("<Return>", self.handle_enter)
        self.entry.focus_set()

        self.add_message(
            "Rogue",
            "Rogue Chat v4 online.\n\nPrueba cosas como:\n"
            "muestrame mis proyectos\n"
            "recuérdame llamar al vet\n"
            "crea un proyecto llamado uber_ai\n"
            "quiero pensar\n"
            "cuál es mi estado"
        )

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

        response = self.process_input(user_text)
        self.add_message("Rogue", response)

        self.entry.focus_set()

    def process_input(self, text):
        t = text.lower().strip()

        if self.pending_action:
            return self.handle_confirmation(t)

        intent = self.detect_intent(t)

        if intent == "project":
            return self.get_projects_response()

        elif intent == "note":
            note_text = self.extract_note_text(text)
            if not note_text:
                return "Dime qué quieres guardar."
            return self.run_note_command(note_text)

        elif intent == "new_project":
            project_name = self.extract_project_name(text)
            if not project_name:
                return "Dime el nombre del proyecto que quieres crear."
            self.pending_action = {
                "type": "new_project",
                "name": project_name
            }
            return f'Voy a crear el proyecto "{project_name}" en tu carpeta projects.\nEscribe SI para confirmar.'

        elif intent == "think":
            return (
                "Vamos a pensar.\n\n"
                "Respóndeme esto en una sola frase:\n"
                "1. Qué quieres resolver\n"
                "2. Qué te está frenando\n"
                "3. Cuál sería el siguiente paso más pequeño"
            )

        elif intent == "plan":
            return (
                "Vamos a planearlo.\n\n"
                "Dime:\n"
                "1. el proyecto\n"
                "2. el resultado que quieres\n"
                "3. lo que ya tienes hecho"
            )

        elif intent == "status":
            return self.get_status_response()

        elif intent == "clean_desktop":
            return "Todavía tengo el modo de limpiar escritorio en manual por seguridad. Luego lo conectamos con confirmación."

        else:
            return (
                "Todavía estoy en fase inicial.\n\n"
                "Ahora mismo puedo ayudarte con:\n"
                "- ver proyectos\n"
                "- guardar notas\n"
                "- crear proyectos\n"
                "- pensar\n"
                "- planear\n"
                "- ver estado"
            )

    def handle_confirmation(self, text):
        if text in ["si", "sí", "yes"]:
            action = self.pending_action
            self.pending_action = None

            if action["type"] == "new_project":
                return self.create_project(action["name"])

            return "Acción confirmada, pero no reconocida."

        elif text in ["no", "cancelar", "cancel"]:
            self.pending_action = None
            return "Listo. Acción cancelada."

        else:
            return "Tengo una acción pendiente. Escribe SI para confirmar o NO para cancelar."

    def detect_intent(self, t):
        new_project_patterns = [
            "crea un proyecto",
            "crear proyecto",
            "nuevo proyecto",
            "haz un proyecto"
        ]

        project_patterns = [
            "que proyectos tengo",
            "qué proyectos tengo",
            "muestrame mis proyectos",
            "muéstrame mis proyectos",
            "ver proyectos",
            "mostrar proyectos",
            "lista de proyectos",
            "mis proyectos",
            "projects"
        ]

        note_patterns = [
            "recuerda",
            "recuérdame",
            "recordar",
            "guarda esto",
            "guardar nota",
            "nota",
            "apunta",
            "anota"
        ]

        think_patterns = [
            "quiero pensar",
            "ayudame a pensar",
            "ayúdame a pensar",
            "piensa conmigo",
            "think",
            "pensar"
        ]

        plan_patterns = [
            "haz un plan",
            "planea",
            "planifica",
            "organiza mis pasos"
        ]

        status_patterns = [
            "estado",
            "status",
            "como estas",
            "cómo estás",
            "cual es mi estado",
            "cuál es mi estado",
            "system status"
        ]

        clean_patterns = [
            "organiza mi escritorio",
            "limpia el escritorio",
            "clean desktop"
        ]

        if self.matches_any(t, new_project_patterns):
            return "new_project"
        if self.matches_any(t, project_patterns):
            return "project"
        if self.matches_any(t, note_patterns):
            return "note"
        if self.matches_any(t, think_patterns):
            return "think"
        if self.matches_any(t, plan_patterns):
            return "plan"
        if self.matches_any(t, status_patterns):
            return "status"
        if self.matches_any(t, clean_patterns):
            return "clean_desktop"

        return "unknown"

    def matches_any(self, text, patterns):
        for pattern in patterns:
            if pattern in text:
                return True
        return False

    def extract_note_text(self, text):
        cleaned = text
        removable_phrases = [
            "recuérdame",
            "recuerdame",
            "recuerda",
            "recordar",
            "guarda esto",
            "guardar nota",
            "nota",
            "apunta",
            "anota"
        ]

        for phrase in removable_phrases:
            cleaned = cleaned.replace(phrase, "")
            cleaned = cleaned.replace(phrase.capitalize(), "")

        return cleaned.strip(" :,-")

    def extract_project_name(self, text):
        lowered = text.lower()
        markers = [
            "llamado",
            "llamada",
            "named"
        ]

        for marker in markers:
            if marker in lowered:
                idx = lowered.find(marker)
                name = text[idx + len(marker):].strip(" :,-")
                return name.replace(" ", "_").lower()

        parts = text.split()
        if len(parts) >= 4:
            possible = parts[-1].strip(" :,-")
            return possible.replace(" ", "_").lower()

        return ""

    def get_projects_response(self):
        try:
            if not PROJECTS.exists():
                return "No encontré la carpeta de proyectos."

            items = [item.name for item in PROJECTS.iterdir()]
            if not items:
                return "Ahora mismo no tienes proyectos creados."

            items.sort()
            project_list = ", ".join(items)
            return f"Tienes {len(items)} proyectos ahora mismo:\n{project_list}"
        except Exception as e:
            return f"No pude leer tus proyectos: {e}"

    def get_status_response(self):
        try:
            memory_count = self.count_items(BASE / "memory")
            projects_count = self.count_items(BASE / "projects")
            agents_count = self.count_items(BASE / "agents")
            autonomy_count = self.count_items(BASE / "autonomy")

            return (
                "Estado actual de Rogue:\n"
                f"- memoria: {memory_count} items\n"
                f"- proyectos: {projects_count} items\n"
                f"- agentes: {agents_count} items\n"
                f"- autonomía: {autonomy_count} items"
            )
        except Exception as e:
            return f"No pude leer el estado: {e}"

    def count_items(self, folder):
        if folder.exists() and folder.is_dir():
            return len(list(folder.iterdir()))
        return 0

    def run_note_command(self, note_text):
        try:
            result = subprocess.run(
                ["python", str(BASE / "Code" / "memory_engine.py")] + note_text.split(),
                capture_output=True,
                text=True,
                cwd=BASE
            )

            if result.returncode == 0:
                return "Listo. Ya guardé esa nota en tu memoria."
            else:
                error_text = result.stderr.strip() or result.stdout.strip()
                return f"No pude guardar la nota. {error_text}"
        except Exception as e:
            return f"Error guardando nota: {e}"

    def create_project(self, project_name):
        try:
            project_path = PROJECTS / project_name

            if project_path.exists():
                return f'Ese proyecto ya existe: "{project_name}".'

            project_path.mkdir(parents=True, exist_ok=True)
            return f'Listo. Ya creé el proyecto "{project_name}".'
        except Exception as e:
            return f"No pude crear el proyecto: {e}"

if __name__ == "__main__":
    root = tk.Tk()
    app = RogueChatApp(root)
    root.mainloop()