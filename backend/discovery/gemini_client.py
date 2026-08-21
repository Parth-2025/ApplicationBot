import json
import threading
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

    def _call_model(self, prompt: str):
        # The google-generativeai SDK's own request_options timeout isn't
        # reliably honored on every transport path (observed hanging past
        # its stated timeout during a live run). A daemon thread with a
        # hard join() deadline guarantees this call returns or raises
        # regardless of what the SDK does internally - and being a daemon
        # thread, an SDK call that never returns won't block process exit.
        result: dict = {}

        def target():
            try:
                result["response"] = self._model.generate_content(
                    prompt, request_options={"timeout": self._request_timeout}
                )
            except Exception as exc:  # noqa: BLE001 - captured and re-raised on the caller's thread
                result["error"] = exc

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=self._request_timeout)

        if thread.is_alive():
            raise TimeoutError(
                f"Gemini call did not return within {self._request_timeout}s"
            )
        if "error" in result:
            raise result["error"]
        return result["response"]

    def generate_json(self, prompt: str, retries: int = 1) -> dict:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = self._call_model(prompt)
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
