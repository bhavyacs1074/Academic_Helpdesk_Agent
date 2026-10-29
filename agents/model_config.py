from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm

load_dotenv()

OLLAMA_MODEL = "ollama_chat/gemma4:e4b"
OLLAMA_API_BASE = "http://localhost:11434"
OLLAMA_EXTRA_BODY = {"think": False}


def create_ollama_model() -> LiteLlm:
    return LiteLlm(
        model=OLLAMA_MODEL,
        api_base=OLLAMA_API_BASE,
        extra_body=OLLAMA_EXTRA_BODY,
    )
