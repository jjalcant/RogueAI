import ollama
import docx

# archivo que quieres analizar
file_path = "lab.docx"

# leer documento
doc = docx.Document(file_path)

text = "\n".join([p.text for p in doc.paragraphs])

# enviar texto al modelo
response = ollama.chat(
    model="qwen3:8b",
    messages=[
        {
            "role": "user",
            "content": f"Analyze this document and help me step by step:\n\n{text}"
        }
    ]
)

print("\n--- AI RESPONSE ---\n")
print(response["message"]["content"])