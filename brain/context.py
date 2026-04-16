def get_recent_context_list(conversation_memory, limit=6):
    if not conversation_memory:
        return []

    lines = []
    for item in conversation_memory[-limit:]:
        role = "User" if item.get("role") == "user" else "Assistant"
        content = item.get("content", "")
        lines.append(f"{role}: {content}")
    return lines


def get_recent_context_text(conversation_memory, limit=4):
    if not conversation_memory:
        return "sin contexto reciente"

    lines = []
    for item in conversation_memory[-limit:]:
        role = "Tú" if item.get("role") == "user" else "Rogue"
        content = item.get("content", "")
        lines.append(f"- {role}: {content[:120]}")
    return "\n".join(lines)