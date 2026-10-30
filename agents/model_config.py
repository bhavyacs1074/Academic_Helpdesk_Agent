import os

from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm

load_dotenv()

OLLAMA_CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "gemma4:e4b")
OLLAMA_API_BASE = os.getenv("OLLAMA_API_BASE", "http://localhost:11434")
OLLAMA_EXTRA_BODY = {"think": False}


def create_ollama_model() -> LiteLlm:
    return LiteLlm(
        model=f"ollama_chat/{OLLAMA_CHAT_MODEL}",
        api_base=OLLAMA_API_BASE,
        extra_body=OLLAMA_EXTRA_BODY,
    )
