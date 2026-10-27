from langchain_groq import ChatGroq

from app.core.config import get_settings


class AIServiceError(Exception):
    """An AI-provider problem, with a message that is safe to show to the user."""

    def __init__(self, message: str, status_code: int = 503):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_chat_model() -> ChatGroq:
    settings = get_settings()
    if not settings.groq_api_key:
        raise AIServiceError("AI service is not configured.", 503)

    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=0,  # consistent, less creative output for analysis
        timeout=settings.llm_timeout_seconds,
        max_retries=2,  # the Groq client retries network errors, 429s and 5xx
    )