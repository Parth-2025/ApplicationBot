import json
import time

import google.generativeai as genai

from . import config


class GeminiError(Exception):
    pass


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        model=None,
        request_timeout: float = 30.0,
    ):
        self._request_timeout = request_timeout
        if model is not None:
            self._model = model
            return
        genai.configure(api_key=api_key or config.get_gemini_api_key())
        self._model = genai.GenerativeModel(model_name or config.get_gemini_model_name())

    def generate_json(self, prompt: str, retries: int = 1) -> dict:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = self._model.generate_content(
                    prompt, request_options={"timeout": self._request_timeout}
                )
                text = response.text.strip()
                if text.startswith("```"):
                    text = text.strip("`")
                    if text.lower().startswith("json"):
                        text = text[4:]
                return json.loads(text.strip())
            except json.JSONDecodeError as exc:
                last_error = exc
                break
            except Exception as exc:  # noqa: BLE001 - any Gemini SDK/network failure
                last_error = exc
                if attempt < retries:
                    time.sleep(2**attempt)
        raise GeminiError(f"Gemini call failed after {retries + 1} attempt(s): {last_error}")
