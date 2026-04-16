"""Desktop command registry for the Rogue Tkinter control panel."""

from dataclasses import dataclass
from typing import Callable


def normalize_command_name(value):
    """Normalize command input for stable registry lookups."""
    return " ".join(str(value).strip().lower().split())


@dataclass(frozen=True)
class CommandDefinition:
    name: str
    aliases: tuple[str, ...]
    description: str
    example: str
    handler: Callable[[str], object]
    category: str
    requires_confirmation: bool = False
    confirmation_message: str = ""
    implemented: bool = True


def build_command_registry(app):
    """Return the desktop command definitions used by the command bar and help view."""
    return [
        CommandDefinition(
            name="help",
            aliases=(),
            description="Show the desktop help view with supported commands and examples.",
            example="help",
            handler=lambda _command: app.show_help(),
            category="Navigation",
        ),
        CommandDefinition(
            name="back",
            aliases=("esc",),
            description="Return to the previous secondary view or safely return to the dashboard.",
            example="back",
            handler=lambda _command: app.go_back(),
            category="Navigation",
        ),
        CommandDefinition(
            name="home",
            aliases=(),
            description="Return to the main dashboard view.",
            example="home",
            handler=lambda _command: app.show_home(),
            category="Navigation",
        ),
        CommandDefinition(
            name="status",
            aliases=("system status",),
            description="Show a desktop status overview for backend, memory, tools, and tasks.",
            example="status",
            handler=lambda _command: app.show_status_overview(),
            category="System",
        ),
        CommandDefinition(
            name="agent status",
            aliases=(),
            description="Run the agent-backed system status workflow and render the structured result.",
            example="agent status",
            handler=lambda _command: app.run_registered_router_command("agent report system status"),
            category="System",
        ),
        CommandDefinition(
            name="tasks",
            aliases=(),
            description="Show recent and active agent tasks in a readable task summary view.",
            example="tasks",
            handler=lambda _command: app.show_tasks_overview(),
            category="System",
        ),
        CommandDefinition(
            name="task history",
            aliases=(),
            description="Show recent task activity and desktop actions from the current session.",
            example="task history",
            handler=lambda _command: app.show_task_history(),
            category="System",
        ),
        CommandDefinition(
            name="memory",
            aliases=(),
            description="Show saved memory notes from the persistent memory store.",
            example="memory",
            handler=lambda _command: app.show_memory_overview(),
            category="System",
        ),
        CommandDefinition(
            name="scan downloads",
            aliases=("analyze downloads",),
            description="Inspect Downloads and refresh the dashboard with a folder analysis summary.",
            example="scan downloads",
            handler=lambda _command: app.run_registered_router_command("inspect downloads"),
            category="Analysis",
        ),
        CommandDefinition(
            name="scan desktop",
            aliases=("analyze desktop",),
            description="Inspect Desktop and refresh the dashboard with a folder analysis summary.",
            example="scan desktop",
            handler=lambda _command: app.run_registered_router_command("scan desktop"),
            category="Analysis",
        ),
        CommandDefinition(
            name="largest files",
            aliases=(),
            description="Open a focused view of the largest files from the latest folder summary.",
            example="largest files",
            handler=lambda _command: app.show_folder_summary_section("largest_files", "Largest Files"),
            category="Analysis",
        ),
        CommandDefinition(
            name="newest files",
            aliases=(),
            description="Open a focused view of the newest files from the latest folder summary.",
            example="newest files",
            handler=lambda _command: app.show_folder_summary_section("newest_files", "Newest Files"),
            category="Analysis",
        ),
        CommandDefinition(
            name="top file types",
            aliases=(),
            description="Open a focused view of the top file types from the latest folder summary.",
            example="top file types",
            handler=lambda _command: app.show_folder_summary_section("top_file_types", "Top File Types"),
            category="Analysis",
        ),
        CommandDefinition(
            name="duplicates",
            aliases=(),
            description="Scan Downloads for duplicate files and show the result in chat.",
            example="duplicates",
            handler=lambda _command: app.run_registered_router_command("scan duplicates in downloads"),
            category="Analysis",
        ),
        CommandDefinition(
            name="open downloads",
            aliases=(),
            description="Open the Downloads folder in the system file explorer.",
            example="open downloads",
            handler=lambda _command: app.run_registered_router_command("open downloads folder"),
            category="Actions",
        ),
        CommandDefinition(
            name="open desktop",
            aliases=(),
            description="Open the Desktop folder in the system file explorer.",
            example="open desktop",
            handler=lambda _command: app.run_registered_router_command("open desktop folder"),
            category="Actions",
        ),
        CommandDefinition(
            name="open folder",
            aliases=(),
            description="Open a folder when a path or safe alias is provided.",
            example="open folder C:\\Users\\You\\Documents",
            handler=lambda _command: app.show_stub_message(
                "Open folder needs a target path or alias. Example: open downloads or open folder C:\\Users\\You\\Documents",
                title="Open Folder",
            ),
            category="Actions",
            implemented=False,
        ),
        CommandDefinition(
            name="organize downloads",
            aliases=(),
            description="Run the current Downloads organization preview workflow.",
            example="organize downloads",
            handler=lambda _command: app.run_registered_router_command("organize my downloads"),
            category="Actions",
            requires_confirmation=True,
            confirmation_message="Run the Downloads organization workflow?",
        ),
        CommandDefinition(
            name="smart cleanup",
            aliases=(),
            description="Run the recursive desktop cleanup preview workflow.",
            example="smart cleanup",
            handler=lambda _command: app.run_registered_router_command("clean up my desktop"),
            category="Actions",
            requires_confirmation=True,
            confirmation_message="Run the desktop smart cleanup preview?",
        ),
        CommandDefinition(
            name="cleanup temp",
            aliases=(),
            description="Reserved for temporary-file cleanup. The command is listed now but not implemented yet.",
            example="cleanup temp",
            handler=lambda _command: app.show_stub_message(
                "Cleanup temp is not implemented yet. The command is registered so it stays visible in Help.",
                title="Cleanup Temp",
            ),
            category="Actions",
            requires_confirmation=True,
            confirmation_message="Cleanup temp is a risky action path. Continue to view the current stub?",
            implemented=False,
        ),
        CommandDefinition(
            name="move files",
            aliases=(),
            description="Reserved for explicit file move workflows with source and destination inputs.",
            example="move files",
            handler=lambda _command: app.show_stub_message(
                "Move files is not implemented in the desktop command bar yet. Use the chat router for explicit move commands when needed.",
                title="Move Files",
            ),
            category="Actions",
            requires_confirmation=True,
            confirmation_message="Move files can change local data. Continue to view the current stub?",
            implemented=False,
        ),
        CommandDefinition(
            name="generate report",
            aliases=(),
            description="Run the workspace summary workflow and refresh the dashboard preview.",
            example="generate report",
            handler=lambda _command: app.run_registered_router_command("workspace summary"),
            category="Actions",
        ),
    ]
