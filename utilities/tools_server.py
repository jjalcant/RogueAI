from interpreter import interpreter
import os

os.chdir("C:\\RogueAI")

interpreter.auto_run = False
interpreter.safe_mode = "ask"
interpreter.llm.model = "ollama/deepseek-coder"

interpreter.system_message = """
You are Rogue, a powerful local AI assistant.

Workspace: C:\\RogueAI
"""

print("ROGUE ONLINE")

while True:
    command = input("\n>> ")

    response = interpreter.chat(command)

    if isinstance(response, list):
        for r in response:
            if isinstance(r, dict) and "content" in r:
                print(r["content"])
    else:
        print(response)