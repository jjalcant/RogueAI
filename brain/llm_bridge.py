import requests

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "llama3:latest"
TIMEOUT_SECONDS = 120
READINESS_TIMEOUT_SECONDS = 2


def get_ollama_status(timeout=READINESS_TIMEOUT_SECONDS):
    tags_url = OLLAMA_URL.replace("/api/generate", "/api/tags")
    try:
        response = requests.get(tags_url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        models = data.get("models", [])
        installed_models = [item.get("name", "") for item in models if isinstance(item, dict)]
        model_available = any(name == MODEL for name in installed_models)
        return {
            "reachable": True,
            "url": tags_url,
            "model": MODEL,
            "model_available": model_available,
            "installed_models": installed_models,
            "message": (
                f"Ollama reachable. Model configured: {MODEL}."
                if model_available
                else f"Ollama reachable, but model '{MODEL}' is not listed."
            ),
        }
    except Exception as e:
        return {
            "reachable": False,
            "url": tags_url,
            "model": MODEL,
            "model_available": False,
            "installed_models": [],
            "message": (
                "Ollama unavailable. Rogue will continue in router-only mode. "
                f"Start Ollama and ensure '{MODEL}' is available. Details: {e}"
            ),
        }


def ask_llm(prompt, context=None):
    try:
        if context:
            ctx = "\n".join(context)
            full_prompt = (
                "You are Rogue, a powerful local AI assistant running on the user's PC.\n\n"
                f"Context:\n{ctx}\n\n"
                f"User request:\n{prompt}\n\n"
                "Respond clearly, directly, and practically."
            )
        else:
            full_prompt = prompt

        payload = {
            "model": MODEL,
            "prompt": full_prompt,
            "stream": False
        }

        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=TIMEOUT_SECONDS
        )
        response.raise_for_status()

        data = response.json()
        return data.get("response", "Model returned empty response.")

    except Exception as e:
        return (
            "Ollama is unavailable right now. Rogue is still running in router-only mode, "
            "so local commands continue to work. "
            f"Start Ollama at {OLLAMA_URL} with model '{MODEL}'. Details: {e}"
        )
