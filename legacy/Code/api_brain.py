import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("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"))

SYSTEM_PROMPT = """
You are Rogue, a local personal AI assistant running on the user's PC.

Core behavior:
- Be clear, direct, and useful.
- Prefer practical answers.
- Keep responses concise but intelligent.
- Help with planning, decision-making, execution, and organization.
- When the user asks for something that sounds like a local PC action, do not pretend it was executed unless the local app confirms it.
- When asked to think, structure the answer.
- When asked to plan, give actionable next steps.
"""

def ask_llm(user_message, recent_context=None):
    if not os.getenv("OPENAI_API_KEY"):
        return "No encontré OPENAI_API_KEY. Primero configura tu API key en PowerShell."

    context_text = ""
    if recent_context:
        joined = "\n".join(recent_context[-6:])
        context_text = f"\nRecent conversation context:\n{joined}\n"

    try:
        response = client.responses.create(
            model="gpt-5",
            input=[
                {
                    "role": "system",
                    "content": [
                        {"type": "input_text", "text": SYSTEM_PROMPT}
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": f"{context_text}\nUser message: {user_message}"
                        }
                    ],
                },
            ],
        )

        return response.output_text.strip() or "No hubo respuesta del modelo."

    except Exception as e:
        return f"Error con OpenAI API: {e}"