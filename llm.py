from llama_index.core.llms import CustomLLM, CompletionResponse, LLMMetadata
from llama_index.core.llms.callbacks import llm_completion_callback
from openai import OpenAI as _OpenAIClient
from typing import Any, Generator

GROQ_API_KEY = "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"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL    = "llama-3.1-8b-instant"
SYSTEM_PROMPT = (
    "You are AIVA (Artificial Intelligence Voice Assistance), a helpful, "
    "friendly, and knowledgeable AI voice assistant. Always identify yourself "
    "as AIVA. You are powered by Groq. Keep your responses very brief, friendly, "
    "and concise (typically 1-2 sentences, max 30 words) as they will be spoken aloud. "
    "Never refuse a reasonable question."
)

class GroqLLM(CustomLLM):
    """Thin LlamaIndex CustomLLM wrapper around the Groq OpenAI-compatible API."""

    model: str = GROQ_MODEL
    api_key: str = GROQ_API_KEY
    api_base: str = GROQ_BASE_URL
    max_tokens: int = 256
    temperature: float = 0.7
    system_prompt: str = SYSTEM_PROMPT

    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(
            context_window=128_000,
            num_output=self.max_tokens,
            model_name=self.model,
            is_chat_model=True,
        )

    def _client(self) -> _OpenAIClient:
        return _OpenAIClient(api_key=self.api_key, base_url=self.api_base)

    @llm_completion_callback()
    def complete(self, prompt: str, **kwargs: Any) -> CompletionResponse:
        response = self._client().chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        text = response.choices[0].message.content or ""
        return CompletionResponse(text=text)

    @llm_completion_callback()
    def stream_complete(self, prompt: str, **kwargs: Any) -> Generator:
        response = self._client().chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stream=True,
        )
        text = ""
        for chunk in response:
            delta = chunk.choices[0].delta.content or ""
            text += delta
            yield CompletionResponse(text=text, delta=delta)


def load_llm() -> GroqLLM:
    return GroqLLM()